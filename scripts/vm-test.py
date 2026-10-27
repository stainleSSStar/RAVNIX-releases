#!/usr/bin/env python3
"""Test the actual release ISO and text installer on disposable QEMU disks only."""
import argparse
import base64
import re
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile
import time

PASSWORD = 'ravnix-test-password'

class Console:
    def __init__(self, connection, process, timeout):
        self.connection, self.process = connection, process
        self.deadline = time.monotonic() + timeout
        self.data = bytearray()
        self.cursor = 0
        self.terminal_buffer = b''

    def expect(self, pattern, timeout=900):
        until = min(self.deadline, time.monotonic() + timeout)
        while pattern not in self.data[self.cursor:]:
            if time.monotonic() > until or self.process.poll() is not None:
                raise RuntimeError(f'Console did not receive {pattern!r}')
            try:
                chunk = self.connection.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                raise RuntimeError('Serial console closed')
            self.data.extend(chunk)
            print(chunk.decode('utf-8', 'replace'), end='', flush=True)
            self.answer_terminal_queries(chunk)
            if b'\r\nRAVNIX_VM_FAIL\r\n' in self.data[self.cursor:]:
                raise RuntimeError('Guest probe failed')
        self.cursor = self.data.index(pattern, self.cursor) + len(pattern)

    def answer_terminal_queries(self, chunk):
        # Fish/agetty query a real terminal before accepting interactive input.
        # Replies describe a basic ANSI terminal, not a graphics test shortcut.
        self.terminal_buffer += chunk
        pattern = rb'\x1b(?:\[6n|\[(?:0)?c|\[\?u|\[>0q|\]11;\?(?:\x07|\x1b\\)|P\+q[^\x1b]*\x1b\\)'
        matches = list(re.finditer(pattern, self.terminal_buffer))
        for match in matches:
            query = match.group()
            if query == b'\x1b[6n':
                reply = b'\x1b[1;1R'
            elif query in (b'\x1b[c', b'\x1b[0c'):
                reply = b'\x1b[?1;2c'
            elif query == b'\x1b[?u':
                reply = b'\x1b[?0u'
            elif query == b'\x1b[>0q':
                reply = b'\x1bP>|RAVNIX-test-terminal\x1b\\'
            elif query.startswith(b'\x1b]11;'):
                reply = b'\x1b]11;rgb:0000/0000/0000\x1b\\'
            else:
                reply = b'\x1bP0+r\x1b\\'
            self.connection.sendall(reply)
        if matches:
            self.terminal_buffer = self.terminal_buffer[matches[-1].end():]
        self.terminal_buffer = self.terminal_buffer[-256:]

    def send(self, text):
        self.connection.sendall(text.replace('\n', '\r').encode())

    def run(self, body, marker, timeout=900):
        print('CHECK:', marker, flush=True)
        self.send(probe_command(body, marker) + '\n')
        self.expect(('\r\n'+marker+'\r\n').encode(), timeout)


def probe_script(body, marker):
    # A newline is valid after both a command and a trailing comment; a leading
    # semicolon on the following line is a Bash syntax error.
    return ('set -Eeuo pipefail\n'
            'trap \'printf "\\nRAVNIX_VM_FAIL\\n"\' ERR\n'
            + body.rstrip() + '\nprintf "\\n' + marker + '\\n"\n')


def probe_command(body, marker):
    # Send one terminal line, avoiding readline continuation prompts. The outer
    # check also catches parse errors, which cannot trigger the script's ERR trap.
    encoded = base64.b64encode(probe_script(body, marker).encode()).decode('ascii')
    return ('bash -c "$(printf %s ' + shlex.quote(encoded) + ' | base64 -d)"'
            ' || printf "\\nRAVNIX_VM_FAIL\\n"')

HEALTH = '''
for attempt in {1..90}; do
 if systemctl is-active --quiet NetworkManager; then break; fi
 sleep 1
done
systemctl is-active NetworkManager
nmcli general status
source /etc/os-release
test "$ID" = ravnix
test "$ID_LIKE" = nixos
case "$(getent passwd "$USER" | cut -d: -f7)" in */fish) ;; *) false;; esac
for command in nano less curl lspci lsusb ethtool smartctl; do command -v "$command"; done
for command in Xorg Xwayland xfce4-session startx; do
 if command -v "$command"; then false; fi
done
if systemctl is-active --quiet display-manager; then false; fi
if systemctl is-active --quiet sshd; then false; fi
if ss -H -lnt | awk '{print $4}' | grep -Eq ':(22|6000)$'; then false; fi
timeout 90 systemctl is-system-running --wait || true
systemctl --failed --no-pager
test -z "$(systemctl --failed --no-legend --plain)"
'''

