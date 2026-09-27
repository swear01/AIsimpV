import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from render_freestyle import rows, validate


class RenderTest(unittest.TestCase):
    def test_escaped_source_and_checked_locations(self):
        card = {'original_locations': [{'file': 'original/a.v', 'start': 1, 'end': 1}],
                'candidate_locations': []}
        self.assertIn('&lt;script&gt;', rows('original', 'a.v', '<script>', [card]))
        validate([card], {'original/a.v': '<script>', 'candidate/a.v': 'module a;'})
        card['original_locations'][0]['end'] = 2
        with self.assertRaises(ValueError):
            validate([card], {'original/a.v': '<script>', 'candidate/a.v': 'module a;'})
