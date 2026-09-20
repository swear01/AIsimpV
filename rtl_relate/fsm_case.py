"""R1 hand-written RTL re-encoding and its positive/negative certificates."""

import json
from pathlib import Path
import time

from .fixtures import make_certificate
from .frontend import export_rtl
from .ir import bv, op, ref, symbols_of


ROOT = Path(__file__).resolve().parents[1]


def _state(model):
    states = symbols_of(model, "state")
    if len(states) != 1:
        raise ValueError("FSM fixture must export exactly one state")
    key = next(iter(states))
    if model["symbols"][key]["origin"] != "state":
        raise ValueError("FSM state origin differs from the expected manifest")
    return key


def _encode(state):
    return op("ite", op("eq", state, bv(2, 3)), bv(1, 2),
              op("ite", op("eq", state, bv(4, 3)), bv(2, 2), bv(0, 2)))


def prepare_case(variant, out_dir):
    """Export the actual RTL and bind a certificate to the frozen R1 contract."""
    if variant not in {"good", "coarse", "bad_certificate"}:
        raise ValueError("FSM variant must be good, coarse, or bad_certificate")
    out_dir = Path(out_dir)
    directory = ROOT / "fixtures/public/fsm"
    concrete_source = directory / "concrete.v"
    abstract_kind = "coarse" if variant == "coarse" else "good"
    abstract_source = directory / f"{abstract_kind}.v"
    nondet = ["z"] if variant == "coarse" else []
    started = time.perf_counter()
    concrete = export_rtl(concrete_source, "fsm_concrete", out_dir / "concrete")
    abstract = export_rtl(abstract_source, "fsm_" + abstract_kind, out_dir / "abstract", nondet=nondet)
    frontend_seconds = time.perf_counter() - started
    contract = json.loads((ROOT / "fixtures/contracts/r1_fsm.json").read_text())
    ckey, akey = _state(concrete), _state(abstract)
    state = ref("c." + ckey)
    legal = op("or", op("eq", state, bv(1, 3)), op("eq", state, bv(2, 3)))
    if variant != "bad_certificate":
        legal = op("or", legal, op("eq", state, bv(4, 3)))
    witness = {}
    if variant == "coarse":
        next_state = op("ite", op("eq", ref("u.advance"), bv(1, 1)),
                        op("ite", op("eq", state, bv(1, 3)), bv(2, 3),
                           op("ite", op("eq", state, bv(2, 3)), bv(4, 3), bv(1, 3))), state)
        zkey, = symbols_of(abstract, "nondet")
        witness[zkey] = _encode(next_state)
    certificate = make_certificate(concrete, abstract, contract, {akey: _encode(state)}, legal, witness)
    result = {
        "task_id": "R1-fsm", "concrete": concrete, "abstract": abstract,
        "contract": contract, "certificate": certificate,
        "concrete_source": str(concrete_source), "abstract_source": str(abstract_source),
        "concrete_top": "fsm_concrete", "abstract_top": "fsm_" + abstract_kind,
        "concrete_parameters": {}, "abstract_parameters": {}, "nondet": nondet,
        "frontend_seconds": frontend_seconds,
        "concrete_cover_trace": {
            "inputs": [{"advance": value} for value in (0, 1, 1, 1)],
            "observations": [dict(zip(("idle", "busy", "done"), values)) for values in
                             ((1, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))],
        },
    }
    if variant == "good":
        astate = ref("c." + akey)
        reverse_h = op("ite", op("eq", astate, bv(0, 2)), bv(1, 3),
                       op("ite", op("eq", astate, bv(1, 2)), bv(2, 3), bv(4, 3)))
        result["reverse_certificate"] = make_certificate(
            abstract, concrete, contract, {ckey: reverse_h}, op("ule", astate, bv(2, 2)), {})
    if variant == "coarse":
        result["coarse_counterexample"] = {
            "inputs": [{"advance": 0}, {"advance": 0}],
            "observations": [{"idle": 1, "busy": 0, "done": 0},
                             {"idle": 0, "busy": 0, "done": 0},
                             {"idle": 0, "busy": 0, "done": 0}],
        }
    return result
