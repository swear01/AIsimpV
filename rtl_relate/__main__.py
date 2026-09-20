"""Reproducible feasibility experiments and a data-file certificate-check command."""
import argparse
import csv
import json
from pathlib import Path
import platform
import subprocess
import time

from .checker import check, input_ports, validate_interface
from .fixtures import make_certificate, p1, p5
from .frontend import export_rtl
from .ir import digest, evaluate, load_json, op, ref, bv, symbols_of
from .properties import _prefix_query, _validate_trace, check_property, replay
from .solver import identity, run


ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def rtl_pair(case, out, contract, template):
    tops = {"p1": ("p1_concrete", "p1_abstract"), "p5_hold": ("p5_concrete", "p5_hold"),
            "p5_coarse": ("p5_concrete", "p5_coarse"), "p5_bug": ("p5_bug", "p5_coarse")}[case]
    models = [export_rtl(ROOT / "fixtures/rtl" / (top + ".v"), top, out / role,
                         nondet=("z",) if role == "abstract" else (), clock=contract["clock"]["name"])
              for role, top in zip(("concrete", "abstract"), tops)]
    c, a = models
    names = [{symbol["origin"]: key for key, symbol in model["symbols"].items()}
             for model in models]

    def bind(expr):
        if "ref" in expr and expr["ref"].startswith("c."):
            return ref("c." + names[0][expr["ref"][2:]])
        return {key: [bind(arg) for arg in value] if key == "args" else value for key, value in expr.items()}

    # This is an authored gold-certificate template, not inferred name-based equivalence.
    certificate = make_certificate(c, a, contract,
        {names[1][key]: bind(expr) for key, expr in template["h"].items()}, bind(template["J"]),
        {names[1][key]: bind(expr) for key, expr in template["w"].items()})
    costs = [load_json(out / role / "frontend.json")["wall_seconds"] for role in ("concrete", "abstract")]
    return c, a, certificate, costs


def violates(trace, contract):
    _validate_trace(trace, contract)
    types = {f"{prefix}.{key}": typ for prefix in ("o", "n") for key, typ in contract["observations"].items()}
    types.update({f"u.{key}": typ for key, typ in contract["inputs"].items()})
    for index, inputs in enumerate(trace["inputs"]):
        values = {f"o.{key}": val for key, val in trace["observations"][index].items()}
        values.update({f"n.{key}": val for key, val in trace["observations"][index + 1].items()})
        values.update({f"u.{key}": val for key, val in inputs.items()})
        if not evaluate(contract["property"]["step"], values, types):
            return True
    return False


def trace_in_abstract(model, contract, trace, out):
    types = validate_interface(model, contract)
    _validate_trace(trace, contract)
    return run(_prefix_query(model, types, input_ports(model), trace, 5000), out, "abstract_trace")


