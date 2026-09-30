/*
 *  PicoRV32 -- A Small RISC-V (RV32I) Processor Core
 *
 *  Copyright (C) 2015  Claire Xenia Wolf <claire@yosyshq.com>
 *
 *  Permission to use, copy, modify, and/or distribute this software for any
 *  purpose with or without fee is hereby granted, provided that the above
 *  copyright notice and this permission notice appear in all copies.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 *  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 *  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 *  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 *  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 *  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 *  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 */

/*
 * PARTIAL MODEL -- NOT THE UPSTREAM PICORV32 CORE.
 *
 * This file is a candidate simplification for the riscv-formal insn_add_ch0
 * task only. The module 'picorv32' keeps the upstream parameter list and port
 * list, but its body is a reduced multi-cycle RV32I-subset core:
 *   - fetches 32-bit instructions over the native mem interface (mem_ready is
 *     still a free input, stalls are still possible),
 *   - executes LUI, AUIPC, all RV32I OP-IMM and all RV32I OP (funct7 0000000 /
 *     0100000) instructions through a real 32-entry register file and ALU,
 *   - every other encoding (RVC, loads, stores, branches, JAL/JALR, SYSTEM,
 *     FENCE, M-extension, custom IRQ insns, illegal) retires with rvfi_trap=1
 *     and halts the core.
 * RVFI is produced at retirement for the retiring instruction (no upstream
 * dbg_* staging). See explanation.md for the exact list of lost behaviors.
 * This core-only file omits the seven auxiliary module definitions. The
 * insn_add_ch0 wrapper instantiates picorv32 directly; use picorv32.v if
 * picorv32_axi, picorv32_wb or other auxiliary modules are needed.
 */

/* verilator lint_off WIDTH */
/* verilator lint_off PINMISSING */
/* verilator lint_off CASEOVERLAP */
/* verilator lint_off CASEINCOMPLETE */

`timescale 1 ns / 1 ps
// `default_nettype none

`ifdef DEBUG
  `define debug(debug_command) debug_command
`else
  `define debug(debug_command)
`endif

`ifdef FORMAL
  `define FORMAL_KEEP (* keep *)
  `define assert(assert_expr) assert(assert_expr)
`else
  `ifdef DEBUGNETS
    `define FORMAL_KEEP (* keep *)
  `else
    `define FORMAL_KEEP
  `endif
  `define assert(assert_expr) empty_statement
`endif

