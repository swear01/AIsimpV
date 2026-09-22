"""Native benchmark screening must distinguish a proof, a CEX, and no property."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from scripts.screen_baselines import ROOT, classify_ric3, prove


class BaselineScreenTests(unittest.TestCase):
    def test_ric3_verdict_requires_matching_exit_and_unique_verdict(self):
        for code, output, expected in ((20, 'UNSAT\n', 'SAFE'), (10, 'SAT\n', 'CEX'),
                                       (20, 'UNSAT\r\n', 'SAFE'), (10, 'SAT\r\n', 'CEX'),
                                       (30, 'UNKNOWN\n', 'UNKNOWN'), (0, 'UNSAT\n', 'ERROR'),
                                       (20, 'SAT\n', 'ERROR'), (20, 'UNSAT\nSAT\n', 'ERROR'),
                                       (20, 'no verdict', 'ERROR')):
            self.assertEqual(classify_ric3(code, output), expected)

    def test_ric3_native_proof_cex_and_unknown_initial_state(self):
        ric3 = os.environ.get('RTL_RELATE_RIC3')
        yosys = os.environ.get('RTL_RELATE_YOSYS')
        if not ric3 or not yosys:
            self.skipTest('explicit pinned rIC3 and Yosys paths not configured')
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, init, update, statement, expected in (
                    ('safe', '=0', "q < 2 ? q + 1 : q", 'assert(q <= 2);', 'SAFE'),
                    ('cex', '=0', 'q + 1', 'assert(q <= 2);', 'CEX'),
                    ('uninitialized', '', 'q', 'assert(q == 0);', 'CEX'),
                    ('absent', '=0', 'q', '', 'ERROR')):
                with self.subTest(name=name):
                    source = root / (name + '.v')
                    source.write_text(f'module main(input clk, output reg [1:0] q{init});\n'
                                      f'always @(posedge clk) q <= {update};\n'
                                      + (f'always @(posedge clk) {statement}\n' if statement else '')
                                      + 'endmodule\n')
                    result = prove(source, 'main', root / name, yosys, None, ric3=ric3, timeout=20)
                    self.assertEqual(result['status'], expected, result)
                    self.assertEqual(result['engine'], 'ric3-ic3')

    def test_empty_catalog_is_rejected_before_creating_output(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = root / 'empty.json'
            catalog.write_text('{"tasks": {}}')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/screen_baselines.py'),
                                     '--catalog', str(catalog), '--out', str(root / 'out')],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn('empty, unknown or duplicate task selection', result.stderr)
            self.assertFalse((root / 'out').exists())

    def test_native_assertions_are_preserved_and_required(self):
        yosys = os.environ.get('RTL_RELATE_YOSYS', str(ROOT / '.tools/yosys-venv/bin/yowasp-yosys'))
        smtbmc = str(Path(yosys).with_name('yowasp-yosys-smtbmc'))
        if not Path(yosys).is_file() or not Path(smtbmc).is_file() or not shutil.which('z3'):
            self.skipTest('pinned frontend, SMTBMC and Z3 not installed')
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