def experiment(stage, case, factory, root):
    started = time.perf_counter()
    out = root / stage / case
    out.mkdir(parents=True)
    c, a, contract, certificate = factory()
    frozen = load_json(ROOT / "fixtures/contracts" / ("p1.json" if case == "p1" else "p5.json"))
    if digest(frozen) != digest(contract):
        raise ValueError("fixture differs from frozen contract")
    costs = [0.0, 0.0]
    if stage == "rtl":
        c, a, certificate, costs = rtl_pair(case, out / "frontend", contract, certificate)
    gate = check(c, a, contract, certificate, out / "certificate")
    row = {"stage": stage, "case": case, "gate": gate["status"], "status": gate["status"],
           "concrete_bits": sum(symbols_of(c, "state").values()),
           "abstract_bits": sum(symbols_of(a, "state").values()),
           "contract_sha256": digest(contract), "concrete_sha256": digest(c), "abstract_sha256": digest(a),
           "certificate_sha256": digest(certificate), "frontend_seconds": sum(costs),
           "certificate_seconds": gate["seconds"], "abstract_property_seconds": 0.0,
           "replay_seconds": 0.0, "concrete_search_seconds": 0.0, "strictness_seconds": 0.0}
    if gate["status"] != "ACCEPTED":
        row.update(total_machine_seconds=sum(costs) + gate["seconds"], wall_seconds=time.perf_counter() - started)
        save(out / "result.json", row)
        return row
    abstract_result = check_property(a, contract, out / "abstract_property")
    baseline = check_property(c, contract, out / "direct_concrete")
    row.update(abstract_property=abstract_result["status"], concrete_property=baseline["status"],
               abstract_property_seconds=abstract_result["seconds"],
               b0_seconds=costs[0] + baseline["seconds"],
               status=abstract_result["status"])
    if abstract_result["status"] == "ABSTRACT_CEX":
        trace = abstract_result["trace"]
        save(out / "abstract_trace.json", trace)
        result = replay(c, contract, trace, out / "abstract_replay")
        row.update(abstract_replay=result["status"], replay_seconds=result["seconds"])
        if result["status"] == "FEASIBLE" and violates(trace, contract):
            row.update(status="BUG", bug_source="exact abstract trace replay")
        elif result["status"] == "INFEASIBLE":
            row["status"] = "SPURIOUS_TRACE"
            row["concrete_search_seconds"] = baseline["seconds"]
            if baseline["status"] == "ABSTRACT_CEX":
                concrete_trace = baseline["trace"]
                save(out / "different_concrete_bug_trace.json", concrete_trace)
                concrete_result = replay(c, contract, concrete_trace, out / "concrete_bug_replay")
                row["replay_seconds"] += concrete_result["seconds"]
                row["concrete_bug_replay"] = concrete_result["status"]
                if concrete_result["status"] == "FEASIBLE" and violates(concrete_trace, contract):
                    row.update(status="BUG", bug_source="different trace from exact concrete search")
        else:
            row["status"] = "UNRESOLVED"
    if case == "p1":
        trace = {"inputs": [{}], "observations": [{"done": 0}, {"done": 1}]}
        save(out / "early_done_trace.json", trace)
        at = trace_in_abstract(a, contract, trace, out / "strictness")
        ct = replay(c, contract, trace, out / "strictness/concrete")
        row["strictness"] = {"abstract": at["status"], "concrete": ct["status"]}
    elif case == "p5_hold":
        trace = {"inputs": [{"en": 1, "ready": 1}], "observations": [{"v": 0, "q": 0}, {"v": 1, "q": 0}]}
        save(out / "extra_abstract_trace.json", trace)
        at = trace_in_abstract(a, contract, trace, out / "strictness")
        ct = replay(c, contract, trace, out / "strictness/concrete")
        row["strictness"] = {"abstract": at["status"], "concrete": ct["status"]}
    if "strictness" in row:
        row["strictness_seconds"] = at["seconds"] + ct["seconds"]
    row["total_machine_seconds"] = sum(row[key] for key in (
        "frontend_seconds", "certificate_seconds", "abstract_property_seconds", "replay_seconds", "concrete_search_seconds", "strictness_seconds"))
    row["wall_seconds"] = time.perf_counter() - started
    save(out / "result.json", row)
    return row


