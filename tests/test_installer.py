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
        # The options belong to the installer: the harness runs the installer
        # inside the guest and never calls nix itself.
        source = (ROOT/'scripts/install.sh').read_text()
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

    def test_the_seeded_profile_belongs_to_the_account(self):
        # The copy of the profile runs as root and would leave the
        # configuration directory of the account owned by root. The account
        # then cannot write it, the session of the user manager fails and the
        # shell cannot save its history.
        source = (ROOT/'modules/desktop.nix').read_text()
        script = re.search(r'system\.activationScripts\."users-ravnix-profile" = \{\n'
                           r'    text = \'\'\n(.*?)\n    \'\';', source, re.S).group(1)
        # Nix reads an unescaped dollar sign as the start of its own
        # interpolation, so the expansion of the shell would be a syntax error
        # in the module. Only the interpolation of the accounts is intended.
        rest = re.sub(r'\$\{lib\.concatStringsSep.*?\};', '', script, flags=re.S)
        for match in re.finditer(r'\$\{', rest):
            self.assertEqual(rest[max(0, match.start()-2):match.start()], "''",
                             'the activation script has an unescaped interpolation')
        # Render the string the way Nix does: an escaped interpolation marker
        # becomes a plain dollar sign, so the shell sees the expansion it
        # expects.
        script = script.replace("''${", '${')
        # Render the Nix interpolation with a single account.
        script = re.sub(r'\$\{lib\.concatStringsSep.*?\};',
                        'operator:/home/operator;', script, flags=re.S)
        with tempfile.TemporaryDirectory(prefix='ravnix-skel-') as temporary:
            root = Path(temporary)
            skel = root/'skel'
            (skel/'.config'/'fastfetch').mkdir(parents=True)
            (skel/'.config'/'fastfetch'/'config.jsonc').write_text('{}')
            home = root/'home'
            home.mkdir()
            script = script.replace('/etc/skel', str(skel)).replace('/home/operator', str(home))
            # The test does not run as root, so the ownership change is
            # recorded instead of performed.
            bindir = root/'bin'
            bindir.mkdir()
            (bindir/'chown').write_text('#!/bin/sh\necho "CHOWN:$*" >> "%s"\n' % (root/'calls'))
            (bindir/'chown').chmod(0o755)
            environment = dict(os.environ, PATH=str(bindir)+':'+os.environ['PATH'])
            result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                                    env=environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((home/'.config'/'fastfetch'/'config.jsonc').is_file(),
                            'the profile was not seeded')
            calls = (root/'calls').read_text()
            self.assertIn('CHOWN:-R operator %s' % home, calls,
                          'the seeded files were not given back to the account')

    def test_a_broken_cache_connection_is_retried_more_often(self):
        # The binary cache dropped the TLS connection again and again during
        # the test runs. The default of five attempts per file was not enough
        # to get past it. The installed system carries the same settings, so a
        # rebuild on the installed machine is protected in the same way.
        self.assertIn('--option download-attempts 10', (ROOT/'scripts/install.sh').read_text())
        base = (ROOT/'modules/base.nix').read_text()
        self.assertIn('download-attempts = 10', base)
        self.assertIn('connect-timeout = 30', base)
        self.assertIn('stalled-download-timeout = 120', base)

    def test_the_installed_system_carries_the_pinned_nixpkgs_source(self):
        # A rebuild on the installed machine evaluates the configuration from
        # the Nixpkgs source. When the source is not in the store, the machine
        # has to download the whole tree before it can rebuild itself, and a
        # broken connection to the binary cache aborts the rebuild.
        base = (ROOT/'modules/base.nix').read_text()
        self.assertIn('nixpkgsSource', base)
        self.assertIn('system.extraDependencies = [ nixpkgsSource ];', base)
        # The live image takes the source from the base module, so it must not
        # be listed a second time.
        live = (ROOT/'modules/live.nix').read_text()
        self.assertNotIn('\n    nixpkgsSource\n', live)
        # The installed configuration has to import the base module, otherwise
        # the installed system does not get the source.
        self.assertIn('./modules/base.nix', (ROOT/'scripts/install.sh').read_text())

    def test_the_prepared_layout_has_to_match_what_ravnix_installs(self):
        # The graphical installer prepares the disk. A layout that the
        # bootloader of the distribution cannot read would leave a system that
        # does not boot, so the installation stops before it writes anything.
        mocks = '''
findmnt() {
  case "$*" in
    *"-o FSTYPE --target"*)
      case "${!#}" in
        */boot/efi) echo "$MOCK_ESP_FSTYPE";;
        *) echo "$MOCK_FSTYPE";;
      esac;;
    *"-o SOURCE --target"*) echo "$MOCK_SOURCE";;
    *"-o TARGET"*) echo "$MOCK_MOUNTS";;
    *) :;;
  esac
}
lsblk() { echo "$MOCK_SIZE"; }
parted() { echo "$MOCK_TABLE"; }
'''
        def layout(mode, fstype='ext4', source='/dev/sda3', size=40 * 1024 ** 3,
                   mounts='/tmp/target\n/tmp/target/boot/efi', esp='vfat', table=''):
            environment = dict(
                os.environ,
                MOCK_FSTYPE=fstype, MOCK_SOURCE=source, MOCK_SIZE=str(size),
                MOCK_MOUNTS=mounts, MOCK_ESP_FSTYPE=esp, MOCK_TABLE=table,
            )
            return subprocess.run(
                ['bash', '-c', FUNCTIONS + mocks +
                 f'check_prepared_layout /tmp/target /dev/sda {mode}'],
                capture_output=True, text=True, env=environment)

        # A UEFI machine with its EFI system partition at the place where the
        # configuration expects it.
        uefi = layout('uefi')
        self.assertEqual(uefi.returncode, 0, uefi.stderr)
        # A BIOS machine with a partition for the BIOS bootloader.
        bios = layout('bios', table='Partition Table: gpt\n 2 513MB 521MB bios_grub')
        self.assertEqual(bios.returncode, 0, bios.stderr)
        # A BIOS machine with an MBR partition table carries the bootloader in
        # the space between the MBR and the first partition.
        mbr = layout('bios', table='Partition Table: msdos')
        self.assertEqual(mbr.returncode, 0, mbr.stderr)
        # Without the EFI system partition there is no bootloader on a UEFI
        # machine.
        without_esp = layout('uefi', mounts='/tmp/target')
        self.assertNotEqual(without_esp.returncode, 0)
        self.assertIn('EFI system partition is not mounted', without_esp.stderr)
        # An EFI system partition that is not a FAT filesystem is useless.
        wrong_esp = layout('uefi', esp='ext4')
        self.assertNotEqual(wrong_esp.returncode, 0)
        self.assertIn('FAT filesystem', wrong_esp.stderr)
        # Without a partition for the BIOS bootloader there is no bootloader on
        # a BIOS machine.
        without_bios = layout('bios', table='Partition Table: gpt')
        self.assertNotEqual(without_bios.returncode, 0)
        self.assertIn('BIOS bootloader', without_bios.stderr)
        # A filesystem the bootloader cannot read.
        for filesystem in ['btrfs', 'f2fs', 'xfs']:
            with self.subTest(filesystem=filesystem):
                result = layout('uefi', fstype=filesystem)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('RAVNIX installs ext4', result.stderr)
        # An encrypted root is not unlocked by the RAVNIX configuration.
        encrypted = layout('uefi', source='/dev/mapper/luks-1234')
        self.assertNotEqual(encrypted.returncode, 0)
        self.assertIn('encrypted', encrypted.stderr)
        # A disk that is too small for the installed system.
        small = layout('uefi', size=8 * 1024 ** 3)
        self.assertNotEqual(small.returncode, 0)
        self.assertIn('smaller than 16 GiB', small.stderr)

    def test_the_graphical_target_is_a_mount_point_and_not_an_installation(self):
        # The graphical installer formats the disk and mounts it empty, so the
        # target has no /etc yet. The installer has to accept such a target and
        # refuse a directory that is not mounted and a target that already
        # holds a NixOS installation.
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'target'
            target.mkdir()
            prepared = self.shell(f'findmnt() {{ echo {target}; }}; check_target_mount {target}')
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            unmounted = self.shell(f'findmnt() {{ echo /somewhere/else; }}; check_target_mount {target}')
            self.assertNotEqual(unmounted.returncode, 0)
            self.assertIn('not a mount point', unmounted.stderr)
            (target / 'etc').mkdir()
            (target / 'etc' / 'NIXOS').write_text('')
            installed = self.shell(f'findmnt() {{ echo {target}; }}; check_target_mount {target}')
            self.assertNotEqual(installed.returncode, 0)
            self.assertIn('already holds a NixOS installation', installed.stderr)
            missing = self.shell(f'findmnt() {{ echo {target}; }}; check_target_mount {target}/nothing')
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('does not exist', missing.stderr)

    def test_the_automated_installation_needs_its_values(self):
        # The graphical installer prepares the disk and collects the answers,
        # so it calls the installation with the values instead of asking.
        missing = self.shell('parse_arguments --non-interactive')
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('automated installation needs', missing.stderr)
        complete = self.shell('parse_arguments --non-interactive --root /tmp/target '
                               '--disk /dev/sda --hostname ravnix-test --username tester; '
                               'echo "$root $disk $hostname $username $interactive"')
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertEqual(complete.stdout.strip(), '/tmp/target /dev/sda ravnix-test tester 0')
        for missing_value in ['--root', '--disk', '--hostname', '--username']:
            with self.subTest(option=missing_value):
                result = self.shell(f'parse_arguments --non-interactive {missing_value}')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Missing value', result.stderr)

    def test_the_automated_options_belong_to_the_automated_installation(self):
        # The text installer asks for the disk itself and erases it only after
        # the exact confirmation, so it must not accept a disk from outside.
        for option in ['--disk /dev/sda', '--root /tmp/target', '--hostname box',
                       '--username tester', '--timezone Europe/Warsaw']:
            with self.subTest(option=option):
                result = self.shell('parse_arguments ' + option)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('automated installation', result.stderr)

    def test_the_configuration_of_the_machine_carries_the_answers(self):
        # Both installers write the same configuration, so the graphical one
        # ends with the same system as the text one.
        bios = self.shell('host_configuration ravnix-test tester Europe/Warsaw bios /dev/sda')
        self.assertEqual(bios.returncode, 0, bios.stderr)
        configuration = bios.stdout
        self.assertIn('networking.hostName = "ravnix-test";', configuration)
        self.assertIn('time.timeZone = "Europe/Warsaw";', configuration)
        self.assertIn('users.users."tester" = {', configuration)
        self.assertIn('enable = true;', configuration)
        self.assertIn('device = "/dev/sda";', configuration)
        self.assertIn('efiSupport = false;', configuration)
        self.assertIn('efiInstallAsRemovable = false;', configuration)
        uefi = self.shell('host_configuration ravnix-test tester Europe/Warsaw uefi /dev/sda')
        self.assertIn('device = "nodev";', uefi.stdout)
        self.assertIn('efiSupport = true;', uefi.stdout)
        self.assertIn('efiInstallAsRemovable = true;', uefi.stdout)

    def test_both_installers_install_the_same_pinned_configuration(self):
        # The graphical installer has to end with the same system as the text
        # installer, so both install the flake of the copied source tree.
        source = (ROOT/'scripts/install.sh').read_text()
        self.assertIn('--flake "path:$root/etc/nixos#ravnix"', source)
        self.assertIn('write_configuration "$root"', source)
        self.assertIn('write_configuration /mnt', source)

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

    def plan_check(self, live, target, configuration='/nix/store/config-source'):
        # The check reads the requisites of the live image and of the
        # installation, so the rule is exercised without a Nix installation.
        with tempfile.TemporaryDirectory(prefix='ravnix-plan-') as temporary:
            live_file = Path(temporary)/'live.txt'
            target_file = Path(temporary)/'target.txt'
            live_file.write_text('\n'.join(live) + '\n')
            target_file.write_text('\n'.join(target) + '\n')
            return subprocess.run(
                ['python3', str(ROOT/'scripts/check-install-plan.py'),
                 str(live_file), str(target_file), configuration],
                capture_output=True, text=True)

    def test_a_package_source_fails_the_plan_check(self):
        # A package source that the live image does not carry means the
        # installation would have to download it and compile it.
        live = ['/nix/store/live.drv', '/nix/store/nixos-units.pl']
        target = ['/nix/store/kernel.drv', '/nix/store/linux-6.18.56.tar.xz',
                  '/nix/store/config-source']
        result = self.plan_check(live, target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('linux-6.18.56.tar.xz', result.stdout)
        self.assertIn('depends on', result.stderr)

    def test_a_source_tree_fails_the_plan_check(self):
        live = ['/nix/store/live.drv']
        target = ['/nix/store/package.drv', '/nix/store/aaa-source']
        result = self.plan_check(live, target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('aaa-source', result.stdout)

    def test_small_rendered_files_pass_the_plan_check(self):
        # The sudoers file and the systemd units are rendered for every
        # configuration, so they are built from small scripts of the Nixpkgs
        # source tree, which the live image carries.
        live = ['/nix/store/live.drv', '/nix/store/bbb-nixos-units.pl']
        target = ['/nix/store/units.drv', '/nix/store/bbb-nixos-units.pl']
        result = self.plan_check(live, target)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('nothing has to be downloaded', result.stdout)

    def test_derivations_that_are_built_locally_pass_the_plan_check(self):
        # Derivations that will be built in the guest are fine, their inputs
        # are in the live image.
        live = ['/nix/store/live.drv']
        target = ['/nix/store/initrd.drv', '/nix/store/system.drv']
        result = self.plan_check(live, target)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # The system profile and the initial ramdisk are built in the guest.
        self.assertIn('2 derivations', result.stdout)

    def test_the_configuration_source_is_never_a_download(self):
        # The configuration is copied into the new system and read from
        # there, so its source never comes from the network.
        live = ['/nix/store/live.drv']
        target = ['/nix/store/system.drv', '/nix/store/config-source']
        result = self.plan_check(live, target)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_kernel_parameters_are_parsed_and_checked(self):
        # The serial console of the test needs the parameters, and they must
        # not be able to smuggle anything into the generated configuration.
        ok = self.shell('parse_arguments --kernel-params "console=ttyS0,115200n8"; echo "$kernel_params"')
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.strip(), 'console=ttyS0,115200n8')
        # NixOS wants one parameter per list entry and no spaces inside one.
        generated = self.shell('kernel_params_nix "console=tty0 console=ttyS0,115200n8"')
        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.assertEqual(generated.stdout.strip(),
                         'boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];')
        empty = self.shell('kernel_params_nix ""')
        self.assertEqual(empty.stdout.strip(), '')
        equal = self.shell('parse_arguments --kernel-params=quiet; echo "$kernel_params"')
        self.assertEqual(equal.returncode, 0, equal.stderr)
        self.assertEqual(equal.stdout.strip(), 'quiet')
        for bad in ['a"b', "a'b", 'a;rm -rf /', 'a$(id)', 'a`id`', 'a|b']:
            with self.subTest(parameter=bad):
                result = self.shell('parse_arguments --kernel-params '+shlex.quote(bad))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('unsupported characters', result.stderr)
        unknown = self.shell('parse_arguments --unknown')
        self.assertNotEqual(unknown.returncode, 0)
        self.assertIn('Unknown option', unknown.stderr)
        missing = self.shell('parse_arguments --kernel-params')
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('Missing value', missing.stderr)

    @unittest.skipUnless(shutil.which('nix-instantiate'), 'Nix evaluator runs in Linux CI')
    def test_generated_host_evaluates_with_keyword_usernames(self):
        # The configuration of the machine is written by the function both
        # installers call, so the test calls it as well.
        names=['operator', 'if', 'then', 'else', 'assert', 'with', 'let', 'in',
               'rec', 'inherit', 'or', 'alice-bob']
        with tempfile.TemporaryDirectory(prefix='ravnix-config-') as temporary:
            host=Path(temporary)/'host.nix'
            for mode in ['bios', 'uefi']:
                for name in names:
                    with self.subTest(mode=mode, username=name):
                        generated=self.shell(
                            'getent() { return 2; }; validate_username '+shlex.quote(name)+'\n'
                            'host_configuration ravnix-test '+shlex.quote(name)+
                            ' Europe/Warsaw '+mode+' /dev/disk/by-id/test')
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
