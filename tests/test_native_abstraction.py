"""The native gate must prove inclusion without constraining the final property."""
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from scripts.native_abstraction import (clock_of, cut_model, export_json, normalize, prepare_candidate,
                                        property_source, witnessed_product)
from scripts.screen_baselines import ROOT, prove, save
from scripts.search_abstractions import worker


class NativeAbstractionTests(unittest.TestCase):
    def setUp(self):
        self.yosys = os.environ.get('RTL_RELATE_YOSYS', str(ROOT / '.tools/yosys-venv/bin/yowasp-yosys'))
        self.smtbmc = str(Path(self.yosys).with_name('yowasp-yosys-smtbmc'))
        if not Path(self.yosys).is_file() or not Path(self.smtbmc).is_file() or not shutil.which('z3'):
            self.skipTest('pinned frontend, SMTBMC and Z3 not installed')

    def test_input_init_cannot_hide_a_real_initial_counterexample(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'original.v'
            source.write_text('module main(input clk,input flag); reg first=1;\n'
                'always @(posedge clk) first<=0; always @* if(first) assert(flag); endmodule\n')
            original = prove(source, 'main', root / 'original', self.yosys, self.smtbmc,
                             depth=3, timeout=15)
            self.assertEqual(original['status'], 'CEX', original)
            source.write_text('module abstract_design(input clk,(* init=1 *) input flag,\n'
                'output __ar_a,output __ar_en); assign __ar_a=1; assign __ar_en=1; endmodule\n')
            with self.assertRaisesRegex(ValueError, 'only stored state'):
                prepare_candidate(source, root / 'rejected', self.yosys)

    def test_witnessed_inclusion_free_choices_and_rejected_assumptions(self):
        yosys, smtbmc = self.yosys, self.smtbmc
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / 'original.v'
            original.write_text('module main(input clk, output reg [1:0] q=0);\n'
                'wire [1:0] next_q = q < 2 ? q + 1 : q;\n'
                'always @(posedge clk) begin q <= next_q; assert(q <= 2); end\nendmodule\n')
            direct = prove(original, 'main', root / 'direct', yosys, smtbmc, depth=5, timeout=15)
            self.assertEqual(direct['status'], 'SAFE', direct)
            concrete, contract = normalize(root / 'direct/model.json', 'main', root / 'normalized', yosys)
            self.assertEqual(len(contract['assertion_names']), 1)
            contract['depth'] = 5
            save(root / 'normalized/contract.json', contract)
            same = root / 'same'
            same.mkdir()
            (same / 'abstract.v').write_text((root / 'normalized/design.v').read_text()
                                            .replace('module concrete_design(', 'module abstract_design('))
            save(same / 'certificate.json', {'witnesses': {}, 'invariants': []})
            checked, seconds = worker(ROOT, root, same, root / 'worker', 'ai', yosys, smtbmc, 15)
            self.assertEqual(checked['status'], 'SUCCESS', checked)
            self.assertEqual(checked['property']['assumptions'], 0)
            self.assertGreaterEqual(seconds, checked['property']['seconds'] + checked['correctness']['seconds'])
            fake = root / 'slow-yosys'
            child_pid = root / 'child.pid'
            fake.write_text('#!/usr/bin/python3\nimport subprocess,sys,time\n'
                'from pathlib import Path\n'
                'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\n'
                f'Path({str(child_pid)!r}).write_text(str(p.pid))\n'
                'time.sleep(60)\n')
            fake.chmod(0o755)
            timed, seconds = worker(ROOT, root, same, root / 'timed-worker', 'ai',
                                    str(fake), smtbmc, 0.5)
            self.assertEqual(timed['status'], 'UNKNOWN', timed)
            self.assertLess(seconds, 3)
            process = Path('/proc') / child_pid.read_text() / 'stat'
            self.assertTrue(not process.exists() or process.read_text().split()[2] == 'Z',
                            'timed-out evaluation left a live solver descendant')
            cut = cut_model(concrete, contract, ['next_q'])
            cut_source = export_json(cut, 'abstract_design', root / 'cut', yosys)
            cut_property = root / 'cut-property.v'
            cut_property.write_text(property_source(cut_source, cut, contract, 'abstract_design'))
            cut_result = prove(cut_property, 'native_property', root / 'cut-result', yosys, smtbmc,
                               depth=5, timeout=15)
            self.assertEqual(cut_result['status'], 'CEX', cut_result)
            with self.assertRaises(ValueError):
                cut_model(concrete, contract, ['clk'])
            candidate = root / 'candidate.v'
            candidate.write_text('module abstract_design(input clk, input [1:0] z,\n'
                'output reg [1:0] q=0, output reg __ar_a, output reg __ar_en=0);\n'
                'always @(posedge clk) begin q<=z; __ar_a<=q<=2; __ar_en<=1; end\nendmodule\n')
            abstract = prepare_candidate(candidate, root / 'candidate-prep', yosys)
            cert = {'witnesses': {'z': 'next_q'}, 'invariants': []}
            product = witnessed_product(concrete, abstract, contract, cert, root / 'product', yosys)
            gate = prove(product, 'native_product', root / 'gate', yosys, smtbmc, depth=5, timeout=15)
            self.assertEqual(gate['status'], 'SAFE', gate)
            free = root / 'free.v'
            free.write_text(property_source(candidate, abstract, contract, 'abstract_design'))
            prop = prove(free, 'native_property', root / 'property', yosys, smtbmc, depth=5, timeout=15)
            self.assertEqual(prop['status'], 'CEX', prop)
            self.assertEqual(prop['assumptions'], 0)
            wrong = {'witnesses': {'z': 'q'}, 'invariants': []}
            product = witnessed_product(concrete, abstract, contract, wrong, root / 'wrong', yosys)
            rejected = prove(product, 'native_product', root / 'wrong-gate', yosys, smtbmc, depth=5, timeout=15)
            self.assertEqual(rejected['status'], 'CEX', rejected)
            false_helper = {'witnesses': {'z': 'next_q'}, 'invariants': [{'bool': False}]}
            product = witnessed_product(concrete, abstract, contract, false_helper, root / 'false-helper', yosys)
            rejected = prove(product, 'native_product', root / 'false-helper-gate', yosys, smtbmc,
                             depth=5, timeout=15)
            self.assertEqual(rejected['status'], 'CEX', rejected)
            self.assertEqual(rejected['assumptions'], 0)
            candidate.write_text(candidate.read_text().replace('endmodule', 'always @* assume(0); endmodule'))
            with self.assertRaisesRegex(ValueError, 'design-only'):
                prepare_candidate(candidate, root / 'invalid', yosys)
            candidate.write_text('module abstract_design; initial $readmemh("private", mem); endmodule')
            with self.assertRaisesRegex(ValueError, 'system tasks'):
                prepare_candidate(candidate, root / 'external-read', yosys)
            candidate.write_text('module abstract_design; initial \\$readmemh ("private", mem); endmodule')
            with self.assertRaisesRegex(ValueError, 'system tasks'):
                prepare_candidate(candidate, root / 'escaped-external-read', yosys)

    def test_memory_partial_initialization_and_anyconst_survive_normalization(self):
        yosys, smtbmc = self.yosys, self.smtbmc
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'memory.v'
            source.write_text('module main(input clk,input wr,input [1:0] addr,input [7:0] d,output [7:0] q);\n'
                'reg [7:0] mem[0:3]; initial mem[0]=0;\n'
                '(* anyconst *) reg [1:0] pick;\n'
                'assign q=mem[pick]; always @(posedge clk) if(wr) mem[addr]<=d;\n'
                'always @* assert(q==0); endmodule\n')
            result = prove(source, 'main', root / 'direct', yosys, smtbmc, depth=3, timeout=15)
            self.assertEqual(result['status'], 'CEX', result)
            concrete, contract = normalize(root / 'direct/model.json', 'main', root / 'normalized', yosys)
            self.assertEqual(len(contract['constant_inputs']), 1)
            memories = [c for c in concrete['cells'].values() if c['type'] == '$mem_v2']
            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0]['parameters']['INIT'].count('x'), 24)
            wrapped = root / 'normalized-property.v'
            wrapped.write_text(property_source(root / 'normalized/design.v', concrete, contract, 'concrete_design'))
            again = prove(wrapped, 'native_property', root / 'again', yosys, smtbmc, depth=3, timeout=15)
            self.assertEqual(again['status'], 'CEX', again)
            initial_trace = (root / 'again/base.stdout.log').read_text()
            self.assertIn('Checking assertions in step 0', initial_trace)
            self.assertNotIn('Checking assertions in step 1', initial_trace)
            # A memory read-register initializer and its wire alias cannot
            # conflict: an empty initial-state set would make inclusion vacuous.
            memory = memories[0]
            memory['parameters']['RD_CLK_ENABLE'] = '1'
            memory['parameters']['RD_CLK_POLARITY'] = '1'
            memory['parameters']['RD_INIT_VALUE'] = '0' * 8
            memory['connections']['RD_CLK'] = concrete['ports']['clk']['bits']
            concrete['netnames']['q']['attributes']['init'] = '1' * 8
            with self.assertRaisesRegex(ValueError, 'conflicting state initialization'):
                clock_of(concrete)
