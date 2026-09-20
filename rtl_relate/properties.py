"""Free-choice safety checks and exact concrete prefix replay, without certificates."""

from collections import deque
from itertools import product
from pathlib import Path
import json
import time

from . import solver as smt
from .ir import (Invalid, Unsupported, digest, emit, evaluate, expr_type, fields,
                 literal, sort, symbols_of)


# ponytail: tiny finite closure only; add a symbolic reachability backend for larger domains.
MAX_DOMAIN = 65536
MAX_TRANSITIONS = 100000


def _validate(model, contract):
    from .checker import input_ports, validate_contract, validate_interface

    validate_contract(contract)
    types = validate_interface(model, contract)
    states = symbols_of(model, "state")
    for expr in model["observe"].values():
        try:
            expr_type(expr, states)
        except Invalid as error:
            raise Unsupported("property/replay v0 requires Moore observations") from error
    return types, input_ports(model)


def _variables(types, prefix):
    bindings = {key: f"{prefix}_{index}" for index, key in enumerate(types)}
    return bindings, [f"(declare-fun {bindings[key]} () {sort(typ)})" for key, typ in types.items()]


def _property_types(contract):
    return {**{f"{prefix}.{key}": typ for prefix in ("o", "n") for key, typ in contract["observations"].items()},
            **{f"u.{key}": typ for key, typ in contract["inputs"].items()}}


def _finish(result, start, out_dir, name):
    result["seconds"] = time.perf_counter() - start
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    return result


def _domain(types):
    return (dict(zip(types, values)) for values in product(
        *((False, True) if typ == "bool" else range(1 << typ) for typ in types.values())))


def _closure(model, contract, types, ports, timeout_ms):
    states = symbols_of(model, "state")
    choices = {key: typ for key, typ in types.items() if key not in states}
    bits = sum(1 if typ == "bool" else typ for typ in types.values())
    if bits > MAX_DOMAIN.bit_length() or 1 << bits > MAX_DOMAIN:
        return {"status": "UNKNOWN", "reason": "finite-domain cap exceeded"}
    deadline = time.perf_counter() + timeout_ms / 1000
    prop_types = _property_types(contract)
    observed = lambda state: {key: evaluate(expr, state, types) for key, expr in model["observe"].items()}
    key_of = lambda state: tuple(state[key] for key in states)
    state_of = lambda key: dict(zip(states, key))
    parents = {key_of(state): None for state in _domain(states) if evaluate(model["init"], state, types)}
    if not parents:
        raise Invalid("SMT and finite initial-domain checks disagree")
    pending = deque(parents)
    transitions = 0
    while pending:
        key = pending.popleft()
        state = state_of(key)
        before = observed(state)
        for choice in _domain(choices):
            if transitions >= MAX_TRANSITIONS or time.perf_counter() > deadline:
                return {"status": "UNKNOWN", "reason": "finite-closure budget exhausted",
                        "transitions": transitions, "reachable_states": len(parents)}
            transitions += 1
            values = {**state, **choice}
            following = {name: evaluate(expr, values, types) for name, expr in model["next"].items()}
            after = observed(following)
            inputs = {port: choice[symbol] for port, symbol in ports.items()}
            prop_values = {**{f"o.{name}": value for name, value in before.items()},
                           **{f"n.{name}": value for name, value in after.items()},
                           **{f"u.{name}": value for name, value in inputs.items()}}
            if not evaluate(contract["property"]["step"], prop_values, prop_types):
                trace_inputs, observations = [inputs], [before, after]
                cursor = key
                while parents[cursor] is not None:
                    cursor, previous_inputs = parents[cursor]
                    trace_inputs.insert(0, previous_inputs)
                    observations.insert(0, observed(state_of(cursor)))
                return {"status": "ABSTRACT_CEX", "trace": {"inputs": trace_inputs, "observations": observations},
                        "transitions": transitions, "reachable_states": len(parents)}
            next_key = key_of(following)
            if next_key not in parents:
                parents[next_key] = (key, inputs)
                pending.append(next_key)
    return {"status": "SAFE", "transitions": transitions, "reachable_states": len(parents)}


