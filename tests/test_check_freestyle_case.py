import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_freestyle_case import check


class BoundFrontendTest(unittest.TestCase):
    def test_external_file_read_is_rejected_before_frontend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design = root / 'design.v'
            prop = root / 'property.v'
            design.write_text('module axilxbar; initial $readmemh("/secret", mem);\nendmodule\n')
            prop.write_text('module p; endmodule\n')
            with self.assertRaises(ValueError):
                check('candidate', design, prop, root, '/nonexistent/yosys')