def mutations(root):
    rows = []
    names = ("wrong_init", "wrong_step", "wrong_observation", "wrong_witness", "false_J",
             "noninductive_J", "missing_mapping", "wrong_width", "stale_hash", "empty_initial")
    for name in names:
        c, a, k, cert = p1()
        truth = "correct abstraction, invalid certificate"
        if name == "wrong_init": a["init"] = op("eq", ref("d"), bv(1, 1))
        elif name == "wrong_step": a["next"]["d"] = ref("d")
        elif name == "wrong_observation": a["observe"]["done"] = op("bvnot", ref("d"))
        elif name == "wrong_witness": cert["w"]["z"] = bv(0, 1)
        elif name == "false_J": cert["J"] = {"bool": False}
        elif name == "noninductive_J":
            cert["J"] = op("ult", ref("c.x"), bv(2, 2))
            cert["w"]["z"] = bv(0, 1)
        elif name == "missing_mapping": cert["h"] = {}
        elif name == "wrong_width": cert["w"]["z"] = bv(0, 2)
        elif name == "empty_initial": c["init"] = {"bool": False}
        if name in {"wrong_init", "wrong_step", "wrong_observation"}:
            truth = "invalid abstraction"
        elif name == "empty_initial": truth = "invalid concrete initial domain"
        cert.update(concrete_sha256=digest(c), abstract_sha256=digest(a))
        if name == "stale_hash": cert["contract_sha256"] = "0" * 64
        result = check(c, a, k, cert, root / "mutations" / name)
        expected = "ERROR" if name in {"missing_mapping", "wrong_width", "stale_hash"} else "CERTIFICATE_REJECTED"
        rows.append({"case": name, "ground_truth": truth, "expected": expected,
                     "status": result["status"], "seconds": result["seconds"]})
    return rows


def demo(out):
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True)
        git_head = revision.stdout.strip() if revision.returncode == 0 else None
    except FileNotFoundError:
        git_head = None
    provenance = {"python": platform.python_version(), "platform": platform.platform(), "solver": identity(),
                  "git_head": git_head,
                  "code_sha256": digest({str(p.relative_to(ROOT)): p.read_text() for p in sorted((ROOT / "rtl_relate").glob("*.py"))}),
                  "claim": "Manual gold feasibility; no LLM or speedup experiment"}
    save(out / "environment.json", provenance)
    rows = []
    for stage in ("manual", "rtl"):
        for case, factory in (("p1", p1), ("p5_hold", lambda: p5("hold")),
                              ("p5_coarse", lambda: p5("coarse")), ("p5_bug", lambda: p5("bug"))):
            case_started = time.perf_counter()
            try:
                row = experiment(stage, case, factory, out)
            except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
                row = {"stage": stage, "case": case, "status": "ERROR", "reason": str(error),
                       "wall_seconds": time.perf_counter() - case_started}
                save(out / stage / case / "result.json", row)
            rows.append(row)
            print(f"{stage:6} {case:10} {row.get('gate', '-'):10} {row['status']}", flush=True)
    negative = mutations(out)
    expected = {"p1": "SAFE", "p5_hold": "SAFE", "p5_coarse": "SPURIOUS_TRACE", "p5_bug": "BUG"}
    success = all(row["status"] == expected[row["case"]] for row in rows) and all(row["status"] == row["expected"] for row in negative)
    success = success and all(row.get("strictness") == {"abstract": "sat", "concrete": "INFEASIBLE"}
                              for row in rows if row["case"] in {"p1", "p5_hold"})
    summary = {"success": success, "rows": rows, "mutations": negative,
               "suite_wall_seconds": time.perf_counter() - started,
               "cost_note": "Human preparation unmeasured. Per-pair machine cost includes strictness probes and every concrete fallback result, including failures/UNKNOWN. The independent B0 comparison is excluded unless used as fallback. Per-case and suite wall times also retain overhead and all failed attempts."}
    save(out / "summary.json", summary)
    keys = sorted(set().union(*(row.keys() for row in rows)))
    with (out / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        writer.writerows(rows)
    return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demonstration = commands.add_parser("demo", help="run retained manual and real RTL P1/P5 experiments")
    demonstration.add_argument("--out", required=True, type=Path)
    checking = commands.add_parser("check", help="check four data-only JSON inputs against the supplied frozen contract")
    for name in ("concrete", "abstract", "contract", "certificate"):
        checking.add_argument(name, type=Path)
    checking.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            return demo(args.out)
        args.out.mkdir(parents=True, exist_ok=False)
        result = check(*(load_json(getattr(args, name)) for name in ("concrete", "abstract", "contract", "certificate")), args.out)
        print(json.dumps({"status": result["status"], "reason": result.get("reason")}, indent=2))
        return 0 if result["status"] == "ACCEPTED" else 1
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f"ERROR: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
