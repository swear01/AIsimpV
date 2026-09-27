# axilxbar freestyle pilot

See the [September 30 execution plan](../../docs/freestyle_rewrite_plan_20260930.md). `original/` is the frozen starting problem from ZipCPU/wb2axip commit `2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b`; the upstream RTL keeps its Apache-2.0 notices. The single `property.v` is our derived read-response hold task, not the upstream formal suite. The exact binding from its six ports to master 0 is in `task.json`.

Use Yosys 0.69 to repeat the frontend checks from the repository root:

```sh
SRC=experiments/freestyle_axilxbar/original
yosys -Q -T -p "read_verilog -sv -defer $SRC/addrdecode.v $SRC/skidbuffer.v $SRC/axilxbar.v; hierarchy -check -top axilxbar; proc; check"
yosys -Q -T -p "read_verilog -formal -sv $SRC/property.v; hierarchy -check -top axilxbar_read_hold_property; proc; check"
```

The two commands check design and property separately. They do not prove property binding, satisfiability, safety, or correspondence. `FORMAL` is not enabled for the design, so the upstream assertion suite is outside this task.

For a candidate retaining the starting property interface, check the explicit binding and assertion cell as well:

```sh
python3 scripts/check_freestyle_case.py \
  --candidate experiments/freestyle_axilxbar/candidate-01 \
  --out results/freestyle-axilxbar/connected-01
```

This still does not run a solver. A candidate with a changed property interface needs its own declared binding; do not silently apply the starting binding.

Generate a fresh candidate and blind analysis into a new `results/` directory:

```sh
python3 scripts/freestyle_pilot.py rewrite --out results/freestyle-axilxbar/rewrite-01 --provider deepseek
python3 scripts/freestyle_pilot.py analyze \
  --candidate results/freestyle-axilxbar/rewrite-01/candidate \
  --out results/freestyle-axilxbar/analysis-01 --provider deepseek
```

The analyzer receives original and candidate code, environment changes, and frontend summary. It does not receive `explanation.md` or earlier generation text. `results/` is ignored by Git; preserved local raw requests and responses are kept under the workspace's `artifacts/` directory after the run. The reviewed code snapshots, analysis and static page live beside this README.
