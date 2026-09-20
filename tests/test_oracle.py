"""Exhaustive integer oracles independent of the SMT emitter and checker."""

import itertools
import unittest

from rtl_relate.fixtures import p1, p5
from rtl_relate.ir import evaluate


def _step(model, values):
    types = {name: symbol["type"] for name, symbol in model["symbols"].items()}
    return {name: evaluate(expr, values, types) for name, expr in model["next"].items()}


def producer_step(x, q, v, en, ready, *, bug=False):
    load = not v or ready
    return {"x": (x + 1) % 4, "q": x ^ 3 if en and (bug or load) else q, "v": en if load else v}


class ExhaustiveOracleTests(unittest.TestCase):
    def test_p1_all_four_states_match_integer_oracle(self):
        concrete, abstract, _, certificate = p1()
        for x in range(4):
            with self.subTest(x=x):
                expected = min(x + 1, 3)
                self.assertEqual(_step(concrete, {"x": x}), {"x": expected})
                values = {"c.x": x}
                d = evaluate(certificate["h"]["d"], values, {"c.x": 2})
                z = evaluate(certificate["w"]["z"], values, {"c.x": 2})
                self.assertEqual(d, int(x == 3))
                self.assertEqual(z, int(x == 2))
                self.assertEqual(_step(abstract, {"d": d, "z": z}), {"d": int(expected == 3)})

    def test_p1_free_choice_preserves_done_but_can_finish_early(self):
        _, abstract, _, _ = p1()
        for d, z in itertools.product(range(2), repeat=2):
            next_d = _step(abstract, {"d": d, "z": z})["d"]
            self.assertTrue(not d or next_d)
        self.assertEqual(_step(abstract, {"d": 0, "z": 1})["d"], 1)
        self.assertNotEqual(int(min(0 + 1, 3) == 3), 1)

    def test_p1_nondeterminism_is_fresh_each_step(self):
        _, abstract, _, _ = p1()

        def trace(choices):
            result = [0]
            for z in choices:
                result.append(_step(abstract, {"d": result[-1], "z": z})["d"])
            return result

        self.assertEqual(trace([0, 0, 1]), [0, 0, 0, 1])
        self.assertNotIn([0, 0, 0, 1], [trace([z] * 3) for z in range(2)])

    def test_p5_all_128_state_input_combinations_match_integer_oracle(self):
        combinations = list(itertools.product(range(4), range(4), range(2), range(2), range(2)))
        self.assertEqual(len(combinations), 128)
        for kind in ("hold", "coarse", "bug"):
            concrete, abstract, _, certificate = p5(kind)
            for x, q, v, en, ready in combinations:
                with self.subTest(kind=kind, x=x, q=q, v=v, en=en, ready=ready):
                    expected = producer_step(x, q, v, en, ready, bug=kind == "bug")
                    self.assertEqual(_step(concrete, dict(x=x, q=q, v=v, en=en, ready=ready)), expected)
                    witness_values = {"c.x": x, "c.q": q, "c.v": v, "u.en": en, "u.ready": ready}
                    witness_types = {"c.x": 2, "c.q": 2, "c.v": 1, "u.en": 1, "u.ready": 1}
                    z = evaluate(certificate["w"]["z"], witness_values, witness_types)
                    actual = _step(abstract, dict(q=q, v=v, en=en, ready=ready, z=z))
                    self.assertEqual(actual, {"q": expected["q"], "v": expected["v"]})
                    for state in ("v", "q"):
                        self.assertEqual(evaluate(certificate["h"][state], witness_values, witness_types), {"v": v, "q": q}[state])

    def test_p5_hold_property_for_every_free_choice(self):
        _, abstract, _, _ = p5("hold")
        for q, v, en, ready, z in itertools.product(range(4), range(2), range(2), range(2), range(4)):
            next_state = _step(abstract, dict(q=q, v=v, en=en, ready=ready, z=z))
            if v and not ready:
                self.assertEqual(next_state, {"v": 1, "q": q})

    def test_p5_coarse_has_spurious_hold_violation(self):
        _, abstract, _, _ = p5("coarse")
        state = {"v": 0, "q": 0}
        state = _step(abstract, dict(state, en=1, ready=1, z=3))
        self.assertEqual(state, {"v": 1, "q": 3})
        changed = _step(abstract, dict(state, en=1, ready=0, z=2))
        self.assertNotEqual(changed["q"], state["q"])
        concrete_first = producer_step(0, 0, 0, 1, 1)
        concrete_second = producer_step(**concrete_first, en=1, ready=0)
        self.assertEqual(concrete_second["q"], 3)
        self.assertNotEqual(concrete_second["q"], changed["q"])

    def test_p5_bug_has_legal_two_step_counterexample(self):
        concrete, _, _, _ = p5("bug")
        first = _step(concrete, dict(x=0, q=0, v=0, en=1, ready=1))
        second = _step(concrete, dict(first, en=1, ready=0))
        self.assertEqual(first, {"x": 1, "q": 3, "v": 1})
        self.assertEqual(second, {"x": 2, "q": 2, "v": 1})
        self.assertNotEqual(first["q"], second["q"])

    def test_p5_hold_adds_behavior(self):
        _, abstract, _, _ = p5("hold")
        self.assertEqual(_step(abstract, dict(v=0, q=0, en=1, ready=1, z=0))["q"], 0)
        self.assertEqual(producer_step(0, 0, 0, 1, 1)["q"], 3)


if __name__ == "__main__":
    unittest.main()
