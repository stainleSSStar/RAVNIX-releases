#!/usr/bin/env python3
"""Test the actual release ISO and text installer on disposable QEMU disks only."""
import argparse
import base64
import os
import re
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile
import time

PASSWORD = 'ravnix-test-password'

# The console carries an absolute deadline for the whole session, so it has to
# be longer than the longest single step of the test. The live session copies
# the whole desktop closure into the guest, which takes hours under software
# emulation: a three hour session deadline aborted installations that were
# still making progress. The deadline is only a backstop, the timeout of each
# single expectation is what normally ends a step, and the job timeout in the
# workflow is the outer bound.
LIVE_DEADLINE = 28800     # 8 hours
SESSION_DEADLINE = 21600  # 6 hours

# The installation copies the desktop closure into the guest and builds the
# configuration on top of it. The step limit is a backstop for a stalled
# guest, the job timeout in the workflow is the outer bound.
INSTALL_STEP = 16200  # 4.5 hours
BUILD_STEP = 16200    # the rebuild inside the installed system


class Phase:
    """Report how long every step of the test took.

    A failed run has to name the step that consumed the time: the store copy,
    the build of the configuration or the health check."""

    def __init__(self):
        self.start = self.last = time.monotonic()

    def mark(self, name):
        now = time.monotonic()
        print(f'PHASE: {name} took {int(now - self.last)}s (total {int(now - self.start)}s)', flush=True)
        self.last = now

def qemu_accelerator():
    """Hardware virtualisation makes the installation test about ten times
    faster. The runners expose /dev/kvm, but the probe keeps the test working
    on machines without it."""
    if not Path('/dev/kvm').exists() or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        return 'tcg'
    try:
        probe = subprocess.run(
            ['qemu-system-x86_64','-machine','accel=kvm','-display','none','-nodefaults','-S'],
            input=b'quit\n', capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return 'tcg'
    return 'kvm' if probe.returncode == 0 else 'tcg'

class Console:
    def __init__(self, connection, process, timeout):
        self.connection, self.process = connection, process
        self.deadline = time.monotonic() + timeout
        self.data = bytearray()
        self.cursor = 0
        self.terminal_buffer = b''

    def expect(self, pattern, timeout=900):
        start = time.monotonic()
        until = min(self.deadline, start + timeout)
        while pattern not in self.data[self.cursor:]:
            if time.monotonic() > until or self.process.poll() is not None:
                waited = int(time.monotonic() - start)
                raise RuntimeError(
                    f'Console did not receive {pattern!r} after {waited}s '
                    f'(step limit {timeout}s, session limit {int(self.deadline - start)}s)')
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
            'trap \'printf "\\nRAVNIX_VM_FAIL\\n"; printf "failed command: %s\\n" "$BASH_COMMAND"\' ERR\n'
            + body.rstrip() + '\nprintf "\\n' + marker + '\\n"\n')


def probe_command(body, marker):
    # Send one terminal line, avoiding readline continuation prompts. The outer
    # check also catches parse errors, which cannot trigger the script's ERR trap.
    encoded = base64.b64encode(probe_script(body, marker).encode()).decode('ascii')
    return ('bash -c "$(printf %s ' + shlex.quote(encoded) + ' | base64 -d)"'
            ' || printf "\\nRAVNIX_VM_FAIL\\n"')

