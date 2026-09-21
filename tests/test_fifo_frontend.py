"""Finite FIFO init evidence must reject hidden constraints on memory aliases."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.assess_fifo import assessment, audit_netlist


class FifoAuditTests(unittest.TestCase):
    def test_free_memory_and_control_init_are_checked_by_physical_bit(self):
        nets = {f'mem[{i}]': {'bits': list(range(10 + i * 8, 18 + i * 8))}
                for i in range(4)}
        for name, bits, init in [('wr_addr', [42, 43, 44], '000'),
                                 ('rd_addr', [45, 46, 47], '000'),
                                 ('o_fill', [48, 49, 50], '000'),
                                 ('o_empty', [51], '1')]:
            nets[name] = {'bits': bits, 'attributes': {'init': init}}
        module = {'ports': {'i_clk': {'bits': [2]}}, 'netnames': nets,
                  'cells': {'state': {'type': '$dff', 'parameters': {'CLK_POLARITY': '1'},
                                     'connections': {'CLK': [2], 'Q': list(range(10, 52))}}}}
        self.assertEqual(audit_netlist(module)['unconstrained_initial_memory_bits'], 32)
        altered = deepcopy(module)
        altered['netnames']['hidden_alias'] = {'bits': [10], 'attributes': {'init': '0'}}
        with self.assertRaisesRegex(ValueError, 'memory initial bits were constrained'):
            audit_netlist(altered)
        altered = deepcopy(module)
        altered['netnames']['o_empty']['attributes']['init'] = '0'
        with self.assertRaisesRegex(ValueError, 'wrong control initialization'):
            audit_netlist(altered)
        altered = deepcopy(module)
        altered['cells']['state']['connections']['CLK'] = [3]
        with self.assertRaisesRegex(ValueError, 'shared positive clock'):
            audit_netlist(altered)

    def test_version_failure_cannot_be_hidden_by_a_later_timeout(self):
        def run(argv, directory, name):
            (directory / f'{name}.stdout.log').write_text('')
            return {'status': 'ERROR' if name == 'version' else 'UNKNOWN'}

        with tempfile.TemporaryDirectory() as temporary, \
                patch('scripts.assess_fifo.command', side_effect=run), \
                patch('scripts.assess_fifo.export_rtl', side_effect=OSError('unavailable')):
            result = assessment(Path(temporary) / 'run', '/missing/yosys')
        self.assertEqual(result['stages']['expand']['status'], 'UNKNOWN')
        self.assertEqual(result['status'], 'ERROR')