`define PICORV32_V


/***************************************************************
 * picorv32 (reduced partial model for insn_add_ch0)
 ***************************************************************/

module picorv32 #(
	parameter [ 0:0] ENABLE_COUNTERS = 1,
	parameter [ 0:0] ENABLE_COUNTERS64 = 1,
	parameter [ 0:0] ENABLE_REGS_16_31 = 1,
	parameter [ 0:0] ENABLE_REGS_DUALPORT = 1,
	parameter [ 0:0] LATCHED_MEM_RDATA = 0,
	parameter [ 0:0] TWO_STAGE_SHIFT = 1,
	parameter [ 0:0] BARREL_SHIFTER = 0,
	parameter [ 0:0] TWO_CYCLE_COMPARE = 0,
	parameter [ 0:0] TWO_CYCLE_ALU = 0,
	parameter [ 0:0] COMPRESSED_ISA = 0,
	parameter [ 0:0] CATCH_MISALIGN = 1,
	parameter [ 0:0] CATCH_ILLINSN = 1,
	parameter [ 0:0] ENABLE_PCPI = 0,
	parameter [ 0:0] ENABLE_MUL = 0,
	parameter [ 0:0] ENABLE_FAST_MUL = 0,
	parameter [ 0:0] ENABLE_DIV = 0,
	parameter [ 0:0] ENABLE_IRQ = 0,
	parameter [ 0:0] ENABLE_IRQ_QREGS = 1,
	parameter [ 0:0] ENABLE_IRQ_TIMER = 1,
	parameter [ 0:0] ENABLE_TRACE = 0,
	parameter [ 0:0] REGS_INIT_ZERO = 0,
	parameter [31:0] MASKED_IRQ = 32'h 0000_0000,
	parameter [31:0] LATCHED_IRQ = 32'h ffff_ffff,
	parameter [31:0] PROGADDR_RESET = 32'h 0000_0000,
	parameter [31:0] PROGADDR_IRQ = 32'h 0000_0010,
	parameter [31:0] STACKADDR = 32'h ffff_ffff
) (
	input clk, resetn,
	output reg trap,

	output reg        mem_valid,
	output reg        mem_instr,
	input             mem_ready,

	output reg [31:0] mem_addr,
	output reg [31:0] mem_wdata,
	output reg [ 3:0] mem_wstrb,
	input      [31:0] mem_rdata,

	// Look-Ahead Interface
	output            mem_la_read,
	output            mem_la_write,
	output     [31:0] mem_la_addr,
	output reg [31:0] mem_la_wdata,
	output reg [ 3:0] mem_la_wstrb,

	// Pico Co-Processor Interface (PCPI)
	output reg        pcpi_valid,
	output reg [31:0] pcpi_insn,
	output     [31:0] pcpi_rs1,
	output     [31:0] pcpi_rs2,
	input             pcpi_wr,
	input      [31:0] pcpi_rd,
	input             pcpi_wait,
	input             pcpi_ready,

	// IRQ Interface
	input      [31:0] irq,
	output reg [31:0] eoi,

`ifdef RISCV_FORMAL
	output reg        rvfi_valid,
	output reg [63:0] rvfi_order,
	output reg [31:0] rvfi_insn,
	output reg        rvfi_trap,
	output reg        rvfi_halt,
	output reg        rvfi_intr,
	output reg [ 1:0] rvfi_mode,
	output reg [ 1:0] rvfi_ixl,
	output reg [ 4:0] rvfi_rs1_addr,
	output reg [ 4:0] rvfi_rs2_addr,
	output reg [31:0] rvfi_rs1_rdata,
	output reg [31:0] rvfi_rs2_rdata,
	output reg [ 4:0] rvfi_rd_addr,
	output reg [31:0] rvfi_rd_wdata,
	output reg [31:0] rvfi_pc_rdata,
	output reg [31:0] rvfi_pc_wdata,
	output reg [31:0] rvfi_mem_addr,
	output reg [ 3:0] rvfi_mem_rmask,
	output reg [ 3:0] rvfi_mem_wmask,
	output reg [31:0] rvfi_mem_rdata,
	output reg [31:0] rvfi_mem_wdata,

	output reg [63:0] rvfi_csr_mcycle_rmask,
	output reg [63:0] rvfi_csr_mcycle_wmask,
	output reg [63:0] rvfi_csr_mcycle_rdata,
	output reg [63:0] rvfi_csr_mcycle_wdata,

	output reg [63:0] rvfi_csr_minstret_rmask,
	output reg [63:0] rvfi_csr_minstret_wmask,
	output reg [63:0] rvfi_csr_minstret_rdata,
	output reg [63:0] rvfi_csr_minstret_wdata,
