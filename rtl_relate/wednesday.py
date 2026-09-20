"""Run the preregistered RTL matrix, retaining failed attempts and proof evidence."""

import argparse
import csv
import hashlib
import math
import json
from pathlib import Path
import subprocess
import sys
import time

from .checker import check
from .ir import digest, load_json, symbols_of
from .properties import replay
from .__main__ import save, trace_in_abstract, violates


TASKS = ("R1-fsm", "R2-skid8", "R3-skid32", "R4-pipe32")
VARIANTS = ("good", "coarse", "bad_certificate")
ROOT = Path(__file__).resolve().parents[1]


def prepare(task, variant, out):
    if task == "R1-fsm":
        from .fsm_case import prepare_case
        return prepare_case(variant, out)
    if task == "R4-pipe32":
        from .pipeline_case import prepare_case
        return prepare_case(variant, out)
    from .skid_cases import prepare_case
    case = prepare_case(8 if task == "R2-skid8" else 32, variant, out)
    case["concrete_cover_trace"] = case.pop("cover_trace")
    if variant != "coarse":
        case.pop("coarse_counterexample", None)
    return case


def state_size(model):
    states = symbols_of(model, "state")
    monitor = sum(width for key, width in states.items()
                  if model["symbols"][key]["origin"].split(".")[-1]
                  in {"tmp_stageOne", "tmp_stageTwo"})
    return {"total": sum(states.values()), "monitor": monitor,
            "design": sum(states.values()) - monitor,
            "nondet": sum(symbols_of(model, "nondet").values())}


def validate_trace_pair(case, trace, out):
    """A reachable violating trace and an exact C replay are separate evidence."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    save(out / "trace.json", trace)
    a = trace_in_abstract(case["abstract"], case["contract"], trace, out / "abstract")
    c = replay(case["concrete"], case["contract"], trace, out / "concrete", timeout_ms=30000)
    bad = violates(trace, case["contract"])
    status = ("SPURIOUS_TRACE" if a["status"] == "sat" and bad and c["status"] == "INFEASIBLE"
              else "BUG" if a["status"] == "sat" and bad and c["status"] == "FEASIBLE"
              else "EXTRA_ABSTRACT_TRACE" if a["status"] == "sat" and c["status"] == "INFEASIBLE"
              else "UNRESOLVED")
    result = {"status": status, "abstract": a["status"], "concrete": c["status"],
              "violates_property": bad, "seconds": a["seconds"] + c["seconds"],
              "provenance": "authored short trace, independently checked by SMT"}
    save(out / "result.json", result)
    return result


def worker(request, response):
    """Fixed local operations only; descendants share the worker's process group."""
    request = load_json(request)
    functions = {"prepare": prepare, "certificate": check,
                 "trace": validate_trace_pair, "replay": replay}
    try:
        value = functions[request["operation"]](*request["args"], **request["kwargs"])
        result = {"ok": True, "value": value}
    except Exception as error:
        result = {"ok": False, "reason": f"{type(error).__name__}: {error}"}
    Path(response).write_text(json.dumps(result, default=str) + "\n")


