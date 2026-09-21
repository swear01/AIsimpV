"""Native-memory abstraction checks by a witnessed synchronous product.

The original h/J/w checker is unchanged. This adapter preserves native assertion
signals and symbolic initialization. A complete product proof establishes trace
inclusion for the supplied choices; the abstract property runs with free choices.
"""
import copy
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rtl_relate.formal import _run
from rtl_relate.ir import expr_type
from scripts.screen_baselines import prove, save, sha

PREFIX = '__ar_'
FORMAL = {'$assert', '$assume', '$cover', '$check', '$live', '$fair',
          '$anyconst', '$anyseq', '$allconst', '$allseq', '$initstate', '$print'}
COMB = {'$add', '$sub', '$mul', '$div', '$mod', '$and', '$or', '$xor', '$xnor',
        '$not', '$logic_not', '$logic_and', '$logic_or', '$eq', '$ne', '$lt', '$le',
        '$gt', '$ge', '$mux', '$pmux', '$reduce_and', '$reduce_or', '$reduce_xor',
        '$reduce_xnor', '$reduce_bool', '$shl', '$shr', '$sshl', '$sshr', '$shift',
        '$shiftx', '$pos', '$neg', '$slice', '$concat'}


def identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name):
        raise ValueError('simple port/module identifier required: ' + str(name))
    return name


def clock_of(module):
    """Only positive-edge synchronous state, including native memory ports."""
    clocks, stored, initial_pairs = set(), set(), []
    for cell in module['cells'].values():
        kind, con, par = cell['type'], cell['connections'], cell['parameters']
        if kind == '$dff':
            if int(par['CLK_POLARITY'], 2) != 1:
                raise ValueError('negative-edge state is unsupported')
            clocks.update(con['CLK'])
            stored.update(con['Q'])
        elif kind == '$mem_v2':
            if any(b != '0' for b in con['RD_ARST']):
                raise ValueError('asynchronous memory read resets are unsupported')
            if int(par['WR_CLK_ENABLE'], 2) != (1 << int(par['WR_PORTS'], 2)) - 1:
                raise ValueError('asynchronous memory writes are unsupported')
            for mode in ('RD', 'WR'):
                enabled = int(par[mode + '_CLK_ENABLE'], 2)
                polarities = int(par[mode + '_CLK_POLARITY'].replace('x', '0'), 2)
                if enabled & ~polarities:
                    raise ValueError('negative-edge memory is unsupported')
                clocks.update(bit for i, bit in enumerate(con[mode + '_CLK']) if enabled >> i & 1)
            width = int(par['WIDTH'], 2)
            read_initial = par['RD_INIT_VALUE']
            if len(read_initial) != len(con['RD_DATA']) or set(read_initial) - set('01x'):
                raise ValueError('unsupported memory read initialization')
            read_initial = list(reversed(read_initial))
            for i in range(int(par['RD_PORTS'], 2)):
                if int(par['RD_CLK_ENABLE'], 2) >> i & 1:
                    bits = con['RD_DATA'][i * width:(i + 1) * width]
                    stored.update(bits)
                    initial_pairs.extend(zip(bits, read_initial[i * width:(i + 1) * width]))
        elif kind not in COMB | FORMAL:
            raise ValueError('unsupported native cell: ' + kind)
    # Yosys honors init attributes on inputs too; those would silently assume
    # an environment restriction and can make a false product proof pass.
    initial = {}
    inputs = {b for p in module['ports'].values() if p['direction'] == 'input' for b in p['bits']}
    for net in module['netnames'].values():
        value = net.get('attributes', {}).get('init')
        if value is None:
            continue
        if not isinstance(value, str) or len(value) != len(net['bits']) or set(value) - set('01x'):
            raise ValueError('unsupported initialization encoding')
        initial_pairs.extend(zip(net['bits'], reversed(value)))
    for bit, val in initial_pairs:
        if val == 'x':
            continue
        if isinstance(bit, str):
            if bit != val:
                raise ValueError('conflicting constant initialization')
            continue
        if bit not in stored or bit in inputs:
            raise ValueError('initialization may constrain only stored state')
        if bit in initial and initial[bit] != val:
            raise ValueError('conflicting state initialization')
        initial[bit] = val
    if not clocks:
        return None
    if len(clocks) != 1:
        raise ValueError('one positive-edge clock required')
    matches = [n for n, p in module['ports'].items()
               if p['direction'] == 'input' and p['bits'] == list(clocks)]
    if len(matches) != 1:
        raise ValueError('clock must be one unambiguous input')
    return identifier(matches[0])


