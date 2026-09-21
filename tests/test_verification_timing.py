"""Timing summaries must preserve failed attempts and exclude recorded warmups."""
import unittest
from scripts.measure_verification import REPEATS, summarize


class TimingSummaryTests(unittest.TestCase):
    def rows(self):
        return [dict(task='R1-fsm', warmup=False, status='PASS', concrete_property=2,
                     abstract_property=1, concrete_solver_processes=1,
                     abstract_solver_processes=0.5, frontend=2, certificate=1,
                     validation_path=4) for _ in range(REPEATS)]

    def test_component_gain_does_not_hide_total_cost_or_include_warmup(self):
        rows = self.rows()
        rows.append(dict(task='R1-fsm', warmup=True, status='ERROR'))
        result = summarize(rows)['R1-fsm']
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['comparisons']['property']['paired_speedup_C_over_A']['median'], 2)
        self.assertEqual(result['comparisons']['known_candidate_validation']['paired_speedup_C_over_A']['median'], 0.5)
        self.assertEqual(result['comparisons']['property']['alternative_faster_pairs'], REPEATS)

    def test_failed_or_missing_measurement_cannot_form_success_only_median(self):
        rows = self.rows()
        rows[-1] = dict(task='R1-fsm', warmup=False, status='ERROR')
        for selected in (rows, rows[:-1]):
            result = summarize(selected)['R1-fsm']
            self.assertEqual(result['status'], 'INCOMPLETE')
            self.assertNotIn('comparisons', result)