`endif

	// Trace Interface
	output reg        trace_valid,
	output reg [35:0] trace_data
);
	// Parameters COMPRESSED_ISA, ENABLE_*MUL, ENABLE_DIV, ENABLE_PCPI, ENABLE_IRQ*,
	// ENABLE_COUNTERS*, BARREL_SHIFTER, TWO_*, LATCHED_MEM_RDATA, ENABLE_TRACE,
	// STACKADDR, PROGADDR_IRQ, MASKED_IRQ, LATCHED_IRQ, ENABLE_REGS_16_31 and
	// ENABLE_REGS_DUALPORT are accepted for interface compatibility but ignored.

	localparam [7:0] cpu_state_trap   = 8'b10000000;
	localparam [7:0] cpu_state_fetch  = 8'b01000000;
	localparam [7:0] cpu_state_iwait  = 8'b00100000;
	localparam [7:0] cpu_state_exec   = 8'b00001000;

	reg [7:0] cpu_state;
	reg [31:0] reg_pc;
	reg [31:0] insn_q;

	reg [31:0] cpuregs [0:31];

	integer i;
	initial begin
		if (REGS_INIT_ZERO) begin
			for (i = 0; i < 32; i = i+1)
				cpuregs[i] = 0;
		end
	end

	task empty_statement;
		begin end
	endtask

	// Unused interfaces tied off
	assign pcpi_rs1 = 32'b0;
	assign pcpi_rs2 = 32'b0;
	assign mem_la_write = 1'b0;
	assign mem_la_addr = {reg_pc[31:2], 2'b00};
	assign mem_la_read = resetn && cpu_state == cpu_state_fetch && !(CATCH_MISALIGN && |reg_pc[1:0]);

	always @* begin
		mem_la_wdata = 32'b0;
		mem_la_wstrb = 4'b0;
	end

	always @(posedge clk) begin
		pcpi_valid <= 0;
		pcpi_insn <= 0;
		eoi <= 0;
		trace_valid <= 0;
		trace_data <= 0;
	end

	// Decoder (32-bit RV32I subset)

	wire [6:0] d_opcode = insn_q[6:0];
	wire [2:0] d_funct3 = insn_q[14:12];
	wire [6:0] d_funct7 = insn_q[31:25];
	wire [4:0] d_rd     = insn_q[11:7];
	wire [4:0] d_rs1    = insn_q[19:15];
	wire [4:0] d_rs2    = insn_q[24:20];

	wire d_lui   = d_opcode == 7'b0110111;
	wire d_auipc = d_opcode == 7'b0010111;
	wire d_opimm = d_opcode == 7'b0010011 && (
			d_funct3 == 3'b001 ? d_funct7 == 7'b0000000 :
			d_funct3 == 3'b101 ? (d_funct7 == 7'b0000000 || d_funct7 == 7'b0100000) : 1'b1);
	wire d_op    = d_opcode == 7'b0110011 && (d_funct7 == 7'b0000000 ||
			(d_funct7 == 7'b0100000 && (d_funct3 == 3'b000 || d_funct3 == 3'b101)));

	wire d_supported = d_lui || d_auipc || d_opimm || d_op;
	wire d_uses_rs1  = d_opimm || d_op;
	wire d_uses_rs2  = d_op;

	wire [31:0] cpuregs_rs1 = d_rs1 ? cpuregs[d_rs1] : 32'b0;
	wire [31:0] cpuregs_rs2 = d_rs2 ? cpuregs[d_rs2] : 32'b0;

	wire [31:0] d_imm = (d_lui || d_auipc) ? {insn_q[31:12], 12'b0} : {{20{insn_q[31]}}, insn_q[31:20]};

	wire [31:0] reg_op1 = d_lui ? 32'b0 : d_auipc ? reg_pc : cpuregs_rs1;
	wire [31:0] reg_op2 = d_op ? cpuregs_rs2 : d_imm;

	// ALU

	reg [31:0] alu_out;
	always @* begin
		if (d_lui || d_auipc)
			alu_out = reg_op1 + reg_op2;
		else case (d_funct3)
			3'b000: alu_out = (d_op && d_funct7[5]) ? reg_op1 - reg_op2 : reg_op1 + reg_op2;
			3'b001: alu_out = reg_op1 << reg_op2[4:0];
			3'b010: alu_out = {31'b0, $signed(reg_op1) < $signed(reg_op2)};
			3'b011: alu_out = {31'b0, reg_op1 < reg_op2};
			3'b100: alu_out = reg_op1 ^ reg_op2;
			3'b101: alu_out = $signed({d_funct7[5] ? reg_op1[31] : 1'b0, reg_op1}) >>> reg_op2[4:0];
			3'b110: alu_out = reg_op1 | reg_op2;
			default: alu_out = reg_op1 & reg_op2;
		endcase
	end

	// Register file write-back (at retirement)

	wire cpuregs_write = resetn && cpu_state == cpu_state_exec && d_supported && d_rd != 0;

	always @(posedge clk) begin
		if (cpuregs_write)
`ifdef PICORV32_TESTBUG_001
			cpuregs[d_rd ^ 1] <= alu_out;
`elsif PICORV32_TESTBUG_002
			cpuregs[d_rd] <= alu_out ^ 1;
`else
			cpuregs[d_rd] <= alu_out;
