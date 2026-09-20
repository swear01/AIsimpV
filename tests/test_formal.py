"""Qualify actual RTL proofs, free choices, bounded results and failure reporting."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from rtl_relate.formal import prove_rtl
from rtl_relate.ir import bv, digest, load_json, op, ref

ROOT = Path(__file__).resolve().parents[1]


class FormalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name)
        cls.contract = load_json(ROOT / "fixtures/contracts/p5.json")
        cls.results = {}
        for name in ("p5_concrete", "p5_hold", "p5_coarse", "p5_bug"):
            cls.results[name] = prove_rtl(ROOT / f"fixtures/rtl/{name}.v", name, cls.contract,
                                          cls.out / name, nondet=("z",) if name in {"p5_hold", "p5_coarse"} else ())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_proofs_and_reachable_violations(self):
        self.assertEqual({k: v["status"] for k, v in self.results.items()}, {
            "p5_concrete": "SAFE", "p5_hold": "SAFE", "p5_coarse": "CEX", "p5_bug": "CEX"})
        for name, result in self.results.items():
            self.assertEqual(result["contract_sha256"], digest(self.contract))
            self.assertEqual(result["free_nondeterminism"], True)
            self.assertGreater(result["seconds"], 0)
            self.assertIn("state_bits", result["after_property_preprocessing"])
            self.assertIn("model.smt2", result["hashes"])
            self.assertEqual(json.loads((self.out / name / "formal.json").read_text()), result)
            if result["status"] == "SAFE":
                self.assertEqual(result["stages"]["induction"]["returncode"], 0)
            else:
                self.assertTrue((self.out / name / "base.vcd").is_file())
                self.assertTrue((self.out / name / "base.yw").is_file())
        self.assertEqual(self.results["p5_hold"]["nondet"], ["z"])
        smt = (self.out / "p5_hold/model.smt2").read_text()
        self.assertNotIn("; yosys-smt2-assume ", smt)

    def test_bmc_success_is_not_safe(self):
        result = prove_rtl(ROOT / "fixtures/rtl/p5_concrete.v", "p5_concrete", self.contract,
                           self.out / "bounded", mode="bmc", depth=4)
        self.assertEqual(result["status"], "BOUNDED", result)
        self.assertEqual(result["bounded_edges"], 3)
        self.assertNotIn("induction", result["stages"])

    def test_induction_failure_is_not_a_reachable_bug(self):
        contract = copy.deepcopy(self.contract)
        contract["inputs"] = {}
        contract["observations"] = {"q": 1}
        contract["property"] = {"id": "not-yet", "step": op("eq", ref("n.q"), bv(0, 1))}
        for depth, expected in ((2, "BOUNDED"), (6, "CEX")):
            result = prove_rtl(ROOT / "fixtures/formal/qualification.v", "delayed_bug", contract,
                               self.out / f"delayed-{depth}", depth=depth)
            self.assertEqual(result["status"], expected, result)
            self.assertEqual(result["requested_depth"], depth)
            if expected == "CEX":
                self.assertEqual(result["counterexample_step"], 3)
                self.assertNotIn("bounded_depth", result)
                self.assertNotIn("bounded_edges", result)
            else:
                self.assertEqual(result["bounded_edges"], depth - 1)

    def test_32_bit_overflow_is_preserved_before_extension(self):
        contract = copy.deepcopy(self.contract)
        contract["inputs"] = {"u": 32}
        contract["observations"] = {"q": 32}
        add = op("add", ref("u.u"), bv(0xffffffff, 32))
        extend = lambda expr: {"op": "zext", "args": [expr], "width": 33}
        contract["property"] = {"id": "wrapped-add", "step": op("eq", extend(ref("n.q")), extend(add))}
        result = prove_rtl(ROOT / "fixtures/formal/qualification.v", "arithmetic", contract,
                           self.out / "overflow")
        self.assertEqual(result["status"], "SAFE", result)

    def test_budget_and_tool_errors_remain_failures(self):
        source = ROOT / "fixtures/rtl/p5_concrete.v"
        timed = prove_rtl(source, "p5_concrete", self.contract, self.out / "timeout", timeout_seconds=0.0001)
        self.assertEqual(timed["status"], "UNKNOWN", timed)
        missing = prove_rtl(source, "p5_concrete", self.contract, self.out / "missing", smtbmc="/nonexistent/smtbmc")
        self.assertEqual(missing["status"], "UNSUPPORTED", missing)
        malformed = self.out / "malformed.v"
        malformed.write_text("module broken;")
        error = prove_rtl(malformed, "broken", self.contract, self.out / "error")
        self.assertEqual(error["status"], "ERROR", error)
        self.assertTrue((self.out / "error/design.stderr.log").exists())

    def test_unregistered_choices_and_clock_mismatch_are_rejected(self):
        result = prove_rtl(ROOT / "fixtures/rtl/p5_hold.v", "p5_hold", self.contract, self.out / "unregistered")
        self.assertEqual(result["status"], "ERROR", result)
        wrong = copy.deepcopy(self.contract)
        wrong["clock"]["name"] = "other_clock"
        result = prove_rtl(ROOT / "fixtures/rtl/p5_concrete.v", "p5_concrete", wrong, self.out / "clock")
        self.assertEqual(result["status"], "UNSUPPORTED", result)

    def test_attempt_reuse_preserves_evidence(self):
        previous = (self.out / "p5_concrete/formal.json").read_bytes()
        result = prove_rtl(ROOT / "fixtures/rtl/p5_concrete.v", "p5_concrete", self.contract, self.out / "p5_concrete")
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual((self.out / "p5_concrete/formal.json").read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
