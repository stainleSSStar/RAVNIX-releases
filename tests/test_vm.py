import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

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
        console=Mock();console.process.wait.return_value=1
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