def check_property(model, contract, out_dir, solver="z3", timeout_ms=5000):
    """Prove every edge safe, or exhaust the reachable closure; never constrain z by w."""
    start = time.perf_counter()
    result = {"status": "ERROR", "queries": [], "free_nondeterminism": True}
    try:
        types, ports = _validate(model, contract)
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise Invalid("positive integer timeout required")
        result.update(model_sha256=digest(model), contract_sha256=digest(contract),
                      nondet_symbols=list(symbols_of(model, "nondet")))
        bindings, declarations = _variables(types, "s")
        initial = smt.run(smt.query(declarations, emit(model["init"], bindings, types), timeout_ms),
                          out_dir, "property_initial", solver, timeout_ms)
        result["queries"].append(initial)
        if initial["status"] != "sat":
            result.update(status="UNKNOWN" if initial["status"] == "unknown" else "ERROR",
                          reason="empty initial set" if initial["status"] == "unsat" else "initial-domain solver failure")
        else:
            next_bindings = {key: emit(expr, bindings, types) for key, expr in model["next"].items()}
            prop_bindings = {**{f"o.{key}": emit(expr, bindings, types) for key, expr in model["observe"].items()},
                             **{f"n.{key}": emit(expr, next_bindings, types) for key, expr in model["observe"].items()},
                             **{f"u.{port}": bindings[symbol] for port, symbol in ports.items()}}
            violation = f"(not {emit(contract['property']['step'], prop_bindings, _property_types(contract))})"
            step = smt.run(smt.query(declarations, violation, timeout_ms), out_dir, "property_step", solver, timeout_ms)
            result["queries"].append(step)
            result["method"] = "all-state one-step"
            if step["status"] == "unsat":
                result["status"] = "SAFE"
            elif step["status"] == "sat":
                result["method"] = "complete finite reachable closure"
                result.update(_closure(model, contract, types, ports, timeout_ms))
            else:
                result.update(status="UNKNOWN" if step["status"] == "unknown" else "ERROR",
                              reason="property-step solver failure")
    except Unsupported as error:
        result.update(status="UNSUPPORTED", reason=str(error))
    except (Invalid, ValueError, TypeError, KeyError, OSError) as error:
        result.update(status="ERROR", reason=str(error))
    return _finish(result, start, out_dir, "property")


def _validate_trace(trace, contract):
    fields(trace, {"inputs", "observations"}, "trace")
    if not isinstance(trace["inputs"], list) or not isinstance(trace["observations"], list):
        raise Invalid("trace inputs and observations must be lists")
    if len(trace["observations"]) != len(trace["inputs"]) + 1:
        raise Invalid("trace must contain one more observation than input")
    for category in ("inputs", "observations"):
        schema = contract[category]
        for values in trace[category]:
            fields(values, schema, f"trace {category}")
            for key, typ in schema.items():
                value = values[key]
                if typ == "bool":
                    if type(value) is not bool:
                        raise Invalid(f"trace {key}: expected Bool")
                elif type(value) is not int or not 0 <= value < 1 << typ:
                    raise Invalid(f"trace {key}: BV value out of range")


def _prefix_query(model, types, ports, trace, timeout_ms):
    """One independent state and free choice namespace per sampled step."""
    declarations, constraints, previous = [], [], None
    states = symbols_of(model, "state")
    for index, observations in enumerate(trace["observations"]):
        step_types = types if index < len(trace["inputs"]) else states
        bindings, declared = _variables(step_types, f"t{index}")
        declarations.extend(declared)
        if previous is None:
            constraints.append(emit(model["init"], bindings, types))
        else:
            constraints.extend(f"(= {bindings[key]} {emit(expr, previous, types)})"
                               for key, expr in model["next"].items())
        constraints.extend(f"(= {emit(model['observe'][key], bindings, types)} "
                           f"{literal(value, expr_type(model['observe'][key], types))})"
                           for key, value in observations.items())
        if index < len(trace["inputs"]):
            constraints.extend(f"(= {bindings[ports[key]]} {literal(value, types[ports[key]])})"
                               for key, value in trace["inputs"][index].items())
        previous = bindings
    return smt.query(declarations, "(and " + " ".join(constraints) + ")", timeout_ms)


def replay(model, contract, trace, out_dir, solver="z3", timeout_ms=5000):
    """Fix only public inputs and observations; SAT is exact-prefix feasibility, not BUG."""
    start = time.perf_counter()
    result = {"status": "ERROR", "queries": []}
    try:
        types, ports = _validate(model, contract)
        if symbols_of(model, "nondet"):
            raise Unsupported("concrete replay v0 excludes concrete nondeterminism")
        _validate_trace(trace, contract)
        if type(timeout_ms) is not int or timeout_ms <= 0:
            raise Invalid("positive integer timeout required")
        result.update(model_sha256=digest(model), contract_sha256=digest(contract), trace_sha256=digest(trace))
        query = smt.run(_prefix_query(model, types, ports, trace, timeout_ms), out_dir, "replay_prefix", solver, timeout_ms)
        result["queries"].append(query)
        result["status"] = {"sat": "FEASIBLE", "unsat": "INFEASIBLE", "unknown": "UNKNOWN", "error": "ERROR"}[query["status"]]
    except Unsupported as error:
        result.update(status="UNSUPPORTED", reason=str(error))
    except (Invalid, ValueError, TypeError, KeyError, OSError) as error:
        result.update(status="ERROR", reason=str(error))
    return _finish(result, start, out_dir, "replay")
