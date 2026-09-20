"""Bounded Yosys -> BTOR2 frontend; unsupported RTL semantics fail closed."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


class Unsupported(ValueError):
    pass


PIPELINE_SHA256 = "9a28c1109682583337c71df11383cd451dc941bf0724ca51c820c1e7bf8d2eaa"


def _bv(value, width):
    return {"bv": value, "width": width}


def _op(name, *args):
    return {"op": name, "args": list(args)}


def parse_btor2(text, *, name, source_sha256, nondet=(), clock="clk", signed=None):
    """Parse the exported BV subset; clock validation belongs to export_rtl."""
    from .ir import expr_type, validate_model

    lines = [line.split(";", 1)[0].split() for line in text.splitlines()]
    lines = [line for line in lines if line]
    # Yosys gives output registers anonymous states; direct graph aliases recover names.
    aliases = {}
    for line in lines:
        if len(line) == 4 and line[1] == "output":
            aliases.setdefault(line[2], line[3])
    sorts, nodes, widths, symbols, states, initial, next_, observe = {}, {}, {}, {}, {}, {}, {}, {}
    declared_inputs, seen, clock_node = set(), set(), None
    signed = signed or {}
    nondet = set(nondet)

    def get(token):
        node = int(token)
        if node == clock_node:
            raise Unsupported("clock used as data")
        if node not in nodes:
            raise Unsupported(f"unknown/forward BTOR2 node {node}")
        return nodes[node]

    def pred(expr):
        return _op("eq", expr, _bv(1, 1))

    def bit(expr):
        return _op("ite", expr, _bv(1, 1), _bv(0, 1))

    for line in lines:
        try:
            node, tag = int(line[0]), line[1]
            if node <= 0 or node in seen or (seen and node <= max(seen)):
                raise Unsupported("BTOR2 IDs must be unique and increasing")
            seen.add(node)
            if tag == "sort":
                if len(line) != 4 or line[2] != "bitvec" or not 1 <= int(line[3]) <= 256:
                    raise Unsupported("only BV widths 1..256 are supported")
                sorts[node] = int(line[3])
                continue
            if tag in {"constraint", "bad", "fair", "justice"}:
                raise Unsupported(f"BTOR2 {tag} would change the frozen contract")
            if tag == "output":
                if len(line) != 4 or line[3] in observe:
                    raise Unsupported("outputs require unique explicit names")
                observe[line[3]] = get(line[2])
                continue
            width = sorts[int(line[2])]
            widths[node] = width
            if tag in {"state", "input"}:
                if len(line) not in {3, 4}:
                    raise Unsupported("invalid state/input declaration")
                origin = line[3] if len(line) == 4 else aliases.get(str(node))
                if origin is None or origin in {s["origin"] for s in symbols.values()}:
                    raise Unsupported("state/input requires an unambiguous name")
                if tag == "input":
                    declared_inputs.add(origin)
                if tag == "input" and origin == clock:
                    if width != 1 or clock_node is not None:
                        raise Unsupported("clock must be one BV1 input")
                    clock_node = node
                    continue
                symbol = f"btor_{node}"
                symbols[symbol] = {"kind": "nondet" if origin in nondet else tag,
                                   "type": width, "signed": bool(signed.get(origin, False)),
                                   "origin": origin}
                if tag == "state":
                    if origin in nondet:
                        raise Unsupported("nondeterminism must be an input")
                    states[node] = symbol
                nodes[node] = {"ref": symbol}
            elif tag in {"const", "constd", "consth", "zero", "one", "ones"}:
                if tag in {"zero", "one", "ones"}:
                    if len(line) not in {3, 4}:
                        raise Unsupported("invalid constant")
                    value = {"zero": 0, "one": 1, "ones": (1 << width) - 1}[tag]
                else:
                    if len(line) not in {4, 5}:
                        raise Unsupported("invalid constant")
                    base = {"const": 2, "constd": 10, "consth": 16}[tag]
                    value = int(line[3], base)
                    if tag == "const" and (len(line[3]) != width or set(line[3]) - {"0", "1"}):
                        raise Unsupported("constant contains undefined bits or wrong width")
                    if not -(1 << (width - 1)) <= value < (1 << width):
                        raise Unsupported("constant exceeds its width")
                    value %= 1 << width
                nodes[node] = _bv(value, width)
            elif tag in {"init", "next"}:
                if len(line) not in {5, 6}:
                    raise Unsupported("invalid init/next")
                target = int(line[3])
                if target not in states or widths[target] != width or widths[int(line[4])] != width:
                    raise Unsupported("init/next does not match a declared state width")
                dest = initial if tag == "init" else next_
                symbol = states[target]
                if symbol in dest:
                    raise Unsupported("duplicate init/next")
                value = get(line[4])
                if tag == "init" and "bv" not in value:
                    raise Unsupported("v0 requires explicit fully defined constant initial state")
                dest[symbol] = value
            else:
                unary = {"not": "bvnot"}
                binary = {"and": "bvand", "or": "bvor", "xor": "bvxor", "add": "add",
                          "sub": "sub", "concat": "concat"}
                comparisons = {"eq": "eq", "neq": "eq", "ult": "ult", "ulte": "ule"}
                arity = 1 if tag in unary else 2 if tag in binary or tag in comparisons else 3 if tag == "ite" else None
                if arity is not None:
                    if len(line) not in {3 + arity, 4 + arity}:
                        raise Unsupported(f"invalid {tag} arity")
                    args = [get(token) for token in line[3:3 + arity]]
                    if tag in unary or tag in binary:
                        nodes[node] = _op((unary | binary)[tag], *args)
                    elif tag in comparisons:
                        if width != 1:
                            raise Unsupported("comparison result must be BV1")
                        comparison = _op(comparisons[tag], *args)
                        nodes[node] = bit(_op("not", comparison) if tag == "neq" else comparison)
                    else:
                        if widths[int(line[3])] != 1:
                            raise Unsupported("ite condition must be BV1")
                        nodes[node] = _op("ite", pred(args[0]), args[1], args[2])
                elif tag == "redor":
                    if len(line) not in {4, 5} or width != 1:
                        raise Unsupported("invalid reduction-or")
                    nodes[node] = bit(_op("not", _op("eq", get(line[3]),
                                                   _bv(0, widths[int(line[3])]))))
                elif tag in {"uext", "sext"}:
                    if len(line) not in {5, 6}:
                        raise Unsupported("invalid extension")
                    extra = int(line[4])
                    if extra < 0 or widths[int(line[3])] + extra != width:
                        raise Unsupported("extension width mismatch")
                    nodes[node] = get(line[3]) if extra == 0 else {
                        "op": "zext" if tag == "uext" else "sext", "args": [get(line[3])], "width": width}
                elif tag == "slice":
                    if len(line) not in {6, 7}:
                        raise Unsupported("invalid slice")
                    high, low = int(line[4]), int(line[5])
                    if not 0 <= low <= high < widths[int(line[3])] or high - low + 1 != width:
                        raise Unsupported("slice width mismatch")
                    nodes[node] = {"op": "extract", "args": [get(line[3])], "high": high, "low": low}
                else:
                    raise Unsupported(f"unsupported BTOR2 operator: {tag}")
                actual = expr_type(nodes[node], {key: val["type"] for key, val in symbols.items()})
                if actual != width:
                    raise Unsupported(f"operator {tag} result width mismatch")
        except (IndexError, KeyError, ValueError) as error:
            raise Unsupported(f"BTOR2 line {' '.join(line)}: {error}") from error
    if clock_node is None or not nondet <= declared_inputs - {clock}:
        raise Unsupported("missing clock or registered nondeterministic input")
    if set(initial) != set(states.values()) or set(next_) != set(states.values()):
        raise Unsupported("every state requires explicit initialization and next state")
    if not states or not observe:
        raise Unsupported("model requires state and observations")
    equations = [_op("eq", {"ref": symbol}, value) for symbol, value in initial.items()]
    init = equations[0]
    for equation in equations[1:]:
        init = _op("and", init, equation)
    model = {"version": 1, "name": name, "source_sha256": source_sha256, "symbols": symbols,
             "clock": {"name": clock, "edge": "positive"},
             "init": init, "next": next_, "observe": observe}
    validate_model(model)
    return model


def _check_netlist(module, clock):
    ports, cells = module["ports"], module.get("cells", {})
    if clock not in ports or ports[clock]["direction"] != "input" or len(ports[clock]["bits"]) != 1:
        raise Unsupported("clock must be a single input port")
    clock_bit = ports[clock]["bits"][0]
    allowed = {"$dff", "$add", "$sub", "$eq", "$ne", "$lt", "$le", "$mux", "$not",
               "$and", "$or", "$xor", "$logic_not", "$logic_and", "$logic_or", "$reduce_or", "$reduce_bool"}
    state_bits = []
    for cell in cells.values():
        if cell["type"] not in allowed:
            raise Unsupported(f"unsupported cell {cell['type']} (no arrays/latches/async clocks)")
        for port, bits in cell["connections"].items():
            if any(bit in {"x", "z"} for bit in bits):
                raise Unsupported("undefined/high-impedance RTL bit")
            if clock_bit in bits and not (cell["type"] == "$dff" and port == "CLK"):
                raise Unsupported("clock used as data or gated clock")
        if cell["type"] == "$dff":
            if cell["connections"]["CLK"] != [clock_bit] or int(cell["parameters"]["CLK_POLARITY"], 2) != 1:
                raise Unsupported("requires one shared positive-edge clock")
            state_bits.extend(cell["connections"]["Q"])
    if not state_bits or len(state_bits) != len(set(state_bits)):
        raise Unsupported("missing or multiply driven state")
    if any(port["direction"] not in {"input", "output"} for port in ports.values()):
        raise Unsupported("inout ports unsupported")
    if any(clock_bit in port["bits"] for name, port in ports.items() if name != clock):
        raise Unsupported("clock aliases another port")
    for net in module.get("netnames", {}).values():
        if any(bit in {"x", "z"} for bit in net["bits"]):
            raise Unsupported("undefined/high-impedance RTL net")
        init = net.get("attributes", {}).get("init")
        if init is not None and set(init) - {"0", "1"}:
            raise Unsupported("partially/uninitialized RTL state")


def export_rtl(source, top, out_dir, *, nondet=(), clock="clk", executable=None, timeout=60,
               parameters=None, profile=None):
    """Export real RTL, retain provenance/logs, and return the root typed model."""
    source, out_dir = Path(source).resolve(), Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", top):
        raise Unsupported("top must be a simple Verilog identifier")
    parameters = {} if parameters is None else parameters
    if not isinstance(parameters, dict) or any(
            not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or
            type(value) is not int or not 0 <= value < 1 << 32
            for key, value in parameters.items()):
        raise Unsupported("parameters require simple names and unsigned 32-bit integers")
    if profile not in {None, "avr_pipeline32"}:
        raise Unsupported("unknown trusted extraction profile")
    executable = executable or os.environ.get("RTL_RELATE_YOSYS")
    if not executable:
        local = Path(__file__).resolve().parents[1] / ".tools/yosys-venv/bin/yowasp-yosys"
        executable = str(local) if local.exists() else shutil.which("yosys")
    if not executable:
        raise Unsupported("Yosys unavailable; run scripts/bootstrap_yosys.sh")
    executable = str(Path(shutil.which(str(executable)) or executable).resolve())
    # Work on a retained source copy: shell/command quoting cannot alter the input path.
    source_bytes = source.read_bytes()
    (out_dir / "source.v").write_bytes(source_bytes)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    chparam = "".join(f" -chparam {key} {value}" for key, value in sorted(parameters.items()))
    extraction = ("write_json original-netlist.json; expose main/tmp_stageOne main/tmp_stageTwo main/prop; "
                  "chformal -assert -remove; ") if profile else ""
    normalize = "delete -output main/prop; " if profile else ""
    script = (f"read_verilog -sv source.v; hierarchy -check -top {top}{chparam}; proc; {extraction}opt_clean; "
              "check -assert; write_json netlist.json; write_btor -i model.info model.btor2; "
              f"{normalize}write_verilog -noattr normalized.v\n")
    (out_dir / "export.ys").write_text(script)
    started = time.monotonic()
    command = [executable, "-Q", "-T", "-s", "export.ys"]
    metadata = {"command": command, "top": top, "clock": clock, "nondet": sorted(nondet),
                "source_path": str(source), "source_sha256": source_sha256,
                "parameters": parameters, "profile": profile,
                "script_sha256": hashlib.sha256(script.encode()).hexdigest(), "status": "UNSUPPORTED"}
    try:
        if profile and (source_sha256 != PIPELINE_SHA256 or top != "main" or clock != "clock" or
                        parameters or nondet):
            raise Unsupported("avr_pipeline32 requires the exact pinned source and interface")
        version = subprocess.run([executable, "-V"], capture_output=True, text=True, timeout=timeout, check=True)
        metadata["version"] = version.stdout.strip()
        metadata["executable_sha256"] = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
        tools_root = Path(executable).parent.parent
        wasm = list(tools_root.glob("lib/python*/site-packages/yowasp_yosys/yosys.wasm"))
        if wasm:
            metadata["wasm_sha256"] = hashlib.sha256(wasm[0].read_bytes()).hexdigest()
        result = subprocess.run(command, cwd=out_dir, capture_output=True, text=True, timeout=timeout)
        (out_dir / "yosys.stdout.log").write_text(result.stdout)
        (out_dir / "yosys.stderr.log").write_text(result.stderr)
        metadata["returncode"] = result.returncode
        if result.returncode:
            raise Unsupported("Yosys export failed; see retained logs")
        modules = json.loads((out_dir / "netlist.json").read_text())["modules"]
        if set(modules) != {top}:
            raise Unsupported("v0 requires one flattened module")
        module = modules[top]
        for key, value in parameters.items():
            if int(module.get("parameter_default_values", {}).get(key, "-1"), 2) != value:
                raise Unsupported(f"parameter {key} was not applied")
        _check_netlist(module, clock)
        if profile:
            original = json.loads((out_dir / "original-netlist.json").read_text())["modules"][top]
            checks = [(key, cell) for key, cell in original["cells"].items()
                      if cell["type"] in {"$check", "$assert", "$assume", "$cover", "$live", "$fair"}]
            if len(checks) != 1:
                raise Unsupported("pipeline extraction requires exactly one original assertion")
            cell_name, cell = checks[0]
            if (cell["type"] != "$check" or cell["parameters"].get("FLAVOR") != "assert" or
                    int(cell["parameters"].get("TRG_ENABLE", "1"), 2) != 0 or
                    cell["connections"] != {"A": original["netnames"]["prop"]["bits"],
                                            "ARGS": [], "EN": ["1"], "TRG": []}):
                raise Unsupported("pipeline assertion has changed enable, sampling, or predicate")
        info = (out_dir / "model.info").read_text().splitlines()
        if len([line for line in info if line.startswith("posedge ")]) != 1 or any(line.startswith("negedge ") for line in info):
            raise Unsupported("BTOR2 clock metadata must contain one positive edge")
        btor = (out_dir / "model.btor2").read_text()
        source_hash = hashlib.sha256(json.dumps({"rtl": source_bytes.decode(), "top": top, "clock": clock,
            "nondet": sorted(nondet), "script": script, "version": metadata["version"]}, sort_keys=True).encode()).hexdigest()
        model = parse_btor2(btor, name=top, source_sha256=source_hash, nondet=nondet, clock=clock,
                           signed={name: net.get("signed", 0) for name, net in module["netnames"].items()})
        if profile:
            from .ir import digest
            predicate = _op("eq", model["observe"].pop("prop"), _bv(1, 1))
            assertion = {"profile": profile, "source_sha256": source_sha256,
                         "model_sha256": digest(model), "cell": cell_name, "sampling": "before_update",
                         "predicate": predicate, "monitor_states": ["tmp_stageOne", "tmp_stageTwo"]}
            (out_dir / "assertion.json").write_text(json.dumps(assertion, indent=2) + "\n")
            metadata["assertion_sha256"] = hashlib.sha256((out_dir / "assertion.json").read_bytes()).hexdigest()
            metadata["original_netlist_sha256"] = hashlib.sha256((out_dir / "original-netlist.json").read_bytes()).hexdigest()
        (out_dir / "model.json").write_text(json.dumps(model, indent=2) + "\n")
        metadata["btor2_sha256"] = hashlib.sha256(btor.encode()).hexdigest()
        metadata["netlist_sha256"] = hashlib.sha256((out_dir / "netlist.json").read_bytes()).hexdigest()
        metadata["normalized_sha256"] = hashlib.sha256((out_dir / "normalized.v").read_bytes()).hexdigest()
        metadata["status"] = "EXPORTED"
        return model
    except subprocess.TimeoutExpired as error:
        (out_dir / "yosys.stdout.log").write_bytes(error.stdout or b"")
        (out_dir / "yosys.stderr.log").write_bytes(error.stderr or b"")
        metadata["error"] = "Yosys timeout"
        raise Unsupported("Yosys timeout") from error
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        metadata["error"] = str(error)
        raise Unsupported(str(error)) from error
    finally:
        metadata["wall_seconds"] = time.monotonic() - started
        (out_dir / "frontend.json").write_text(json.dumps(metadata, indent=2) + "\n")
