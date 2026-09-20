"""Hand-written, version-bound feasibility models; these are not RTL exports."""

from hashlib import sha256
from pathlib import Path

from .ir import bv, digest, op, ref


def _symbol(kind, width, origin):
    return {"kind": kind, "type": width, "signed": False, "origin": origin}


def _model(name, symbols, init, next_state, observations):
    return {
        "version": 1,
        "name": name,
        "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "clock": {"name": "clk", "edge": "positive"},
        "symbols": symbols,
        "init": init,
        "next": next_state,
        "observe": observations,
    }


def _contract(inputs, observations, property_id, step):
    return {
        "version": 1,
        "semantics": "single-clock-bv-v0",
        "clock": {"name": "clk", "edge": "positive"},
        "reset": None,
        "environment": True,
        "sampling": "before_update",
        "inputs": inputs,
        "observations": observations,
        "property": {"id": property_id, "step": step},
    }


def make_certificate(concrete, abstract, contract, h, J, w):
    return {
        "version": 1,
        "concrete_sha256": digest(concrete),
        "abstract_sha256": digest(abstract),
        "contract_sha256": digest(contract),
        "h": h,
        "J": J,
        "w": w,
    }


def p1():
    x, d, z = ref("x"), ref("d"), ref("z")
    concrete = _model(
        "p1-counter",
        {"x": _symbol("state", 2, "manual.counter.x")},
        op("eq", x, bv(0, 2)),
        {"x": op("ite", op("eq", x, bv(3, 2)), x, op("add", x, bv(1, 2)))},
        {"done": op("ite", op("eq", x, bv(3, 2)), bv(1, 1), bv(0, 1))},
    )
    abstract = _model(
        "p1-done",
        {"d": _symbol("state", 1, "manual.done.d"), "z": _symbol("nondet", 1, "manual.done.z")},
        op("eq", d, bv(0, 1)),
        {"d": op("bvor", d, z)},
        {"done": d},
    )
    contract = _contract(
        {}, {"done": 1}, "done-is-monotonic",
        op("or", op("not", op("eq", ref("o.done"), bv(1, 1))), op("eq", ref("n.done"), bv(1, 1))),
    )
    certificate = make_certificate(
        concrete, abstract, contract,
        {"d": op("ite", op("eq", ref("c.x"), bv(3, 2)), bv(1, 1), bv(0, 1))},
        {"bool": True},
        {"z": op("ite", op("eq", ref("c.x"), bv(2, 2)), bv(1, 1), bv(0, 1))},
    )
    return concrete, abstract, contract, certificate


def p5(kind="hold"):
    if kind not in {"hold", "coarse", "bug"}:
        raise ValueError("P5 kind must be hold, coarse, or bug")
    x, q, v, en, ready, z = map(ref, ("x", "q", "v", "en", "ready", "z"))
    load = op("or", op("eq", v, bv(0, 1)), op("eq", ready, bv(1, 1)))
    transfer = op("and", load, op("eq", en, bv(1, 1)))
    data = op("bvxor", x, bv(3, 2))
    next_v = op("ite", load, en, v)
    next_q = op("ite", op("eq", en, bv(1, 1)) if kind == "bug" else transfer, data, q)
    symbols = {
        "x": _symbol("state", 2, "manual.producer.x"),
        "q": _symbol("state", 2, "manual.producer.q"),
        "v": _symbol("state", 1, "manual.producer.v"),
        "en": _symbol("input", 1, "en"),
        "ready": _symbol("input", 1, "ready"),
    }
    init = op("and", op("eq", q, bv(0, 2)), op("eq", v, bv(0, 1)))
    concrete = _model(
        "p5-producer-bug" if kind == "bug" else "p5-producer",
        symbols, op("and", init, op("eq", x, bv(0, 2))),
        {"x": op("add", x, bv(1, 2)), "q": next_q, "v": next_v},
        {"q": q, "v": v},
    )
    abstract_symbols = {name: dict(symbol) for name, symbol in symbols.items() if name != "x"}
    abstract_symbols["z"] = _symbol("nondet", 2, "manual.abstract_producer.z")
    abstract = _model(
        "p5-hold" if kind == "hold" else "p5-coarse",
        abstract_symbols, init,
        {"q": op("ite", transfer, z, q) if kind == "hold" else z, "v": next_v},
        {"q": q, "v": v},
    )
    contract = _contract(
        {"en": 1, "ready": 1}, {"q": 2, "v": 1}, "hold-while-stalled",
        op("or",
           op("not", op("and", op("eq", ref("o.v"), bv(1, 1)), op("eq", ref("u.ready"), bv(0, 1)))),
           op("and", op("eq", ref("n.v"), bv(1, 1)), op("eq", ref("n.q"), ref("o.q")))),
    )
    witness_data = op("bvxor", ref("c.x"), bv(3, 2))
    witness_load = op("or", op("eq", ref("c.v"), bv(0, 1)), op("eq", ref("u.ready"), bv(1, 1)))
    witness_transfer = op("and", witness_load, op("eq", ref("u.en"), bv(1, 1)))
    witness = witness_data if kind == "hold" else op(
        "ite", op("eq", ref("u.en"), bv(1, 1)) if kind == "bug" else witness_transfer,
        witness_data, ref("c.q"),
    )
    certificate = make_certificate(
        concrete, abstract, contract,
        {"q": ref("c.q"), "v": ref("c.v")}, {"bool": True}, {"z": witness},
    )
    return concrete, abstract, contract, certificate
