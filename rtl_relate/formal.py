"""Direct RTL safety proof: ordinary Yosys preparation, SMTBMC base and induction."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

from .checker import validate_contract
from .frontend import _check_netlist, Unsupported as FrontendUnsupported
from .ir import Invalid, Unsupported, digest, expr_type


def _identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise Invalid("formal RTL interface requires simple Verilog identifiers")
    return name


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _metrics(module):
    cells = module.get("cells", {})
    return {"cells": len(cells), "state_bits": sum(
        len(cell["connections"]["Q"]) for cell in cells.values()
        if cell["type"] in {"$dff", "$dffe", "$sdff", "$sdffe", "$sdffce", "$ff"}),
        "cell_types": {kind: sum(c["type"] == kind for c in cells.values())
                       for kind in sorted({c["type"] for c in cells.values()})}}


def _run(command, out, name, deadline):
    """Kill the whole solver process group at the shared wall-clock deadline."""
    started = time.monotonic()
    row = {"command": command, "returncode": None, "timeout": False}
    remaining = deadline - started
    stdout = stderr = b""
    try:
        if remaining <= 0:
            row["timeout"] = True
        else:
            process = subprocess.Popen(command, cwd=out, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate()
                row["timeout"] = True
            row["returncode"] = process.returncode
    except OSError as error:
        stderr = str(error).encode("utf-8")
    (out / f"{name}.stdout.log").write_bytes(stdout)
    (out / f"{name}.stderr.log").write_bytes(stderr)
    row.update(seconds=time.monotonic() - started, stdout=f"{name}.stdout.log",
               stderr=f"{name}.stderr.log")
    # Retain both raw streams before decoding; malformed proof output fails closed.
    return row, stdout.decode("utf-8")


def render_harness(top, contract, ports, nondet=()):
    """Compile the frozen typed edge property without changing any DUT choice."""
    types = validate_contract(contract)
    clock = contract["clock"]["name"]
    for name in (top, clock, *ports):
        _identifier(name)
    nondet = tuple(nondet)
    if (set(contract["inputs"]) & set(contract["observations"])
            or clock in contract["inputs"] or clock in contract["observations"]):
        raise Invalid("clock, public inputs and observations must have distinct port names")
    if len(set(nondet)) != len(nondet) or set(nondet) & (set(contract["inputs"]) | {clock}):
        raise Invalid("nondeterministic ports must be unique and separate from public inputs")
    inputs = {clock: 1, **contract["inputs"]}
    for name in nondet:
        if name not in ports or ports[name]["direction"] != "input":
            raise Invalid("nondeterminism must name a DUT input")
        inputs[name] = len(ports[name]["bits"])
    expected = {**{n: ("input", w) for n, w in inputs.items()},
                **{n: ("output", w) for n, w in contract["observations"].items()}}
    actual = {n: (p["direction"], len(p["bits"])) for n, p in ports.items()}
    if actual != expected or any(type(w) is not int for _, w in expected.values()):
        raise Invalid("RTL ports differ from the frozen BV contract and registered nondeterminism")
    lines = ["module __rtl_relate_property(", ",\n".join(
        f"  input wire [{w-1}:0] in_{i}" for i, w in enumerate(inputs.values())), ");"]
    bindings = {n: f"in_{i}" for i, n in enumerate(inputs)}
    for i, (name, width) in enumerate(contract["observations"].items()):
        bindings[name] = f"out_{i}"
        lines.append(f"wire [{width-1}:0] out_{i};")
    connections = ", ".join(f".{name}({bindings[name]})" for name in ports)
    lines.append(f"{top} dut({connections});")
    # The first captured edge includes the DUT's initial observation; history is masked until then.
    lines.append("reg past_valid = 1'b0;")
    expression_bindings = {}
    captures = []
    for prefix, group in (("o", contract["observations"]), ("u", contract["inputs"])):
        for index, (name, width) in enumerate(group.items()):
            previous = f"prev_{prefix}_{index}"
            lines.append(f"reg [{width-1}:0] {previous};")
            captures.append(f"  {previous} <= {bindings[name]};")
            expression_bindings[f"{prefix}.{name}"] = previous
            if prefix == "o":
                expression_bindings[f"n.{name}"] = bindings[name]

    def expression(expr):
        typ = expr_type(expr, types)
        width = 1 if typ == "bool" else typ
        if "ref" in expr:
            return expression_bindings[expr["ref"]]
        if "bool" in expr:
            return f"1'b{int(expr['bool'])}"
        if "bv" in expr:
            return f"{width}'d{expr['bv']}"
        args = [expression(arg) for arg in expr["args"]]
        name = expr["op"]
        operators = {"eq": "==", "and": "&&", "or": "||", "xor": "^", "bvand": "&",
                     "bvor": "|", "bvxor": "^", "add": "+", "sub": "-", "ult": "<", "ule": "<="}
        if name in operators:
            value = f"({args[0]} {operators[name]} {args[1]})"
        elif name in {"not", "bvnot"}:
            value = f"({'!' if name == 'not' else '~'}{args[0]})"
        elif name == "ite":
            value = f"({args[0]} ? {args[1]} : {args[2]})"
        elif name == "concat":
            value = "{" + ", ".join(args) + "}"
        elif name == "extract":
            # Sized intermediate wires also permit slicing constants and expressions.
            value = f"({args[0]} >> {expr['low']})"
        elif name in {"zext", "sext"}:
            value = args[0] if name == "zext" else f"$signed({args[0]})"
        else:
            raise Unsupported(f"formal expression: {name}")
        wire = f"expr_{len(lines)}"
        # Each node has its own exact width: Verilog context must not widen BV arithmetic.
        lines.append(f"wire [{width-1}:0] {wire} = {value};")
        return wire

    predicate = expression(contract["property"]["step"])
    lines.extend([f"always @(posedge {bindings[clock]}) begin", "  past_valid <= 1'b1;",
                  *captures, "end", f"always @* if (past_valid) assert({predicate});", "endmodule", ""])
    return "\n".join(lines)


def prove_rtl(source, top, contract, out_dir, *, nondet=(), parameters=None,
              timeout_seconds=120, depth=20, yosys=None, smtbmc=None, mode="prove"):
    """Return SAFE only after base and induction; a reachable violation is CEX, not BUG.

    Source must be the same design-only RTL consumed by the certificate frontend.
    Its registered free ports remain unconstrained; certificates are never accepted here.
    """
    started = time.monotonic()
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "ERROR", "method": "yosys-smtbmc z3 base + k-induction",
              "mode": mode, "requested_depth": depth, "free_nondeterminism": True, "stages": {}}
    if any(out.iterdir()):
        result.update(reason="formal output directory must be empty; preserve earlier attempts",
                      seconds=time.monotonic() - started)
        return result
    try:
        if (type(timeout_seconds) not in {int, float} or not math.isfinite(timeout_seconds)
                or timeout_seconds <= 0 or type(depth) is not int or depth < 2):
            raise Invalid("positive finite timeout and integer depth >= 2 required")
        if mode not in {"prove", "bmc"}:
            raise Invalid("mode must be prove or bmc")
        if mode == "bmc":
            result["method"] = "yosys-smtbmc z3 bounded model checking"
        _identifier(top)
        validate_contract(contract)
        deadline = started + timeout_seconds
        local = Path(__file__).resolve().parents[1] / ".tools/yosys-venv/bin/yowasp-yosys"
        yosys = yosys or os.environ.get("RTL_RELATE_YOSYS") or (str(local) if local.exists() else shutil.which("yosys"))
        if not yosys:
            raise Unsupported("Yosys unavailable; run scripts/bootstrap_yosys.sh")
        yosys = str(Path(shutil.which(str(yosys)) or yosys).resolve())
        sibling = Path(yosys).with_name("yowasp-yosys-smtbmc" if "yowasp" in Path(yosys).name else "yosys-smtbmc")
        smtbmc = smtbmc or os.environ.get("RTL_RELATE_SMTBMC") or str(sibling)
        smtbmc = str(Path(shutil.which(str(smtbmc)) or smtbmc).resolve())
        z3 = shutil.which("z3")
        if not Path(smtbmc).is_file() or not z3:
            raise Unsupported("yosys-smtbmc or Z3 unavailable")
        source_bytes = Path(source).read_bytes()
        (out / "source.v").write_bytes(source_bytes)
        (out / "contract.json").write_text(json.dumps(contract, indent=2) + "\n")
        result.update(source_sha256=hashlib.sha256(source_bytes).hexdigest(), contract_sha256=digest(contract),
                      top=top, parameters=parameters or {}, nondet=sorted(nondet), timeout_seconds=timeout_seconds,
                      driver_sha256=_sha(__file__), tools={})
        for label, executable, flags in (("yosys", yosys, ["-V"]), ("z3", z3, ["-version"])):
            row, stdout = _run([executable, *flags], out, f"version_{label}", deadline)
            result["stages"][f"version_{label}"] = row
            if row["timeout"]:
                raise TimeoutError("tool identity exceeded budget")
            if row["returncode"] != 0:
                raise Invalid(f"{label} version command failed")
            result["tools"][label] = {"path": executable, "sha256": _sha(executable), "version": stdout.strip()}
        result["tools"]["smtbmc"] = {"path": smtbmc, "sha256": _sha(smtbmc),
                                        "version": "not separately reported; executable/source hashes recorded"}
        package = Path(yosys).parent.parent
        result["tools"]["distribution_files"] = {str(p.relative_to(package)): _sha(p)
            for pattern in ("lib/python*/site-packages/yowasp_yosys/yosys.wasm",
                            "lib/python*/site-packages/yowasp_yosys/smtbmc.py",
                            "lib/python*/site-packages/yowasp_yosys/share/python3/smtio.py",
                            "lib/python*/site-packages/yowasp_yosys/share/python3/ywio.py") for p in package.glob(pattern)}
        params = ""
        for name, value in (parameters or {}).items():
            _identifier(name)
            if type(value) is not int or value < 0:
                raise Invalid("formal parameters must be nonnegative integers")
            params += f" -chparam {name} {value}"
        script = (f"read_verilog -sv source.v\nhierarchy -check -top {top}{params}\n"
                  "proc\nflatten\nopt_clean\ncheck -assert\nwrite_json design.json\nwrite_rtlil design.il\n")
        (out / "design.ys").write_text(script)
        row, _ = _run([yosys, "-Q", "-T", "-s", "design.ys"], out, "design", deadline)
        result["stages"]["design"] = row
        if row["timeout"]:
            raise TimeoutError("RTL preparation exceeded budget")
        if row["returncode"] != 0:
            raise Invalid("RTL preparation failed; see design logs")
        modules = json.loads((out / "design.json").read_text())["modules"]
        if set(modules) != {top}:
            raise Unsupported("formal proof requires one flattened design")
        module = modules[top]
        states = _check_netlist(module, contract["clock"]["name"])
        initial = {bit for net in module["netnames"].values() if "init" in net.get("attributes", {}) for bit in net["bits"]}
        if not states <= initial:
            raise Unsupported("every design state requires explicit initialization")
        result["design_before_property_preprocessing"] = _metrics(module)
        harness = render_harness(top, contract, module["ports"], nondet)
        (out / "harness.sv").write_text(harness)
        script = ("read_rtlil design.il\nread_verilog -formal -sv harness.sv\n"
                  "prep -top __rtl_relate_property -flatten\nchformal -lower\ndffunmap\nopt_clean\n"
                  "check -assert\nwrite_json preprocessed.json\nwrite_smt2 -wires model.smt2\n")
        (out / "prove.ys").write_text(script)
        row, _ = _run([yosys, "-Q", "-T", "-s", "prove.ys"], out, "prepare", deadline)
        result["stages"]["prepare"] = row
        if row["timeout"]:
            raise TimeoutError("property preparation exceeded budget")
        if row["returncode"] != 0:
            raise Invalid("property preparation failed; see prepare logs")
        prepared = json.loads((out / "preprocessed.json").read_text())["modules"]["__rtl_relate_property"]
        result["after_property_preprocessing"] = _metrics(prepared)
        smt_text = (out / "model.smt2").read_text()
        if not re.search(r"^; yosys-smt2-assert ", smt_text, re.M) or re.search(r"^; yosys-smt2-assume ", smt_text, re.M):
            raise Invalid("formal model must contain the trusted assertion and no assumptions")
        result["hashes"] = {name: _sha(out / name) for name in (
            "source.v", "contract.json", "design.ys", "design.il", "design.json", "harness.sv", "prove.ys", "preprocessed.json", "model.smt2")}
        for stage in (["base", "induction"] if mode == "prove" else ["base"]):
            command = [smtbmc, "-s", "z3", "-t", str(depth), "--presat", "--noprogress",
                       "--dump-vcd", f"{stage}.vcd", "--dump-yw", f"{stage}.yw",
                       "--dump-smt2", f"{stage}.smt2"]
            if stage == "induction":
                command.append("-i")
            row, stdout = _run([*command, "model.smt2"], out, stage, deadline)
            result["stages"][stage] = row
            statuses = re.findall(r"Status: (\w+)", stdout)
            status = statuses[-1] if statuses else None
            if row["timeout"]:
                raise TimeoutError(f"{stage} exceeded shared wall-clock budget")
            if status == "FAILED" and row["returncode"] == 1:
                result.update(status="CEX" if stage == "base" else "BOUNDED",
                              reason="reachable property violation" if stage == "base" else "induction inconclusive")
                if stage == "base":
                    checked_steps = re.findall(r"Checking assertions in step (\d+)\.\.", stdout)
                    if checked_steps:
                        result["counterexample_step"] = int(checked_steps[-1])
                break
            if status != "PASSED" or row["returncode"] != 0:
                result.update(status="UNKNOWN" if status in {"UNKNOWN", "PREUNSAT"} else "ERROR",
                              reason=f"{stage} did not establish a proof: {status}")
                break
            if stage == "base":
                result.update(bounded_depth=depth, bounded_edges=depth - 1)
        else:
            result["status"] = "SAFE" if mode == "prove" else "BOUNDED"
    except (Unsupported, FrontendUnsupported) as error:
        result.update(status="UNSUPPORTED", reason=str(error))
    except TimeoutError as error:
        result.update(status="UNKNOWN", reason=str(error))
    except (Invalid, OSError, ValueError, KeyError, TypeError) as error:
        result.update(status="ERROR", reason=str(error))
    result["seconds"] = time.monotonic() - started
    (out / "formal.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
