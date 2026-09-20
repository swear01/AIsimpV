"""Authored skidbuffer rewrites, certificates, and independent trace probes."""

from pathlib import Path

from .fixtures import make_certificate
from .frontend import export_rtl
from .ir import Invalid, bv, load_json, op, ref


ROOT = Path(__file__).resolve().parents[1]


def make_skid_certificate(concrete, abstract, contract, variant="good"):
    """Bind the authored relation to exact typed exporter identities."""
    if variant not in {"good", "coarse", "bad_certificate"}:
        raise ValueError("variant must be good, coarse, or bad_certificate")
    width = contract["inputs"]["i_data"]

    def symbol(model, origin, kind, bits):
        matches = [key for key, value in model["symbols"].items()
                   if value["origin"] == origin and value["kind"] == kind
                   and value["type"] == bits and value["signed"] is False]
        if len(matches) != 1:
            raise Invalid(f"expected one unsigned {kind} {origin} of width {bits}")
        return matches[0]

    r, v, b, q = [symbol(concrete, origin, "state", bits) for origin, bits in (
        ("LOGIC.r_valid", 1), ("LOGIC.REG_OUTPUT.ro_valid", 1),
        ("LOGIC.r_data", width), ("o_data", width))]
    n = symbol(abstract, "n", "state", 2)
    aq = symbol(abstract, "o_data", "state", width)
    z = symbol(abstract, "z", "nondet", width)
    cr, cv, cb, cq = [ref("c." + key) for key in (r, v, b, q)]
    r_set, v_set = op("eq", cr, bv(1, 1)), op("eq", cv, bv(1, 1))
    occupancy = op("ite", r_set, bv(2, 2), op("ite", v_set, bv(1, 2), bv(0, 2)))
    invariant = op("or", op("not", r_set), v_set)
    witness = cb
    if variant == "coarse":
        load = op("or", op("not", v_set), op("eq", ref("u.i_ready"), bv(1, 1)))
        witness = op("ite", load, op("ite", r_set, cb, ref("u.i_data")), cq)
    elif variant == "bad_certificate":
        witness = bv(0, width)
    return make_certificate(concrete, abstract, contract, {n: occupancy, aq: cq},
                            invariant, {z: witness})


def trace_probes():
    """Hand-authored traces; each requires independent prefix SAT/replay checks."""
    def inputs(valid, ready, data, reset=0):
        return {"i_valid": valid, "i_ready": ready, "i_data": data, "i_reset": reset}

    def observed(n, data):
        return {"o_ready": int(n != 2), "o_valid": int(n != 0), "o_data": data}

    cover = {
        "inputs": [inputs(1, 0, 0x12), inputs(1, 0, 0x34), inputs(0, 0, 0x56),
                   inputs(0, 1, 0x78), inputs(0, 0, 0x9a, 1), inputs(0, 0, 0xbc)],
        "observations": [observed(0, 0), observed(1, 0x12), observed(2, 0x12),
                         observed(2, 0x12), observed(1, 0x34), observed(0, 0x34),
                         observed(0, 0xbc)],
    }
    strict = {
        "inputs": [inputs(1, 0, 0x12), inputs(1, 0, 0x34), inputs(0, 1, 0x78)],
        "observations": [observed(0, 0), observed(1, 0x12), observed(2, 0x12),
                         observed(1, 0x56)],
    }
    coarse = {
        "inputs": [inputs(1, 0, 0x12), inputs(0, 0, 0x34)],
        "observations": [observed(0, 0), observed(1, 0x12), observed(1, 0x34)],
    }
    return {"cover_trace": cover, "strictness_trace": strict, "coarse_counterexample": coarse}


def prepare_case(width, variant, out_dir):
    """Export the fixed public C and selected A; leave proof/timing to the runner."""
    if type(width) is not int or width not in {8, 32}:
        raise ValueError("the frozen skidbuffer tasks have width 8 or 32")
    if variant not in {"good", "coarse", "bad_certificate"}:
        raise ValueError("variant must be good, coarse, or bad_certificate")
    out = Path(out_dir)
    concrete_source = ROOT / "fixtures/public/upstream/skidbuffer.v"
    abstract_source = ROOT / "fixtures/public/skidbuffer/skid_abstract.v"
    task = "r2_skid8" if width == 8 else "r3_skid32"
    contract = load_json(ROOT / "fixtures/contracts" / (task + ".json"))
    cparams = {"DW": width, "OPT_OUTREG": 1, "OPT_LOWPOWER": 0,
               "OPT_PASSTHROUGH": 0, "OPT_INITIAL": 1}
    aparams = {"DW": width, "COARSE": int(variant == "coarse")}
    concrete = export_rtl(concrete_source, "skidbuffer", out / "concrete",
                          clock="i_clk", parameters=cparams)
    abstract = export_rtl(abstract_source, "skid_abstract", out / "abstract",
                          clock="i_clk", nondet=("z",), parameters=aparams)
    certificate = make_skid_certificate(concrete, abstract, contract, variant)
    return {
        "task_id": "R2-skid8" if width == 8 else "R3-skid32", "variant": variant,
        "concrete": concrete, "abstract": abstract, "contract": contract,
        "certificate": certificate,
        "concrete_source": out / "concrete/normalized.v",
        "abstract_source": out / "abstract/normalized.v",
        "concrete_top": "skidbuffer", "abstract_top": "skid_abstract",
        "concrete_parameters": {}, "abstract_parameters": {},
        "nondet": ("z",), "trace_origin": "hand-authored",
        "frontend_seconds": sum(load_json(out / role / "frontend.json")["wall_seconds"]
                                for role in ("concrete", "abstract")),
        **trace_probes(),
    }
