"""Real SMT and complete finite-state checks for free-choice properties and replay."""

from copy import deepcopy
from pathlib import Path
import inspect
import tempfile
import unittest
from unittest.mock import patch

from rtl_relate import properties, solver
from rtl_relate.fixtures import p1, p5
from rtl_relate.ir import bv, op, ref, validate_model


class PropertyReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def check(self, model, contract, **kwargs):
        return properties.check_property(model, contract, self.out / "property", **kwargs)

    def replay(self, model, contract, trace, **kwargs):
        return properties.replay(model, contract, trace, self.out / "replay", **kwargs)

    def test_p1_monotonic_is_unbounded_safe_with_free_nondeterminism(self):
        concrete, abstract, contract, _ = p1()
        for model in (concrete, abstract):
            result = self.check(model, contract)
            self.assertEqual(result["status"], "SAFE")
            self.assertEqual(result["method"], "all-state one-step")
            self.assertEqual([query["status"] for query in result["queries"]], ["sat", "unsat"])
            self.assertTrue(result["free_nondeterminism"])
            for query in result["queries"]:
                self.assertEqual(len(query["query_sha256"]), 64)
                self.assertTrue((self.out / "property" / query["query"]).is_file())
        self.assertEqual(result["nondet_symbols"], ["z"])
        self.assertEqual(set(inspect.signature(properties.check_property).parameters),
                         {"model", "contract", "out_dir", "solver", "timeout_ms"})

    def test_p1_early_done_is_impossible_but_three_steps_are_feasible(self):
        concrete, _, contract, _ = p1()
        early = {"inputs": [{}], "observations": [{"done": 0}, {"done": 1}]}
        self.assertEqual(self.replay(concrete, contract, early)["status"], "INFEASIBLE")
        ordinary = {"inputs": [{}, {}, {}], "observations": [{"done": d} for d in (0, 0, 0, 1)]}
        self.assertEqual(self.replay(concrete, contract, ordinary)["status"], "FEASIBLE")

    def test_fresh_abstract_choices_can_delay_done(self):
        _, abstract, contract, _ = p1()
        trace = {"inputs": [{}, {}, {}], "observations": [{"done": d} for d in (0, 0, 0, 1)]}
        query = properties._prefix_query(abstract, validate_model(abstract), {}, trace, 5000)
        result = solver.run(query, self.out, "fresh")
        self.assertEqual(result["status"], "sat")
        self.assertIn("(declare-fun t0_1", query)
        self.assertIn("(declare-fun t1_1", query)
        self.assertIn("(declare-fun t2_1", query)
        fixed = query.replace("(check-sat)", "(assert (= t0_1 t1_1))\n(assert (= t1_1 t2_1))\n(check-sat)")
        self.assertEqual(solver.run(fixed, self.out, "fixed")["status"], "unsat")
        self.assertEqual(self.replay(abstract, contract, trace)["status"], "UNSUPPORTED")

    def test_p5_hold_safe_and_coarse_reachable_cex_is_spurious(self):
        concrete, hold, contract, _ = p5("hold")
        for model in (concrete, hold):
            self.assertEqual(self.check(model, contract)["status"], "SAFE")
        _, coarse, _, _ = p5("coarse")
        result = self.check(coarse, contract)
        self.assertEqual(result["status"], "ABSTRACT_CEX")
        self.assertEqual(result["method"], "complete finite reachable closure")
        trace = result["trace"]
        self.assertEqual(len(trace["observations"]), len(trace["inputs"]) + 1)
        self.assertTrue(all(set(inputs) == {"en", "ready"} for inputs in trace["inputs"]))
        self.assertEqual(self.replay(concrete, contract, trace)["status"], "INFEASIBLE")

    def test_p5_bug_has_exact_legal_violation_and_direct_check_agrees(self):
        bug, _, contract, _ = p5("bug")
        gold, _, _, _ = p5("hold")
        trace = {"inputs": [{"en": 1, "ready": 1}, {"en": 1, "ready": 0}],
                 "observations": [{"v": 0, "q": 0}, {"v": 1, "q": 3}, {"v": 1, "q": 2}]}
        self.assertEqual(self.replay(bug, contract, trace)["status"], "FEASIBLE")
        self.assertEqual(self.replay(gold, contract, trace)["status"], "INFEASIBLE")
        result = self.check(bug, contract)
        self.assertEqual(result["status"], "ABSTRACT_CEX")
        self.assertEqual(self.replay(bug, contract, result["trace"])["status"], "FEASIBLE")

    def test_unreachable_violating_edge_requires_complete_closure(self):
        concrete, _, contract, _ = p1()
        concrete["next"]["x"] = bv(0, 2)
        result = self.check(concrete, contract)
        self.assertEqual(result["status"], "SAFE")
        self.assertEqual(result["method"], "complete finite reachable closure")
        self.assertEqual(result["reachable_states"], 1)
        self.assertEqual(result["transitions"], 1)
        self.assertEqual(result["queries"][1]["status"], "sat")

    def test_domain_and_transition_limits_never_claim_safe(self):
        _, coarse, contract, _ = p5("coarse")
        with patch.object(properties, "MAX_DOMAIN", 1):
            self.assertEqual(self.check(coarse, contract)["status"], "UNKNOWN")
        with patch.object(properties, "MAX_TRANSITIONS", 0):
            self.assertEqual(self.check(coarse, contract)["status"], "UNKNOWN")

    def test_empty_initial_domain_is_not_safe(self):
        concrete, _, contract, _ = p1()
        concrete["init"] = {"bool": False}
        result = self.check(concrete, contract)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["reason"], "empty initial set")

    def test_trace_keys_widths_types_and_lengths_are_validated(self):
        concrete, _, contract, _ = p5()
        valid = {"inputs": [{"en": 0, "ready": 0}],
                 "observations": [{"q": 0, "v": 0}, {"q": 0, "v": 0}]}
        mutations = []
        trace = deepcopy(valid); trace["inputs"][0]["z"] = 0; mutations.append(trace)
        trace = deepcopy(valid); del trace["inputs"][0]["ready"]; mutations.append(trace)
        trace = deepcopy(valid); trace["inputs"][0]["en"] = True; mutations.append(trace)
        trace = deepcopy(valid); trace["observations"][0]["q"] = 4; mutations.append(trace)
        trace = deepcopy(valid); trace["observations"].pop(); mutations.append(trace)
        trace = deepcopy(valid); trace["observations"][0]["missing"] = 0; mutations.append(trace)
        trace = deepcopy(valid); trace["certificate"] = {}; mutations.append(trace)
        for trace in mutations:
            with self.subTest(trace=trace):
                self.assertEqual(self.replay(concrete, contract, trace)["status"], "ERROR")
        self.assertEqual(self.replay(concrete, contract, valid)["status"], "FEASIBLE")

    def test_bad_contract_model_or_mealy_observation_is_rejected(self):
        _, abstract, contract, _ = p1()
        invalid = deepcopy(contract); invalid["property"]["step"] = ref("w.z")
        self.assertEqual(self.check(abstract, invalid)["status"], "ERROR")
        invalid = deepcopy(contract); invalid["observations"]["done"] = 2
        self.assertEqual(self.check(abstract, invalid)["status"], "ERROR")
        invalid = deepcopy(abstract); invalid["next"] = {}
        self.assertEqual(self.check(invalid, contract)["status"], "ERROR")
        abstract["observe"]["done"] = ref("z")
        self.assertEqual(self.check(abstract, contract)["status"], "UNSUPPORTED")

    def test_unknown_and_process_failure_are_never_safe_or_feasible(self):
        concrete, _, contract, _ = p1()
        trace = {"inputs": [], "observations": [{"done": 0}]}
        self.assertEqual(self.check(concrete, contract, solver="/no/such/solver")["status"], "ERROR")
        self.assertEqual(self.replay(concrete, contract, trace, solver="/no/such/solver")["status"], "ERROR")
        with patch.object(properties.smt, "run", return_value={"status": "unknown"}):
            self.assertEqual(self.check(concrete, contract)["status"], "UNKNOWN")
            self.assertEqual(self.replay(concrete, contract, trace)["status"], "UNKNOWN")
        with patch.object(properties.smt, "run", side_effect=[{"status": "sat"}, {"status": "unknown"}]):
            self.assertEqual(self.check(concrete, contract)["status"], "UNKNOWN")
        self.assertEqual(self.check(concrete, contract, timeout_ms=0)["status"], "ERROR")

    def test_external_input_ports_need_not_equal_internal_symbol_ids(self):
        concrete, _, contract, _ = p5()
        renamed = {}
        for key, symbol in concrete["symbols"].items():
            renamed["btor_" + key if symbol["kind"] == "input" else key] = symbol
        concrete["symbols"] = renamed

        def rename_refs(expr):
            if expr.get("ref") in {"en", "ready"}:
                expr["ref"] = "btor_" + expr["ref"]
            for arg in expr.get("args", []):
                rename_refs(arg)

        for expr in concrete["next"].values():
            rename_refs(expr)
        self.assertEqual(self.check(concrete, contract)["status"], "SAFE")
        trace = {"inputs": [{"en": 1, "ready": 1}],
                 "observations": [{"v": 0, "q": 0}, {"v": 1, "q": 3}]}
        self.assertEqual(self.replay(concrete, contract, trace)["status"], "FEASIBLE")


if __name__ == "__main__":
    unittest.main()
