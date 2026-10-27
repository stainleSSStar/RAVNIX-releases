import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import subprocess
import contextlib
import io

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