HEALTH = '''
# Every check is run even when an earlier one failed, so one run reports all
# problems instead of only the first. The block runs in a subshell without
# "errexit" and without the inherited ERR trap: a failing command substitution
# would otherwise abort the whole health check before the remaining checks run.
(
trap - ERR
set +e
failed=0
check() {
  if ! "$@"; then
    echo "HEALTH CHECK FAILED: $*"
    failed=1
  fi
}
for attempt in {1..90}; do
 if systemctl is-active --quiet NetworkManager; then break; fi
 sleep 1
done
check systemctl is-active NetworkManager
nmcli general status || true
source /etc/os-release
check test "$ID" = ravnix
check test "$ID_LIKE" = nixos
login_shell=$(getent passwd "$USER" | cut -d: -f7 || true)
case "$login_shell" in
 */fish) ;;
 *) echo "HEALTH CHECK FAILED: login shell is $login_shell"; failed=1;;
esac
for command in nano less curl lspci lsusb ethtool smartctl; do check command -v "$command"; done
# Desktop stack: Plasma, the everyday console tools and the applications.
# The graphical installer is not part of this list: it lives in the live
# medium only, and the installed system must not carry it.
for command in plasmashell kwin_wayland kwin_x11 startplasma-wayland konsole kate dolphin \
                btop fastfetch mc brave-origin; do
 check command -v "$command"
done
# The graphical network manager is a Plasma applet, not a command: it ships as
# a Qt plugin and a KCM QML package inside the plasma-nm store path. Only
# directories are considered, because the store also holds the derivation file
# of the same name, which would otherwise be picked up first.
nm_package=$(find /nix/store -maxdepth 1 -type d -name '*-plasma-nm-*' 2>/dev/null | head -1 || true)
if [ -z "$nm_package" ]; then
 echo "HEALTH CHECK FAILED: plasma-nm is not in the closure"
 failed=1
else
 for applet_file in "$nm_package"/lib/qt-6/plugins/plasma/applets/org.kde.plasma.networkmanagement.so \
                   "$nm_package"/share/kcm_networkmanagement/qml/main.qml; do
  if [ ! -f "$applet_file" ]; then
   echo "HEALTH CHECK FAILED: missing $applet_file"
   failed=1
  fi
 done
fi
check systemctl is-active display-manager
check test -f /run/current-system/sw/share/backgrounds/ravnix/ravnix-wallpaper.jpg
check test -f /run/current-system/sw/share/color-schemes/RAVNIX-PurpleNeon.colorscheme
check test -f /run/current-system/sw/share/sddm/themes/ravnix/Main.qml
check test -f /run/current-system/sw/share/ravnix/fastfetch-logo.txt
# The fastfetch branding has to point at a file that really exists.
fastfetch_logo=$(grep '"source"' /etc/skel/.config/fastfetch/config.jsonc | head -1 | cut -d '"' -f 4 || true)
check test -f "$fastfetch_logo"
# No SSH server and no SSH or X11 listener. The offending value is printed, so
# a failure says what was actually found.
sshd_state=$(systemctl is-active sshd 2>/dev/null || true)
if [ "$sshd_state" = active ]; then
 echo "HEALTH CHECK FAILED: sshd is running"
 failed=1
fi
listeners=$(ss -H -lnt 2>/dev/null | awk '{print $4}' | grep -E ':(22|6000)$' || true)
if [ -n "$listeners" ]; then
 echo "HEALTH CHECK FAILED: unexpected listeners: $listeners"
 failed=1
fi
timeout 90 systemctl is-system-running --wait || true
systemctl --failed --no-pager || true
failed_units=$(systemctl --failed --no-legend --plain 2>/dev/null || true)
if [ -n "$failed_units" ]; then
 echo "HEALTH CHECK FAILED: failed systemd units: $failed_units"
 failed=1
 # The journal says why the unit failed, which is the only place that knows.
 journalctl --no-pager -b -n 40 2>/dev/null || true
fi
exit "$failed"
)
'''

class VM:
    def __init__(self, command, serial, out, name, deadline=LIVE_DEADLINE):
        self.command, self.serial, self.out, self.name = command, serial, out, name
        self.deadline = deadline
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
            self.console = Console(self.connection, self.process, self.deadline)
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


def command(directory, mode, disk, iso=None, accel='tcg'):
    serial = directory/'serial.sock'
    serial.unlink(missing_ok=True)
    # More guest cores mean a faster store copy during the installation.
    cpus = max(2, min(4, os.cpu_count() or 2))
    args = ['qemu-system-x86_64','-m','4096','-smp',str(cpus),'-display','none',
            '-serial',f'unix:{serial},server=on,wait=off','-nic','user,model=virtio-net-pci',
            '-machine',f'accel={accel}',
            # A KMS-capable display device, so Plasma and the greeter can
            # actually start inside the virtual machine.
            '-vga','virtio',
            # The installation copies ten gigabytes into the guest. A raw
            # image without write-back flushing keeps that copy at the speed of
            # the host disk instead of the speed of a qcow2 layer with a
            # flush after every write.
            '-drive',f'file={disk},format=raw,cache=unsafe,if=none,id=target']
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


