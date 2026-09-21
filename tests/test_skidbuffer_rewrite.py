"""Actual public RTL gates and traces for both frozen skidbuffer widths."""

import copy
from pathlib import Path
import tempfile
import unittest

from rtl_relate.__main__ import trace_in_abstract, violates
from rtl_relate.checker import check
from rtl_relate.ir import Invalid, digest, symbols_of
from rtl_relate.properties import replay
from rtl_relate.skid_cases import make_skid_certificate, prepare_case


class SkidbufferRewriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)
        cls.cases = {(width, variant): prepare_case(width, variant, cls.out / f"{width}-{variant}")
                     for width in (8, 32) for variant in ("good", "coarse", "bad_certificate")}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_exports_and_certificate_only_negative(self):
        for width in (8, 32):
            good, bad = self.cases[width, "good"], self.cases[width, "bad_certificate"]
            for role in ("concrete", "abstract"):
                self.assertEqual(good[role + "_source"].name, "normalized.v")
                self.assertTrue(good[role + "_source"].is_file())
                self.assertEqual(good[role + "_parameters"], {})
            self.assertEqual(sum(symbols_of(good["concrete"], "state").values()), 2 * width + 2)
            self.assertEqual(sum(symbols_of(good["abstract"], "state").values()), width + 2)
            self.assertEqual(list(symbols_of(good["abstract"], "nondet").values()), [width])
            self.assertEqual(digest(good["concrete"]), digest(bad["concrete"]))
            self.assertEqual(digest(good["abstract"]), digest(bad["abstract"]))
            for field in ("h", "J", "contract_sha256"):
                self.assertEqual(good["certificate"][field], bad["certificate"][field])
            self.assertNotEqual(good["certificate"]["w"], bad["certificate"]["w"])
            self.assertNotEqual(digest(good["abstract"]), digest(self.cases[width, "coarse"]["abstract"]))

    def test_all_six_gates(self):
        for (width, variant), case in self.cases.items():
            with self.subTest(width=width, variant=variant):
                result = check(case["concrete"], case["abstract"], case["contract"],
                               case["certificate"], self.out / f"gate-{width}-{variant}")
                expected = "CERTIFICATE_REJECTED" if variant == "bad_certificate" else "ACCEPTED"
                self.assertEqual(result["status"], expected, result)
                self.assertEqual(result["obligations"]["INITIAL_NONEMPTY"]["status"], "sat")
                self.assertEqual(result["obligations"]["STEP_MAP"]["status"],
                                 "sat" if variant == "bad_certificate" else "unsat")
                for obligation in ("INIT_J", "STEP_J", "INIT_MAP", "OBS_MAP"):
                    self.assertEqual(result["obligations"][obligation]["status"], "unsat")

    def test_transfer_full_stall_release_and_reset_cover_is_feasible(self):
        for width in (8, 32):
            case = self.cases[width, "good"]
            trace = case["cover_trace"]
            self.assertFalse(violates(trace, case["contract"]))
            self.assertEqual(trace_in_abstract(case["abstract"], case["contract"], trace,
                             self.out / f"cover-a-{width}")["status"], "sat")
            self.assertEqual(replay(case["concrete"], case["contract"], trace,
                             self.out / f"cover-c-{width}")["status"], "FEASIBLE")
            # Sync reset clears the valid flags, while a stalled data register holds.
            self.assertEqual(trace["inputs"][4]["i_reset"], 1)
            self.assertEqual(trace["observations"][4]["o_data"], trace["observations"][5]["o_data"])
            self.assertEqual(trace["observations"][5]["o_valid"], 0)

    def test_good_abstraction_is_strict_and_keeps_hold_relation(self):
        for width in (8, 32):
            case = self.cases[width, "good"]
            trace = case["strictness_trace"]
            self.assertFalse(violates(trace, case["contract"]))
            self.assertEqual(trace_in_abstract(case["abstract"], case["contract"], trace,
                             self.out / f"strict-a-{width}")["status"], "sat")
            self.assertEqual(replay(case["concrete"], case["contract"], trace,
                             self.out / f"strict-c-{width}")["status"], "INFEASIBLE")
            self.assertEqual(trace_in_abstract(case["abstract"], case["contract"],
                             case["coarse_counterexample"], self.out / f"hold-a-{width}")["status"], "unsat")

    def test_coarse_counterexample_is_feasible_only_in_abstract(self):
        for width in (8, 32):
            case = self.cases[width, "coarse"]
            trace = case["coarse_counterexample"]
            self.assertTrue(violates(trace, case["contract"]))
            self.assertEqual(trace_in_abstract(case["abstract"], case["contract"], trace,
                             self.out / f"coarse-a-{width}")["status"], "sat")
            self.assertEqual(replay(case["concrete"], case["contract"], trace,
                             self.out / f"coarse-c-{width}")["status"], "INFEASIBLE")

    def test_certificate_binding_rejects_ambiguous_or_wrong_typed_manifest(self):
        case = self.cases[8, "good"]
        for mutation in ("signed", "wrong_width", "duplicate", "wrong_origin"):
            concrete = copy.deepcopy(case["concrete"])
            key = next(key for key, value in concrete["symbols"].items()
                       if value["origin"] == "LOGIC.r_data")
            symbol = concrete["symbols"][key]
            if mutation == "signed":
                symbol["signed"] = True
            elif mutation == "wrong_width":
                symbol["type"] = 7
            elif mutation == "duplicate":
                concrete["symbols"]["duplicate"] = dict(symbol)
            else:
                symbol["origin"] = "similar_name_is_not_a_binding"
            with self.subTest(mutation=mutation), self.assertRaises(Invalid):
                make_skid_certificate(concrete, case["abstract"], case["contract"])

    def test_fixed_task_selection_rejects_other_configurations(self):
        for width, variant in ((1, "good"), (True, "good"), (8, "unregistered")):
            with self.assertRaises(ValueError):
                prepare_case(width, variant, self.out / "invalid")


if __name__ == "__main__":
    unittest.main()
