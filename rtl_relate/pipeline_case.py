"""Authored R4 pipeline rewrites, bound only after actual RTL export."""

import json
from pathlib import Path

from .fixtures import make_certificate
from .frontend import export_rtl
from .ir import op, ref


ROOT = Path(__file__).resolve().parents[1]


def _symbol(model, origin, kind, width=32):
    matches = [key for key, symbol in model["symbols"].items()
               if symbol["origin"] == origin and symbol["kind"] == kind
               and symbol["type"] == width and symbol["signed"] is False]
    if len(matches) != 1:
        raise ValueError(f"expected one unsigned {kind} {origin}:{width}")
    return matches[0]


def prepare_case(variant, out_dir):
    """Return exported models, certificate, proof inputs and authored trace probes."""
    if variant not in {"good", "coarse", "bad_certificate"}:
        raise ValueError("pipeline variant must be good, coarse, or bad_certificate")
    out = Path(out_dir)
    concrete_source = ROOT / "fixtures/public/upstream/pipeline.v"
    abstract_top = "pipeline_coarse" if variant == "coarse" else "pipeline_good"
    abstract_source = ROOT / "fixtures/public/pipeline" / (abstract_top + ".v")
    contract = json.loads((ROOT / "fixtures/contracts/r4_pipe32.json").read_text())
    nondet = ("z", "z2") if variant == "coarse" else ("z",)
    concrete = export_rtl(concrete_source, "main", out / "concrete",
                          clock="clock", profile="avr_pipeline32")
    abstract = export_rtl(abstract_source, abstract_top, out / "abstract",
                          clock="clock", nondet=nondet)

    a = ref("c." + _symbol(concrete, "stageOne", "state"))
    b = ref("c." + _symbol(concrete, "stageTwo", "state"))
    h = {_symbol(abstract, "sum", "state"):
         a if variant == "bad_certificate" else op("add", a, b)}
    for origin in ("dataOut", "tmp_stageOne", "tmp_stageTwo"):
        h[_symbol(abstract, origin, "state")] = ref("c." + _symbol(concrete, origin, "state"))
    w = {_symbol(abstract, "z", "nondet"): a}
    if variant == "coarse":
        w[_symbol(abstract, "z2", "nondet")] = b
    certificate = make_certificate(concrete, abstract, contract, h, {"bool": True}, w)
    frontend_seconds = sum(json.loads((out / role / "frontend.json").read_text())["wall_seconds"]
                           for role in ("concrete", "abstract"))

    # Both probes are authored examples; the runner must verify A SAT and C UNSAT.
    zero = {"dataOut": 0, "tmp_stageOne": 0, "tmp_stageTwo": 0}
    inputs = {"dataIn": 0, "c1": 0, "c2": 0, "reset": 0}
    strictness = {"inputs": [inputs], "observations": [zero,
                  {"dataOut": 0, "tmp_stageOne": 1, "tmp_stageTwo": 0xffffffff}]}
    coarse_cex = {"inputs": [dict(inputs, dataIn=1), inputs, inputs],
                  "observations": [zero, zero,
                                   {"dataOut": 1, "tmp_stageOne": 0, "tmp_stageTwo": 0}, zero]}
    cover = {"inputs": [dict(inputs, dataIn=0xffffffff, c1=1, c2=0xffffffff),
                        dict(inputs, dataIn=5, c2=0xffffffff),
                        dict(inputs, dataIn=7, c2=0xffffffff, reset=1),
                        dict(inputs, c2=0xffffffff)],
             "observations": [zero, zero, zero,
                              {"dataOut": 0, "tmp_stageOne": 5, "tmp_stageTwo": 0},
                              {"dataOut": 12, "tmp_stageOne": 7, "tmp_stageTwo": 5}]}
    return {"task_id": "R4-pipe32", "concrete": concrete, "abstract": abstract,
            "contract": contract, "certificate": certificate,
            "concrete_source": out / "concrete/normalized.v", "abstract_source": abstract_source,
            "concrete_top": "main", "abstract_top": abstract_top,
            "concrete_parameters": {}, "abstract_parameters": {}, "nondet": nondet,
            "frontend_seconds": frontend_seconds, "strictness_trace": strictness,
            "coarse_counterexample": coarse_cex if variant == "coarse" else None,
            "concrete_cover_trace": cover}
