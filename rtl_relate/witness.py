"""Recover checked public traces from the trusted SMTBMC harness's Yosys witness."""

import hashlib
import json
from pathlib import Path
import re
import time

from . import solver
from .ir import Invalid, Unsupported, digest, evaluate, load_json, symbols_of
from .properties import _prefix_query, _property_types, _validate


def _initial(model, types):
    values = {}

    def visit(expr):
        if expr.get("op") == "and":
            for arg in expr["args"]:
                visit(arg)
        elif expr.get("op") == "eq":
            left, right = expr["args"]
            if "bv" in left:
                left, right = right, left
            key = left.get("ref")
            if key not in symbols_of(model, "state") or "bv" not in right or key in values:
                raise Unsupported("witness adapter needs one explicit constant assignment per initial state")
            values[key] = right["bv"]
        else:
            raise Unsupported("witness adapter supports only the frontend's constant initial conjunction")

    visit(model["init"])
    if set(values) != set(symbols_of(model, "state")) or not evaluate(model["init"], values, types):
        raise Unsupported("incomplete explicit initialization")
    return values


def _decode(data, module, origins, clock):
    if data.get("format") != "Yosys Witness Trace" or data.get("generator") != "smtbmc":
        raise Invalid("expected a Yosys SMTBMC witness")
    paths = {}
    for origin in [clock, *origins]:
        net = module["netnames"].get(f"dut.{origin}")
        matches = [name for name, port in module["ports"].items()
                   if net is not None and port["direction"] == "input" and port["bits"] == net["bits"]]
        if len(matches) != 1:
            raise Unsupported(f"missing or ambiguous retained DUT input alias: {origin}")
        paths[("\\" + matches[0],)] = (origin, len(net["bits"]))
    clock_path = next(path for path, (name, _) in paths.items() if name == clock)
    if data["clocks"] != [{"path": list(clock_path), "edge": "posedge", "offset": 0}]:
        raise Invalid("witness clock differs from the trusted single-clock harness")
    bit_ids, seen = [], set()
    for signal in data["signals"]:
        path = tuple(signal["path"])
        width, offset, init_only = signal["width"], signal["offset"], signal["init_only"]
        if (not path or any(not isinstance(part, str) for part in path)
                or type(width) is not int or width <= 0 or type(offset) is not int or offset < 0
                or type(init_only) is not bool):
            raise Invalid("invalid witness signal")
        if path not in paths and not init_only:
            raise Unsupported("unexpected non-input witness signal")
        if path in paths and (offset + width > paths[path][1] or init_only):
            raise Invalid("witness input width or sampling differs")
        for bit in range(offset, offset + width):
            if (path, bit) in seen:
                raise Invalid("overlapping witness signals")
            seen.add((path, bit))
            bit_ids.append((path, bit))
    choices, completions = [], []
    for step, item in enumerate(data["steps"]):
        packed = item["bits"]
        if not isinstance(packed, str) or len(packed) > len(bit_ids) or set(packed) - set("01?x"):
            raise Invalid("invalid packed witness bits")
        # Yosys ywio.WitnessValues.unpack enumerates reversed(bits) over signals' LSB-first IDs.
        decoded = dict(zip(bit_ids, reversed(packed)))
        values = {}
        for path, (origin, width) in paths.items():
            if origin == clock:
                continue
            value = 0
            for bit in range(width):
                char = decoded.get((path, bit), "?")
                if char not in "01":
                    completions.append({"step": step, "port": origin, "bit": bit, "value": 0})
                elif char == "1":
                    value |= 1 << bit
            values[origin] = value
        choices.append(values)
    return choices, completions


