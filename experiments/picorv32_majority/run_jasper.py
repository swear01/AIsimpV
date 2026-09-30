#!/usr/bin/env python3
"""Run the pinned generated riscv-formal assertion tasks directly in JasperGold."""

import argparse
import concurrent.futures
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RTL = {
    "original": ROOT / "experiments/picorv32/upstream/picorv32.v",
    "candidate05": ROOT / "experiments/picorv32_majority/candidate-05/picorv32.v",
}
WRAPPER = ROOT / "experiments/picorv32/upstream/wrapper.sv"


def section(source, name):
    match = re.search(rf"(?m)^\[file {re.escape(name)}\]\n(.*?)(?=^\[|\Z)", source, re.S | re.M)
    if not match:
        raise ValueError(f"missing [file {name}]")
    return match.group(1)


def link_file(path, target):
    if path.is_symlink():
        if path.resolve() != target.resolve():
            path.unlink()
            path.symlink_to(target)
    elif path.exists():
        raise ValueError(f"input path is not a link: {path}")
    else:
        path.symlink_to(target)


def prepare(task, design, checks, output, timeout):
    source = task.read_text()
    cycle = re.search(r"`define RISCV_FORMAL_CHECK_CYCLE (\d+)", source)
    if not cycle:
        raise ValueError(f"{task}: missing check cycle")
    work = output / design / task.stem
    work.mkdir(parents=True, exist_ok=True)
    files = re.search(r"(?ms)^\[files\]\n(.*?)(?=^\[|\Z)", source)
    if not files:
        raise ValueError(f"{task}: missing [files]")
    constant_signals = set()
    for line in files.group(1).splitlines():
        if line:
            source_path = Path(line)
            source_dir = source_path.parent.name
            if source_dir not in ("checks", "insns"):
                raise ValueError(f"unexpected pinned source directory: {source_path}")
            target = (checks.parents[2] / source_dir / source_path.name).resolve()
            if not target.is_file():
                raise FileNotFoundError(target)
            if target.suffix in (".sv", ".v"):
                constant_signals.update(re.findall(
                    r"`rvformal_rand_const_reg\s+(?:\[[^\]]+\]\s+)?([A-Za-z_]\w*)",
                    target.read_text(),
                ))
            link_file(work / target.name, target)
    for name in ("defines.sv", f"{task.stem}.sv"):
        (work / name).write_text(section(source, name))
    for name, target in (("wrapper.sv", WRAPPER), ("picorv32.v", RTL[design])):
        link_file(work / name, target)
    tcl = (
        f"analyze -sv {task.stem}.sv wrapper.sv picorv32.v\n"
        "elaborate -top rvfi_testbench\nclock clock\nreset reset\n"
    )
    tcl += "".join(f"assume -constant checker_inst.{name}\n" for name in sorted(constant_signals))
    tcl += (
        f"set_max_trace_length {cycle.group(1)}\n"
        f"set_prove_target_bound {cycle.group(1)}\n"
        f"prove -all -time_limit {timeout}s -max_jobs 4\nreport\n"
    )
    (work / "run.tcl").write_text(tcl)
    return work


def count(report, label):
    match = re.search(rf"(?m)^\s*{re.escape(label)}\s*:\s*(\d+)", report)
    return int(match.group(1)) if match else None


def run(task, design, checks, output, timeout):
    work = prepare(task, design, checks, output, timeout)
    log = work / "console.txt"
    with log.open("w") as stream:
        result = subprocess.run(
            ["timeout", "--kill-after=10s", f"{timeout + 60}s", "jg", "-fpv", "-batch",
             "-no_wait", "-allow_unsupported_OS", "-proj", "jgproject", "-tcl", "run.tcl"],
            cwd=work, stdout=stream, stderr=subprocess.STDOUT, check=False,
        )
    report = log.read_text(errors="replace")
    assertions = count(report, "assertions")
    proven = count(report, "- proven")
    bounded = count(report, "- bounded_proven (user)")
    cex = count(report, "- cex")
    undetermined = count(report, "- undetermined")
    covered = count(report, "- covered")
    unreachable = count(report, "- unreachable")
    if result.returncode == 124:
        status = "timeout"
    elif result.returncode != 0:
        status = "error"
    elif assertions is None or proven is None or bounded is None or cex is None:
        status = "error"
    elif cex:
        status = "fail"
    elif proven + bounded == assertions and result.returncode == 0:
        status = "pass"
    else:
        status = "incomplete"
    return {"task": task.stem, "design": design, "status": status,
            "assertions": assertions, "proven": proven, "bounded_proven": bounded, "cex": cex,
            "undetermined": undetermined, "covered": covered,
            "unreachable": unreachable, "exit_code": result.returncode,
            "log": str(log.relative_to(output))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--design", choices=["original", "candidate05", "both"], default="both")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    if args.jobs < 1 or args.timeout < 1:
        parser.error("--jobs and --timeout must be positive")
    tasks = sorted(task for task in args.checks.glob("*.sby")
                   if task.stem != "cover" and not task.stem.endswith("_z3"))
    if args.only:
        selected = set(args.only)
        tasks = [task for task in tasks if task.stem in selected]
        if len(tasks) != len(selected):
            parser.error("--only names must match generated assertion tasks")
    elif len(tasks) != 86:
        parser.error(f"expected 86 generated assertion tasks, got {len(tasks)}")
    designs = list(RTL) if args.design == "both" else [args.design]
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run, task, design, args.checks, args.output, args.timeout):
                   (task.stem, design) for design in designs for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            task, design = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {"task": task, "design": design, "status": "error", "error": str(error)}
            results.append(row)
            (args.output / "summary.json").write_text(json.dumps(
                sorted(results, key=lambda item: (item["design"], item["task"])), indent=2) + "\n")
            print(f'{len(results)}/{len(futures)} {design} {task}: {row["status"]}', flush=True)


if __name__ == "__main__":
    main()
