import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_upstream_axilxbar import check


class UpstreamFrontendTest(unittest.TestCase):
    def test_missing_check_count_is_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design = root / 'axilxbar.v'
            design.write_text('module axilxbar; endmodule\n')
            with patch('check_upstream_axilxbar.subprocess.run',
                       return_value=SimpleNamespace(returncode=0, stdout='no count\n')):
                result = check('candidate', design, root, 'yosys')
        self.assertEqual(result['status'], 'NO_FORMAL_CHECKS')
        self.assertIsNone(result['check_cells'])