def export_json(module, top, out, yosys, deadline=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'design.json', {'modules': {top: module}})
    (out / 'export.ys').write_text('read_json design.json\ncheck -assert\nwrite_verilog design.v\n')
    row, _ = _run([yosys, '-Q', '-T', '-s', 'export.ys'], out, 'export',
                  min(time.monotonic() + 30, deadline if deadline is not None else float('inf')))
    save(out / 'export.json', row)
    if row['timeout']:
        raise TimeoutError('native JSON export exceeded budget')
    if row['returncode'] != 0:
        raise ValueError('native JSON export failed')
    return out / 'design.v'


def normalize(prepared, top, out, yosys):
    """Expose exactly the original assert A/EN; share original anyconst choices."""
    module = copy.deepcopy(json.loads(Path(prepared).read_text())['modules'][top])
    clock = clock_of(module)
    if clock is None:
        raise ValueError('original model requires a positive-edge clock')
    if any(n.startswith(PREFIX) for n in module['ports'] | module['netnames']):
        raise ValueError('reserved normalization prefix collision')
    ports = module['ports']
    for name in ports:
        identifier(name)
    assertions, consts = [], []
    for name, cell in list(module['cells'].items()):
        kind = cell['type']
        if kind == '$assert':
            assertions.append((name, cell['connections']))
            del module['cells'][name]
        elif kind == '$cover':
            del module['cells'][name]
        elif kind == '$anyconst':
            port = PREFIX + 'const_' + str(len(consts))
            bits = cell['connections']['Y']
            ports[port] = {'direction': 'input', 'bits': bits}
            module['netnames'][port] = {'hide_name': 0, 'bits': bits, 'attributes': {}}
            consts.append(port)
            del module['cells'][name]
        elif kind in FORMAL:
            raise ValueError('unsupported original formal construct: ' + kind)
    if not assertions:
        raise ValueError('original assertions required')
    original_outputs = [n for n, p in ports.items() if p['direction'] == 'output']
    for suffix, pin in [('a', 'A'), ('en', 'EN')]:
        bits = [bit for _, con in assertions for bit in con[pin]]
        if len(bits) != len(assertions):
            raise ValueError('assertion pins must have width one')
        name = PREFIX + suffix
        ports[name] = {'direction': 'output', 'bits': bits}
        module['netnames'][name] = {'hide_name': 0, 'bits': bits, 'attributes': {}}
    source = export_json(module, 'concrete_design', out, yosys)
    metadata = {'clock': clock, 'constant_inputs': consts, 'original_outputs': original_outputs,
                'assertion_names': [n for n, _ in assertions], 'original_model_sha256': sha(prepared),
                'design_sha256': sha(source), 'ports': ports}
    save(Path(out) / 'contract.json', metadata)
    return module, metadata


