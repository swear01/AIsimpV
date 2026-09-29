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

`timescale 1 ns / 1 ps

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

	localparam S_IDLE = 2'd0;
	localparam S_WAIT = 2'd1;
	localparam S_ADD  = 2'd2;
	localparam S_HALT = 2'd3;

	reg [1:0] state;
	reg [31:0] pc;
	reg [31:0] insn;

	wire [31:0] next_insn = mem_rdata;
	wire next_is_add = (next_insn[6:0] == 7'b0110011) &&
	                   (next_insn[14:12] == 3'b000) &&
	                   (next_insn[31:25] == 7'b0000000);

	assign mem_la_read = 0;
	assign mem_la_write = 0;
	assign mem_la_addr = 0;
	assign pcpi_rs1 = 0;
	assign pcpi_rs2 = 0;

	always @(posedge clk) begin
		if (!resetn) begin
			state <= S_IDLE;
			pc <= PROGADDR_RESET;
			trap <= 0;
			mem_valid <= 0;
			mem_instr <= 0;
			mem_addr <= 0;
			mem_wdata <= 0;
			mem_wstrb <= 0;
			mem_la_wdata <= 0;
			mem_la_wstrb <= 0;
			pcpi_valid <= 0;
			pcpi_insn <= 0;
			eoi <= 0;
			trace_valid <= 0;
			trace_data <= 0;
`ifdef RISCV_FORMAL
			rvfi_valid <= 0;
			rvfi_order <= 0;
			rvfi_insn <= 0;
			rvfi_trap <= 0;
			rvfi_halt <= 0;
			rvfi_intr <= 0;
			rvfi_mode <= 0;
			rvfi_ixl <= 0;
			rvfi_rs1_addr <= 0;
			rvfi_rs2_addr <= 0;
			rvfi_rs1_rdata <= 0;
			rvfi_rs2_rdata <= 0;
			rvfi_rd_addr <= 0;
			rvfi_rd_wdata <= 0;
			rvfi_pc_rdata <= 0;
			rvfi_pc_wdata <= 0;
			rvfi_mem_addr <= 0;
			rvfi_mem_rmask <= 0;
			rvfi_mem_wmask <= 0;
			rvfi_mem_rdata <= 0;
			rvfi_mem_wdata <= 0;
			rvfi_csr_mcycle_rmask <= 0;
			rvfi_csr_mcycle_wmask <= 0;
			rvfi_csr_mcycle_rdata <= 0;
			rvfi_csr_mcycle_wdata <= 0;
			rvfi_csr_minstret_rmask <= 0;
			rvfi_csr_minstret_wmask <= 0;
			rvfi_csr_minstret_rdata <= 0;
			rvfi_csr_minstret_wdata <= 0;
`endif
		end else begin
			trap <= 0;
			mem_valid <= 0;
			mem_instr <= 0;
			mem_wstrb <= 0;
			mem_wdata <= 0;
			mem_la_wdata <= 0;
			mem_la_wstrb <= 0;
			pcpi_valid <= 0;
			pcpi_insn <= 0;
			eoi <= 0;
			trace_valid <= 0;
			trace_data <= 0;
`ifdef RISCV_FORMAL
			rvfi_valid <= 0;
`endif

			case (state)
				S_IDLE: begin
					mem_valid <= 1;
					mem_instr <= 1;
					mem_addr <= pc;
					if (mem_ready) begin
						insn <= next_insn;
						mem_valid <= 0;
						state <= next_is_add ? S_ADD : S_HALT;
					end else begin
						state <= S_WAIT;
					end
				end
				S_WAIT: begin
					mem_valid <= 1;
					mem_instr <= 1;
					mem_addr <= pc;
					if (mem_ready) begin
						insn <= next_insn;
						mem_valid <= 0;
						state <= next_is_add ? S_ADD : S_HALT;
					end
				end
				S_ADD: begin
`ifdef RISCV_FORMAL
					rvfi_valid <= 1;
					rvfi_insn <= insn;
					rvfi_trap <= 0;
					rvfi_halt <= 0;
					rvfi_intr <= 0;
					rvfi_mode <= 3;
					rvfi_ixl <= 1;
					rvfi_rs1_addr <= insn[19:15];
					rvfi_rs2_addr <= insn[24:20];
					rvfi_rs1_rdata <= 0;
					rvfi_rs2_rdata <= 0;
					rvfi_rd_addr <= insn[11:7];
					rvfi_rd_wdata <= 0;
					rvfi_pc_rdata <= pc;
					rvfi_pc_wdata <= pc + 4;
					rvfi_mem_addr <= 0;
					rvfi_mem_rmask <= 0;
					rvfi_mem_wmask <= 0;
					rvfi_mem_rdata <= 0;
					rvfi_mem_wdata <= 0;
					rvfi_csr_mcycle_rmask <= 0;
					rvfi_csr_mcycle_wmask <= 0;
					rvfi_csr_mcycle_rdata <= 0;
					rvfi_csr_mcycle_wdata <= 0;
					rvfi_csr_minstret_rmask <= 0;
					rvfi_csr_minstret_wmask <= 0;
					rvfi_csr_minstret_rdata <= 0;
					rvfi_csr_minstret_wdata <= 0;
`endif
					pc <= pc + 4;
					state <= S_IDLE;
				end
				S_HALT: begin
					// stay halted
				end
			endcase
		end
	end
endmodule
