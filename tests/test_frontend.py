"""Real RTL differential checks and fail-closed frontend boundaries (stdlib only)."""
import itertools
import json
from pathlib import Path
import random
import tempfile
import unittest

from rtl_relate.frontend import Unsupported, export_rtl, parse_btor2
from rtl_relate.ir import digest, emit, evaluate, sort, validate_model
from rtl_relate.solver import query, run

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

    def test_export_version_and_compile_share_one_deadline(self):
        tool = self.output / 'slow-yosys'
        tool.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(0.3)\nprint("fake version")\n')
        tool.chmod(0o755)
        with self.assertRaisesRegex(Unsupported, 'Yosys timeout'):
            export_rtl(ROOT / 'fixtures/rtl/p1_concrete.v', 'p1_concrete',
                       self.output / 'shared-deadline', executable=tool, timeout=0.5)

    def test_malformed_parameter_metadata_is_unsupported(self):
        tool = self.output / 'malformed-yosys'
        for index, raw in enumerate((None, '', '10x', '10z', 8, '0010')):
            with self.subTest(raw=raw):
                module = {'parameter_default_values': {} if raw is None else {'DW': raw}}
                netlist = json.dumps({'modules': {'p1_concrete': module}})
                tool.write_text('#!/usr/bin/env python3\nimport pathlib, sys\n'
                                'if "-V" in sys.argv: print("Yosys test")\n'
                                f'else: pathlib.Path("netlist.json").write_text({netlist!r})\n')
                tool.chmod(0o755)
                out = self.output / f'malformed-parameter-{index}'
                with self.assertRaisesRegex(Unsupported, 'defined binary value'):
                    export_rtl(ROOT / 'fixtures/rtl/p1_concrete.v', 'p1_concrete',
                               out, executable=tool, parameters={'DW': 8})
                self.assertEqual(json.loads((out / 'frontend.json').read_text())['status'], 'UNSUPPORTED')

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
            gold.replace('8 or 1 5 3', '8 redor 1 5 3 unexpected'),
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

    def test_reduction_and_inequality_are_bv1(self):
        text = ('1 sort bitvec 1\n2 sort bitvec 2\n3 input 1 clk\n4 input 2 x\n'
                '5 state 2 q\n6 zero 2\n7 init 2 5 6\n8 next 2 5 4\n'
                '9 redor 1 4\n10 output 9 nonzero\n11 neq 1 4 6\n12 output 11 different\n')
        model = parse_btor2(text, name='reductions', source_sha256='0' * 64)
        types = validate_model(model)
        for x in range(4):
            env = {'btor_4': x, 'btor_5': 0}
            self.assertEqual({name: evaluate(expr, env, types) for name, expr in model['observe'].items()},
                             {'nonzero': int(x != 0), 'different': int(x != 0)})


class PublicFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        cls.sources = ROOT / 'fixtures/public/upstream'
        cls.pipeline = export_rtl(cls.sources / 'pipeline.v', 'main', cls.output / 'pipeline',
                                  clock='clock', profile='avr_pipeline32')
        cls.normalized = export_rtl(cls.output / 'pipeline/normalized.v', 'main',
                                    cls.output / 'normalized', clock='clock')
        cls.skids = {}
        for width in (8, 32):
            cls.skids[width] = export_rtl(cls.sources / 'skidbuffer.v', 'skidbuffer',
                cls.output / f'skid{width}', clock='i_clk', parameters={
                    'DW': width, 'OPT_OUTREG': 1, 'OPT_LOWPOWER': 0,
                    'OPT_PASSTHROUGH': 0, 'OPT_INITIAL': 1})

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_pipeline_exact_assertion_is_preserved_and_not_assumed(self):
        model = self.pipeline
        types = validate_model(model)
        self.assertEqual(set(model['observe']), {'dataOut', 'tmp_stageOne', 'tmp_stageTwo'})
        self.assertEqual(sum(s['type'] for s in model['symbols'].values() if s['kind'] == 'state'), 160)
        assertion = json.loads((self.output / 'pipeline/assertion.json').read_text())
        self.assertEqual(assertion['model_sha256'], digest(model))
        bindings = {key: key for key in types}
        observed = {name: emit(expr, bindings, types) for name, expr in model['observe'].items()}
        expected = (f"(or (= {observed['dataOut']} (bvadd {observed['tmp_stageTwo']} "
                    f"{observed['tmp_stageOne']})) (= {observed['dataOut']} (_ bv0 32)))")
        declarations = [f'(declare-fun {key} () {sort(typ)})' for key, typ in types.items()]
        mismatch = f"(not (= {emit(assertion['predicate'], bindings, types)} {expected}))"
        result = run(query(declarations, mismatch, 5000), self.output / 'predicate', 'equivalence')
        self.assertEqual(result['status'], 'unsat', result)
        # No init/J/property assumptions: the original predicate must still be falsifiable.
        result = run(query(declarations, f'(not {expected})', 5000),
                     self.output / 'predicate', 'nonvacuity')
        self.assertEqual(result['status'], 'sat', result)
        self.assertEqual((self.output / 'pipeline/source.v').read_bytes(),
                         (self.sources / 'pipeline.v').read_bytes())

    def test_pipeline_reset_arithmetic_monitor_and_normalized_rtl(self):
        random_values = random.Random(42)
        edge = [0, 1, (1 << 31), (1 << 32) - 1]
        for model in (self.pipeline, self.normalized):
            types = validate_model(model)
            for index in range(200):
                values = {key: random_values.randrange(1 << width) for key, width in types.items()}
                if index < len(edge):
                    values = {key: edge[index] & ((1 << width) - 1) for key, width in types.items()}
                v = {model['symbols'][key]['origin']: val for key, val in values.items()}
                expected = {'stageOne': (v['dataIn'] + v['c1']) & 0xffffffff,
                            'stageTwo': v['stageOne'] & v['c2'],
                            'tmp_stageOne': v['stageOne'], 'tmp_stageTwo': v['stageTwo'],
                            'dataOut': 0 if v['reset'] else (v['stageTwo'] + v['stageOne']) & 0xffffffff}
                actual = {model['symbols'][key]['origin']: evaluate(expr, values, types)
                          for key, expr in model['next'].items()}
                self.assertEqual(actual, expected)
                self.assertEqual({key: evaluate(expr, values, types) for key, expr in model['observe'].items()},
                                 {key: v[key] for key in model['observe']})
                self.assertEqual(evaluate(model['init'], values, types),
                                 all(values[key] == 0 for key in model['next']))

    def test_skid_parameters_and_transition_boundaries(self):
        for width, model in self.skids.items():
            types = validate_model(model)
            self.assertEqual(sum(s['type'] for s in model['symbols'].values() if s['kind'] == 'state'),
                             2 * width + 2)
            payloads = [0, 1, (1 << (width - 1)), (1 << width) - 1]
            for r, v, reset, valid, ready in itertools.product(range(2), repeat=5):
                for b, q, data in itertools.product(payloads, repeat=3):
                    vals = {'LOGIC.r_valid': r, 'LOGIC.REG_OUTPUT.ro_valid': v,
                            'LOGIC.r_data': b, 'o_data': q, 'i_reset': reset,
                            'i_valid': valid, 'i_ready': ready, 'i_data': data}
                    env = {key: vals[symbol['origin']] for key, symbol in model['symbols'].items()}
                    expected = {'LOGIC.r_valid': 0 if reset else 1 if valid and not r and v and not ready else 0 if ready else r,
                                'LOGIC.REG_OUTPUT.ro_valid': 0 if reset else valid | r if not v or ready else v,
                                'LOGIC.r_data': data if not r else b,
                                'o_data': (b if r else data) if not v or ready else q}
                    actual = {model['symbols'][key]['origin']: evaluate(expr, env, types)
                              for key, expr in model['next'].items()}
                    self.assertEqual(actual, expected)
                    self.assertEqual({key: evaluate(expr, env, types) for key, expr in model['observe'].items()},
                                     {'o_ready': 1 - r, 'o_valid': v, 'o_data': q})
            self.assertEqual((self.output / f'skid{width}/source.v').read_bytes(),
                             (self.sources / 'skidbuffer.v').read_bytes())

    def test_extraction_and_parameter_boundaries_fail_closed(self):
        changed = self.output / 'changed-pipeline.v'
        changed.write_text((self.sources / 'pipeline.v').read_text().replace('assert property ( prop );',
                                                                          'assert property ( 1 );'))
        with self.assertRaises(Unsupported):
            export_rtl(changed, 'main', self.output / 'changed', clock='clock', profile='avr_pipeline32')
        with self.assertRaises(Unsupported):
            export_rtl(self.sources / 'pipeline.v', 'main', self.output / 'unextracted', clock='clock')
        for parameters in ({'DW; shell': 8}, {'DW': '8'}, {'DW': True}, {'DW': -1}, {'missing': 8}):
            with self.subTest(parameters=parameters), self.assertRaises(Unsupported):
                export_rtl(self.sources / 'skidbuffer.v', 'skidbuffer', self.output / 'invalid-parameters',
                           clock='i_clk', parameters=parameters)


if __name__ == '__main__':
    unittest.main()