def partition_script(device, mode):
    # The layout that the graphical installer prepares before it hands over to
    # the installation. The partitioning module of Calamares creates the same
    # layout on a BIOS and on a UEFI machine: a GPT disk with an EFI system
    # partition at /boot/efi, a small partition that holds the BIOS bootloader
    # and the ext4 root filesystem. The gap in front of the first partition is
    # two megabytes on a UEFI machine and one megabyte on a BIOS machine.
    gap='2MiB' if mode=='uefi' else '1MiB'
    esp_end='514MiB' if mode=='uefi' else '513MiB'
    bios_end='522MiB' if mode=='uefi' else '521MiB'
    return '''set -e
device=DEVICE
parted -s "$device" mklabel gpt
parted -s "$device" mkpart ESP fat32 GAP ESPEND
parted -s "$device" set 1 esp on
parted -s "$device" mkpart BIOSBOOT ESPEND BIOSEND
parted -s "$device" set 2 bios_grub on
parted -s "$device" mkpart primary ext4 BIOSEND 100%
partprobe "$device"
udevadm settle
case "$device" in
  *[0-9]) root="${device}p3"; esp="${device}p1";;
  *) root="${device}3"; esp="${device}1";;
esac
mkfs.ext4 -F -L RAVNIX_ROOT "$root"
mount -t ext4 "$root" /mnt
mkfs.fat -F 32 -n RAVNIX_EFI "$esp"
mkdir -p /mnt/boot/efi
mount -t vfat "$esp" /mnt/boot/efi
'''.replace('DEVICE', device).replace('GAP', gap).replace('ESPEND', esp_end).replace('BIOSEND', bios_end)


def graphical_installation(directory, mode, disk, iso, accel, out, phase):
    # The graphical installer has to end with the same system as the text
    # installer, so the automated installation is tested as well. The graphical
    # installer partitions the disk, mounts the target and sets the password of
    # the new account; the installation itself is the same program the text
    # installer runs.
    device='/dev/sda' if mode=='bios' else '/dev/nvme0n1'
    # The disk of the text installation is wiped: the graphical installer
    # starts with an empty disk as well.
    subprocess.run(['qemu-img','create','-f','raw',str(disk),'40G'],check=True)
    args,serial=command(directory,mode,disk,iso,accel)
    with VM(args,serial,out,f'vm-{mode}-graphical-live',deadline=LIVE_DEADLINE) as console:
        quiet_bash(console,live=True)
        phase.mark('graphical live session ready')
        console.run(partition_script(device,mode),'RAVNIX_GRAPHICAL_TARGET')
        phase.mark('graphical target prepared')
        console.send(f"ravnix-install --non-interactive --root /mnt --disk {device} "
                     "--hostname ravnix-graphical --username tester --timezone Europe/Warsaw "
                     "|| printf '\\nRAVNIX_VM_FAIL\\n'\n")
        print('WAIT: graphical installation', mode, flush=True)
        console.expect(b'RAVNIX installation complete',timeout=INSTALL_STEP)
        phase.mark('graphical installation')
        # The graphical installer sets the password of the new account itself.
        console.run(f"printf 'tester:{PASSWORD}\\n' | nixos-enter --root /mnt --command chpasswd; "
                    'sync; umount -R /mnt','RAVNIX_GRAPHICAL_PASSWORD')
        phase.mark('graphical password set')
        poweroff(console)
    args,serial=command(directory,mode,disk,accel=accel)
    with VM(args,serial,out,f'vm-{mode}-graphical',deadline=SESSION_DEADLINE) as console:
        console.expect(b'login:',timeout=1800)
        console.send('tester\n')
        console.expect(b'Password:',timeout=30)
        console.send(PASSWORD+'\n')
        quiet_bash(console)
        phase.mark('graphical system booted')
        console.run(HEALTH+'\ntest "$(hostname)" = ravnix-graphical\n'
                    'test -f "$HOME/.config/fastfetch/config.jsonc"\n'
                    'if sudo -n true; then false; fi\n','RAVNIX_GRAPHICAL_OK')
        phase.mark('graphical system health check')
        # The graphical installer runs the users module after the installation,
        # and that module can set the password of the root account. The RAVNIX
        # policy keeps the root account locked, and the installed system
        # carries none of the installer commands.
        console.send("sudo -k; sudo -p 'RAVNIX_SUDO_PASSWORD: ' bash --noprofile --norc\n")
        console.expect(b'RAVNIX_SUDO_PASSWORD: ',timeout=30)
        console.send(PASSWORD+'\n')
        console.expect(b'# ',timeout=30)
        console.run('test "$(passwd -S root | awk \'{print $2}\')" = L; '
                    'for command in ravnix-install ravnix-guide nixos-install calamares; '
                    'do if command -v "$command"; then false; fi; done; '
                    'test ! -e /etc/ravnix/live; '
                    'if grep -R -E "autologin.*ravnix|NOPASSWD" /etc/sudoers /etc/sudoers.d; then false; fi',
                    'RAVNIX_GRAPHICAL_ROOT_OK')
        phase.mark('graphical system root policy')
        poweroff(console)


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
    console.expect(prompt,timeout=1800)
    console.send(('sudo -n ' if live else 'exec ')+'bash --noprofile --norc\n')
    console.expect(b'# ' if live else b'$ ',timeout=30)
    console.send('stty -echo; printf "\\nRAVNIX_SERIAL_READY\\n"\n')
    console.expect(b'\r\nRAVNIX_SERIAL_READY\r\n',timeout=30)


