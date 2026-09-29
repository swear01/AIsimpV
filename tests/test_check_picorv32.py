import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_picorv32 import check, inline_file


class PicoFrontendTest(unittest.TestCase):
    def test_extracts_generated_checker_and_rejects_empty_formal_count(self):
        source = '[file defines.sv]\n`define RISCV_FORMAL\n[file check.sv]\nmodule check; endmodule\n'
        self.assertEqual(inline_file(source, 'defines.sv'), '`define RISCV_FORMAL')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design = root / 'picorv32.v'
            design.write_text('module picorv32; endmodule\n')
            with patch('check_picorv32.subprocess.run',
                       return_value=SimpleNamespace(returncode=0, stdout='0 objects.\n')):
                result = check('candidate', design, root, 'yosys')
        self.assertEqual(result['status'], 'NO_FORMAL_CHECKS')
        self.assertEqual(result['formal_check_cells'], 0)


if __name__ == '__main__':
    unittest.main()
