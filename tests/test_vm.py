import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import subprocess
import contextlib
import io
import re
import tempfile

spec=importlib.util.spec_from_file_location('vm',Path(__file__).resolve().parents[1]/'scripts/vm-test.py')
vm=importlib.util.module_from_spec(spec);spec.loader.exec_module(vm)

class VMProtocol(unittest.TestCase):
    def test_fragmented_serial_marker(self):
        connection=Mock();connection.recv.side_effect=[b'noise\r\nRAV',b'NIX_OK\r\n']
        process=Mock();process.poll.return_value=None
        console=vm.Console(connection,process,30)
        console.expect(b'\r\nRAVNIX_OK\r\n')
        self.assertEqual(console.cursor,len(console.data))

    def test_failure_marker_is_not_a_pass(self):
        connection=Mock();connection.recv.return_value=b'\r\nRAVNIX_VM_FAIL\r\n'
        process=Mock();process.poll.return_value=None
        with self.assertRaisesRegex(RuntimeError,'Guest probe failed'):
            vm.Console(connection,process,30).expect(b'never')

    def test_unclean_shutdown_fails(self):
        console=Mock();console.process.poll.return_value=1;console.process.returncode=1
        with self.assertRaisesRegex(RuntimeError,'QEMU exited'):
            vm.poweroff(console)

    def test_the_session_deadline_outlasts_the_longest_step(self):
        # The console carries an absolute deadline for the whole session. A
        # three hour deadline aborted installations that were still copying the
        # desktop closure into the guest, so it has to be longer than the
        # longest single step of the test.
        self.assertGreater(vm.LIVE_DEADLINE,14400)
        self.assertGreater(vm.SESSION_DEADLINE,14400)

    def test_the_installation_step_outlasts_the_job_budget(self):
        # The installation copies ten gigabytes into the guest and builds the
        # configuration on top of it. The step limit has to be longer than
        # the copy and shorter than the job timeout of the workflow.
        self.assertGreaterEqual(vm.INSTALL_STEP, 14400)
        self.assertLessEqual(vm.INSTALL_STEP, 21600)
        self.assertGreater(vm.LIVE_DEADLINE, vm.INSTALL_STEP)

    def test_the_test_installs_once_with_a_serial_console(self):
        # A second installation would evaluate the whole desktop system again,
        # which takes a quarter of an hour on the emulated processor.
        source = (Path(__file__).resolve().parents[1]/'scripts/vm-test.py').read_text()
        self.assertEqual(source.count('console.send("ravnix-install'), 1)
        self.assertIn('--kernel-params', source)
        self.assertNotIn('nixos-install --root /mnt --flake', source)

    def test_every_step_reports_its_duration(self):
        # A run that fails has to name the step that used the time.
        source = (Path(__file__).resolve().parents[1]/'scripts/vm-test.py').read_text()
        self.assertIn("phase.mark('installation and password')", source)
        self.assertIn('class Phase:', source)

    def test_the_live_session_gets_the_long_deadline(self):
        manager=Mock()
        manager.__enter__=Mock(return_value=Mock())
        manager.__exit__=Mock(return_value=False)
        with contextlib.redirect_stdout(io.StringIO()), \
             patch.object(vm,'VM',return_value=manager) as session, \
             patch.object(vm,'command',return_value=([],None)), \
             patch.object(vm,'poweroff'), \
             patch.object(vm.subprocess,'run'):
            vm.test_mode(Path('unused.iso'),'bios',Path('.'))
        deadlines=[call.kwargs.get('deadline') for call in session.call_args_list]
        self.assertEqual(deadlines[0],vm.LIVE_DEADLINE)
        # The installed system, the rebuilt system, the live session of the
        # graphical installation and the system it produces.
        self.assertEqual(deadlines[1:],[vm.SESSION_DEADLINE,vm.SESSION_DEADLINE,
                                        vm.LIVE_DEADLINE,vm.SESSION_DEADLINE])

    def test_the_graphical_installation_is_tested_as_well(self):
        # The graphical installer has to end with the same system as the text
        # installer, so it is installed, booted and checked in the test too.
        source=(Path(__file__).resolve().parents[1]/'scripts/vm-test.py').read_text()
        self.assertIn('def graphical_installation(', source)
        self.assertIn('graphical_installation(directory,mode,disk,iso,accel,out,phase)', source)
        self.assertIn('--non-interactive --root /mnt', source)
        self.assertIn('RAVNIX_GRAPHICAL_OK', source)
        self.assertIn('text and graphical installation', source)

    def test_the_graphical_target_is_prepared_the_way_the_installer_expects(self):
        # The graphical installer partitions the disk and mounts the target
        # before the installation runs. The layout is the same on a BIOS and on
        # a UEFI machine: an EFI system partition at the place where the
        # configuration expects it, a partition for the BIOS bootloader and the
        # root filesystem.
        script=vm.partition_script('/dev/nvme0n1','uefi')
        result=subprocess.run(['bash','-n','-c',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('device=/dev/nvme0n1',script)
        self.assertIn('"${device}p3"',script)
        self.assertIn('mount -t vfat "$esp" /mnt/boot/efi',script)
        # A UEFI machine keeps two megabytes in front of the first partition.
        self.assertIn('mkpart ESP fat32 2MiB 514MiB',script)
        bios=vm.partition_script('/dev/sda','bios')
        # A BIOS machine keeps one megabyte in front of the first partition.
        self.assertIn('mkpart ESP fat32 1MiB 513MiB',bios)
        # GRUB writes the BIOS bootloader into a partition of its own.
        self.assertIn('parted -s "$device" set 2 bios_grub on',bios)
        self.assertIn('mkpart BIOSBOOT 513MiB 521MiB',bios)

    def test_the_graphical_target_is_prepared_with_the_right_commands(self):
        # The partition script runs against a real disk in the virtual machine.
        # Here the tools are replaced by scripts that record what they are
        # asked to do, so the whole sequence can be checked without a disk.
        # The mount is the important part: it fails when its directory is
        # missing, and the live medium has no /mnt.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bindir=root/'bin'; bindir.mkdir()
            calls=root/'calls'
            def fake(name, body):
                path=bindir/name; path.write_text(body); path.chmod(0o755)
            def record(name):
                fake(name,'#!/bin/sh\necho "%s $*" >> %s\nexit 0\n'%(name,calls))
            for name in ('parted','partprobe','udevadm','mkfs.ext4','mkfs.fat'):
                record(name)
            # The mount fails when the directory does not exist, like the real
            # one does. The mount point is the last argument.
            fake('mount','#!/bin/sh\n'
                'for point; do :; done\n'
                '[ -d "$point" ] || { echo "mount: $point: mount point does not exist." >&2; exit 32; }\n'
                'echo "mount $*" >> %s\nexit 0\n'%calls)
            script=vm.partition_script('/dev/sda','bios')
            script=script.replace('/mnt',str(root/'mnt'))
            environment={'PATH':str(bindir)+':/usr/bin:/bin'}
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=environment)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            recorded=calls.read_text()
            self.assertIn('parted -s /dev/sda mklabel gpt',recorded)
            self.assertIn('parted -s /dev/sda mkpart ESP fat32 1MiB 513MiB',recorded)
            self.assertIn('parted -s /dev/sda set 1 esp on',recorded)
            self.assertIn('parted -s /dev/sda mkpart BIOSBOOT 513MiB 521MiB',recorded)
            self.assertIn('parted -s /dev/sda set 2 bios_grub on',recorded)
            self.assertIn('parted -s /dev/sda mkpart primary ext4 521MiB 100%',recorded)
            self.assertIn('mkfs.ext4 -F -L RAVNIX_ROOT /dev/sda3',recorded)
            self.assertIn('mkfs.fat -F 32 -n RAVNIX_EFI /dev/sda1',recorded)
            self.assertIn('mount -t ext4 /dev/sda3 %s'%(root/'mnt'),recorded)
            self.assertIn('mount -t vfat /dev/sda1 %s'%(root/'mnt'/'boot'/'efi'),recorded)

    def test_the_graphical_target_creates_its_mount_point(self):
        # The live medium has no /mnt: the text installer creates it, and the
        # graphical installer mounts the target at its own place. Without the
        # directory the mount fails with "mount point does not exist".
        script = vm.partition_script('/dev/sda', 'bios')
        self.assertIn('mkdir -p /mnt', script)
        self.assertLess(script.index('mkdir -p /mnt'), script.index('mount -t ext4'))

    def test_the_shell_prompt_carries_the_name_of_the_machine(self):
        # The prompt of the shell is "user@host", and the graphical
        # installation gives the machine another name than the text one. The
        # test has to look for the prompt of the machine it just installed.
        console=Mock()
        vm.quiet_bash(console,live=False,host='ravnix-graphical')
        self.assertEqual(console.expect.call_args_list[0].args[0],b'tester@ravnix-graphical ~ > ')
        console=Mock()
        vm.quiet_bash(console,live=False)
        self.assertEqual(console.expect.call_args_list[0].args[0],b'tester@ravnix-test ~ > ')

    def test_every_phase_of_the_test_gets_its_own_firmware_variables(self):
        # The firmware keeps the order of the boot entries it has found. A
        # stale entry for a disk that is empty now leaves the machine in the
        # EFI shell instead of booting the medium, so the graphical phase
        # needs variables of its own.
        source = Path(vm.__file__).resolve().read_text()
        self.assertEqual(source.count("variables='vars-graphical.fd'"), 2)
        self.assertIn("shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd',store)", source)
        self.assertNotIn("if not variables.exists()", source)

    def test_the_graphical_installation_keeps_the_serial_console(self):
        # The serial console is the only way into the installed system, so the
        # graphical installation has to ask for the console parameters, the way
        # the text installation does.
        source = Path(vm.__file__).resolve().read_text()
        self.assertIn("--kernel-params 'console=tty0 console=ttyS0,115200n8'", source)

    def test_the_graphical_password_is_written_into_the_shadow_file(self):
        # The graphical interface sets the password itself. The test does not
        # drive the interface, so it does what the users module of Calamares
        # does: a hash of the password goes into the shadow file of the target.
        source = Path(vm.__file__).resolve().read_text()
        self.assertIn('mkpasswd -m sha512crypt', source)
        self.assertIn("usermod -p", source)
        self.assertIn('nixos-enter --root /mnt --command', source)

    def test_the_graphical_installer_belongs_to_the_live_medium_only(self):
        # The health block runs in the live session and in the installed
        # system. The graphical installer is in the live medium only, so it
        # cannot be in the list of commands that both of them have to provide:
        # the installed system has to be free of it.
        self.assertNotIn('calamares', vm.HEALTH)
        source = Path(vm.__file__).resolve().read_text()
        # The live session has to carry the graphical installer ...
        self.assertIn('command -v calamares;', source)
        # ... and the installed system must not.
        self.assertIn('nixos-install calamares', source)

    def test_a_failed_expectation_names_both_limits(self):
        # A failure has to say which limit was reached, otherwise a run that
        # was cut short by the session deadline looks like a broken guest.
        connection=Mock();connection.recv.return_value=b'noise'
        process=Mock();process.poll.return_value=None
        console=vm.Console(connection,process,30)
        with self.assertRaises(RuntimeError) as failure:
            console.expect(b'never',timeout=0)
        self.assertIn('step limit 0s',str(failure.exception))
        self.assertIn('session limit',str(failure.exception))

    def test_fragmented_fish_terminal_queries_receive_replies(self):
        connection=Mock();process=Mock()
        console=vm.Console(connection,process,30)
        console.answer_terminal_queries(b'hello\x1b[')
        connection.sendall.assert_not_called()
        console.answer_terminal_queries(b'6n\x1b[0c')
        self.assertEqual([x.args[0] for x in connection.sendall.call_args_list],
                         [b'\x1b[1;1R',b'\x1b[?1;2c'])
        console.answer_terminal_queries(b'plain text')
        self.assertEqual(connection.sendall.call_count,2)

    def test_boot_menu_arrow_is_not_a_fish_prompt(self):
        console=Mock()
        vm.quiet_bash(console,live=True)
        self.assertEqual(console.expect.call_args_list[0].args[0],b'ravnix@ravnix ~ > ')
        vm.quiet_bash(console,live=False)
        self.assertEqual(console.expect.call_args_list[3].args[0],b'tester@ravnix-test ~ > ')

    def test_shutdown_drains_serial_until_qemu_exits(self):
        console=Mock()
        console.data=bytearray()
        console.process.poll.side_effect=[None, None, 0]
        console.process.returncode=0
        console.connection.recv.side_effect=[b'shutdown progress', b'power down']
        vm.poweroff(console)
        self.assertEqual(console.data, b'shutdown progresspower down')
        console.process.wait.assert_not_called()

    def test_probe_trailing_newline_and_comment_are_valid(self):
        for body in ['true\n', 'true\n# trailing comment\n']:
            with self.subTest(body=body):
                result=subprocess.run(['bash', '-c', vm.probe_command(body, 'PROBE_OK')],
                                      capture_output=True, text=True)
                self.assertEqual(result.stdout, '\nPROBE_OK\n', result.stderr)
                self.assertNotIn('\n', vm.probe_command(body, 'PROBE_OK'))

    def test_probe_syntax_and_command_errors_fail_immediately(self):
        for body in ['if', 'false']:
            with self.subTest(body=body):
                result=subprocess.run(['bash', '-c', vm.probe_command(body, 'PROBE_OK')],
                                      capture_output=True, text=True)
                self.assertIn('\nRAVNIX_VM_FAIL\n', result.stdout)
                self.assertNotIn('PROBE_OK', result.stdout)

    def test_every_firmware_probe_has_valid_bash_syntax(self):
        # Collect the actual test_mode probes without running QEMU or accessing
        # devices. Validate their generated shell, including the installed checks.
        original_run=subprocess.run
        probes=[]
        console=Mock()
        def check_probe(body, marker, **kwargs):
            result=original_run(['bash', '-n', '-c', vm.probe_script(body, marker)],
                                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, marker+': '+result.stderr)
            probes.append(marker)
        console.run.side_effect=check_probe
        manager=Mock()
        manager.__enter__=Mock(return_value=console)
        manager.__exit__=Mock(return_value=False)
        with contextlib.redirect_stdout(io.StringIO()), \
             patch.object(vm, 'VM', return_value=manager), \
             patch.object(vm, 'command', return_value=([], None)), \
             patch.object(vm, 'poweroff'), \
             patch.object(vm.subprocess, 'run'):
            for mode in ['bios', 'uefi']:
                vm.test_mode(Path('unused.iso'), mode, Path('.'))
        self.assertEqual(probes.count('RAVNIX_USER_OK'), 4)
        self.assertEqual(probes.count('RAVNIX_REBUILD_OK'), 2)

    def test_the_guest_probes_only_use_nix_flags_that_exist(self):
        # Nix 2.35 does not know every flag of every nix command. A probe that
        # uses an unknown flag fails the whole firmware test before the
        # installation even starts, so the flags of "nix-store --query" are
        # taken from the Nix 2.35.4 source (src/nix/nix-store/nix-store.cc).
        query_flags = {'--outputs', '--requisites', '-R', '--references',
                       '--referrers', '--referrers-closure', '--deriver', '-d',
                       '--valid-derivers', '--binding', '-b', '--hash', '--size',
                       '--tree', '--graph', '--graphml', '--resolve', '--roots'}
        bodies = []
        console = Mock()
        console.run.side_effect = lambda body, marker, **kwargs: bodies.append(body)
        manager = Mock()
        manager.__enter__ = Mock(return_value=console)
        manager.__exit__ = Mock(return_value=False)
        with contextlib.redirect_stdout(io.StringIO()), \
             patch.object(vm, 'VM', return_value=manager), \
             patch.object(vm, 'command', return_value=([], None)), \
             patch.object(vm, 'poweroff'), \
             patch.object(vm.subprocess, 'run'):
            for mode in ['bios', 'uefi']:
                vm.test_mode(Path('unused.iso'), mode, Path('.'))
        self.assertTrue(bodies, 'no probe was collected')
        for body in bodies:
            for flag in re.findall(r'nix-store --query (--?[\w-]+)', body):
                with self.subTest(flag=flag):
                    self.assertIn(flag, query_flags)

    def test_accelerator_uses_hardware_virtualisation_when_it_works(self):
        # Software emulation makes the installation test ten times slower, so
        # the accelerator is probed before the virtual machine is started.
        with patch.object(vm.Path, 'exists', return_value=False):
            self.assertEqual(vm.qemu_accelerator(), 'tcg')
        with patch.object(vm.Path, 'exists', return_value=True), \
             patch.object(vm.os, 'access', return_value=True), \
             patch.object(vm.subprocess, 'run') as probe:
            probe.return_value=Mock(returncode=0)
            self.assertEqual(vm.qemu_accelerator(), 'kvm')
            probe.return_value=Mock(returncode=1)
            self.assertEqual(vm.qemu_accelerator(), 'tcg')

    def test_command_uses_the_requested_accelerator(self):
        args,_=vm.command(Path('/tmp'),'bios',Path('/tmp/disk.qcow2'),None,'kvm')
        self.assertIn('accel=kvm',args)
        args,_=vm.command(Path('/tmp'),'bios',Path('/tmp/disk.qcow2'),None,'tcg')
        self.assertIn('accel=tcg',args)

    def health_environment(self, root, with_installer=True):
        # A fake system for the health block: the commands of the desktop, the
        # files of the branding and the answers of the tools.
        bindir=root/'bin'; bindir.mkdir()
        def fake(name, body):
            path=bindir/name; path.write_text(body); path.chmod(0o755)
        fake('systemctl','#!/bin/sh\n'
            'case "$1 $2" in\n'
            '"is-active --quiet") [ "$3" = NetworkManager ] && exit 0; exit 3;;\n'
            '"is-active sshd") exit 3;;\n'
            '"is-active display-manager") echo active; exit 0;;\n'
            '"is-system-running --wait") echo running; exit 0;;\n'
            '"--failed "*) exit 0;;\n'
            'esac\nexit 0\n')
        fake('nmcli','#!/bin/sh\necho "STATE CONNECTIVITY"\n')
        fake('ss','#!/bin/sh\necho "LISTEN 0 4096 127.0.0.53:53 0.0.0.0:*"\n')
        fake('getent','#!/bin/sh\n'
            '[ "$2" = ravnix ] && echo "ravnix:x:1000:1000::/home/ravnix:/bin/fish"\nexit 0\n')
        fake('timeout','#!/bin/sh\nshift\nexec "$@"\n')
        commands=('nano','less','curl','lspci','lsusb','ethtool','smartctl',
                  'plasmashell','kwin_wayland','kwin_x11','startplasma-wayland',
                  'konsole','kate','dolphin','btop','fastfetch','mc','brave-origin')
        if with_installer:
            commands=commands+('calamares',)
        for command in commands:
            fake(command,'#!/bin/sh\nexit 0\n')
        share=root/'sw'/'share'
        for relative in ('backgrounds/ravnix/ravnix-wallpaper.jpg',
                         'color-schemes/RAVNIX-PurpleNeon.colors',
                         'color-schemes/RAVNIX-PurpleNeon.colorscheme',
                         'plasma/look-and-feel/org.kde.ravnix.purpleneon.desktop/metadata.json',
                         'plasma/look-and-feel/org.kde.ravnix.purpleneon.desktop/contents/defaults',
                         'sddm/themes/ravnix/Main.qml','ravnix/fastfetch-logo.txt'):
            (share/relative).parent.mkdir(parents=True,exist_ok=True)
            (share/relative).touch()
        (root/'etc').mkdir()
        (root/'etc'/'os-release').write_text('ID=ravnix\nID_LIKE=nixos\n')
        (root/'etc'/'fastfetch.jsonc').write_text(
            '{"source": "%s"}\n'%(share/'ravnix'/'fastfetch-logo.txt'))
        # The configuration of the desktop of a new account.
        skel=root/'etc'/'skel'/'.config'
        skel.mkdir(parents=True)
        (skel/'kdeglobals').write_text(
            '[General]\nColorScheme=RAVNIX-PurpleNeon\n\n'
            '[KDE]\nlookAndFeelPackage=org.kde.ravnix.purpleneon.desktop\n')
        (skel/'kcminputrc').write_text('[Mouse]\ncursorTheme=breeze_cursors\n')
        package=root/'store'/'8p5pbqx8z842kwa4k0csiv0jdydr2nlz-plasma-nm-6.6.6'
        for relative in ('lib/qt-6/plugins/plasma/applets/org.kde.plasma.networkmanagement.so',
                         'share/kcm_networkmanagement/qml/main.qml'):
            (package/relative).parent.mkdir(parents=True,exist_ok=True)
            (package/relative).touch()
        # The store also holds the derivation of the same name. It sorts
        # first and is a file, so it must not be mistaken for the package.
        (root/'store'/'0abc-plasma-nm-6.6.6.drv').write_text('derivation')
        script=vm.HEALTH
        script=script.replace('/etc/os-release',str(root/'etc'/'os-release'))
        script=script.replace('/etc/skel/.config/fastfetch/config.jsonc',
                               str(root/'etc'/'fastfetch.jsonc'))
        script=script.replace('/etc/skel/.config/kdeglobals',
                               str(root/'etc'/'skel'/'.config'/'kdeglobals'))
        script=script.replace('/etc/skel/.config/kcminputrc',
                               str(root/'etc'/'skel'/'.config'/'kcminputrc'))
        script=script.replace('/run/current-system/sw',str(root/'sw'))
        script=script.replace('/nix/store',str(root/'store'))
        environment={'PATH':str(bindir)+':/usr/bin:/bin','USER':'ravnix','HOME':str(root)}
        return script, environment

    def test_health_block_runs_every_check_despite_a_failing_substitution(self):
        # The probe runs with "set -Eeuo pipefail" and an ERR trap. A command
        # substitution that fails used to fire that trap inside the
        # substitution, abort the health check and hide every later failure.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            script,environment=self.health_environment(root)
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=environment)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('HEALTH CHECK FAILED',result.stdout)
            # Every check ran: the last one reports the systemd state.
            self.assertIn('running',result.stdout)
            # A missing applet file is reported with its path.
            package=root/'store'/'8p5pbqx8z842kwa4k0csiv0jdydr2nlz-plasma-nm-6.6.6'
            (package/'share/kcm_networkmanagement/qml/main.qml').unlink()
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=environment)
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)
            self.assertIn('missing',result.stdout)
            self.assertIn('main.qml',result.stdout)

    def test_the_health_block_passes_in_a_system_without_the_installer(self):
        # The health block runs in the live session and in the installed
        # system. The graphical installer lives in the live medium only, so a
        # block that demanded it would fail every run of the release pipeline.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            script,environment=self.health_environment(root,with_installer=False)
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=environment)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('HEALTH CHECK FAILED',result.stdout)