def test_mode(iso, mode, out):
    phase=Phase()
    with tempfile.TemporaryDirectory(prefix='ravnix-vm-') as tmp:
        directory=Path(tmp);disk=directory/'target.img'
        # The desktop closure is about 10 GiB, so the installation needs more
        # room than the console-era image did. The image is a sparse file.
        subprocess.run(['qemu-img','create','-f','raw',str(disk),'40G'],check=True)
        accel=qemu_accelerator()
        print('ACCELERATOR:', accel, flush=True)
        args,serial=command(directory,mode,disk,iso,accel)
        with VM(args,serial,out,f'vm-{mode}-live',deadline=LIVE_DEADLINE) as console:
            quiet_bash(console,live=True)
            phase.mark('live session ready')
            # The store of the live image decides what the installation has to
            # build. The numbers are cheap and say where a slow run spent its
            # time: a store that is not registered has to be rebuilt. Only
            # flags of Nix 2.35 are used, because a probe with an unknown flag
            # fails the whole firmware test before the installation starts.
            console.run('echo "store paths: $(ls /nix/store | wc -l)"\n'
                        'echo "system paths: $(nix-store --query --requisites /run/current-system | wc -l)"\n'
                        'echo "nixpkgs source: $(ls -d /nix/store/*-source 2>/dev/null | wc -l)"','RAVNIX_STORE_INFO')
            # The live user's login shell remains Fish even when the test runs Bash as root.
            # The graphical installer belongs to the live medium, so it has to be
            # there and nowhere else.
            console.run(HEALTH.replace('$USER','ravnix')+'\ncommand -v ravnix-install; command -v ravnix-guide; command -v calamares; test -f /etc/ravnix/live; sudo -u ravnix sudo -n true; nm-online -q --timeout=90', 'RAVNIX_LIVE_OK')
            phase.mark('live health check')
            print('INSTALL:', mode, flush=True)
            # The serial console is part of the installation, so the test needs
            # one installation and not two.
            console.send("ravnix-install --kernel-params 'console=tty0 console=ttyS0,115200n8' || printf '\\nRAVNIX_VM_FAIL\\n'\n")
            device='/dev/sda' if mode=='bios' else '/dev/nvme0n1'
            for prompt,answer in [('Target whole disk:',device),('Hostname:','ravnix-test'),('Username:','tester'),('Timezone [Europe/Warsaw]:','Europe/Warsaw'),(f'Type ERASE {device} to continue:',f'ERASE {device}')]:
                console.expect(prompt.encode(),timeout=120)
                console.send(answer+'\n')
            print('WAIT: installation and password prompt', mode, flush=True)
            # Copying about 10 GiB into the guest store takes a long time under
            # software emulation, so the wait has to be generous. The live
            # session deadline is longer than this step, so a slow but healthy
            # installation is never cut short.
            console.expect(b'New password:',timeout=INSTALL_STEP)
            phase.mark('installation and password')
            console.send(PASSWORD+'\n')
            console.expect(b'Retype new password:',timeout=60)
            console.send(PASSWORD+'\n')
            console.expect(b'Reboot now? [y/N]:',timeout=120)
            console.send('n\n')
            # The installation has to have landed on the disk: the system
            # configuration, the store and the bootloader.
            console.run('mount '+device+'2 /mnt' if mode=='bios' else 'mount '+device+'p2 /mnt', 'RAVNIX_TARGET_MOUNTED')
            if mode=='uefi':
                console.run('mount /dev/nvme0n1p1 /mnt/boot/efi','RAVNIX_ESP_MOUNTED')
            console.run('test -f /mnt/etc/nixos/host.nix; test -f /mnt/etc/nixos/hardware-configuration.nix; '
                        'test -d /mnt/nix/store; test -d /mnt/boot/grub; sync; umount -R /mnt','RAVNIX_TARGET_INSTALLED')
            phase.mark('installation on the disk')
            poweroff(console)
        for stage in ('installed','rebuilt'):
            args,serial=command(directory,mode,disk,accel=accel)
            with VM(args,serial,out,f'vm-{mode}-{stage}',deadline=SESSION_DEADLINE) as console:
                console.expect(b'login:',timeout=1800)
                console.send('tester\n')
                console.expect(b'Password:',timeout=30)
                console.send(PASSWORD+'\n')
                quiet_bash(console)
                phase.mark(f'{stage} system booted')
                console.run(HEALTH+'''\ntest "$(hostname)" = ravnix-test
if getent passwd ravnix; then false; fi
for command in ravnix-install ravnix-guide nixos-install calamares; do if command -v "$command"; then false; fi; done
test ! -e /etc/ravnix/live
test -w /etc/nixos/host.nix || test -r /etc/nixos/host.nix
if sudo -n true; then false; fi
# The user's own fastfetch branding has to be in place as well.
test -f "$HOME/.config/fastfetch/config.jsonc"
# The browser has to start as an ordinary user, not only exist on disk.
timeout 180 brave-origin --version >/tmp/ravnix-brave-version.txt 2>&1 || true
sleep 3
cat /tmp/ravnix-brave-version.txt
# The output has to name the browser and carry a version number, so a
# Chromium sandbox abort does not pass for a successful start.
grep -qiE 'brave|chromium' /tmp/ravnix-brave-version.txt
grep -qE '[0-9]+[.][0-9]+' /tmp/ravnix-brave-version.txt
''','RAVNIX_USER_OK')
                console.send("sudo -k; sudo -p 'RAVNIX_SUDO_PASSWORD: ' bash --noprofile --norc\n")
                console.expect(b'RAVNIX_SUDO_PASSWORD: ',timeout=30)
                console.send(PASSWORD+'\n')
                console.expect(b'# ',timeout=30)
                console.run('test "$(passwd -S root | awk \'{print $2}\')" = L; visudo -cf /etc/sudoers; test -f /etc/nixos/flake.lock; test -f /etc/nixos/hardware-configuration.nix; test -f /etc/nixos/host.nix; if grep -R -E "autologin.*ravnix|NOPASSWD" /etc/sudoers /etc/sudoers.d; then false; fi; nm-online -q --timeout=90','RAVNIX_ROOT_OK')
                phase.mark(f'{stage} system health check')
                if stage=='installed':
                    console.run('nixos-rebuild boot --flake path:/etc/nixos#ravnix','RAVNIX_REBUILD_OK',timeout=BUILD_STEP)
                    phase.mark('rebuild inside the installed system')
                poweroff(console)
        graphical_installation(directory,mode,disk,iso,accel,out,phase)
        print(f'PASS: {mode} live, desktop, text and graphical installation, login, rebuild, reboot',flush=True)


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
        report.write_text('PASS: BIOS and UEFI live, KDE Plasma desktop, text and graphical installation, password login, rebuild and reboot.\nPhysical hardware, Secure Boot, dual boot and encryption are not tested.\n')

if __name__=='__main__':
    main()
