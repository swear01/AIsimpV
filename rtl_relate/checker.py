"""Five sufficient simulation obligations, with fail-closed certificate binding."""
from pathlib import Path
import json
import subprocess
import time

from . import __version__
from .ir import (Invalid, Unsupported, digest, emit, expr_type, fields, sort,
                 symbols_of, valid_type, validate_model)
from .solver import identity, query, run


def validate_contract(contract):
    fields(contract, {"version", "semantics", "clock", "reset", "environment", "sampling",
                      "inputs", "observations", "property"}, "contract")
    if (type(contract["version"]) is not int or contract["version"] != 1 or
            contract["semantics"] != "single-clock-bv-v0" or contract["reset"] is not None or
            contract["environment"] is not True or contract["sampling"] != "before_update"):
        raise Unsupported("only v0 single-clock explicit-init E=true before-update semantics supported")
    fields(contract["clock"], {"name", "edge"}, "clock")
    if contract["clock"]["edge"] != "positive" or not isinstance(contract["clock"]["name"], str) or not contract["clock"]["name"]:
        raise Unsupported("one named positive-edge clock required")
    for group in ("inputs", "observations"):
        if not isinstance(contract[group], dict) or group == "observations" and not contract[group]:
            raise Invalid(f"invalid {group}")
        for key, typ in contract[group].items():
            if not isinstance(key, str) or not key:
                raise Invalid(f"invalid {group} name")
            valid_type(typ)
    fields(contract["property"], {"id", "step"}, "property")
    if not isinstance(contract["property"]["id"], str) or not contract["property"]["id"]:
        raise Invalid("property ID required")
    types = {f"{prefix}.{k}": t for prefix in ("o", "n") for k, t in contract["observations"].items()}
    types.update({f"u.{k}": t for k, t in contract["inputs"].items()})
    if expr_type(contract["property"]["step"], types) != "bool":
        raise Invalid("property must be Bool")
    return types


def input_ports(model):
    ports = {}
    for key, symbol in model["symbols"].items():
        if symbol["kind"] == "input":
            if symbol["origin"] in ports:
                raise Invalid("duplicate public port identity")
            ports[symbol["origin"]] = key
    return ports


def validate_interface(model, contract):
    types = validate_model(model)
    if model["clock"] != contract["clock"]:
        raise Invalid("clock differs from frozen contract")
    ports = input_ports(model)
    if {port: types[key] for port, key in ports.items()} != contract["inputs"]:
        raise Invalid("public input interface differs from frozen contract")
    if {key: expr_type(expr, types) for key, expr in model["observe"].items()} != contract["observations"]:
        raise Invalid("observation interface differs from frozen contract")
    return types


def check_contract(concrete, abstract, contract):
    validate_contract(contract)
    return validate_interface(concrete, contract), validate_interface(abstract, contract)


def validate_certificate(concrete, abstract, contract, cert):
    fields(cert, {"version", "concrete_sha256", "abstract_sha256", "contract_sha256", "h", "J", "w"}, "certificate")
    if type(cert["version"]) is not int or cert["version"] != 1:
        raise Unsupported("certificate version")
    for key, obj in (("concrete", concrete), ("abstract", abstract), ("contract", contract)):
        if cert[key + "_sha256"] != digest(obj):
            raise Invalid(f"stale {key} hash")
    cstates = symbols_of(concrete, "state")
    astates = symbols_of(abstract, "state")
    nondet = symbols_of(abstract, "nondet")
    if not isinstance(cert["h"], dict) or set(cert["h"]) != set(astates):
        raise Invalid("h must cover all abstract states exactly")
    if not isinstance(cert["w"], dict) or set(cert["w"]) != set(nondet):
        raise Invalid("w must cover all abstract nondeterminism exactly")
    state_types = {f"c.{key}": typ for key, typ in cstates.items()}
    witness_types = state_types | {f"u.{key}": typ for key, typ in contract["inputs"].items()}
    for key, expr in cert["h"].items():
        if expr_type(expr, state_types) != astates[key]:
            raise Invalid(f"h type mismatch: {key}")
    if expr_type(cert["J"], state_types) != "bool":
        raise Invalid("J must be Bool")
    for key, expr in cert["w"].items():
        if expr_type(expr, witness_types) != nondet[key]:
            raise Invalid(f"w type mismatch: {key}")
    return state_types, witness_types


def conjunction(items):
    return "(and " + " ".join(items) + ")" if items else "true"


