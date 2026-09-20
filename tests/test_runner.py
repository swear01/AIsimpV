"""Do not lose failed-search costs or promote feasible nonviolations to bugs."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rtl_relate import __main__ as runner
from rtl_relate.fixtures import p5


class RunnerTests(unittest.TestCase):
    def test_every_fallback_result_is_charged(self):
        trace = {"inputs": [{"en": 0, "ready": 0}],
                 "observations": [{"q": 0, "v": 0}, {"q": 0, "v": 0}]}
        for status in ("SAFE", "UNKNOWN", "ERROR"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as out, \
                    patch.object(runner, "check", return_value={"status": "ACCEPTED", "seconds": 1}), \
                    patch.object(runner, "check_property", side_effect=[
                        {"status": "ABSTRACT_CEX", "seconds": 2, "trace": trace},
                        {"status": status, "seconds": 7}]), \
                    patch.object(runner, "replay", return_value={"status": "INFEASIBLE", "seconds": 3}):
                row = runner.experiment("manual", "p5_coarse", lambda: p5("coarse"), Path(out))
                self.assertEqual(row["concrete_search_seconds"], 7)
                self.assertEqual(row["total_machine_seconds"], 13)
                self.assertEqual(row["status"], "SPURIOUS_TRACE")

    def test_rejected_gate_retains_elapsed_cost(self):
        with tempfile.TemporaryDirectory() as out, patch.object(runner, "check", return_value={"status": "UNKNOWN", "seconds": 4}):
            row = runner.experiment("manual", "p5_hold", p5, Path(out))
            self.assertEqual(row["total_machine_seconds"], 4)
            self.assertIn("wall_seconds", row)

    def test_feasible_nonviolation_is_never_a_bug(self):
        trace = {"inputs": [{"en": 0, "ready": 0}],
                 "observations": [{"q": 0, "v": 0}, {"q": 0, "v": 0}]}
        with tempfile.TemporaryDirectory() as out, \
                patch.object(runner, "check", return_value={"status": "ACCEPTED", "seconds": 1}), \
                patch.object(runner, "check_property", side_effect=[
                    {"status": "ABSTRACT_CEX", "seconds": 2, "trace": trace},
                    {"status": "SAFE", "seconds": 7}]), \
                patch.object(runner, "replay", return_value={"status": "FEASIBLE", "seconds": 3}):
            row = runner.experiment("manual", "p5_coarse", lambda: p5("coarse"), Path(out))
            self.assertEqual(row["status"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