class VM:
    def __init__(self, command, serial, out, name):
        self.command, self.serial, self.out, self.name = command, serial, out, name
        self.process = self.connection = self.console = None

    def __enter__(self):
        print('BOOT:', self.name, flush=True)
        try:
            with (self.out/f'{self.name}-qemu.log').open('wb') as log:
                self.process = subprocess.Popen(self.command, stdout=log, stderr=subprocess.STDOUT)
            self.connection = socket.socket(socket.AF_UNIX)
            deadline = time.monotonic()+60
            while True:
                if self.process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('QEMU failed to start')
                try:
                    self.connection.connect(str(self.serial))
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    time.sleep(.1)
            self.connection.settimeout(1)
            self.console = Console(self.connection, self.process, 3600)
            return self.console
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, kind, error, tb):
        try:
            if self.console:
                (self.out/f'{self.name}-serial.log').write_bytes(self.console.data)
                if kind:
                    print(self.console.data[-24000:].decode('utf-8','replace'), flush=True)
        finally:
            if self.connection:
                self.connection.close()
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()


def command(directory, mode, disk, iso=None):
    serial = directory/'serial.sock'
    serial.unlink(missing_ok=True)
    args = ['qemu-system-x86_64','-m','4096','-smp','2','-display','none',
            '-serial',f'unix:{serial},server=on,wait=off','-nic','user,model=virtio-net-pci',
            '-machine','accel=tcg',
            '-drive',f'file={disk},format=qcow2,if=none,id=target']
    if mode == 'bios':
        args += ['-device','ich9-ahci,id=sata','-device','ide-hd,drive=target,bus=sata.0,serial=RAVNIXTEST']
    else:
        args += ['-device','nvme,drive=target,serial=RAVNIXTEST']
        code = Path('/usr/share/OVMF/OVMF_CODE_4M.fd')
        if not code.exists():
            raise RuntimeError('Install ovmf')
        variables = directory/'vars.fd'
        if not variables.exists():
            shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd',variables)
        args += ['-drive',f'if=pflash,format=raw,readonly=on,file={code}',
                 '-drive',f'if=pflash,format=raw,file={variables}']
    if iso:
        args += ['-cdrom',str(iso),'-boot','order=d']
    else:
        args += ['-boot','order=c']
    return args,serial


def poweroff(console):
    # Keep consuming serial output: a full socket can block the guest during
    # shutdown, so waiting only on QEMU can deadlock an otherwise healthy VM.
    console.send('sync; systemctl poweroff\n')
    deadline = time.monotonic() + 180
    while console.process.poll() is None:
        if time.monotonic() > deadline:
            raise RuntimeError('Guest did not power off cleanly')
        try:
            chunk = console.connection.recv(65536)
        except socket.timeout:
            continue
        if chunk:
            console.data.extend(chunk)
            print(chunk.decode('utf-8', 'replace'), end='', flush=True)
        else:
            # Serial EOF may precede process exit by a few milliseconds.
            time.sleep(.1)
    if console.process.returncode != 0:
        raise RuntimeError(f'QEMU exited with {console.process.returncode}')


def quiet_bash(console, live=False):
    prompt = b'ravnix@ravnix ~ > ' if live else b'tester@ravnix-test ~ > '
    console.expect(prompt,timeout=600)
    console.send(('sudo -n ' if live else 'exec ')+'bash --noprofile --norc\n')
    console.expect(b'# ' if live else b'$ ',timeout=30)
    console.send('stty -echo; printf "\\nRAVNIX_SERIAL_READY\\n"\n')
    console.expect(b'\r\nRAVNIX_SERIAL_READY\r\n',timeout=30)


