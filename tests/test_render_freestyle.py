import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from render_freestyle import render, rows, validate


class RenderTest(unittest.TestCase):
    def test_escaped_source_and_checked_locations(self):
        card = {'original_locations': [{'file': 'original/a.v', 'start': 1, 'end': 1}],
                'candidate_locations': []}
        self.assertIn('&lt;script&gt;', rows('original', 'a.v', '<script>', [card]))
        validate([card], {'original/a.v': '<script>', 'candidate/a.v': 'module a;'})
        card['original_locations'][0]['end'] = 2
        with self.assertRaises(ValueError):
            validate([card], {'original/a.v': '<script>', 'candidate/a.v': 'module a;'})

    def test_output_names_come_from_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / 'case'
            candidate = root / 'candidate'
            (case / 'original').mkdir(parents=True)
            candidate.mkdir()
            (case / 'original/axilxbar.v').write_text('module axilxbar; endmodule\n')
            (case / 'task.json').write_text(json.dumps({
                'files': ['original/axilxbar.v'],
                'candidate_outputs': {'axilxbar_v': 'compact.v', 'explanation': 'why.txt',
                                      'environment_changes': 'env.txt'},
            }))
            (candidate / 'compact.v').write_text('module axilxbar; endmodule\n')
            (candidate / 'why.txt').write_text('reason text')
            (candidate / 'env.txt').write_text('setting text')
            output = root / 'review.html'
            render(candidate, {'changes': []}, output, case)
            page = output.read_text()
        self.assertIn('candidate/compact.v', page)
        self.assertIn('reason text', page)
        self.assertIn('setting text', page)
        self.assertNotIn('candidate/why.txt', page)
