"""Native benchmark screening must distinguish a proof, a CEX, and no property."""
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from scripts.screen_baselines import ROOT, prove


class BaselineScreenTests(unittest.TestCase):
    def test_native_assertions_are_preserved_and_required(self):
        yosys = os.environ.get('RTL_RELATE_YOSYS', str(ROOT / '.tools/yosys-venv/bin/yowasp-yosys'))
        if not Path(yosys).is_file() or not shutil.which('z3'):
            self.skipTest('pinned frontend and Z3 not installed')
        smtbmc = str(Path(yosys).with_name('yowasp-yosys-smtbmc'))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, update, assertion, expected in (
                    ('safe', "q < 2 ? q + 1 : q", 'assert(q <= 2);', 'SAFE'),
                    ('cex', 'q + 1', 'assert(q <= 2);', 'CEX'),
                    ('absent', 'q + 1', '', 'ERROR')):
                with self.subTest(name=name):
                    source = root / (name + '.v')
                    source.write_text('module main(input clk, output reg [1:0] q=0);\n'
                                      f'always @(posedge clk) q <= {update};\n'
                                      + (f'always @(posedge clk) {assertion}\n' if assertion else '') + 'endmodule\n')
                    result = prove(source, 'main', root / name, yosys, smtbmc, depth=5, timeout=20)
                    self.assertEqual(result['status'], expected, result)
                    self.assertEqual((root / name / 'source.v').read_bytes(), source.read_bytes())
                    self.assertTrue((root / name / 'result.json').is_file())
                    if expected == 'SAFE':
                        self.assertIn('induction', result['stages'])
                    if expected == 'ERROR':
                        self.assertIn('no assertion', result['reason'])