def bounded(operation, args, kwargs, out, deadline):
    from .formal import _run

    if time.monotonic() >= deadline:
        raise TimeoutError(f"budget exhausted before {operation}")
    out.mkdir(parents=True, exist_ok=True)
    request, response = out / "request.json", out / "response.json"
    request.write_text(json.dumps({"operation": operation, "args": args, "kwargs": kwargs}, default=str))
    command = [sys.executable, "-c",
               "import sys; sys.path.insert(0,sys.argv[1]); "
               "from rtl_relate.wednesday import worker; worker(sys.argv[2],sys.argv[3])",
               str(ROOT), str(request), str(response)]
    process, _ = _run(command, out, "worker", deadline)
    save(out / "process.json", process)
    if process["timeout"]:
        raise TimeoutError(f"{operation} exceeded its wall-clock deadline")
    if process["returncode"] != 0 or not response.is_file():
        raise ValueError(f"{operation} worker failed; see retained process logs")
    result = load_json(response)
    if not result["ok"]:
        raise ValueError(result["reason"])
    return result["value"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_case(task, case, frontend):
    """Bind the frozen task, exported models and actual property-proof source bytes."""
    manifest_path = ROOT / "fixtures/public/sources.json"
    entry, = [row for row in load_json(manifest_path)["tasks"] if row["id"] == task]
    frozen = load_json(ROOT / entry["contract"]["path"])
    if digest(frozen) != entry["contract"]["sha256"] or digest(case["contract"]) != digest(frozen):
        raise ValueError("contract differs from frozen source manifest")
    if sha(ROOT / entry["concrete"]["path"]) != entry["concrete"]["sha256"]:
        raise ValueError("concrete source differs from frozen source manifest")
    result = {"manifest_sha256": sha(manifest_path)}
    for role in ("concrete", "abstract"):
        directory = frontend / role
        meta = load_json(directory / "frontend.json")
        nondet = sorted(case.get("nondet", ())) if role == "abstract" else []
        if (meta["status"] != "EXPORTED" or digest(load_json(directory / "model.json")) != digest(case[role])
                or meta["top"] != case[role + "_top"] or meta["clock"] != frozen["clock"]["name"]
                or meta["nondet"] != nondet):
            raise ValueError(f"{role} model/interface differs from retained frontend")
        if role == "concrete" and (meta["source_sha256"] != entry["concrete"]["sha256"]
                or meta["top"] != entry["top"] or meta["parameters"] != entry["parameters"] or meta["nondet"]):
            raise ValueError("concrete frontend differs from frozen source manifest")
        source_hash = sha(case[role + "_source"])
        raw_hash, normalized_hash = sha(directory / "source.v"), sha(directory / "normalized.v")
        parameters = meta["parameters"] if source_hash == raw_hash else {}
        if (source_hash not in {raw_hash, normalized_hash} or raw_hash != meta["source_sha256"]
                or sha(directory / "normalized.v") != meta["normalized_sha256"]):
            raise ValueError(f"{role} proof source differs from certified frontend")
        if case.get(role + "_parameters", {}) != parameters:
            raise ValueError(f"{role} proof parameters differ from certified frontend")
        result[role + "_source_sha256"] = source_hash
    return result


def validate_proof(result, row, role, case):
    nondet = sorted(case.get("nondet", ())) if role == "abstract" else []
    if result["status"] in {"SAFE", "CEX", "BOUNDED"} and (
            result.get("source_sha256") != row[role + "_source_sha256"]
            or result.get("contract_sha256") != row["contract_sha256"]
            or result.get("top") != case[role + "_top"]
            or result.get("parameters") != case.get(role + "_parameters", {})
            or result.get("nondet") != nondet):
        raise ValueError(f"{role} property proof binding differs from certificate inputs")


def run_task(task, root, task_budget=1800):
    from .formal import prove_rtl

    if type(task_budget) not in {int, float} or not math.isfinite(task_budget) or task_budget <= 0:
        raise ValueError("task budget must be a positive finite number")
    root = Path(root).resolve()
    started = time.monotonic()
    deadline = started + task_budget
    baseline, baseline_binding, gold_binding = None, None, None
    baseline_seconds = 0.0
    rows = []
    for variant in VARIANTS:
        attempt_start = time.monotonic()
        out = root / task / variant
        out.mkdir(parents=True)
        row = {"task_id": task, "variant": variant, "candidate_id": f"{task}-{variant}",
               "status": "ERROR", "expected_met": False, "frontend_seconds": 0.0,
               "certificate_seconds": 0.0, "abstract_property_seconds": 0.0, "replay_seconds": 0.0,
               "extra_certificate_seconds": 0.0, "b0_seconds": baseline_seconds if baseline else None,
               "attempt_b0_seconds": 0.0, "human_minutes": None, "generation_seconds": 0.0,
               "origin": "authored gold/coarse/certificate control", "artifact_path": str(out.relative_to(root))}

        def phase(name, cost, cap, operation, *args, **kwargs):
            phase_start = time.monotonic()
            phase_deadline = min(deadline, phase_start + cap)
            if phase_start >= deadline:
                raise TimeoutError(f"task budget exhausted before {name}")
            try:
                if operation == "proof":
                    # The proof driver kills its own solver sessions at this shared deadline.
                    remaining = phase_deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(f"budget exhausted before {name}")
                    return prove_rtl(*args, timeout_seconds=remaining, **kwargs)
                return bounded(operation, args, kwargs, out / "phases" / name, phase_deadline)
            finally:
                row[cost] += time.monotonic() - phase_start

        try:
            if time.monotonic() >= deadline:
                row.update(status="NOT_RUN", reason="task wall-time budget exhausted")
                continue
            case = phase("frontend", "frontend_seconds", task_budget, "prepare", task, variant, out / "frontend")
            c, a, contract, cert = (case[k] for k in ("concrete", "abstract", "contract", "certificate"))
            row.update(concrete_sha256=digest(c), abstract_sha256=digest(a),
                       contract_sha256=digest(contract), certificate_sha256=digest(cert),
                       concrete_size=state_size(c), abstract_size=state_size(a))
            row.update(validate_case(task, case, out / "frontend"))
            binding = (digest(c), digest(contract))
            if baseline_binding is not None and baseline_binding != binding:
                raise ValueError("concrete model/contract changed across the fixed task")
            if variant == "good":
                gold_binding = digest(a)
            if variant == "bad_certificate" and digest(a) != gold_binding:
                raise ValueError("bad-certificate control changed the good abstraction")
            if baseline is None:
                baseline_binding = binding
                baseline = phase("baseline", "attempt_b0_seconds", 120, "proof",
                                 case["concrete_source"], case["concrete_top"], contract,
                                 root / task / "baseline", parameters=case.get("concrete_parameters"), depth=20)
                baseline_seconds = row["attempt_b0_seconds"]
                validate_proof(baseline, row, "concrete", case)
            row.update(b0_status=baseline["status"], b0_seconds=baseline_seconds,
                       b0_artifact=f"{task}/baseline")
            gate = phase("certificate", "certificate_seconds", 120, "certificate",
                         c, a, contract, cert, out / "certificate", timeout_ms=10000)
            row.update(certificate_status=gate["status"], status=gate["status"])
            if variant == "bad_certificate":
                row["expected_met"] = gate["status"] == "CERTIFICATE_REJECTED"
                if gate["status"] == "ACCEPTED":
                    row.update(status="ERROR", reason="negative certificate unexpectedly accepted")
                continue
            if gate["status"] != "ACCEPTED":
                continue
            prop = phase("abstract_property", "abstract_property_seconds", 120, "proof",
                         case["abstract_source"], case["abstract_top"], contract, out / "abstract_property",
                         nondet=case.get("nondet", ()), parameters=case.get("abstract_parameters"), depth=20)
            row.update(abstract_property_status=prop["status"], status=prop["status"])
            validate_proof(prop, row, "abstract", case)
            for key in ("coarse_counterexample", "strictness_trace"):
                if case.get(key) is None:
                    continue
                result = phase(key, "replay_seconds", 30, "trace", case, case[key], out / key)
                row[key] = result
                if result["violates_property"]:
                    if (result["abstract"] == "sat" and prop["status"] == "SAFE"
                            or result["concrete"] == "FEASIBLE" and baseline["status"] == "SAFE"):
                        raise ValueError(f"SAFE proof conflicts with reachable violating {key}")
                    if result["status"] == "BUG":
                        row["status"] = "BUG"
                    elif key == "coarse_counterexample":
                        row["status"] = result["status"]
            if case.get("concrete_cover_trace") is not None:
                trace = case["concrete_cover_trace"]
                save(out / "cover_trace.json", trace)
                cover = phase("cover", "replay_seconds", 30, "replay", c, contract, trace,
                              out / "cover", timeout_ms=30000)
                row["cover_status"] = cover["status"]
                if cover["status"] == "FEASIBLE" and violates(trace, contract):
                    if prop["status"] == "SAFE" or baseline["status"] == "SAFE":
                        raise ValueError("SAFE proof conflicts with violating concrete cover")
                    row["status"] = "BUG"
            if case.get("reverse_certificate") is not None:
                reverse = phase("reverse_certificate", "extra_certificate_seconds", 120, "certificate",
                                a, c, contract, case["reverse_certificate"], out / "reverse_certificate", timeout_ms=10000)
                row["reverse_certificate_status"] = reverse["status"]
            row["expected_met"] = (row["status"] == "SAFE" if variant == "good"
                                   else row["status"] == "SPURIOUS_TRACE")
            if "cover_status" in row:
                row["expected_met"] &= row["cover_status"] == "FEASIBLE"
            if "reverse_certificate_status" in row:
                row["expected_met"] &= row["reverse_certificate_status"] == "ACCEPTED"
            if "strictness_trace" in row:
                row["expected_met"] &= row["strictness_trace"]["status"] == "EXTRA_ABSTRACT_TRACE"
        except TimeoutError as error:
            row.update(status="UNKNOWN", reason=str(error), expected_met=False)
        except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError) as error:
            row.update(status="ERROR", reason=f"{type(error).__name__}: {error}", expected_met=False)
        finally:
            row["attempt_wall_seconds"] = time.monotonic() - attempt_start
            row["workflow_seconds"] = row["attempt_wall_seconds"] - row["attempt_b0_seconds"]
            row["orchestration_seconds"] = row["workflow_seconds"] - sum(row[k] for k in (
                "frontend_seconds", "certificate_seconds", "abstract_property_seconds", "replay_seconds", "extra_certificate_seconds"))
            save(out / "result.json", row)
            rows.append(row)
            print(task, variant, row["status"], row.get("reason", ""), flush=True)
    elapsed = time.monotonic() - started
    return rows, {"task_id": task, "wall_seconds": elapsed,
                  "reporting_seconds": elapsed - sum(row["attempt_wall_seconds"] for row in rows),
                  "b0_seconds": sum(row["attempt_b0_seconds"] for row in rows), "budget_seconds": task_budget}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", choices=TASKS, action="append")
    parser.add_argument("--task-budget", type=float, default=1800,
                        help="positive finite wall-time budget per task, in seconds (default: 1800)")
    args = parser.parse_args()
    if args.task and len(args.task) != len(set(args.task)):
        parser.error("--task values must be unique")
    if not math.isfinite(args.task_budget) or args.task_budget <= 0:
        parser.error("--task-budget must be a positive finite number")
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    rows, tasks = [], []
    for task in args.task or TASKS:
        records, task_record = run_task(task, args.out, task_budget=args.task_budget)
        rows.extend(records)
        tasks.append(task_record)
    source = {str(p.relative_to(Path(__file__).parent)): p.read_text()
              for p in Path(__file__).parent.glob("*.py")}
    summary = {"rows": rows, "tasks": tasks, "suite_wall_seconds": time.perf_counter() - start,
               "source_sha256": digest(source), "success": all(r.get("expected_met", False) for r in rows),
               "cost_note": "Single pilot measurements, not speedup evidence. Workflow is measured attempt wall time minus the actual B0 stage, including failed phases and orchestration. Task wall time also includes reporting. All variants and reverse/trace checks are included. B0 is cached once per identical C/contract. Human preparation time is unmeasured. LLM pilots are separate."}
    save(args.out / "summary.json", summary)
    keys = sorted(set().union(*(r.keys() for r in rows)))
    with (args.out / "results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, keys)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, sort_keys=True) if isinstance(v, dict) else v for k, v in r.items()} for r in rows)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