def test_mode(iso, mode, out):
    with tempfile.TemporaryDirectory(prefix='ravnix-vm-') as tmp:
        directory=Path(tmp);disk=directory/'target.qcow2'
        subprocess.run(['qemu-img','create','-f','qcow2',str(disk),'20G'],check=True)
        args,serial=command(directory,mode,disk,iso)
        with VM(args,serial,out,f'vm-{mode}-live') as console:
            quiet_bash(console,live=True)
            # The live user's login shell remains Fish even when the test runs Bash as root.
            console.run(HEALTH.replace('$USER','ravnix')+'\ncommand -v ravnix-install; command -v ravnix-guide; test -f /etc/ravnix/live; sudo -u ravnix sudo -n true; nm-online -q --timeout=90', 'RAVNIX_LIVE_OK')
            print('INSTALL:', mode, flush=True)
            console.send("ravnix-install || printf '\\nRAVNIX_VM_FAIL\\n'\n")
            device='/dev/sda' if mode=='bios' else '/dev/nvme0n1'
            for prompt,answer in [('Target whole disk:',device),('Hostname:','ravnix-test'),('Username:','tester'),('Timezone [Europe/Warsaw]:','Europe/Warsaw'),(f'Type ERASE {device} to continue:',f'ERASE {device}')]:
                console.expect(prompt.encode(),timeout=120)
                console.send(answer+'\n')
            print('WAIT: installation and password prompt', mode, flush=True)
            console.expect(b'New password:',timeout=2400)
            console.send(PASSWORD+'\n')
            console.expect(b'Retype new password:',timeout=60)
            console.send(PASSWORD+'\n')
            console.expect(b'Reboot now? [y/N]:',timeout=120)
            console.send('n\n')
            # Test-only serial console, never an autologin or password bypass.
            console.run('mount '+device+'2 /mnt' if mode=='bios' else 'mount '+device+'p2 /mnt', 'RAVNIX_TARGET_MOUNTED')
            if mode=='uefi':
                console.run('mount /dev/nvme0n1p1 /mnt/boot/efi','RAVNIX_ESP_MOUNTED')
            console.run("sed -i '/networking.hostName/a\\  boot.kernelParams = [ \"console=tty0\" \"console=ttyS0,115200n8\" ];' /mnt/etc/nixos/host.nix; nixos-install --root /mnt --flake path:/mnt/etc/nixos#ravnix --no-root-passwd; sync; umount -R /mnt",'RAVNIX_INSTALLED',timeout=1200)
            poweroff(console)
        for stage in ('installed','rebuilt'):
            args,serial=command(directory,mode,disk)
            with VM(args,serial,out,f'vm-{mode}-{stage}') as console:
                console.expect(b'login:',timeout=600)
                console.send('tester\n')
                console.expect(b'Password:',timeout=30)
                console.send(PASSWORD+'\n')
                quiet_bash(console)
                console.run(HEALTH+'''\ntest "$(hostname)" = ravnix-test
if getent passwd ravnix; then false; fi
for command in ravnix-install ravnix-guide nixos-install; do if command -v "$command"; then false; fi; done
test ! -e /etc/ravnix/live
test -w /etc/nixos/host.nix || test -r /etc/nixos/host.nix
if sudo -n true; then false; fi
''','RAVNIX_USER_OK')
                console.send("sudo -k; sudo -p 'RAVNIX_SUDO_PASSWORD: ' bash --noprofile --norc\n")
                console.expect(b'RAVNIX_SUDO_PASSWORD: ',timeout=30)
                console.send(PASSWORD+'\n')
                console.expect(b'# ',timeout=30)
                console.run('test "$(passwd -S root | awk \'{print $2}\')" = L; visudo -cf /etc/sudoers; test -f /etc/nixos/flake.lock; test -f /etc/nixos/hardware-configuration.nix; test -f /etc/nixos/host.nix; if grep -R -E "autologin.*ravnix|NOPASSWD" /etc/sudoers /etc/sudoers.d; then false; fi; nm-online -q --timeout=90','RAVNIX_ROOT_OK')
                if stage=='installed':
                    console.run('nixos-rebuild boot --flake path:/etc/nixos#ravnix','RAVNIX_REBUILD_OK',timeout=1200)
                poweroff(console)
        print(f'PASS: {mode} live, text installation, login, rebuild, reboot',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('iso',type=Path)
    parser.add_argument('--mode',choices=['bios','uefi','both'],default='both')
    args=parser.parse_args();iso=args.iso.resolve()
    if not iso.is_file(): parser.error('ISO not found')
    out=iso.parent
    report=out/'VM-TESTS.txt';report.unlink(missing_ok=True)
    for mode in (['bios','uefi'] if args.mode=='both' else [args.mode]):
        test_mode(iso,mode,out)
    if args.mode=='both':
        report.write_text('PASS: BIOS and UEFI live, text installation, password login, rebuild and reboot.\nPhysical hardware, Secure Boot, dual boot and encryption are not tested.\n')

if __name__=='__main__':
    main()
