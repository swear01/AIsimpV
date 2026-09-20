"""Runner regressions: contradictory evidence, shared deadlines and failed costs."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from rtl_relate import wednesday as w
from rtl_relate.fixtures import p1
from rtl_relate.ir import digest


class WednesdayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        c, a, k, certificate = p1()
        self.case = {"concrete": c, "abstract": a, "contract": k, "certificate": certificate,
                     "concrete_source": "C.v", "abstract_source": "A.v",
                     "concrete_top": "C", "abstract_top": "A"}
        self.clock = 0.0
        self.operations = []
        self.proof_status = "SAFE"
        self.proof_time = 0.0
        self.fail_prepare = False
        self.trace = {"status": "SPURIOUS_TRACE", "abstract": "sat", "concrete": "INFEASIBLE",
                      "violates_property": True, "seconds": 1}
        self.addCleanup(patch.stopall)
        patch.object(w.time, "monotonic", side_effect=lambda: self.clock).start()
        patch.object(w, "validate_case", return_value={"concrete_source_sha256": "c", "abstract_source_sha256": "a"}).start()
        patch.object(w, "bounded", side_effect=self.bounded).start()
        patch("rtl_relate.formal.prove_rtl", side_effect=self.prove).start()

    def bounded(self, operation, args, kwargs, out, deadline):
        self.operations.append((operation, self.clock, deadline))
        self.clock += 1
        if operation == "prepare":
            if self.fail_prepare:
                raise ValueError("frontend failed after work")
            return deepcopy(self.case)
        if operation == "certificate":
            return {"status": "ACCEPTED", "seconds": 1}
        if operation == "trace":
            return dict(self.trace)
        if operation == "replay":
            return {"status": "FEASIBLE", "seconds": 1}
        self.fail(operation)

    def prove(self, source, top, contract, out, **kwargs):
        self.operations.append(("proof", self.clock, kwargs["timeout_seconds"]))
        self.clock += self.proof_time
        role = "concrete" if top == "C" else "abstract"
        return {"status": self.proof_status, "seconds": self.proof_time,
                "source_sha256": "c" if role == "concrete" else "a",
                "contract_sha256": digest(contract), "top": top,
                "parameters": {}, "nondet": []}

    def run_one(self, variant="good", budget=1800):
        with patch.object(w, "VARIANTS", (variant,)):
            return w.run_task("R1-fsm", self.root, budget)[0][0]

    def test_any_reachable_violating_trace_conflicts_with_safe(self):
        for key in ("coarse_counterexample", "strictness_trace"):
            with self.subTest(key=key):
                self.case[key] = {}
                self.root = self.root / key
                row = self.run_one()
                self.assertEqual(row["status"], "ERROR")
                self.assertFalse(row["expected_met"])
                self.assertEqual(row["abstract_property_status"], "SAFE")
                self.assertEqual(row[key]["abstract"], "sat")
                self.assertIn("conflicts", row["reason"])
                self.case.pop(key)

    def test_expired_baseline_never_starts_certificate(self):
        self.proof_time = 3
        row = self.run_one(budget=2)
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertFalse(any(op[0] == "certificate" for op in self.operations))
        self.assertEqual(row["attempt_b0_seconds"], 3)
        self.assertEqual(row["workflow_seconds"], 1)

    def test_prepare_failure_preserves_full_cost(self):
        self.fail_prepare = True
        row = self.run_one()
        self.assertEqual(row["status"], "ERROR")
        self.assertEqual(row["frontend_seconds"], 1)
        self.assertEqual(row["workflow_seconds"], row["attempt_wall_seconds"])
        self.assertEqual(row["workflow_seconds"], 1)
        self.assertTrue((self.root / "R1-fsm/good/result.json").exists())

    def test_certificate_and_trace_caps_share_remaining_task_budget(self):
        self.case["strictness_trace"] = {}
        self.trace = {"status": "EXTRA_ABSTRACT_TRACE", "abstract": "sat", "concrete": "INFEASIBLE",
                      "violates_property": False, "seconds": 1}
        row = self.run_one(budget=40)
        self.assertEqual(row["status"], "SAFE")
        caps = {op: deadline - start for op, start, deadline in self.operations if op != "proof"}
        self.assertEqual(caps["certificate"], 39)
        self.assertEqual(caps["trace"], 30)

    def test_trace_without_legal_concrete_execution_never_becomes_bug(self):
        self.proof_status = "CEX"
        self.case["coarse_counterexample"] = {}
        row = self.run_one("coarse")
        self.assertEqual(row["status"], "SPURIOUS_TRACE")
        self.assertTrue(row["expected_met"])
        self.root = self.root / "unknown"
        self.trace.update(status="UNRESOLVED", concrete="UNKNOWN")
        self.assertEqual(self.run_one("coarse")["status"], "UNRESOLVED")

    def test_bad_certificate_cannot_change_abstraction(self):
        calls = [0]
        original = self.bounded
        def changed(operation, args, kwargs, out, deadline):
            value = original(operation, args, kwargs, out, deadline)
            if operation == "prepare":
                calls[0] += 1
                if calls[0] == 2:
                    value["abstract"]["name"] = "changed"
            return value
        with patch.object(w, "VARIANTS", ("good", "bad_certificate")), patch.object(w, "bounded", side_effect=changed):
            rows, _ = w.run_task("R1-fsm", self.root)
        self.assertEqual(rows[-1]["status"], "ERROR")
        self.assertIn("changed the good abstraction", rows[-1]["reason"])

    def test_proof_hash_mismatch_never_claims_safe(self):
        with patch("rtl_relate.formal.prove_rtl", return_value={"status": "SAFE", "source_sha256": "wrong"}):
            row = self.run_one()
        self.assertEqual(row["status"], "ERROR")
        self.assertIn("binding differs", row["reason"])


class CLITests(unittest.TestCase):
    def test_invalid_task_and_budget_fail_before_creating_output(self):
        cases = [["--task", "R1-fsm", "--task", "R1-fsm"]]
        cases += [["--task-budget=" + value] for value in ("0", "-1", "nan", "inf", "-inf")]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "must-not-exist"
            for options in cases:
                with self.subTest(options=options), patch.object(w.sys, "argv", [
                        "wednesday", "--out", str(out), *options]), patch.object(w, "run_task") as run, \
                        patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as error:
                    w.main()
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()
                self.assertFalse(out.exists())

    def test_default_and_explicit_budget_reach_each_selected_task(self):
        for options, expected in (([], 1800), (["--task-budget", "120"], 120)):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / "result"
                with patch.object(w.sys, "argv", ["wednesday", "--out", str(out), *options]), \
                        patch.object(w, "run_task", return_value=([{"expected_met": True}], {})) as run:
                    self.assertEqual(w.main(), 0)
                self.assertEqual([call.args[0] for call in run.call_args_list], list(w.TASKS))
                self.assertTrue(all(call.kwargs == {"task_budget": expected} for call in run.call_args_list))


class DeadlineAndManifestTests(unittest.TestCase):
    def test_real_certificate_worker_is_killed_at_aggregate_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            solver = out / "slow-solver"
            solver.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n")
            solver.chmod(0o755)
            c, a, k, cert = p1()
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                w.bounded("certificate", (c, a, k, cert, out / "certificate"),
                          {"solver": str(solver)}, out / "worker", started + 0.25)
            self.assertLess(time.monotonic() - started, 2)
            process = json.loads((out / "worker/process.json").read_text())
            self.assertTrue(process["timeout"])
            self.assertTrue((out / "worker/request.json").exists())
            self.assertTrue((out / "worker/worker.stdout.log").exists())

    def test_modified_frozen_contract_is_rejected_before_proving(self):
        entry = next(x for x in w.load_json(w.ROOT / "fixtures/public/sources.json")["tasks"] if x["id"] == "R1-fsm")
        contract = w.load_json(w.ROOT / entry["contract"]["path"])
        contract["property"]["step"] = {"bool": True}
        with self.assertRaisesRegex(ValueError, "frozen source manifest"):
            w.validate_case("R1-fsm", {"contract": contract}, Path("unused"))


if __name__ == "__main__":
    unittest.main()
