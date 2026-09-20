"""Actual RTL certificates plus independent reset, arithmetic and trace checks."""

from pathlib import Path
import tempfile
import unittest

from rtl_relate.__main__ import trace_in_abstract, violates
from rtl_relate.checker import check
from rtl_relate.ir import digest, evaluate, symbols_of, validate_model
from rtl_relate.pipeline_case import prepare_case
from rtl_relate.properties import replay


class PipelineRewriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)
        cls.cases = {kind: prepare_case(kind, cls.out / kind)
                     for kind in ("good", "coarse", "bad_certificate")}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exported_gold_and_coarse_certify_but_wrong_mapping_does_not(self):
        for kind, case in self.cases.items():
            with self.subTest(kind=kind):
                result = check(*(case[key] for key in ("concrete", "abstract", "contract", "certificate")),
                               self.out / kind / "gate")
                self.assertEqual(result["status"],
                                 "CERTIFICATE_REJECTED" if kind == "bad_certificate" else "ACCEPTED")
                if kind == "bad_certificate":
                    self.assertEqual(result["obligations"]["STEP_MAP"]["status"], "sat")
        self.assertEqual(digest(self.cases["good"]["abstract"]),
                         digest(self.cases["bad_certificate"]["abstract"]))
        for kind in ("good", "coarse"):
            case = self.cases[kind]
            self.assertTrue(case["concrete_source"].is_file())
            self.assertEqual(sum(symbols_of(case["concrete"], "state").values()), 160)
            self.assertEqual(sum(symbols_of(case["abstract"], "state").values()), 128)

    def test_real_rtl_preserves_modular_arithmetic_and_only_output_resets(self):
        mask = (1 << 32) - 1
        for kind in ("good", "coarse"):
            model = self.cases[kind]["abstract"]
            types = validate_model(model)
            for reset, total in ((0, 3), (1, 3), (0, mask), (1, mask)):
                values = {"sum": total, "dataOut": 19, "tmp_stageOne": 23,
                          "tmp_stageTwo": 29, "dataIn": 0xffffffff, "c1": 3,
                          "c2": 0xffffffff, "reset": reset, "z": 7, "z2": 11}
                env = {key: values[symbol["origin"]] for key, symbol in model["symbols"].items()}
                actual = {model["symbols"][key]["origin"]: evaluate(expr, env, types)
                          for key, expr in model["next"].items()}
                self.assertEqual(actual, {"sum": 9, "dataOut": 0 if reset else total,
                                         "tmp_stageOne": 7,
                                         "tmp_stageTwo": (total - 7) & mask if kind == "good" else 11})
                self.assertEqual(set(symbols_of(model, "nondet")), set(self.cases[kind]["certificate"]["w"]))

    def test_free_choices_have_extra_traces_and_coarse_loses_original_property(self):
        for kind in ("good", "coarse"):
            case = self.cases[kind]
            trace = case["strictness_trace"]
            self.assertEqual(trace_in_abstract(case["abstract"], case["contract"], trace,
                                              self.out / kind / "strictness")["status"], "sat")
            self.assertEqual(replay(case["concrete"], case["contract"], trace,
                                    self.out / kind / "strictness_concrete")["status"], "INFEASIBLE")
        case = self.cases["coarse"]
        trace = case["coarse_counterexample"]
        self.assertTrue(violates(trace, case["contract"]))
        self.assertEqual(trace_in_abstract(case["abstract"], case["contract"], trace,
                                          self.out / "coarse/cex_abstract")["status"], "sat")
        self.assertEqual(replay(case["concrete"], case["contract"], trace,
                                self.out / "coarse/cex_concrete")["status"], "INFEASIBLE")
        gold = self.cases["good"]
        self.assertEqual(trace_in_abstract(gold["abstract"], gold["contract"], trace,
                                          self.out / "good/coarse_trace")["status"], "unsat")

    def test_concrete_cover_replays_reset_history_and_overflow(self):
        case = self.cases["good"]
        self.assertFalse(violates(case["concrete_cover_trace"], case["contract"]))
        self.assertEqual(replay(case["concrete"], case["contract"], case["concrete_cover_trace"],
                                self.out / "good/concrete_cover")["status"], "FEASIBLE")


if __name__ == "__main__":
    unittest.main()
