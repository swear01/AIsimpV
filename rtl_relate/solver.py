"""Run the external solver and retain complete query and process evidence."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import time


def identity(executable="z3"):
    path = shutil.which(executable)
    if path is None:
        raise FileNotFoundError(executable)
    resolved = Path(path).resolve()
    version = subprocess.run([str(resolved), "-version"], text=True, capture_output=True,
                             timeout=10, check=True).stdout.strip()
    return {"path": str(resolved), "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
            "version": version}


def query(declarations, violation, timeout_ms):
    # get-model also runs after UNSAT; its exact expected error is handled below.
    return (f"(set-logic QF_BV)\n(set-option :produce-models true)\n"
            f"(set-option :timeout {timeout_ms})\n" + "\n".join(declarations) +
            f"\n(assert {violation})\n(check-sat)\n(get-model)\n")


def run(query, out_dir, name, solver="z3", timeout_ms=5000):
    if type(timeout_ms) is not int or timeout_ms <= 0:
        raise ValueError("positive integer timeout required")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / (name + ".smt2")
    path.write_text(query)
    start = time.perf_counter()
    row = {"status": "error", "stdout": "", "stderr": "", "returncode": None,
           "query_sha256": hashlib.sha256(query.encode()).hexdigest(), "query": path.name}
    try:
        p = subprocess.run([solver, "-smt2", str(path)], text=True, capture_output=True,
                           timeout=timeout_ms / 1000 + 1)
        row.update(stdout=p.stdout, stderr=p.stderr, returncode=p.returncode)
        lines = p.stdout.strip().splitlines()
        status = lines[0].strip() if lines else ""
        tail = "\n".join(lines[1:]).strip()
        no_model = '(error "line ' in tail and tail.endswith(': model is not available")') and tail.count("\n") == 0
        if not p.stderr and status == "sat" and p.returncode == 0 and tail.startswith("(") and "(error" not in tail:
            row["status"] = "sat"
            row["counterexample_smt"] = tail
        elif not p.stderr and status in {"unsat", "unknown"} and (
                p.returncode == 0 and not tail or p.returncode == 1 and no_model):
            row["status"] = status
        else:
            row["reason"] = "unrecognized solver output or process failure"
    except subprocess.TimeoutExpired as e:
        row.update(status="unknown", reason="process timeout",
                   stdout=e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else e.stdout or "",
                   stderr=e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else e.stderr or "")
    except OSError as e:
        row["reason"] = str(e)
    row["seconds"] = time.perf_counter() - start
    (out / (name + ".stdout")).write_text(row["stdout"])
    (out / (name + ".stderr")).write_text(row["stderr"])
    (out / (name + ".json")).write_text(json.dumps(row, indent=2) + "\n")
    return row
