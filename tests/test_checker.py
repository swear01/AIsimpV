"""Positive and adversarial checks through the real certificate gate."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from rtl_relate.checker import check
from rtl_relate.fixtures import p1, p5
from rtl_relate.ir import bv, digest, op, ref
from rtl_relate.solver import query as solver_query, run as solver_run


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.C, self.A, self.K, self.cert = p1()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)

    def run_check(self, expected, obligation=None, *, rebind=True, **kwargs):
        if rebind:
            for name, model in (("concrete", self.C), ("abstract", self.A), ("contract", self.K)):
                self.cert[name + "_sha256"] = digest(model)
        result = check(self.C, self.A, self.K, self.cert, self.output, **kwargs)
        self.assertEqual(result["status"], expected, result)
        if obligation:
            self.assertEqual(result["obligations"][obligation]["status"], "sat", result)
        return result

    def test_gold_p1_accepts_and_saves_queries(self):
        result = self.run_check("ACCEPTED")
        self.assertEqual(result["obligations"]["INITIAL_NONEMPTY"]["status"], "sat")
        for name in ("INIT_J", "STEP_J", "INIT_MAP", "STEP_MAP", "OBS_MAP"):
            self.assertEqual(result["obligations"][name]["status"], "unsat")
        self.assertGreaterEqual(len(list(self.output.rglob("*.smt2"))), 6)

    def test_all_three_p5_certificates_accept(self):
        for kind in ("hold", "coarse", "bug"):
            with self.subTest(kind=kind):
                self.C, self.A, self.K, self.cert = p5(kind)
                self.run_check("ACCEPTED")

    def test_wrong_abstract_initial_state(self):
        self.A["init"] = op("eq", ref("d"), bv(1, 1))
        self.run_check("CERTIFICATE_REJECTED", "INIT_MAP")

    def test_wrong_concrete_initial_state(self):
        self.C["init"] = op("eq", ref("x"), bv(3, 2))
        self.run_check("CERTIFICATE_REJECTED", "INIT_MAP")

    def test_wrong_abstract_transition(self):
        self.A["next"]["d"] = bv(0, 1)
        self.run_check("CERTIFICATE_REJECTED", "STEP_MAP")

    def test_wrong_observation(self):
        self.A["observe"]["done"] = op("bvnot", ref("d"))
        self.run_check("CERTIFICATE_REJECTED", "OBS_MAP")

    def test_wrong_witness(self):
        self.cert["w"]["z"] = bv(0, 1)
        self.run_check("CERTIFICATE_REJECTED", "STEP_MAP")

    def test_wrong_mapping(self):
        self.cert["h"]["d"] = bv(0, 1)
        self.run_check("CERTIFICATE_REJECTED", "OBS_MAP")

    def test_false_invariant(self):
        self.cert["J"] = {"bool": False}
        self.run_check("CERTIFICATE_REJECTED", "INIT_J")

    def test_noninductive_invariant_cannot_hide_wrong_witness(self):
        self.cert["J"] = op("ult", ref("c.x"), bv(2, 2))
        self.cert["w"]["z"] = bv(0, 1)
        result = self.run_check("CERTIFICATE_REJECTED", "STEP_J")
        self.assertEqual(result["obligations"]["STEP_MAP"]["status"], "unsat")

    def test_empty_concrete_initial_set(self):
        self.C["init"] = {"bool": False}
        result = self.run_check("CERTIFICATE_REJECTED")
        self.assertEqual(result["obligations"]["INITIAL_NONEMPTY"]["status"], "unsat")

    def test_missing_mapping_state(self):
        self.cert["h"].clear()
        self.run_check("ERROR")

    def test_extra_mapping_state(self):
        self.cert["h"]["ghost"] = bv(0, 1)
        self.run_check("ERROR")

    def test_wrong_mapping_width(self):
        self.cert["h"]["d"] = bv(0, 2)
        self.run_check("ERROR")

    def test_missing_witness(self):
        self.cert["w"].clear()
        self.run_check("ERROR")

    def test_extra_witness(self):
        self.cert["w"]["ghost"] = bv(0, 1)
        self.run_check("ERROR")

    def test_wrong_witness_width(self):
        self.cert["w"]["z"] = bv(0, 2)
        self.run_check("ERROR")

    def test_wrong_invariant_type(self):
        self.cert["J"] = bv(1, 1)
        self.run_check("ERROR")

    def test_missing_model_state_transition(self):
        self.C["next"].clear()
        self.run_check("ERROR")

    def test_missing_model_clock(self):
        self.C.pop("clock")
        self.run_check("ERROR")

    def test_abstract_clock_name_must_match_contract(self):
        self.A["clock"]["name"] = "other_clk"
        self.run_check("ERROR")

    def test_concrete_clock_name_must_match_contract(self):
        self.C["clock"]["name"] = "other_clk"
        self.run_check("ERROR")

    def test_model_negative_clock_edge_is_unsupported(self):
        self.A["clock"]["edge"] = "negative"
        self.run_check("UNSUPPORTED")

    def test_unknown_symbol_in_model(self):
        self.C["next"]["x"] = ref("missing")
        self.run_check("ERROR")

    def test_unknown_symbol_in_certificate(self):
        self.cert["h"]["d"] = ref("c.missing")
        self.run_check("ERROR")

    def test_abstract_reference_in_mapping(self):
        self.cert["h"]["d"] = ref("a.d")
        self.run_check("ERROR")

    def test_future_reference_in_witness(self):
        self.cert["w"]["z"] = ref("n.x")
        self.run_check("ERROR")

    def test_public_input_not_allowed_in_mapping(self):
        self.C, self.A, self.K, self.cert = p5()
        self.cert["h"]["v"] = ref("u.en")
        self.run_check("ERROR")

    def test_model_hash_mismatch(self):
        self.cert["concrete_sha256"] = "0" * 64
        self.run_check("ERROR", rebind=False)

    def test_abstract_hash_mismatch(self):
        self.cert["abstract_sha256"] = "0" * 64
        self.run_check("ERROR", rebind=False)

    def test_contract_hash_mismatch(self):
        self.cert["contract_sha256"] = "0" * 64
        self.run_check("ERROR", rebind=False)

    def test_changed_contract_requires_new_binding(self):
        self.K["property"]["step"] = {"bool": True}
        self.run_check("ERROR", rebind=False)

    def test_unknown_operator_is_unsupported(self):
        self.cert["w"]["z"] = op("division-not-supported", bv(1, 1), bv(1, 1))
        self.run_check("UNSUPPORTED")

    def test_unknown_semantics_is_unsupported(self):
        self.K["semantics"] = "multi-clock"
        self.run_check("UNSUPPORTED")

    def test_missing_contract_input(self):
        self.C, self.A, self.K, self.cert = p5()
        self.K["inputs"].pop("ready")
        self.run_check("ERROR")

    def test_wrong_contract_observation_width(self):
        self.K["observations"]["done"] = 2
        self.run_check("ERROR")

    def test_wrong_model_next_width(self):
        self.C["next"]["x"] = bv(0, 1)
        self.run_check("ERROR")

    def test_input_dependent_initial_state_is_rejected(self):
        self.C, self.A, self.K, self.cert = p5()
        self.C["init"] = op("eq", ref("en"), bv(1, 1))
        self.run_check("ERROR")

    def test_concrete_nondeterminism_is_unsupported(self):
        self.C["symbols"]["noise"] = {"kind": "nondet", "type": 1, "signed": False, "origin": "noise"}
        self.run_check("UNSUPPORTED")

    def test_duplicate_public_input_origins_are_rejected(self):
        self.C, self.A, self.K, self.cert = p5()
        self.A["symbols"]["en"]["origin"] = "ready"
        self.run_check("ERROR")

    def test_boolean_width_is_not_integer_width(self):
        self.cert["w"]["z"] = {"bv": 0, "width": True}
        self.run_check("ERROR")

    def test_negative_bv_literal(self):
        self.cert["w"]["z"] = {"bv": -1, "width": 1}
        self.run_check("ERROR")

    def test_out_of_range_bv_literal(self):
        self.cert["w"]["z"] = {"bv": 2, "width": 1}
        self.run_check("ERROR")

    def test_mealy_step_and_observation_must_share_witness(self):
        self.C["observe"]["done"] = bv(1, 1)
        self.A["next"]["d"] = ref("z")
        self.A["observe"]["done"] = op("bvand", op("bvnot", ref("d")), ref("z"))
        self.cert["h"]["d"] = bv(0, 1)
        for witness, failing in ((0, "OBS_MAP"), (1, "STEP_MAP")):
            with self.subTest(witness=witness):
                self.cert["w"]["z"] = bv(witness, 1)
                self.run_check("CERTIFICATE_REJECTED", failing)

    @staticmethod
    def solver_row(status):
        return {"status": status, "stdout": status + "\n", "stderr": "", "returncode": 0, "seconds": 0.0}

    def test_initial_unknown_is_not_accepted(self):
        with patch("rtl_relate.checker.run", return_value=self.solver_row("unknown")):
            self.run_check("UNKNOWN")

    def test_proof_unknown_is_not_accepted(self):
        rows = [self.solver_row(s) for s in ("sat", "unknown", "unsat", "unsat", "unsat", "unsat")]
        with patch("rtl_relate.checker.run", side_effect=rows):
            self.run_check("UNKNOWN")

    def test_initial_solver_error_is_not_accepted(self):
        with patch("rtl_relate.checker.run", return_value=self.solver_row("error")):
            self.run_check("ERROR")

    def test_proof_solver_error_is_not_accepted(self):
        rows = [self.solver_row(s) for s in ("sat", "error", "unsat", "unsat", "unsat", "unsat")]
        with patch("rtl_relate.checker.run", side_effect=rows):
            self.run_check("ERROR")

    def fake_solver(self, body, *, version_ok=True):
        path = self.output / "fake-solver"
        version = "import sys\nif '-version' in sys.argv:\n    print('test-solver')\n    sys.exit(0)\n" if version_ok else ""
        path.write_text("#!/usr/bin/env python3\n" + version + body)
        path.chmod(0o755)
        return str(path)

    def test_real_subprocess_unknown(self):
        solver = self.fake_solver("print('unknown')\n")
        self.run_check("UNKNOWN", solver=solver)

    def test_real_subprocess_failure(self):
        solver = self.fake_solver("import sys\nprint('unsat')\nsys.exit(2)\n")
        self.run_check("ERROR", solver=solver)

    def test_solver_version_process_failure(self):
        solver = self.fake_solver("import sys\nsys.exit(2)\n", version_ok=False)
        self.run_check("ERROR", solver=solver)

    def test_solver_version_timeout(self):
        with patch("rtl_relate.solver.subprocess.run", side_effect=subprocess.TimeoutExpired(["z3", "-version"], 10)):
            self.run_check("ERROR")

    def test_real_subprocess_timeout(self):
        solver = self.fake_solver("import time\ntime.sleep(2)\nprint('unsat')\n")
        self.run_check("UNKNOWN", solver=solver, timeout_ms=1)

    def test_missing_solver_binary(self):
        self.run_check("ERROR", solver=str(self.output / "does-not-exist"))

    def test_real_solver_sat_retains_counterexample(self):
        row = solver_run(solver_query([], "true", 5000), self.output, "real-sat")
        self.assertEqual(row["status"], "sat", row)
        self.assertEqual(row["returncode"], 0, row)
        self.assertIn("counterexample_smt", row)

    def test_real_solver_unsat_handles_expected_get_model_error(self):
        row = solver_run(solver_query([], "false", 5000), self.output, "real-unsat")
        self.assertEqual(row["status"], "unsat", row)
        self.assertIn("unsat", row["stdout"])

    def test_expected_no_model_error_for_unsat_and_unknown(self):
        for status in ("unsat", "unknown"):
            with self.subTest(status=status):
                stdout = status + '\n(error "line 6 column 10: model is not available")\n'
                solver = self.fake_solver(f"import sys\nsys.stdout.write({stdout!r})\nsys.exit(1)\n")
                row = solver_run(solver_query([], "true", 5000), self.output, "no-model-" + status, solver=solver)
                self.assertEqual(row["status"], status, row)
                self.assertEqual(row["returncode"], 1)

    def test_malformed_solver_outputs_fail_closed(self):
        cases = (
            ("sat\n", 0, ""),
            ("unsat\nsat\n", 0, ""),
            ("unsat\n(error \"unrelated error\")\n", 1, ""),
            ("sat\n()\n", 1, ""),
            ("unsat\n", 0, "warning"),
            ("garbage\n", 0, ""),
        )
        for index, (stdout, code, stderr) in enumerate(cases):
            with self.subTest(stdout=stdout, code=code, stderr=stderr):
                solver = self.fake_solver(
                    f"import sys\nsys.stdout.write({stdout!r})\nsys.stderr.write({stderr!r})\nsys.exit({code})\n"
                )
                row = solver_run(solver_query([], "true", 5000), self.output, f"malformed-{index}", solver=solver)
                self.assertEqual(row["status"], "error", row)


if __name__ == "__main__":
    unittest.main()