def prepare_candidate(source, out, yosys, deadline=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    raw = Path(source).read_bytes()
    if len(raw) > 262144 or b'`' in raw:
        raise ValueError('candidate too large or contains preprocessing')
    # Escaping a builtin name must not bypass the file-reading task boundary.
    if re.search(rb'\$(?:readmem[bh]|writemem[bh]|fopen|fread|fscanf|system)\b', raw):
        raise ValueError('candidate contains unsupported system tasks/functions')
    system_names = re.findall(rb'(?<![A-Za-z0-9_$\\])(\$[A-Za-z_]\w*)', raw)
    if set(system_names) - {b'$signed', b'$unsigned', b'$clog2'}:
        raise ValueError('candidate contains unsupported system tasks/functions')
    (out / 'source.v').write_bytes(raw)
    # Inspect before async-reset conversion: candidate semantics cannot be silently changed.
    (out / 'prepare.ys').write_text('read_verilog -formal -sv source.v\n'
        'hierarchy -check -top abstract_design\nprep -top abstract_design -flatten\n'
        'dffunmap\nopt_clean\ncheck -assert\nwrite_json model.json\n')
    row, _ = _run([yosys, '-Q', '-T', '-s', 'prepare.ys'], out, 'prepare',
                  min(time.monotonic() + 30, deadline if deadline is not None else float('inf')))
    save(out / 'preparation.json', row)
    if row['timeout']:
        raise TimeoutError('candidate preparation exceeded budget')
    if row['returncode'] != 0:
        raise ValueError('candidate preparation failed')
    module = json.loads((out / 'model.json').read_text())['modules']['abstract_design']
    if any(module.get('attributes', {}).get(k) for k in ('blackbox', 'whitebox')):
        raise ValueError('candidate may not be a blackbox/whitebox')
    if any(c['type'] in FORMAL for c in module['cells'].values()):
        raise ValueError('candidate must be design-only, with nondeterminism in declared input ports')
    clock_of(module)
    return module


def taps(module, names):
    """Expose checked current combinational/state signals, never guessed identifiers."""
    module = copy.deepcopy(module)
    outputs = {}
    for i, name in enumerate(sorted(set(names))):
        if name not in module['netnames']:
            raise ValueError('unknown witness/invariant signal: ' + name)
        port = PREFIX + 'tap_' + str(i)
        if port in module['ports'] or port in module['netnames']:
            raise ValueError('tap name collision')
        bits = module['netnames'][name]['bits']
        module['ports'][port] = {'direction': 'output', 'bits': bits}
        module['netnames'][port] = {'hide_name': 0, 'bits': bits, 'attributes': {}}
        outputs[name] = port
    return module, outputs


def cut_candidates(module, metadata):
    inputs = {b for p in module['ports'].values() if p['direction'] == 'input' for b in p['bits']}
    result, seen = {}, set()
    for name, net in sorted(module['netnames'].items()):
        bits = tuple(net['bits'])
        if (net.get('hide_name') or name.startswith(PREFIX) or name in module['ports']
                or len(bits) < 2 or any(type(b) is not int or b in inputs for b in bits)
                or len(set(bits)) != len(bits) or bits in seen):
            continue
        result[name] = {'width': len(bits)}
        seen.add(bits)
    return result


def cut_model(concrete, metadata, names):
    """Trusted havoc template: remove drivers, add free inputs, retain all monitors.

    The original value at each cut is an existential witness. No assumption,
    assertion, uncut driver or initialization constraint is strengthened.
    """
    available = cut_candidates(concrete, metadata)
    if (not isinstance(names, list) or any(not isinstance(n, str) for n in names)
            or len(set(names)) != len(names) or not set(names) <= set(available)):
        raise ValueError('unknown or duplicate cutpoint')
    selected = set()
    for name in names:
        bits = set(concrete['netnames'][name]['bits'])
        if selected & bits:
            raise ValueError('overlapping cutpoints')
        selected |= bits
    module = copy.deepcopy(concrete)
    all_bits = [b for cell in module['cells'].values() for bits in cell['connections'].values()
                for b in bits if type(b) is int]
    all_bits += [b for net in module['netnames'].values() for b in net['bits'] if type(b) is int]
    fresh = {b: max(all_bits, default=1) + 1 + i for i, b in enumerate(sorted(selected))}
    for cell in module['cells'].values():
        for pin, direction in cell['port_directions'].items():
            if direction == 'output':
                cell['connections'][pin] = [fresh.get(b, b) for b in cell['connections'][pin]]
    for net in module['netnames'].values():
        attributes = net.get('attributes', {})
        if 'init' in attributes:
            initial = list(reversed(attributes['init']))
            for i, bit in enumerate(net['bits']):
                if bit in selected:
                    initial[i] = 'x'
            if set(initial) == {'x'}:
                del attributes['init']
            else:
                attributes['init'] = ''.join(reversed(initial))
    for i, name in enumerate(names):
        port = PREFIX + 'choice_' + str(i)
        if port in module['ports'] or port in module['netnames']:
            raise ValueError('cutpoint input collision')
        bits = module['netnames'][name]['bits']
        module['ports'][port] = {'direction': 'input', 'bits': bits}
        module['netnames'][port] = {'hide_name': 0, 'bits': bits, 'attributes': {}}
    return module


def references(expr):
    if not isinstance(expr, dict):
        raise ValueError('typed expression required')
    if 'ref' in expr:
        return {expr['ref']}
    return set().union(*(references(a) for a in expr.get('args', [])))


def expression(expr, bindings, types, declarations):
    typ = expr_type(expr, types)
    if 'ref' in expr:
        return bindings[expr['ref']]
    if 'bool' in expr:
        return "1'b" + str(int(expr['bool']))
    if 'bv' in expr:
        return f"{expr['width']}'d{expr['bv']}"
    args = [expression(a, bindings, types, declarations) for a in expr['args']]
    op = expr['op']
    binary = {'eq': '==', 'and': '&&', 'or': '||', 'xor': '^', 'bvand': '&', 'bvor': '|',
              'bvxor': '^', 'add': '+', 'sub': '-', 'ult': '<', 'ule': '<='}
    if op in binary:
        value = f'({args[0]} {binary[op]} {args[1]})'
    elif op in {'not', 'bvnot'}:
        value = f'({"!" if op == "not" else "~"}{args[0]})'
    elif op == 'ite':
        value = f'({args[0]} ? {args[1]} : {args[2]})'
    elif op == 'concat':
        value = '{' + ', '.join(args) + '}'
    elif op == 'extract':
        value = f'({args[0]} >> {expr["low"]})'
    elif op in {'zext', 'sext'}:
        value = args[0] if op == 'zext' else f'$signed({args[0]})'
    else:
        raise ValueError('unsupported expression')
    name = PREFIX + 'expr_' + str(len(declarations))
    declarations.append(f'wire [{(1 if typ == "bool" else typ)-1}:0] {name} = {value};')
    return name


def property_source(design, module, metadata, top):
    """No certificate assumptions: every new abstract input is free each step."""
    ports = module['ports']
    constants = set(metadata['constant_inputs'])
    lines, arguments, inputs = [], [], []
    for i, (name, port) in enumerate(ports.items()):
        identifier(name)
        wire = 'p' + str(i)
        width = len(port['bits'])
        if port['direction'] == 'input' and name not in constants:
            inputs.append(f'input wire [{width-1}:0] {wire}')
        else:
            lines.append(('(* anyconst *) reg' if name in constants else 'wire')
                         + f' [{width-1}:0] {wire};')
        arguments.append(f'.{name}({wire})')
    index = {n: 'p' + str(i) for i, n in enumerate(ports)}
    lines.insert(0, 'module native_property(' + ', '.join(inputs) + ');')
    lines.append(top + ' dut(' + ', '.join(arguments) + ');')
    for i in range(len(metadata['assertion_names'])):
        lines.append(f'always @* assert(!{index[PREFIX+"en"]}[{i}] || {index[PREFIX+"a"]}[{i}]);')
    lines.append('endmodule')
    return Path(design).read_text() + '\n' + '\n'.join(lines) + '\n'


def witnessed_product(concrete, abstract, metadata, certificate, out, yosys, deadline=None):
    """A complete product proof is sufficient, possibly stronger than necessary.

    Each original anyconst is shared. Extra A inputs use current C signals only.
    A initial states are universally checked, so no existential initial-state
    mapping is silently assumed. Helper relations are assertions, never assumes.
    """
    if set(certificate) != {'witnesses', 'invariants'}:
        raise ValueError('certificate requires witnesses and invariants')
    witnesses, invariants = certificate['witnesses'], certificate['invariants']
    if not isinstance(witnesses, dict) or not isinstance(invariants, list) or len(invariants) > 128:
        raise ValueError('invalid certificate collections')
    if clock_of(abstract) not in (None, metadata['clock']):
        raise ValueError('candidate clock differs')
    signature = lambda m: {n: (p['direction'], len(p['bits'])) for n, p in m['ports'].items()}
    expected, actual = signature(concrete), signature(abstract)
    if any(actual.get(n) != spec for n, spec in expected.items()):
        raise ValueError('frozen port interface differs')
    if set(actual) - set(expected) != set(witnesses) or set(witnesses) & set(expected):
        raise ValueError('every extra abstract input requires exactly one witness')
    types = {side + '.' + n: len(v['bits']) for side, mod in [('c', concrete), ('a', abstract)]
             for n, v in mod['netnames'].items() if n != metadata['clock']}
    needed = {'c': set(witnesses.values()), 'a': set()}
    for name, signal in witnesses.items():
        identifier(name)
        if not isinstance(signal, str) or 'c.' + signal not in types:
            raise ValueError('witness must name a current concrete signal')
        if actual[name] != ('input', types['c.' + signal]):
            raise ValueError('witness input direction or width differs')
    for invariant in invariants:
        if expr_type(invariant, types) != 'bool':
            raise ValueError('helper invariant must be Bool')
        for name in references(invariant):
            needed[name[:1]].add(name[2:])
    cmod, cmap = taps(concrete, needed['c'])
    amod, amap = taps(abstract, needed['a'])
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    csrc = export_json(cmod, 'concrete_design', out / 'concrete', yosys, deadline)
    asrc = export_json(amod, 'abstract_design', out / 'abstract', yosys, deadline)
    lines, inputs, shared = [], [], {}
    for i, (name, port) in enumerate(concrete['ports'].items()):
        if port['direction'] != 'input':
            continue
        wire = 'u' + str(i)
        shared[name] = wire
        width = len(port['bits'])
        if name in metadata['constant_inputs']:
            lines.append(f'(* anyconst *) reg [{width-1}:0] {wire};')
        else:
            inputs.append(f'input wire [{width-1}:0] {wire}')
    lines.insert(0, 'module native_product(' + ', '.join(inputs) + ');')
    output_wires, bindings = {}, {}
    for side, module, mapped in [('c', cmod, cmap), ('a', amod, amap)]:
        arguments = []
        for i, (name, port) in enumerate(module['ports'].items()):
            if port['direction'] == 'output':
                wire = side + str(i)
                lines.append(f'wire [{len(port["bits"])-1}:0] {wire};')
                output_wires[side, name] = wire
            elif name in shared:
                wire = shared[name]
            elif side == 'a' and name in witnesses:
                wire = output_wires['c', cmap[witnesses[name]]]
            else:
                raise ValueError('unexpected port in product')
            arguments.append(f'.{identifier(name)}({wire})')
        lines.append(('concrete_design' if side == 'c' else 'abstract_design')
                     + ' ' + side + '(' + ', '.join(arguments) + ');')
        bindings.update({side + '.' + name: output_wires[side, port] for name, port in mapped.items()})
    for name in metadata['original_outputs']:
        lines.append(f'always @* assert({output_wires["c",name]} == {output_wires["a",name]});')
    for i in range(len(metadata['assertion_names'])):
        c_bad = f'({output_wires["c",PREFIX+"en"]}[{i}] && !{output_wires["c",PREFIX+"a"]}[{i}])'
        a_bad = f'({output_wires["a",PREFIX+"en"]}[{i}] && !{output_wires["a",PREFIX+"a"]}[{i}])'
        lines.append(f'always @* assert({c_bad} == {a_bad});')
    for invariant in invariants:
        predicate = expression(invariant, bindings, types, lines)
        lines.append('always @* assert(' + predicate + ');')
    lines.append('endmodule')
    target = out / 'product.v'
    target.write_text(csrc.read_text() + '\n' + asrc.read_text() + '\n' + '\n'.join(lines) + '\n')
    save(out / 'binding.json', {'concrete_sha256': sha(csrc), 'abstract_sha256': sha(asrc),
                             'product_sha256': sha(target), 'certificate': certificate,
                             'contract': metadata, 'initial_mapping': 'universal-product'})
    return target