def check(concrete, abstract, contract, certificate, out_dir, solver="z3", timeout_ms=5000):
    started = time.perf_counter()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {"status": "ERROR", "checker_version": __version__, "obligations": {}}
    try:
        for key, value in (("concrete", concrete), ("abstract", abstract), ("contract", contract), ("certificate", certificate)):
            report[key + "_sha256"] = digest(value)
            (out / (key + ".json")).write_text(json.dumps(value, indent=2) + "\n")
        if type(timeout_ms) is not int or not 0 < timeout_ms <= 30000:
            raise Invalid("per-query timeout must be 1..30000 ms")
        ct, at = check_contract(concrete, abstract, contract)
        if symbols_of(concrete, "nondet"):
            raise Unsupported("concrete next must be deterministic given registered public inputs")
        st, wt = validate_certificate(concrete, abstract, contract, certificate)
        report.update(concrete_sha256=digest(concrete), abstract_sha256=digest(abstract),
                      contract_sha256=digest(contract), certificate_sha256=digest(certificate),
                      solver=identity(solver), checker_source_sha256=digest({
                          p: Path(__file__).with_name(p).read_text() for p in ("ir.py", "solver.py", "checker.py")}))
        cstates = symbols_of(concrete, "state")
        declarations, cb, ub = [], {}, {}
        for i, (key, typ) in enumerate(cstates.items()):
            cb[key] = f"s{i}"
            declarations.append(f"(declare-fun s{i} () {sort(typ)})")
        for i, (key, typ) in enumerate(contract["inputs"].items()):
            ub[key] = f"u{i}"
            declarations.append(f"(declare-fun u{i} () {sort(typ)})")
        cb.update({key: ub[port] for port, key in input_ports(concrete).items()})
        bindings = {f"c.{key}": cb[key] for key in cstates}
        wbindings = bindings | {f"u.{key}": val for key, val in ub.items()}
        cn = {key: emit(expr, cb, ct) for key, expr in concrete["next"].items()}
        nb = {f"c.{key}": val for key, val in cn.items()}
        hb = {key: emit(expr, bindings, st) for key, expr in certificate["h"].items()}
        wb = {key: emit(expr, wbindings, wt) for key, expr in certificate["w"].items()}
        ab = hb | wb | {key: ub[port] for port, key in input_ports(abstract).items()}
        initial = emit(concrete["init"], cb, ct)
        invariant = emit(certificate["J"], bindings, st)
        report["symbol_bindings"] = {"concrete": cb, "public_inputs": ub}
        obligations = {
            "INIT_J": f"(and {initial} (not {invariant}))",
            "STEP_J": f"(and {invariant} (not {emit(certificate['J'], nb, st)}))",
            "INIT_MAP": f"(and {initial} (not {emit(abstract['init'], hb, at)}))",
            "STEP_MAP": f"(and {invariant} (not " + conjunction([
                f"(= {emit(abstract['next'][key], ab, at)} {emit(expr, nb, st)})"
                for key, expr in certificate["h"].items()]) + "))",
            "OBS_MAP": f"(and {invariant} (not " + conjunction([
                f"(= {emit(abstract['observe'][key], ab, at)} {emit(expr, cb, ct)})"
                for key, expr in concrete["observe"].items()]) + "))",
        }
        row = run(query(declarations, initial, timeout_ms), out, "INITIAL_NONEMPTY", solver, timeout_ms)
        report["obligations"]["INITIAL_NONEMPTY"] = row
        if row["status"] != "sat":
            report["status"] = {"unsat": "CERTIFICATE_REJECTED", "unknown": "UNKNOWN"}.get(row["status"], "ERROR")
            report["reason"] = "concrete initial domain not established nonempty"
        else:
            for name, violation in obligations.items():
                report["obligations"][name] = run(query(declarations, violation, timeout_ms), out, name, solver, timeout_ms)
            statuses = [r["status"] for k, r in report["obligations"].items() if k != "INITIAL_NONEMPTY"]
            report["status"] = ("ERROR" if "error" in statuses else "CERTIFICATE_REJECTED" if "sat" in statuses
                                else "UNKNOWN" if "unknown" in statuses else "ACCEPTED" if all(s == "unsat" for s in statuses)
                                else "ERROR")
    except Unsupported as error:
        report.update(status="UNSUPPORTED", reason=str(error))
    except (Invalid, KeyError, TypeError, ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        report.update(status="ERROR", reason=str(error))
    report["seconds"] = time.perf_counter() - started
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
