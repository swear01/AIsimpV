# PicoRV32 majority-behavior rewrite

This experiment asks one LLM for **one simplified PicoRV32 model** that still represents the behavior relevant to most tasks in the pinned upstream riscv-formal configuration. The input is the complete original core, its wrapper, and the [86 generated assertion-task names and intent groups](assertion_intents.md). The generated cover task and three separately maintained `.sby` files are recorded but excluded from this denominator. The prior [ADD-only pilot](../picorv32/README.md) is a separate experiment.

The target of roughly 80% means at least 69 of those 86 task intentions would need credible behavioral support in the *same* candidate. It is a research target, **not a measured coverage rate**. Task names are correlated; the report also separates RV32I, M, compressed instructions, register/PC/order, and CSR behavior. An opcode decoder, an assertion that passes, or a model-written explanation alone is insufficient evidence. The candidate must still represent meaningful nonzero data and instruction sequences for a task to be considered retained by inspection.

No Formal, compilation, or behavioral verification is run in this phase. The candidate's coverage document is a claim to inspect. Any review states what the RTL visibly supports, what it loses, and what remains unknown. It does not prove equivalence, abstraction soundness, or an 80% result.

The wrapper configuration is fixed at `COMPRESSED_ISA=1`, `ENABLE_FAST_MUL=1`, `ENABLE_DIV=1`, and `BARREL_SHIFTER=1`, with the original memory inputs and reset connection. The pinned source revisions are in [task.json](task.json). The `upstream` link points to the unchanged source snapshot in the adjacent PicoRV32 case.
