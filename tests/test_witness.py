"""Actual SMTBMC counterexamples survive input decoding, abstract validation and replay."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from rtl_relate.formal import prove_rtl
from rtl_relate.frontend import export_rtl
from rtl_relate.ir import load_json
from rtl_relate.properties import replay
from rtl_relate.witness import extract_counterexample

ROOT = Path(__file__).resolve().parents[1]


class WitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)
        cls.cases = {}
        definitions = [
            ("p5", "fixtures/rtl/p5_concrete.v", "p5_concrete", "fixtures/rtl/p5_coarse.v", "p5_coarse", "p5", "clk", ("z",), {}, {}, None),
            ("fsm", "fixtures/public/fsm/concrete.v", "fsm_concrete", "fixtures/public/fsm/coarse.v", "fsm_coarse", "r1_fsm", "clk", ("z",), {}, {}, None),
            ("skid", "fixtures/public/upstream/skidbuffer.v", "skidbuffer", "fixtures/public/skidbuffer/skid_abstract.v", "skid_abstract", "r2_skid8", "i_clk", ("z",),
             {"DW": 8, "OPT_OUTREG": 1, "OPT_LOWPOWER": 0, "OPT_PASSTHROUGH": 0, "OPT_INITIAL": 1}, {"DW": 8, "COARSE": 1}, None),
            ("pipeline", "fixtures/public/upstream/pipeline.v", "main", "fixtures/public/pipeline/pipeline_coarse.v", "pipeline_coarse", "r4_pipe32", "clock", ("z", "z2"), {}, {}, "avr_pipeline32"),
        ]
        for name, csrc, ctop, asrc, atop, contract, clock, nd, cp, ap, profile in definitions:
            path = cls.out / name
            c = export_rtl(ROOT / csrc, ctop, path / "c", clock=clock, parameters=cp, profile=profile)
            a = export_rtl(ROOT / asrc, atop, path / "a", clock=clock, parameters=ap, nondet=nd)
            contract = load_json(ROOT / f"fixtures/contracts/{contract}.json")
            formal = prove_rtl(ROOT / asrc, atop, contract, path / "formal", parameters=ap, nondet=nd)
            result = extract_counterexample(a, contract, path / "formal", path / "witness")
            cls.cases[name] = (c, a, contract, formal, result, path)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_coarse_traces_validate_and_are_spurious_on_safe_concrete(self):
        for name, (c, a, contract, formal, result, path) in self.cases.items():
            with self.subTest(name=name):
                self.assertEqual(formal["status"], "CEX", formal)
                self.assertEqual(result["status"], "VALIDATED", result)
                self.assertEqual(result["validation"]["status"], "sat")
                self.assertTrue(result["property_violated"])
                self.assertEqual(len(result["trace"]["inputs"]), formal["counterexample_step"])
                self.assertEqual(result["violation_step"], formal["counterexample_step"] - 1)
                self.assertEqual(result["completed_input_bits"], [])
                self.assertEqual(replay(c, contract, result["trace"], path / "replay")["status"], "INFEASIBLE")
        pipeline = self.cases["pipeline"][4]
        self.assertEqual(pipeline["formal_counterexample_step"], 3)
        self.assertEqual(len(pipeline["trace"]["observations"]), 4)
        skid = self.cases["skid"][4]
        self.assertIn("o_ready", skid["trace"]["observations"][0])

    def altered(self, name, mutation, variant):
        _, a, contract, _, _, path = self.cases[name]
        changed = self.out / variant
        shutil.copytree(path / "formal", changed)
        data = load_json(changed / "base.yw")
        mutation(data)
        (changed / "base.yw").write_text(json.dumps(data))
        return extract_counterexample(a, contract, changed, self.out / (variant + "-result"))

    def test_wrong_format_and_missing_failing_sample_fail_closed(self):
        result = self.altered("p5", lambda data: data.update(format="other"), "format")
        self.assertEqual(result["status"], "ERROR", result)
        result = self.altered("pipeline", lambda data: data["steps"].pop(), "short")
        self.assertEqual(result["status"], "ERROR", result)
        self.assertNotIn("trace", result)

    def test_shifted_input_sequence_does_not_reproduce_the_counterexample(self):
        def swap(data):
            data["steps"][0], data["steps"][1] = data["steps"][1], data["steps"][0]
        result = self.altered("p5", swap, "shifted")
        self.assertEqual(result["status"], "UNRESOLVED", result)
        self.assertNotIn("trace", result)

    def test_missing_irrelevant_bits_are_explicitly_completed_and_revalidated(self):
        def erase_data(data):
            position = 0
            for signal in data["signals"]:
                if signal["path"] == ["\\in_3"]:
                    for step in data["steps"]:
                        bits = list(reversed(step["bits"]))
                        bits[position:position + signal["width"]] = "?" * signal["width"]
                        step["bits"] = "".join(reversed(bits))
                position += signal["width"]
        result = self.altered("skid", erase_data, "completed")
        self.assertEqual(result["status"], "VALIDATED", result)
        self.assertEqual(len(result["completed_input_bits"]), 16)
        self.assertEqual({item["port"] for item in result["completed_input_bits"]}, {"i_data"})
        self.assertEqual(result["validation"]["status"], "sat")


if __name__ == "__main__":
    unittest.main()
