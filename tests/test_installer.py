"""Exercise destructive-operation guards without accessing real disks."""
from pathlib import Path
import os
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

    def test_installation_survives_an_interrupted_download(self):
        # The installation copies about ten gigabytes and needs the network for
        # the paths that are not in the live image. A single failed transfer
        # must not abort an installation that has already erased the disk, so
        # nix is told to build the missing path from source as a last resort.
        for name in ['scripts/install.sh', 'scripts/vm-test.py']:
            source = (ROOT/name).read_text()
            with self.subTest(script=name):
                self.assertIn('--option fallback true', source)
                self.assertIn('--option connect-timeout 30', source)
                self.assertIn('--option stalled-download-timeout 120', source)

    def test_the_resilient_options_belong_to_the_install_command(self):
        # They have to reach nixos-install, not a separate invocation, and the
        # option needs its value as the next argument.
        source = (ROOT/'scripts/install.sh').read_text()
        command = re.search(r'nixos-install[^\n]*(?:\n\s+[^\n]*)?', source).group(0)
        self.assertIn('--option fallback true', command)
        self.assertNotIn('nixos-install', source[source.index(command)+len(command):])

    def test_a_broken_cache_connection_is_retried_more_often(self):
        # The binary cache dropped the TLS connection again and again during
        # the test runs. The default of five attempts per file was not enough
        # to get past it.
        for name in ['scripts/install.sh', 'scripts/vm-test.py']:
            source = (ROOT/name).read_text()
            with self.subTest(script=name):
                self.assertIn('--option download-attempts 10', source)

    def test_the_live_image_carries_the_installation_dependencies(self):
        # The installation builds the initial ramdisk and installs the
        # bootloader inside the guest. When those paths are missing from the
        # live image, the installation depends on the binary cache, and one
        # broken connection to it aborts an installation that has already
        # erased the disk.
        live = (ROOT/'modules/live.nix').read_text()
        block = re.search(r'system\.extraDependencies\s*=\s*\[(.*?)\];', live, re.S)
        self.assertIsNotNone(block, 'the live image must carry the installation dependencies')
        dependencies = block.group(1)
        for package in ['pkgs.grub2',
                        'pkgs.grub2.override { efiSupport = true; }',
                        'pkgs.efibootmgr',
                        'pkgs.makeInitrdNGTool',
                        'pkgs.stdenvNoCC',
                        'pkgs.perl.withPackages']:
            with self.subTest(package=package):
                self.assertIn(package, dependencies)

    def offline_check(self, plan):
        # The check runs against a fake nix that prints a plan, so the rule is
        # exercised without a Nix installation.
        with tempfile.TemporaryDirectory(prefix='ravnix-offline-') as temporary:
            bindir = Path(temporary)/'bin'
            bindir.mkdir()
            fake = bindir/'nix'
            fake.write_text('#!/bin/sh\ncat <<\'EOF\'\n' + plan + '\nEOF\n')
            fake.chmod(0o755)
            environment = dict(os.environ, PATH=str(bindir)+':'+os.environ['PATH'])
            return subprocess.run(['bash', str(ROOT/'scripts/check-offline-install.sh')],
                                  capture_output=True, text=True, env=environment)

    def test_a_package_that_needs_the_network_fails_the_offline_check(self):
        # A real package in the plan means the installation depends on the
        # network, and a broken connection to the cache would abort it.
        plan = ('these 2 paths will be fetched (156.7 MiB download, 9.8 GiB unpacked):\n'
                '  /nix/store/aaa-grub\n'
                '  /nix/store/bbb-initrd\n')
        result = self.offline_check(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('aaa-grub', result.stdout)
        self.assertIn('depends on', result.stderr)

    def test_compiled_perl_modules_fail_the_offline_check(self):
        # The live image carries no compiler, so a compiled Perl module
        # cannot be rebuilt in the guest and has to come from the network.
        plan = ('these 1 paths will be fetched (120.0 KiB download, 900.0 KiB unpacked):\n'
                '  /nix/store/aaa-perl5.42.3-XML-SAX-1.02\n')
        result = self.offline_check(plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Perl', result.stderr)

    def test_small_rendered_files_pass_the_offline_check(self):
        # The sudoers file and the scripts of the login program are rendered
        # for every configuration, so they are tiny and nix rebuilds them
        # locally when the download fails.
        plan = ('these 2 paths will be fetched (40.0 KiB download, 60.0 KiB unpacked):\n'
                '  /nix/store/aaa-sudoers\n'
                '  /nix/store/bbb-getty\n')
        result = self.offline_check(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('aaa-sudoers', result.stdout)

    def test_derivations_that_are_built_locally_pass_the_offline_check(self):
        # Derivations that will be built in the guest are fine, their inputs
        # are in the live image.
        plan = ('these 2 derivations will be built:\n'
                '  /nix/store/aaa-initrd-linux.drv\n'
                '  /nix/store/bbb-system.drv\n')
        result = self.offline_check(plan)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
