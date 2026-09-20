"""Exercise the candidate/trusted boundary without substituting fake LLM results."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('llm_pilot', Path(__file__).parents[1] / 'scripts/llm_pilot.py')
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class PilotBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        (self.bundle / 'concrete.v').write_text('module concrete; endmodule')
        self.trusted = self.root / 'trusted'
        self.trusted.mkdir()
        (self.trusted / 'contract.json').write_text('{}')
        self.run = self.root / 'run'
        config = self.root / '.codex'
        config.mkdir()
        (config / 'config.toml').write_text('model="configured-model"\nmodel_reasoning_effort="high"\n')

    def initialize(self):
        with patch.object(pilot.Path, 'home', return_value=self.root), \
                patch.object(pilot.shutil, 'which', return_value='/usr/bin/codex'), \
                patch.object(pilot.subprocess, 'check_output', return_value='codex-cli test'):
            return pilot.initialize(self.run, self.bundle, [self.trusted], 'certificate')

    def test_bundle_symlink_parent_traversal_and_rules_are_rejected(self):
        (self.bundle / 'leak').symlink_to(self.trusted / 'contract.json')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            self.initialize()
        (self.bundle / 'leak').unlink()
        with self.assertRaisesRegex(ValueError, 'traversal'):
            pilot.plain_path(self.bundle / '..' / 'trusted')
        (self.bundle / 'AGENTS.md').write_text('read gold')
        with self.assertRaisesRegex(ValueError, 'agent rules'):
            self.initialize()

    def test_contract_overwrite_and_deletion_are_detected_before_generation(self):
        self.initialize()
        (self.trusted / 'contract.json').write_text('{"property":false}')
        with self.assertRaisesRegex(ValueError, 'trusted input changed'):
            pilot.load(self.run)
        (self.trusted / 'contract.json').unlink()
        with self.assertRaisesRegex(ValueError, 'empty trusted'):
            pilot.load(self.run)

    def test_candidate_cannot_smuggle_symlink_extra_path_or_change_after_capture(self):
        ledger = self.initialize()
        candidate = self.run / 'attempt-01/candidate'
        candidate.mkdir(parents=True)
        output = candidate / 'certificate.json'
        output.symlink_to(self.trusted / 'contract.json')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            pilot.candidate_hashes(candidate, 'certificate')
        output.unlink()
        output.mkdir()
        (output / 'nested').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'regular files'):
            pilot.candidate_hashes(candidate, 'certificate')
        (output / 'nested').unlink()
        output.rmdir()
        output.write_text('{}')
        (candidate / 'verdict.json').write_text('{"status":"SAFE"}')
        with self.assertRaisesRegex(ValueError, 'unauthorized'):
            pilot.candidate_hashes(candidate, 'certificate')
        (candidate / 'verdict.json').unlink()
        ledger['attempts'] = [{'number': 1, 'status': 'GENERATED',
                               'candidate_sha256': pilot.candidate_hashes(candidate, 'certificate')}]
        pilot.save(self.run, ledger)
        output.write_text('{"edited":true}')
        with self.assertRaisesRegex(ValueError, 'raw candidate changed'):
            pilot.record_verification(self.run, {'status': 'ERROR'}, 1)

    def test_shared_budget_attempt_limit_and_parent_feedback_are_enforced(self):
        ledger = self.initialize()
        ledger['attempts'] = [{'number': 1, 'status': 'GENERATED'}]
        pilot.save(self.run, ledger)
        with self.assertRaisesRegex(ValueError, 'record the previous verification'):
            pilot.generate(self.run, 'unused')
        ledger['attempts'] = [{'verification': {}}] * 4
        pilot.save(self.run, ledger)
        with self.assertRaisesRegex(ValueError, 'four-attempt'):
            pilot.generate(self.run, 'unused')
        ledger['attempts'] = []
        ledger['charged_seconds'] = 900
        pilot.save(self.run, ledger)
        with self.assertRaisesRegex(ValueError, '900-second'):
            pilot.generate(self.run, 'unused')
        for seconds in (-1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                pilot.record_verification(self.run, {}, seconds)

    @unittest.skipUnless(shutil.which('codex') and Path('/usr/bin/python3').exists(), 'live Codex sandbox unavailable')
    def test_live_os_boundary_blocks_gold_contract_write_and_network(self):
        ledger = self.initialize()
        ledger['codex'] = shutil.which('codex')
        runtime = Path(ledger['codex']).resolve()
        ledger['runtime'] = str(runtime.parent.parent if runtime.suffix == '.js' else runtime)
        candidate = self.run / 'candidate'
        candidate.mkdir()
        (candidate / 'certificate.json').write_text('')
        pilot.probe(self.run, ledger, candidate)
        self.assertEqual(ledger['isolation'], 'LOCAL_COMMAND_READ_WRITE_NETWORK_PROBE_PASSED')
        self.assertEqual((self.run / 'boundary-gold.txt').read_text(), 'do not expose')
        self.assertFalse((self.run / 'parent-verdict.json').exists())


if __name__ == '__main__':
    unittest.main()
