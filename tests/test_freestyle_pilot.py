import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from freestyle_pilot import validated_output


class PilotOutputTest(unittest.TestCase):
    def test_rewrite_requires_exact_bounded_text_fields(self):
        valid = {'axilxbar_v': 'module axilxbar; endmodule', 'property_v': 'module p; endmodule',
                 'explanation': 'short', 'environment_changes': 'none'}
        self.assertEqual(validated_output('rewrite', valid), valid)
        with self.assertRaises(ValueError):
            validated_output('rewrite', {**valid, 'extra': 'ignored'})
        with self.assertRaises(ValueError):
            validated_output('rewrite', {**valid, 'axilxbar_v': 42})

    def test_upstream_case_accepts_inline_formal_output(self):
        fields = {'axilxbar_v': '', 'explanation': '', 'environment_changes': ''}
        self.assertEqual(validated_output('rewrite', fields, fields), fields)
        with self.assertRaises(ValueError):
            validated_output('rewrite', {**fields, 'property_v': ''}, fields)
