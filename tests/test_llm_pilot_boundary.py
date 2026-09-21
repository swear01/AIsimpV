"""Exercise the candidate/trusted boundary without substituting fake LLM results."""
import errno
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
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

    def test_failed_atomic_save_preserves_previous_json(self):
        ledger = self.initialize()
        previous = (self.run / 'ledger.json').read_bytes()
        ledger['charged_seconds'] = 123
        with patch.object(pilot.os, 'replace', side_effect=OSError('replace failed')):
            with self.assertRaisesRegex(OSError, 'replace failed'):
                pilot.save(self.run, ledger)
        self.assertEqual((self.run / 'ledger.json').read_bytes(), previous)
        self.assertEqual(pilot.load(self.run)[1]['charged_seconds'], 0)
        self.assertEqual(list(self.run.glob('.ledger-*')), [])

    def test_timeout_keeps_its_status_when_the_process_group_has_exited(self):
        ledger = self.initialize()
        ledger['isolation'] = 'LOCAL_COMMAND_READ_WRITE_NETWORK_PROBE_PASSED'
        pilot.save(self.run, ledger)
        with patch.object(pilot.subprocess, 'Popen') as launch, \
                patch.object(pilot.os, 'killpg', side_effect=ProcessLookupError) as kill:
            process = launch.return_value
            process.communicate.side_effect = [pilot.subprocess.TimeoutExpired('codex', 900), None]
            record = pilot.generate(self.run, 'unused')
        kill.assert_called_once_with(process.pid, pilot.signal.SIGKILL)
        self.assertEqual(process.communicate.call_count, 2)
        self.assertEqual(record['status'], 'TIMEOUT')
        pilot.record_verification(self.run, {'status': 'TIMEOUT'}, 0)
        ledger = pilot.load(self.run)[1]
        self.assertEqual(ledger['attempts'][0]['verification']['status'], 'TIMEOUT')
        self.assertEqual(ledger['charged_seconds'], record['generation_seconds'])

    def test_preflight_failure_reserves_and_charges_attempt_without_model_call(self):
        self.initialize()
        with patch.object(pilot, 'probe', side_effect=pilot.subprocess.TimeoutExpired('probe', 20)), \
                patch.object(pilot.time, 'monotonic', side_effect=[100, 102]), \
                patch.object(pilot.subprocess, 'Popen') as launch:
            record = pilot.generate(self.run, 'unused')
        launch.assert_not_called()
        self.assertEqual(record['status'], 'ISOLATION_OR_RUNNER_ERROR')
        self.assertIn('timed out', record['error'])
        ledger = pilot.load(self.run)[1]
        self.assertEqual(ledger['attempts'], [record])
        self.assertEqual(record['generation_seconds'], 2)
        self.assertEqual(ledger['charged_seconds'], 2)
        with self.assertRaisesRegex(ValueError, 'record the previous verification'):
            pilot.generate(self.run, 'unused')

    def test_existing_candidate_is_preserved_and_failed_setup_is_recorded(self):
        self.initialize()
        candidate = self.run / 'attempt-01/candidate'
        candidate.mkdir(parents=True)
        output = candidate / 'certificate.json'
        output.write_text('preserved raw evidence')
        with patch.object(pilot.time, 'monotonic', side_effect=[100, 103]), \
                patch.object(pilot.subprocess, 'Popen') as launch:
            record = pilot.generate(self.run, 'unused')
        launch.assert_not_called()
        self.assertEqual(output.read_text(), 'preserved raw evidence')
        self.assertEqual(record['status'], 'ISOLATION_OR_RUNNER_ERROR')
        ledger = pilot.load(self.run)[1]
        self.assertEqual(ledger['attempts'], [record])
        self.assertEqual(ledger['charged_seconds'], 3)

    def test_fdopen_failure_closes_raw_descriptor(self):
        candidate = self.root / 'candidate'
        candidate.mkdir()
        output = candidate / 'certificate.json'
        output.write_text('preserved')
        with patch.object(pilot.os, 'fdopen', side_effect=OSError('fdopen failed')) as wrap:
            with self.assertRaisesRegex(OSError, 'fdopen failed'):
                pilot.materialize_response('{"certificate_json":"replacement"}', candidate, 'certificate')
        with self.assertRaises(OSError):
            pilot.os.fstat(wrap.call_args.args[0])
        self.assertEqual(output.read_text(), 'preserved')

    def prepare_driver(self):
        scripts = str(Path(__file__).parents[1] / 'scripts')
        sys.path.insert(0, scripts)
        self.addCleanup(lambda: sys.path.remove(scripts))
        import run_llm_experiments as experiments
        self.run = self.root / 'run-certificate'
        target = self.root / 'bundle-certificate'
        self.bundle.rename(target)
        self.bundle = target
        snapshot = self.root / 'snapshot'
        snapshot.mkdir()
        (snapshot / 'marker').write_text('frozen test snapshot')
        prompt = self.root / 'prompt-certificate.txt'
        prompt.write_text('unused')
        audit = {'status': 'APPROVED_BY_ROOT', 'snapshot_sha256': pilot.file_hashes(snapshot),
                 'bundles': {'certificate': pilot.file_hashes(self.bundle)},
                 'prompts': {'certificate': hashlib.sha256(prompt.read_bytes()).hexdigest()}}
        (self.root / 'audit.json').write_text(json.dumps(audit))
        return experiments, snapshot

    def test_resume_refuses_incomplete_attempt_before_mutating_ledger(self):
        experiments, snapshot = self.prepare_driver()
        ledger = self.initialize()
        ledger['attempts'] = [{'number': 1, 'status': 'RUNNING'}]
        pilot.save(self.run, ledger)
        previous = (self.run / 'ledger.json').read_bytes()
        with patch.object(experiments, '__file__', str(snapshot / 'scripts/run_llm_experiments.py')), \
                patch.object(experiments, 'generate') as generate:
            with self.assertRaisesRegex(ValueError, 'incomplete previous attempt'):
                experiments.run(self.root, 'certificate')
        generate.assert_not_called()
        self.assertEqual((self.run / 'ledger.json').read_bytes(), previous)

    def test_driver_records_preflight_failure_and_resumes_without_retry(self):
        experiments, snapshot = self.prepare_driver()
        mkdir = Path.mkdir

        def fail_candidate(path, *args, **kwargs):
            if path.name == 'candidate':
                raise OSError('candidate setup failed')
            return mkdir(path, *args, **kwargs)

        with patch.object(experiments, '__file__', str(snapshot / 'scripts/run_llm_experiments.py')), \
                patch.object(Path, 'home', return_value=self.root), \
                patch.object(pilot.shutil, 'which', return_value='/usr/bin/codex'), \
                patch.object(pilot.subprocess, 'check_output', return_value='codex-cli test'), \
                patch.object(pilot.subprocess, 'Popen') as launch, \
                patch.object(Path, 'mkdir', autospec=True, side_effect=fail_candidate), \
                patch.object(pilot.time, 'monotonic', side_effect=[100, 102, 103, 104]):
            ledger = experiments.run(self.root, 'certificate')
            previous = (self.run / 'ledger.json').read_bytes()
            resumed = experiments.run(self.root, 'certificate')
        launch.assert_not_called()
        self.assertEqual(len(ledger['attempts']), 1)
        record = ledger['attempts'][0]
        self.assertEqual(record['status'], 'ISOLATION_OR_RUNNER_ERROR')
        self.assertEqual(record['error'], 'candidate setup failed')
        self.assertEqual(record['verification'], {'status': 'ISOLATION_OR_RUNNER_ERROR',
                                                  'reason': 'candidate setup failed'})
        self.assertEqual(ledger['charged_seconds'], 3)
        self.assertEqual(record['generation_seconds'], 2)
        self.assertEqual(record['verification_seconds'], 1)
        self.assertFalse((self.run / 'attempt-01/candidate').exists())
        self.assertEqual(ledger, resumed)
        self.assertEqual((self.run / 'ledger.json').read_bytes(), previous)

    def test_missing_candidate_hash_cannot_be_recorded_as_formal_success(self):
        ledger = self.initialize()
        ledger['attempts'] = [{'number': 1, 'status': 'ISOLATION_OR_RUNNER_ERROR'}]
        pilot.save(self.run, ledger)
        with self.assertRaisesRegex(ValueError, 'infrastructure error feedback'):
            pilot.record_verification(self.run, {'status': 'SUCCESS'}, 0)
        candidate = self.run / 'attempt-01/candidate'
        candidate.mkdir(parents=True)
        (candidate / 'certificate.json').write_text('{}')
        ledger['attempts'][0]['status'] = 'GENERATED'
        pilot.save(self.run, ledger)
        with self.assertRaisesRegex(ValueError, 'raw candidate changed'):
            pilot.record_verification(self.run, {'status': 'SUCCESS'}, 0)

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

    def test_inline_transport_is_verbatim_and_rejects_path_link_attacks(self):
        candidate = self.root / 'candidate'
        candidate.mkdir()
        output = candidate / 'certificate.json'
        output.write_text('')
        raw = '{"h":{},"J":{"bool":true}}\n'
        pilot.materialize_response(json.dumps({'certificate_json': raw}), candidate, 'certificate')
        self.assertEqual(output.read_bytes(), raw.encode())
        with self.assertRaises(ValueError):
            pilot.materialize_response(json.dumps({'../contract.json': raw}), candidate, 'certificate')
        output.unlink()
        output.symlink_to(self.trusted / 'contract.json')
        with self.assertRaises(ValueError):
            pilot.materialize_response(json.dumps({'certificate_json': raw}), candidate, 'certificate')
        output.unlink()
        import os
        os.link(self.trusted / 'contract.json', output)
        with self.assertRaisesRegex(ValueError, 'private regular'):
            pilot.materialize_response(json.dumps({'certificate_json': raw}), candidate, 'certificate')
        self.assertEqual((self.trusted / 'contract.json').read_text(), '{}')

    def test_generated_rtl_cannot_read_external_files_through_yosys(self):
        scripts = str(Path(__file__).parents[1] / 'scripts')
        sys.path.insert(0, scripts)
        self.addCleanup(lambda: sys.path.remove(scripts))
        from run_llm_experiments import validate_candidate_rtl
        source = self.root / 'abstract.v'
        for text in ('`include "outside.v"', '$readmemh("secret", mem);', 'x' * 65537):
            source.write_text(text)
            with self.assertRaises(ValueError):
                validate_candidate_rtl(source)
        source.write_text('module abstract_design; endmodule')
        validate_candidate_rtl(source)

    def test_network_probe_accepts_only_explicit_permission_denials(self):
        for code in (errno.EPERM, errno.EACCES):
            with self.subTest(errno=code), patch('socket.socket') as socket:
                socket.return_value.connect.side_effect = PermissionError(code, 'denied')
                exec(pilot.NETWORK_PROBE, {})
                socket.return_value.connect.assert_called_once_with(('1.1.1.1', 443))
        for error in (TimeoutError(errno.ETIMEDOUT, 'timeout'),
                      ConnectionRefusedError(errno.ECONNREFUSED, 'refused'),
                      OSError(errno.ENETUNREACH, 'offline'),
                      PermissionError(errno.EINVAL, 'unexpected errno')):
            with self.subTest(error=error), patch('socket.socket') as socket:
                socket.return_value.connect.side_effect = error
                with self.assertRaises(type(error)):
                    exec(pilot.NETWORK_PROBE, {})
        with patch('socket.socket'):
            with self.assertRaisesRegex(SystemExit, 'network boundary failed'):
                exec(pilot.NETWORK_PROBE, {})

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