def extract_counterexample(model, contract, formal_dir, out_dir, *, timeout_ms=5000):
    """Derive outputs from the actual witness inputs, then require A-prefix SAT and P violation.

    Missing witness input bits get a recorded zero completion, accepted only when that
    completed execution independently reproduces the reported frozen-property failure.
    """
    start = time.monotonic()
    formal_dir, out = Path(formal_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "ERROR", "trace_origin": "smtbmc-yw-inputs-and-typed-model"}
    if any(out.iterdir()):
        return {**result, "reason": "output directory must be empty", "seconds": time.monotonic() - start}
    try:
        types, ports = _validate(model, contract)
        report = load_json(formal_dir / "formal.json")
        if report["status"] != "CEX" or report["contract_sha256"] != digest(contract):
            raise Invalid("formal result must be CEX for the same frozen contract")
        for name in ("preprocessed.json", "harness.sv", "source.v"):
            actual = hashlib.sha256((formal_dir / name).read_bytes()).hexdigest()
            if actual != report["hashes"][name]:
                raise Invalid(f"stale formal artifact: {name}")
        log = (formal_dir / "base.stdout.log").read_text()
        checked = re.findall(r"Checking assertions in step (\d+)\.\.", log)
        if not checked or "Status: FAILED" not in log:
            raise Invalid("no failed SMTBMC base step in retained log")
        failed_step = int(checked[-1])
        if failed_step < 1 or report.get("counterexample_step", failed_step) != failed_step:
            raise Invalid("formal failure step and trusted edge monitor disagree")
        data = load_json(formal_dir / "base.yw")
        module = load_json(formal_dir / "preprocessed.json")["modules"]["__rtl_relate_property"]
        choices_by_origin = {s["origin"]: key for key, s in model["symbols"].items() if s["kind"] != "state"}
        if len(choices_by_origin) != len(types) - len(symbols_of(model, "state")):
            raise Invalid("ambiguous model input origins")
        choices, completions = _decode(data, module, choices_by_origin, contract["clock"]["name"])
        if len(choices) <= failed_step:
            raise Invalid("witness omits the reported failing sample")
        state = _initial(model, types)
        observed = lambda value: {key: evaluate(expr, value, types) for key, expr in model["observe"].items()}
        trace = {"inputs": [], "observations": [observed(state)]}
        for choice in choices[:failed_step]:
            values = {**state, **{key: choice[origin] for origin, key in choices_by_origin.items()}}
            trace["inputs"].append({port: choice[port] for port in contract["inputs"]})
            state = {key: evaluate(expr, values, types) for key, expr in model["next"].items()}
            trace["observations"].append(observed(state))
        index = failed_step - 1
        prop_values = {**{f"o.{key}": value for key, value in trace["observations"][index].items()},
                       **{f"n.{key}": value for key, value in trace["observations"][index + 1].items()},
                       **{f"u.{key}": value for key, value in trace["inputs"][index].items()}}
        result.update(formal_counterexample_step=failed_step, violation_step=index,
                      completed_input_bits=[c for c in completions if c["step"] < failed_step],
                      provenance={"model_sha256": digest(model), "contract_sha256": digest(contract),
                                  "formal_source_sha256": report["source_sha256"],
                                  "formal_report_sha256": hashlib.sha256((formal_dir / "formal.json").read_bytes()).hexdigest(),
                                  "witness_sha256": hashlib.sha256((formal_dir / "base.yw").read_bytes()).hexdigest(),
                                  "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        if evaluate(contract["property"]["step"], prop_values, _property_types(contract)):
            raise Unsupported("completed witness does not reproduce the reported property violation")
        validation = solver.run(_prefix_query(model, types, ports, trace, timeout_ms), out,
                                "abstract_prefix", timeout_ms=timeout_ms)
        result["validation"] = validation
        if validation["status"] != "sat":
            raise Unsupported("abstract prefix feasibility not established")
        result.update(status="VALIDATED", trace=trace, property_violated=True,
                      nondet_choices=[{name: choice[name] for name, key in choices_by_origin.items()
                                       if model["symbols"][key]["kind"] == "nondet"}
                                      for choice in choices[:failed_step]])
        (out / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    except Unsupported as error:
        result.update(status="UNRESOLVED", reason=str(error))
    except (Invalid, OSError, ValueError, KeyError, TypeError) as error:
        result.update(status="ERROR", reason=str(error))
    result["seconds"] = time.monotonic() - start
    (out / "witness.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