`endif
	end

	// Main state machine: fetch -> iwait -> exec -> fetch, or -> trap

	always @(posedge clk) begin
		trap <= 0;
		if (!resetn) begin
			cpu_state <= cpu_state_fetch;
			reg_pc <= PROGADDR_RESET;
			mem_valid <= 0;
			mem_instr <= 0;
			mem_wstrb <= 0;
			mem_wdata <= 0;
			mem_addr <= 0;
		end else begin
			(* parallel_case, full_case *)
			case (cpu_state)
				cpu_state_trap: begin
					trap <= 1;
					if (mem_ready)
						mem_valid <= 0;
				end
				cpu_state_fetch: begin
					if (CATCH_MISALIGN && |reg_pc[1:0]) begin
						cpu_state <= cpu_state_trap;
					end else begin
						mem_valid <= 1;
						mem_instr <= 1;
						mem_addr <= mem_la_addr;
						mem_wstrb <= 0;
						cpu_state <= cpu_state_iwait;
					end
				end
				cpu_state_iwait: begin
					if (mem_ready) begin
						mem_valid <= 0;
						insn_q <= mem_rdata;
						cpu_state <= cpu_state_exec;
					end
				end
				cpu_state_exec: begin
					if (d_supported) begin
						reg_pc <= reg_pc + 4;
						cpu_state <= cpu_state_fetch;
					end else begin
						cpu_state <= cpu_state_trap;
					end
				end
				default: begin
					cpu_state <= cpu_state_trap;
				end
			endcase
		end
	end

`ifdef RISCV_FORMAL
	// RVFI: reported in the cycle after the retiring exec cycle, for the
	// retiring instruction itself.
	always @(posedge clk) begin
		rvfi_valid <= resetn && cpu_state == cpu_state_exec;
		rvfi_order <= resetn ? rvfi_order + rvfi_valid : 0;

		rvfi_insn <= insn_q;
		rvfi_trap <= !d_supported;
		rvfi_halt <= !d_supported;
		rvfi_intr <= 0;
		rvfi_mode <= 3;
		rvfi_ixl <= 1;

		rvfi_rs1_addr <= d_uses_rs1 ? d_rs1 : 5'd0;
		rvfi_rs1_rdata <= d_uses_rs1 ? cpuregs_rs1 : 32'd0;
		rvfi_rs2_addr <= d_uses_rs2 ? d_rs2 : 5'd0;
		rvfi_rs2_rdata <= d_uses_rs2 ? cpuregs_rs2 : 32'd0;

`ifdef PICORV32_TESTBUG_003
		rvfi_rd_addr <= d_supported ? d_rd ^ 1 : 5'd0;
`else
		rvfi_rd_addr <= d_supported ? d_rd : 5'd0;
`endif
`ifdef PICORV32_TESTBUG_004
		rvfi_rd_wdata <= (d_supported && d_rd) ? alu_out ^ 1 : 32'd0;
`else
		rvfi_rd_wdata <= (d_supported && d_rd) ? alu_out : 32'd0;
`endif

		rvfi_pc_rdata <= reg_pc;
`ifdef PICORV32_TESTBUG_005
		rvfi_pc_wdata <= (d_supported ? reg_pc + 4 : reg_pc) ^ 4;
`else
		rvfi_pc_wdata <= d_supported ? reg_pc + 4 : reg_pc;
`endif

		rvfi_mem_addr <= 0;
		rvfi_mem_rmask <= 0;
		rvfi_mem_wmask <= 0;
		rvfi_mem_rdata <= 0;
		rvfi_mem_wdata <= 0;

		if (!resetn) begin
			rvfi_valid <= 0;
			rvfi_rd_addr <= 0;
			rvfi_rd_wdata <= 0;
		end
	end

	always @* begin
		rvfi_csr_mcycle_rmask = 0;
		rvfi_csr_mcycle_wmask = 0;
		rvfi_csr_mcycle_rdata = 0;
		rvfi_csr_mcycle_wdata = 0;

		rvfi_csr_minstret_rmask = 0;
		rvfi_csr_minstret_wmask = 0;
		rvfi_csr_minstret_rdata = 0;
		rvfi_csr_minstret_wdata = 0;
	end
`endif

	// Formal Verification (kept from upstream where still meaningful)
`ifdef FORMAL
	reg [3:0] last_mem_nowait;
	always @(posedge clk)
		last_mem_nowait <= {last_mem_nowait, mem_ready || !mem_valid};

	// stall the memory interface for max 4 cycles
	restrict property (|last_mem_nowait || mem_ready || !mem_valid);

	// resetn low in first cycle, after that resetn high
	restrict property (resetn != $initstate);

	reg ok;
	always @* begin
		if (resetn) begin
			if (mem_valid && mem_instr)
				assert (mem_wstrb == 0);

			ok = 0;
			if (cpu_state == cpu_state_trap)  ok = 1;
			if (cpu_state == cpu_state_fetch) ok = 1;
			if (cpu_state == cpu_state_iwait) ok = 1;
			if (cpu_state == cpu_state_exec)  ok = 1;
			assert (ok);
		end
	end

	reg last_mem_la_read = 0;
	reg [31:0] last_mem_la_addr;

	always @(posedge clk) begin
		last_mem_la_read <= mem_la_read;
		last_mem_la_addr <= mem_la_addr;

		if (last_mem_la_read) begin
			assert(mem_valid);
			assert(mem_addr == last_mem_la_addr);
			assert(mem_wstrb == 0);
		end
		if (mem_la_read) begin
			assert(!mem_valid || mem_ready);
		end
	end
`endif
endmodule
