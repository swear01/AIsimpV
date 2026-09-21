"""Qualify actual RTL proofs, free choices, bounded results and failure reporting."""

import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import sys
import time
import unittest
from unittest.mock import patch

from rtl_relate.formal import _run, prove_rtl
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

    def test_missing_initial_state_is_rejected_before_property_preparation(self):
        source = self.out / "partial_init.v"
        source.write_text("module partial_init(input clk, output reg q=0); reg r; "
                          "always @(posedge clk) begin q<=r; r<=~r; end endmodule")
        contract = copy.deepcopy(self.contract)
        contract["inputs"] = {}
        contract["observations"] = {"q": 1}
        contract["property"] = {"id": "initialization-boundary", "step": {"bool": True}}
        result = prove_rtl(source, "partial_init", contract, self.out / "partial-init")
        self.assertEqual(result["status"], "UNSUPPORTED", result)
        self.assertEqual(result["reason"], "every design state requires explicit initialization")
        self.assertNotIn("prepare", result["stages"])
        self.assertNotIn("base", result["stages"])

    def test_attempt_reuse_preserves_evidence(self):
        previous = (self.out / "p5_concrete/formal.json").read_bytes()
        result = prove_rtl(ROOT / "fixtures/rtl/p5_concrete.v", "p5_concrete", self.contract, self.out / "p5_concrete")
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual((self.out / "p5_concrete/formal.json").read_bytes(), previous)

    def test_malformed_tool_output_preserves_both_raw_logs(self):
        out = self.out / "invalid-utf8"
        out.mkdir()
        command = [sys.executable, "-c",
                   "import os; os.write(1, b'Status: PASSED\\n\\xff'); os.write(2, b'error\\xfe')"]
        with self.assertRaises(UnicodeDecodeError):
            _run(command, out, "tool", time.monotonic() + 10)
        self.assertEqual((out / "tool.stdout.log").read_bytes(), b"Status: PASSED\n\xff")
        self.assertEqual((out / "tool.stderr.log").read_bytes(), b"error\xfe")


class ProcessTests(unittest.TestCase):
    def test_timeout_bounds_drain_when_escaped_descendant_holds_pipes(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            pid_file = out / "escaped.pid"
            child = ("import os,time; os.write(1,b'partial stdout\\n'); "
                     "os.write(2,b'partial stderr\\xfe'); time.sleep(15)")
            parent = ("import pathlib,subprocess,sys,time; "
                      f"child=subprocess.Popen([sys.executable,'-c',{child!r}], start_new_session=True); "
                      "pathlib.Path('escaped.pid').write_text(str(child.pid)); time.sleep(15)")
            started = time.monotonic()
            try:
                row, stdout = _run([sys.executable, "-c", parent], out, "escaped", started + 2)
                self.assertLess(time.monotonic() - started, 6)
                self.assertTrue(row["timeout"])
                self.assertEqual(row["returncode"], -signal.SIGKILL)
                self.assertEqual(stdout, "partial stdout\n")
                self.assertEqual((out / "escaped.stdout.log").read_bytes(), b"partial stdout\n")
                self.assertEqual((out / "escaped.stderr.log").read_bytes(), b"partial stderr\xfe")
            finally:
                if pid_file.exists():
                    try:
                        os.kill(int(pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_kill_permission_error_is_retained_without_unbounded_drain(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("rtl_relate.formal.subprocess.Popen") as launch, \
                patch("rtl_relate.formal.os.killpg", side_effect=PermissionError("kill denied")):
            process = launch.return_value
            process.communicate.side_effect = subprocess.TimeoutExpired(
                "tool", 1, output=b"partial out", stderr=b"partial err")
            row, stdout = _run(["tool"], Path(directory), "denied", time.monotonic() + 1)
            self.assertTrue(row["timeout"])
            self.assertEqual(stdout, "partial out")
            self.assertEqual(process.communicate.call_count, 1)
            process.stdout.close.assert_called_once()
            process.stderr.close.assert_called_once()
            process.poll.assert_called_once()
            stderr = (Path(directory) / "denied.stderr.log").read_bytes()
            self.assertIn(b"partial err", stderr)
            self.assertIn(b"kill denied", stderr)


if __name__ == "__main__":
    unittest.main()
