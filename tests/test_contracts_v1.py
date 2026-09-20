"""Frozen public-task contracts and the narrow synchronous reset profile."""

from copy import deepcopy
from hashlib import sha256
from itertools import product
from pathlib import Path
import tempfile
import unittest

from rtl_relate.checker import check, validate_contract
from rtl_relate.fixtures import p1
from rtl_relate.ir import Invalid, Unsupported, bv, digest, evaluate, load_json, op, ref


ROOT = Path(__file__).resolve().parents[1]


class ContractV1Tests(unittest.TestCase):
    def contract(self, name):
        return load_json(ROOT / "fixtures/contracts" / (name + ".json"))

    def test_all_frozen_contracts_and_source_hashes(self):
        manifest = load_json(ROOT / "fixtures/public/sources.json")
        self.assertEqual({task["id"] for task in manifest["tasks"]},
                         {"R1-fsm", "R2-skid8", "R3-skid32", "R4-pipe32"})
        for task in manifest["tasks"]:
            contract = load_json(ROOT / task["contract"]["path"])
            validate_contract(contract)
            self.assertEqual(digest(contract), task["contract"]["sha256"])
        for source in manifest["sources"]:
            for file in source["files"]:
                self.assertEqual(sha256((ROOT / file["path"]).read_bytes()).hexdigest(), file["sha256"])

    def test_v0_files_retain_their_original_bytes(self):
        expected = {"p1": "b10dffa37ea867d26a7cbc5e25d642588c7baf81414ac3bff4cf0a29941a6c33",
                    "p5": "c031dc87a1edbf9700152d978d68ab609efa46f79a94e12a3c7e91834507e129"}
        for name, value in expected.items():
            path = ROOT / "fixtures/contracts" / (name + ".json")
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), value)
            validate_contract(load_json(path))

    def test_invalid_reset_profiles_fail_closed(self):
        original = self.contract("r2_skid8")
        variants = [None, True, {}, {**original["reset"], "extra": True}]
        for key, values in {"kind": ("asynchronous", None), "port": ("missing", "i_data", "i_clk", [], ""),
                            "active": (0, True, "1"), "assumption": ("initially_asserted", True)}.items():
            variants.extend({**original["reset"], key: value} for value in values)
        for reset in variants:
            with self.subTest(reset=reset):
                contract = deepcopy(original)
                # A missing reset declaration is supported in v1, but not a malformed object.
                if reset is None:
                    contract["semantics"] = "single-clock-bv-v0"
                else:
                    contract["reset"] = reset
                with self.assertRaises((Invalid, Unsupported)):
                    validate_contract(contract)
        for typ in (True, "bool", 2):
            with self.subTest(reset_type=typ):
                contract = deepcopy(original)
                contract["inputs"]["i_reset"] = typ
                with self.assertRaises((Invalid, Unsupported)):
                    validate_contract(contract)

    def test_contract_sampling_and_environment_remain_fixed(self):
        for key, value in (("environment", {"bool": True}), ("environment", False),
                           ("sampling", "after_update"), ("version", True)):
            with self.subTest(key=key, value=value):
                contract = self.contract("r4_pipe32")
                contract[key] = value
                with self.assertRaises(Unsupported):
                    validate_contract(contract)

    def test_fsm_property_rejects_zero_and_multiple_observations(self):
        contract = self.contract("r1_fsm")
        types = validate_contract(contract)
        for values in product((0, 1), repeat=3):
            env = dict(zip(("o.idle", "o.busy", "o.done"), values))
            self.assertEqual(evaluate(contract["property"]["step"], env, types), sum(values) == 1)

    def test_skid_stall_guard_uses_current_reset_only(self):
        for name in ("r2_skid8", "r3_skid32"):
            contract = self.contract(name)
            types = validate_contract(contract)
            env = {"o.o_valid": 1, "u.i_ready": 0, "u.i_reset": 0,
                   "n.o_valid": 1, "o.o_data": 7, "n.o_data": 8}
            self.assertFalse(evaluate(contract["property"]["step"], env, types))
            env["u.i_reset"] = 1
            self.assertTrue(evaluate(contract["property"]["step"], env, types))
            env.update({"u.i_reset": 0, "n.o_data": 7})
            self.assertTrue(evaluate(contract["property"]["step"], env, types))

    def test_pipeline_property_uses_bv32_current_history_and_overflow(self):
        contract = self.contract("r4_pipe32")
        types = validate_contract(contract)
        env = {"o.dataOut": 1, "o.tmp_stageOne": (1 << 32) - 1, "o.tmp_stageTwo": 2}
        self.assertTrue(evaluate(contract["property"]["step"], env, types))
        env["o.dataOut"] = 2
        self.assertFalse(evaluate(contract["property"]["step"], env, types))
        env["o.dataOut"] = 0
        self.assertTrue(evaluate(contract["property"]["step"], env, types))

    def test_gate_quantifies_reset_as_an_unconstrained_input(self):
        concrete, abstract, contract, cert = p1()
        contract.update(semantics="single-clock-bv-v1", inputs={"rst": 1},
                        reset={"kind": "synchronous", "port": "rst", "active": 1,
                               "assumption": "unconstrained"})
        for model, state in ((concrete, "x"), (abstract, "d")):
            model["symbols"]["rst"] = {"kind": "input", "type": 1, "signed": False, "origin": "rst"}
            model["next"][state] = op("ite", op("eq", ref("rst"), bv(1, 1)),
                                      bv(0, model["symbols"][state]["type"]), model["next"][state])
        for name, model in (("concrete", concrete), ("abstract", abstract), ("contract", contract)):
            cert[name + "_sha256"] = digest(model)
        with tempfile.TemporaryDirectory() as directory:
            result = check(concrete, abstract, contract, cert, Path(directory) / "good")
            self.assertEqual(result["status"], "ACCEPTED", result)
            abstract["next"]["d"] = abstract["next"]["d"]["args"][2]
            cert["abstract_sha256"] = digest(abstract)
            result = check(concrete, abstract, contract, cert, Path(directory) / "missing-reset")
            self.assertEqual(result["status"], "CERTIFICATE_REJECTED", result)
            self.assertEqual(result["obligations"]["STEP_MAP"]["status"], "sat")


if __name__ == "__main__":
    unittest.main()
