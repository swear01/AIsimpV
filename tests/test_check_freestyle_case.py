import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_freestyle_case import bind_property, check


class BoundFrontendTest(unittest.TestCase):
    def test_indented_endmodule_keeps_trailing_comment(self):
        result = bind_property('module axilxbar;\n  endmodule // end\n', 'candidate')
        self.assertIn('axilxbar_read_hold_property f_hold', result)
        self.assertIn('  endmodule // end', result)

    def test_external_file_read_is_rejected_before_frontend(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design = root / 'design.v'
            prop = root / 'property.v'
            design.write_text('module axilxbar; initial $readmemh("/secret", mem);\nendmodule\n')
            prop.write_text('module p; endmodule\n')
            with self.assertRaises(ValueError):
                check('candidate', design, prop, root, '/nonexistent/yosys')
