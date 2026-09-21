#!/usr/bin/env python3
"""Assess one pinned finite FIFO without changing the production frontend."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rtl_relate.frontend import Unsupported, _check_netlist, export_rtl, parse_btor2
from rtl_relate.formal import _run

SOURCE_SHA256 = '76a653781f1ecca1c1da92c4e5105ecd5d0f832b13cbfd31300ec88d9947e0c1'
REVISION = '2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b'
PARAMETERS = dict(BW=8, LGFLEN=2, OPT_ASYNC_READ=1,
                  OPT_WRITE_ON_FULL=0, OPT_READ_ON_EMPTY=0)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def command(argv, directory, name):
    started = time.monotonic()
    try:
        row, _ = _run(argv, directory, name, started + 60)
        row['status'] = 'UNKNOWN' if row['timeout'] else 'OK' if row['returncode'] == 0 else 'ERROR'
    except UnicodeDecodeError as error:
        row = {'command': argv, 'status': 'ERROR', 'reason': str(error),
               'seconds': time.monotonic() - started}
    row['cwd'] = str(directory)
    save(directory / f'{name}.json', row)
    return row


def audit_netlist(module):
    """Check physical init aliases, not just the preferred memory word names."""
    nets = module['netnames']
    memory = {f'mem[{index}]': nets[f'mem[{index}]']['bits'] for index in range(4)}
    bits = [bit for word in memory.values() for bit in word]
    if any(len(word) != 8 for word in memory.values()) or len(set(bits)) != 32:
        raise ValueError('expected four distinct 8-bit memory words')
    initial = {}
    for name, net in nets.items():
        value = net.get('attributes', {}).get('init')
        if value is None:
            continue
        if len(value) != len(net['bits']) or set(value) - set('01x'):
            raise ValueError(f'invalid init attribute on {name}')
        for bit, digit in zip(net['bits'], reversed(value)):
            if digit in '01':
                if bit in initial and initial[bit] != digit:
                    raise ValueError('conflicting initial values')
                initial[bit] = digit
    if any(bit in initial for bit in bits):
        raise ValueError('memory initial bits were constrained')
    controls = {'wr_addr': '000', 'rd_addr': '000', 'o_fill': '000', 'o_empty': '1'}
    for name, expected in controls.items():
        actual = ''.join(initial.get(bit, 'x') for bit in reversed(nets[name]['bits']))
        if actual != expected:
            raise ValueError(f'wrong control initialization: {name}={actual}')
    clock = module['ports']['i_clk']['bits']
    state = []
    for cell in module['cells'].values():
        if cell['type'].startswith('$mem'):
            raise ValueError('memory cell survived expansion')
        if cell['type'] == '$dff':
            if cell['connections']['CLK'] != clock or int(cell['parameters']['CLK_POLARITY'], 2) != 1:
                raise ValueError('state is not on the shared positive clock')
            state.extend(cell['connections']['Q'])
    expected_bits = set(bits) | {bit for name in controls for bit in nets[name]['bits']}
    if len(state) != 42 or set(state) != expected_bits or set(initial) != expected_bits - set(bits):
        raise ValueError('unexpected state or initialization coverage')
    return {'state_bits': 42, 'memory_bits': 32, 'unconstrained_initial_memory_bits': 32,
            'defined_control_initial_bits': 10, 'control_init': controls,
            'clock': {'name': 'i_clk', 'edge': 'positive'}, 'memory_words': memory}


def audit_btor(text):
    lines = [line.split(';', 1)[0].split() for line in text.splitlines()]
    lines = [line for line in lines if line]
    sorts = {line[0]: int(line[3]) for line in lines if line[1:3] == ['sort', 'bitvec']}
    initialized = {line[3] for line in lines if line[1] == 'init'}
    aliases = {line[2]: line[3] for line in lines if line[1] == 'output' and len(line) == 4}
    states = {line[0]: {'width': sorts[line[2]],
                       'name': line[3] if len(line) > 3 else aliases.get(line[0]),
                       'has_init': line[0] in initialized}
              for line in lines if line[1] == 'state'}
    memory = [row for row in states.values() if row['name'] in {f'mem[{i}]' for i in range(4)}]
    if len(memory) != 4 or any(row['width'] != 8 or row['has_init'] for row in memory):
        raise ValueError('BTOR memory names/widths/init do not match the four free words')
    if sum(row['width'] for row in states.values()) != 42:
        raise ValueError('BTOR state width mismatch')
    if sum(row['width'] for row in states.values() if row['has_init']) != 10:
        raise ValueError('BTOR initialized state width mismatch')
    return {'states': states, 'unconstrained_initial_memory_bits': 32,
            'defined_initial_state_bits': 10}


def assessment(out, yosys):
    started = time.monotonic()
    out.mkdir(parents=True, exist_ok=False)
    fixture = ROOT / 'fixtures/public/sfifo'
    source = fixture / 'sfifo.v'
    result = {'task_id': 'F1-sfifo4x8-assessment', 'run_id': out.name,
              'candidate_id': 'finite-memory-map-only', 'core_matrix_member': False,
              'source_revision': REVISION, 'parameters': PARAMETERS,
              'contract_sha256': None, 'contract_note': 'Assessment only; no property contract created.',
              'status': 'ERROR', 'equivalence': 'NOT_RUN', 'certificate': 'NOT_RUN',
              'property': 'NOT_RUN', 'stages': {}}
    stages = result['stages']
    try:
        shutil.copyfile(__file__, out / 'assessment-driver.py')
        result.update(source_sha256=sha(source), script_sha256=sha(Path(__file__)),
                      provenance_sha256=sha(fixture / 'provenance.json'))
        provenance = json.loads((fixture / 'provenance.json').read_text())
        if (result['source_sha256'] != SOURCE_SHA256 or provenance['source_sha256'] != SOURCE_SHA256
                or provenance['revision'] != REVISION or provenance['parameters'] != PARAMETERS):
            raise ValueError('pinned source, provenance, or parameters changed')
        shutil.copyfile(fixture / 'provenance.json', out / 'provenance.json')
        stages['version'] = command([yosys, '-V'], out, 'version')
        result['yosys_version'] = (out / 'version.stdout.log').read_text(errors='replace').strip()
        result['yosys_executable_sha256'] = sha(Path(yosys)) if Path(yosys).is_file() else None
        before = time.monotonic()
        try:
            export_rtl(source, 'sfifo', out / 'original', clock='i_clk',
                       parameters=PARAMETERS, executable=yosys)
            stages['original_frontend'] = {'status': 'EXPORTED'}
        except Unsupported as error:
            stages['original_frontend'] = {'status': 'UNSUPPORTED', 'reason': str(error)}
        except (ValueError, OSError) as error:
            stages['original_frontend'] = {'status': 'ERROR', 'reason': str(error)}
        stages['original_frontend']['seconds'] = time.monotonic() - before
        original = out / 'original/frontend.json'
        if stages['original_frontend']['status'] == 'UNSUPPORTED':
            metadata = json.loads(original.read_text()) if original.exists() else {}
            if metadata.get('error') == 'Yosys timeout':
                stages['original_frontend']['status'] = 'UNKNOWN'
            elif metadata.get('returncode') != 0:
                stages['original_frontend']['status'] = 'ERROR'
        # Independent invocation: original write_btor failure cannot suppress expansion.
        expanded = out / 'expanded'
        expanded.mkdir()
        shutil.copyfile(source, expanded / 'source.v')
        options = ''.join(f' -chparam {key} {value}' for key, value in sorted(PARAMETERS.items()))
        script = (f'read_verilog -sv source.v; hierarchy -check -top sfifo{options}; '
                  'proc; opt_clean; memory_collect; write_json collected.json; '
                  'write_rtlil collected.il; memory_map; pmuxtree; opt_clean -purge; '
                  'check -assert; write_json expanded.json; write_rtlil expanded.il; '
                  'write_verilog -noattr expanded.v\n')
        (expanded / 'expand.ys').write_text(script)
        stages['expand'] = command([yosys, '-Q', '-T', '-s', 'expand.ys'], expanded, 'expand')
        if stages['expand']['status'] != 'OK':
            return result
        collected = json.loads((expanded / 'collected.json').read_text())['modules']['sfifo']
        if any(int(collected['parameter_default_values'][key], 2) != value
               for key, value in PARAMETERS.items()):
            raise ValueError('expanded instance parameters changed')
        if collected['netnames']['r_empty']['bits'] != collected['ports']['o_empty']['bits']:
            raise ValueError('r_empty is not the expected direct o_empty output alias')
        module = json.loads((expanded / 'expanded.json').read_text())['modules']['sfifo']
        result['netlist_init_audit'] = audit_netlist(module)
        result['undefined_cell_ports'] = {
            name: {'type': cell['type'], 'source': cell.get('attributes', {}).get('src'),
                   'ports': {port: bits for port, bits in cell['connections'].items()
                             if any(bit in {'x', 'z'} for bit in bits)}}
            for name, cell in module['cells'].items()
            if any(bit in {'x', 'z'} for bits in cell['connections'].values() for bit in bits)}
        try:
            _check_netlist(module, 'i_clk')
            stages['expanded_netlist'] = {'status': 'SUPPORTED'}
        except Unsupported as error:
            stages['expanded_netlist'] = {'status': 'UNSUPPORTED', 'reason': str(error)}
        (expanded / 'btor.ys').write_text('read_rtlil expanded.il; write_btor -x -i expanded.info expanded.btor2\n')
        stages['btor'] = command([yosys, '-Q', '-T', '-s', 'btor.ys'], expanded, 'btor')
        if stages['btor']['status'] != 'OK':
            return result
        btor = (expanded / 'expanded.btor2').read_text()
        result['btor_init_audit'] = audit_btor(btor)
        try:
            parse_btor2(btor, name='sfifo', source_sha256=sha(source), clock='i_clk')
            stages['expanded_parser'] = {'status': 'SUPPORTED'}
        except Unsupported as error:
            stages['expanded_parser'] = {'status': 'UNSUPPORTED', 'reason': str(error)}
        result['status'] = ('UNSUPPORTED' if any(row['status'] == 'UNSUPPORTED' for row in
                            (stages['expanded_netlist'], stages['expanded_parser'])) else 'FRONTEND_SUPPORTED')
        return result
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        result['error'] = str(error)
        return result
    finally:
        statuses = {stage['status'] for stage in stages.values()}
        if 'ERROR' in statuses:
            result['status'] = 'ERROR'
        elif 'UNKNOWN' in statuses:
            result['status'] = 'UNKNOWN'
        result['wall_seconds'] = time.monotonic() - started
        result['artifact_sha256'] = {str(path.relative_to(out)): sha(path)
                                    for path in sorted(out.rglob('*')) if path.is_file()}
        save(out / 'summary.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--yosys', required=True)
    args = parser.parse_args()
    executable = str(Path(shutil.which(args.yosys) or args.yosys).resolve())
    summary = assessment(args.out.resolve(), executable)
    print(json.dumps({key: summary[key] for key in ('task_id', 'status', 'wall_seconds')}))
    raise SystemExit(1 if summary['status'] in {'ERROR', 'UNKNOWN'} else 0)
