import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import subprocess
import contextlib
import io
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
        self.assertEqual(deadlines[1:],[vm.SESSION_DEADLINE,vm.SESSION_DEADLINE])

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

    def test_health_block_runs_every_check_despite_a_failing_substitution(self):
        # The probe runs with "set -Eeuo pipefail" and an ERR trap. A command
        # substitution that fails used to fire that trap inside the
        # substitution, abort the health check and hide every later failure.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bindir=root/'bin'; bindir.mkdir()
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
            for command in ('nano','less','curl','lspci','lsusb','ethtool','smartctl',
                            'plasmashell','kwin_wayland','kwin_x11','startplasma-wayland',
                            'konsole','kate','dolphin','btop','fastfetch','mc',
                            'brave-origin','calamares'):
                fake(command,'#!/bin/sh\nexit 0\n')
            share=root/'sw'/'share'
            for relative in ('backgrounds/ravnix/ravnix-wallpaper.jpg',
                             'color-schemes/RAVNIX-PurpleNeon.colorscheme',
                             'sddm/themes/ravnix/Main.qml','ravnix/fastfetch-logo.txt'):
                (share/relative).parent.mkdir(parents=True,exist_ok=True)
                (share/relative).touch()
            (root/'etc').mkdir()
            (root/'etc'/'os-release').write_text('ID=ravnix\nID_LIKE=nixos\n')
            (root/'etc'/'fastfetch.jsonc').write_text(
                '{"source": "%s"}\n'%(share/'ravnix'/'fastfetch-logo.txt'))
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
            script=script.replace('/run/current-system/sw',str(root/'sw'))
            script=script.replace('/nix/store',str(root/'store'))
            environment={'PATH':str(bindir)+':/usr/bin:/bin','USER':'ravnix','HOME':str(root)}
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=environment)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('HEALTH CHECK FAILED',result.stdout)
            # Every check ran: the last one reports the systemd state.
            self.assertIn('running',result.stdout)
            # A missing applet file is reported with its path.
            (package/'share/kcm_networkmanagement/qml/main.qml').unlink()
            result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=environment)
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)
            self.assertIn('missing',result.stdout)
            self.assertIn('main.qml',result.stdout)

