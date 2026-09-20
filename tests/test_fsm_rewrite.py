"""R1's real RTL, bidirectional mapping, invariant failure, and free-choice CEX."""

from copy import deepcopy
from itertools import product
from pathlib import Path
import tempfile
import unittest

from rtl_relate.checker import check
from rtl_relate.fsm_case import prepare_case
from rtl_relate.ir import evaluate, symbols_of, validate_model
from rtl_relate.properties import check_property, replay
from rtl_relate.__main__ import trace_in_abstract, violates


class FSMRewriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)
        cls.cases = {kind: prepare_case(kind, cls.out / kind) for kind in
                     ("good", "coarse", "bad_certificate")}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def gate(self, case, name, certificate=None):
        return check(case["concrete"], case["abstract"], case["contract"],
                     certificate or case["certificate"], self.out / name)

    def test_actual_exports_preserve_every_state_and_transition(self):
        models = {"concrete": self.cases["good"]["concrete"],
                  "good": self.cases["good"]["abstract"], "coarse": self.cases["coarse"]["abstract"]}
        checked = 0
        for kind, model in models.items():
            types = validate_model(model)
            state_key, = symbols_of(model, "state")
            self.assertEqual(types[state_key], 3 if kind == "concrete" else 2)
            keys = list(types)
            for values in product(*(range(1 << types[key]) for key in keys)):
                env = dict(zip(keys, values))
                named = {model["symbols"][key]["origin"]: value for key, value in env.items()}
                state = named["state"]
                expected = named["z"] if kind == "coarse" else state
                if kind != "coarse" and named["advance"]:
                    expected = {1: 2, 2: 4}.get(state, 1) if kind == "concrete" else {0: 1, 1: 2}.get(state, 0)
                self.assertEqual(evaluate(model["next"][state_key], env, types), expected)
                codes = (1, 2, 4) if kind == "concrete" else (0, 1, 2)
                self.assertEqual({key: evaluate(expr, env, types) for key, expr in model["observe"].items()},
                                 {key: int(state == code) for key, code in zip(("idle", "busy", "done"), codes)})
                self.assertEqual(evaluate(model["init"], env, types), state == (1 if kind == "concrete" else 0))
                checked += 1
        self.assertEqual(checked, 56)

    def test_good_mapping_proves_both_trace_inclusions(self):
        case = self.cases["good"]
        self.assertEqual(self.gate(case, "good-gate")["status"], "ACCEPTED")
        reverse = check(case["abstract"], case["concrete"], case["contract"],
                        case["reverse_certificate"], self.out / "reverse-gate")
        self.assertEqual(reverse["status"], "ACCEPTED")
        for side in ("concrete", "abstract"):
            self.assertEqual(check_property(case[side], case["contract"], self.out / (side + "-property"))["status"], "SAFE")
        cover = replay(case["concrete"], case["contract"], case["concrete_cover_trace"], self.out / "cover")
        self.assertEqual(cover["status"], "FEASIBLE")

    def test_missing_reachable_state_is_rejected_by_inductive_invariant(self):
        report = self.gate(self.cases["bad_certificate"], "bad-invariant")
        self.assertEqual(report["status"], "CERTIFICATE_REJECTED")
        self.assertEqual(report["obligations"]["INIT_J"]["status"], "unsat")
        self.assertEqual(report["obligations"]["STEP_J"]["status"], "sat")
        certificate = deepcopy(self.cases["good"]["certificate"])
        certificate["J"] = {"bool": True}
        report = self.gate(self.cases["good"], "omitted-invariant", certificate)
        self.assertEqual(report["status"], "CERTIFICATE_REJECTED")
        self.assertEqual(report["obligations"]["OBS_MAP"]["status"], "sat")

    def test_coarse_gate_passes_but_free_nondeterminism_fails_property(self):
        case = self.cases["coarse"]
        self.assertEqual(self.gate(case, "coarse-gate")["status"], "ACCEPTED")
        result = check_property(case["abstract"], case["contract"], self.out / "coarse-property")
        self.assertEqual(result["status"], "ABSTRACT_CEX")
        self.assertTrue(result["free_nondeterminism"])
        for name, trace in (("automatic", result["trace"]), ("declared", case["coarse_counterexample"])):
            accepted = trace_in_abstract(case["abstract"], case["contract"], trace, self.out / (name + "-abstract"))
            self.assertTrue(violates(trace, case["contract"]))
            rejected = replay(case["concrete"], case["contract"], trace, self.out / (name + "-concrete"))
            self.assertEqual(accepted["status"], "sat")
            self.assertEqual(rejected["status"], "INFEASIBLE")


if __name__ == "__main__":
    unittest.main()
