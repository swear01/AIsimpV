"""Real RTL differential checks and fail-closed frontend boundaries (stdlib only)."""
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from rtl_relate.frontend import Unsupported, export_rtl, parse_btor2
from rtl_relate.ir import evaluate, validate_model

ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.models = {}
        cls.output = Path(cls.temp.name)
        for source in sorted((ROOT / 'fixtures/rtl').glob('*.v')):
            nondet = ('z',) if source.stem in {'p1_abstract', 'p5_hold', 'p5_coarse'} else ()
            cls.models[source.stem] = export_rtl(source, source.stem, cls.output / source.stem, nondet=nondet)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_rtl_all_states_match_independent_arithmetic(self):
        checked = 0
        for name, model in self.models.items():
            types = validate_model(model)
            ids = list(model['symbols'])
            for values in itertools.product(*(range(1 << types[key]) for key in ids)):
                env = dict(zip(ids, values))
                vals = {model['symbols'][key]['origin']: value for key, value in env.items()}
                actual = {model['symbols'][key]['origin']: evaluate(expr, env, types)
                          for key, expr in model['next'].items()}
                if name == 'p1_concrete':
                    expected = {'x': min(vals['x'] + 1, 3)}
                    outputs = {'done': int(vals['x'] == 3)}
                elif name == 'p1_abstract':
                    expected = {'d': vals['d'] | vals['z']}
                    outputs = {'done': vals['d']}
                else:
                    load = not vals['v'] or vals['ready']
                    data = vals['x'] ^ 3 if 'x' in vals else vals['z']
                    expected = {'v': vals['en'] if load else vals['v'],
                                'q': data if load and vals['en'] else vals['q']}
                    if name == 'p5_coarse':
                        expected['q'] = vals['z']
                    elif name == 'p5_bug':
                        expected['q'] = data if vals['en'] else vals['q']
                    if 'x' in vals:
                        expected['x'] = (vals['x'] + 1) % 4
                    outputs = {'v': vals['v'], 'q': vals['q']}
                self.assertEqual(actual, expected, (name, vals))
                self.assertEqual({key: evaluate(expr, env, types) for key, expr in model['observe'].items()}, outputs)
                initial = all(value == 0 for key, value in vals.items()
                              if model['symbols'][next(i for i in ids if model['symbols'][i]['origin'] == key)]['kind'] == 'state')
                self.assertEqual(evaluate(model['init'], env, types), initial)
                checked += 1
        self.assertEqual(checked, 520)

    def test_nondeterminism_is_registered_and_provenance_retained(self):
        for name, model in self.models.items():
            metadata = json.loads((self.output / name / 'frontend.json').read_text())
            self.assertEqual(metadata['status'], 'EXPORTED')
            self.assertEqual(len(metadata['btor2_sha256']), 64)
            self.assertTrue(metadata['version'].startswith('Yosys '))
            self.assertTrue((self.output / name / 'yosys.stdout.log').exists())
            self.assertNotIn('clk', {symbol['origin'] for symbol in model['symbols'].values()})
            self.assertEqual(model['clock'], {'name': 'clk', 'edge': 'positive'})
        for symbol in self.models['p5_hold']['symbols'].values():
            if symbol['origin'] == 'z':
                self.assertEqual(symbol['kind'], 'nondet')
                self.assertEqual(symbol['type'], 2)
        with self.assertRaises(Unsupported):
            export_rtl(ROOT / 'fixtures/rtl/p1_concrete.v', 'p1_concrete', self.output / 'missing_nondet', nondet=['missing'])

    def test_export_preserves_actual_clock_for_contract_binding(self):
        source = self.output / 'renamed_clock.v'
        source.write_text((ROOT / 'fixtures/rtl/p1_abstract.v').read_text().replace('clk', 'other_clk'))
        model = export_rtl(source, 'p1_abstract', self.output / 'renamed_clock',
                           clock='other_clk', nondet=['z'])
        self.assertEqual(model['clock'], {'name': 'other_clk', 'edge': 'positive'})
        self.assertNotIn('other_clk', {symbol['origin'] for symbol in model['symbols'].values()})
        self.assertNotEqual(model['source_sha256'], self.models['p1_abstract']['source_sha256'])
        with self.assertRaises(Unsupported):
            export_rtl(source, 'p1_abstract', self.output / 'wrong_clock', clock='clk', nondet=['z'])

    def test_parser_rejects_semantic_omissions(self):
        gold = (self.output / 'p1_abstract/model.btor2').read_text()
        variants = [
            '\n'.join(line for line in gold.splitlines() if ' init ' not in line),
            '\n'.join(line for line in gold.splitlines() if ' next ' not in line),
            gold + '\n100 constraint 3\n',
            gold + '\n100 sort array 1 1\n',
            gold.replace('8 or 1 5 3', '8 mul 1 5 3'),
            gold.replace('8 or 1 5 3', '8 or 1 5 2'),
            gold.replace('4 const 1 0', '4 const 1 x'),
            gold.replace('9 next 1 5 8', '9 next 1 3 8'),
        ]
        for text in variants:
            with self.subTest(text=text), self.assertRaises(Unsupported):
                parse_btor2(text, name='invalid', source_sha256='0' * 64, nondet=['z'])

    def test_rtl_rejects_uninitialized_and_unsupported_clocks(self):
        variants = {
            'uninitialized': 'module bad(input clk, output reg q); always @(posedge clk) q <= ~q; endmodule',
            'negedge': 'module bad(input clk, output reg q=0); always @(negedge clk) q <= ~q; endmodule',
            'async': 'module bad(input clk, input rst, output reg q=0); always @(posedge clk or posedge rst) if(rst) q<=0; else q<=~q; endmodule',
            'multiclock': 'module bad(input clk, input clk2, output reg q=0, output reg r=0); always @(posedge clk) q<=~q; always @(posedge clk2) r<=~r; endmodule',
            'clock_data': 'module bad(input clk, input d, output reg q=0); always @(posedge clk) q<=clk ^ d; endmodule',
        }
        for name, text in variants.items():
            source = self.output / f'{name}.v'
            source.write_text(text)
            with self.subTest(name=name), self.assertRaises(Unsupported):
                export_rtl(source, 'bad', self.output / name)
            self.assertEqual(json.loads((self.output / name / 'frontend.json').read_text())['status'], 'UNSUPPORTED')


if __name__ == '__main__':
    unittest.main()
