"""Exercise destructive-operation guards without accessing real disks."""
from pathlib import Path
import subprocess
import json
import re
import shlex
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = (ROOT / 'scripts/install.sh').read_text().split('main() {')[0]

class InstallerGuards(unittest.TestCase):
    def shell(self, text):
        return subprocess.run(['bash', '-c', FUNCTIONS + '\n' + text], text=True, capture_output=True)

    def test_partition_names(self):
        result = self.shell('partition_path /dev/sda 2; partition_path /dev/nvme0n1 2; partition_path /dev/mmcblk0 1')
        self.assertEqual(result.stdout.splitlines(), ['/dev/sda2', '/dev/nvme0n1p2', '/dev/mmcblk0p1'])

    def test_reserved_and_injected_usernames(self):
        for name in ['root','ravnix','nixos','Admin','a.b','x;reboot','a'*33]:
            with self.subTest(name=name):
                import shlex
                self.assertNotEqual(self.shell('validate_username '+shlex.quote(name)).returncode, 0)

    def test_existing_account_is_rejected(self):
        result = self.shell('getent() { return 0; }; validate_username operator')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('already exists', result.stderr)

    def test_valid_new_account(self):
        self.assertEqual(self.shell('getent() { return 2; }; validate_username operator').returncode, 0)

    def test_non_device_is_rejected_before_inspection(self):
        result = self.shell('lsblk() { echo SHOULD_NOT_RUN; }; validate_disk /definitely/not/a/disk')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('SHOULD_NOT_RUN', result.stdout)

    def test_busy_target_is_never_force_unmounted(self):
        result = self.shell('sleep() { :; }; findmnt() { :; }; umount() { printf "UMOUNT:%s\\n" "$*"; return 1; }; unmount_target')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count('UMOUNT:-R /mnt'), 3)
        self.assertNotIn('-Rl', result.stdout)

    def test_help_is_non_destructive(self):
        result = subprocess.run(['bash', str(ROOT/'scripts/install.sh'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Text installer', result.stdout)

    def test_confirmation_and_identity_recheck_precede_formatting(self):
        source = (ROOT/'scripts/install.sh').read_text()
        self.assertLess(source.index('[[ $answer == "ERASE $disk" ]]'),source.index('parted -s "$disk" mklabel'))
        self.assertLess(source.index('[[ $identity == "$current" ]]'),source.index('parted -s "$disk" mklabel'))
        self.assertLess(source.index('nixos-enter --root /mnt --command "passwd $username"'),source.index('\n unmount_target\n'))

    @unittest.skipUnless(shutil.which('nix-instantiate'), 'Nix evaluator runs in Linux CI')
    def test_generated_host_evaluates_with_keyword_usernames(self):
        source=(ROOT/'scripts/install.sh').read_text()
        template=re.search(r'cat > /mnt/etc/nixos/host\.nix <<HOST\n(.*?)\nHOST',
                           source, re.S).group(1)
        names=['operator', 'if', 'then', 'else', 'assert', 'with', 'let', 'in',
               'rec', 'inherit', 'or', 'alice-bob']
        with tempfile.TemporaryDirectory(prefix='ravnix-config-') as temporary:
            host=Path(temporary)/'host.nix'
            for mode in ['bios', 'uefi']:
                for name in names:
                    with self.subTest(mode=mode, username=name):
                        generated=self.shell(
                            'getent() { return 2; }; validate_username '+shlex.quote(name)+'\n'
                            'hostname=ravnix-test; timezone=Europe/Warsaw; '
                            'bootdevice=/dev/disk/by-id/test; mode='+mode+'; '
                            'username='+shlex.quote(name)+'\ncat <<HOST\n'+template+'\nHOST\n')
                        self.assertEqual(generated.returncode, 0, generated.stderr)
                        host.write_text(generated.stdout)
                        expression='import (builtins.toPath '+json.dumps(str(host))+') {}'
                        evaluated=subprocess.run(
                            ['nix-instantiate', '--eval', '--strict', '--json', '--expr', expression],
                            capture_output=True, text=True)
                        self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
                        config=json.loads(evaluated.stdout)
                        self.assertEqual(list(config['users']['users']), [name])
                        self.assertTrue(config['users']['users'][name]['isNormalUser'])
                        self.assertEqual(config['networking']['hostName'], 'ravnix-test')
                        grub=config['boot']['loader']['grub']
                        self.assertEqual(grub['efiSupport'], mode=='uefi')
                        self.assertEqual(grub['device'], 'nodev' if mode=='uefi' else '/dev/disk/by-id/test')
