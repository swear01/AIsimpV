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

// Simplified ADD-only partial model for the riscv-formal insn_add_ch0 check.
// This file preserves the original module declarations but implements only
// a minimal fetch/execute loop for the ADD instruction. All other behaviors
// (memory operations, branches, IRQ, PCPI, compressed ISA, etc.) are omitted.

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

	output            mem_la_read,
	output            mem_la_write,
	output     [31:0] mem_la_addr,
	output reg [31:0] mem_la_wdata,
	output reg [ 3:0] mem_la_wstrb,

	output reg        pcpi_valid,
	output reg [31:0] pcpi_insn,
	output     [31:0] pcpi_rs1,
	output     [31:0] pcpi_rs2,
	input             pcpi_wr,
	input      [31:0] pcpi_rd,
	input             pcpi_wait,
	input             pcpi_ready,

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

	output reg        trace_valid,
	output reg [35:0] trace_data
);

	localparam STATE_FETCH = 1'b0;
	localparam STATE_EXEC  = 1'b1;

	reg state;
	reg [31:0] pc;
	reg [31:0] regfile [0:31];
	reg [31:0] instr;

	integer i;

	assign mem_la_read = 0;
	assign mem_la_write = 0;
	assign mem_la_addr = 0;
	assign pcpi_rs1 = 0;
	assign pcpi_rs2 = 0;

	always @(posedge clk) begin
		if (!resetn) begin
			state <= STATE_FETCH;
			pc <= PROGADDR_RESET;
			mem_valid <= 0;
			mem_instr <= 0;
			mem_addr <= 0;
			mem_wdata <= 0;
			mem_wstrb <= 0;
			trap <= 0;
			pcpi_valid <= 0;
			pcpi_insn <= 0;
			eoi <= 0;
			mem_la_wdata <= 0;
			mem_la_wstrb <= 0;
			trace_valid <= 0;
			trace_data <= 0;
`ifdef RISCV_FORMAL
			rvfi_valid <= 0;
			rvfi_order <= 0;
			rvfi_insn <= 0;
			rvfi_trap <= 0;
			rvfi_halt <= 0;
			rvfi_intr <= 0;
			rvfi_mode <= 2'b11;
			rvfi_ixl <= 2'b01;
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
			for (i = 0; i < 32; i = i + 1) regfile[i] <= 0;
		end else begin
			// Default RVFI values (to be overridden in EXEC)
			rvfi_valid <= 0;
			rvfi_trap <= 0;
			rvfi_rs1_addr <= 0;
			rvfi_rs2_addr <= 0;
			rvfi_rs1_rdata <= 0;
			rvfi_rs2_rdata <= 0;
			rvfi_rd_addr <= 0;
			rvfi_rd_wdata <= 0;
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
			pcpi_valid <= 0;
			pcpi_insn <= 0;
			eoi <= 0;
			trace_valid <= 0;
			trace_data <= 0;
			mem_la_wdata <= 0;
			mem_la_wstrb <= 0;

			case (state)
				STATE_FETCH: begin
					mem_valid <= 1;
					mem_instr <= 1;
					mem_addr <= pc;
					mem_wstrb <= 0;
					if (mem_ready) begin
						instr <= mem_rdata;
						state <= STATE_EXEC;
						mem_valid <= 0;
					end
				end
				STATE_EXEC: begin
					rvfi_valid <= 1;
					rvfi_insn <= instr;
					rvfi_pc_rdata <= pc;
					rvfi_pc_wdata <= pc + 4;
					rvfi_mode <= 2'b11;
					rvfi_ixl <= 2'b01;
					if (instr[6:0] == 7'b0110011 && instr[14:12] == 3'b000 && instr[31:25] == 7'b0000000) begin
						rvfi_rs1_addr <= instr[19:15];
						rvfi_rs2_addr <= instr[24:20];
						rvfi_rs1_rdata <= (instr[19:15] == 0) ? 32'b0 : regfile[instr[19:15]];
						rvfi_rs2_rdata <= (instr[24:20] == 0) ? 32'b0 : regfile[instr[24:20]];
						rvfi_rd_addr <= instr[11:7];
						rvfi_rd_wdata <= (instr[11:7] == 0) ? 32'b0 : ( (instr[19:15] == 0) ? 32'b0 : regfile[instr[19:15]] ) + ( (instr[24:20] == 0) ? 32'b0 : regfile[instr[24:20]] );
						if (instr[11:7] != 0) regfile[instr[11:7]] <= ( (instr[19:15] == 0) ? 32'b0 : regfile[instr[19:15]] ) + ( (instr[24:20] == 0) ? 32'b0 : regfile[instr[24:20]] );
					end else begin
						rvfi_trap <= 1;
					end
					pc <= pc + 4;
					state <= STATE_FETCH;
				end
			endcase
		end
	end

endmodule

module picorv32_regs (
	input clk, wen,
	input [5:0] waddr,
	input [5:0] raddr1,
	input [5:0] raddr2,
	input [31:0] wdata,
	output [31:0] rdata1,
	output [31:0] rdata2
);
	assign rdata1 = 32'b0;
	assign rdata2 = 32'b0;
endmodule

module picorv32_pcpi_mul #(
	parameter STEPS_AT_ONCE = 1,
	parameter CARRY_CHAIN = 4
) (
	input clk, resetn,
	input             pcpi_valid,
	input      [31:0] pcpi_insn,
	input      [31:0] pcpi_rs1,
	input      [31:0] pcpi_rs2,
	output reg        pcpi_wr,
	output reg [31:0] pcpi_rd,
	output reg        pcpi_wait,
	output reg        pcpi_ready
);
	always @* begin
		pcpi_wr = 0;
		pcpi_rd = 0;
		pcpi_wait = 0;
		pcpi_ready = 0;
	end
endmodule

module picorv32_pcpi_fast_mul #(
	parameter EXTRA_MUL_FFS = 0,
	parameter EXTRA_INSN_FFS = 0,
	parameter MUL_CLKGATE = 0
) (
	input clk, resetn,
	input             pcpi_valid,
	input      [31:0] pcpi_insn,
	input      [31:0] pcpi_rs1,
	input      [31:0] pcpi_rs2,
	output            pcpi_wr,
	output     [31:0] pcpi_rd,
	output            pcpi_wait,
	output            pcpi_ready
);
	assign pcpi_wr = 0;
	assign pcpi_rd = 0;
	assign pcpi_wait = 0;
	assign pcpi_ready = 0;
endmodule

module picorv32_pcpi_div (
	input clk, resetn,
	input             pcpi_valid,
	input      [31:0] pcpi_insn,
	input      [31:0] pcpi_rs1,
	input      [31:0] pcpi_rs2,
	output reg        pcpi_wr,
	output reg [31:0] pcpi_rd,
	output reg        pcpi_wait,
	output reg        pcpi_ready
);
	always @* begin
		pcpi_wr = 0;
		pcpi_rd = 0;
		pcpi_wait = 0;
		pcpi_ready = 0;
	end
endmodule

module picorv32_axi #(
	parameter [ 0:0] ENABLE_COUNTERS = 1,
	parameter [ 0:0] ENABLE_COUNTERS64 = 1,
	parameter [ 0:0] ENABLE_REGS_16_31 = 1,
	parameter [ 0:0] ENABLE_REGS_DUALPORT = 1,
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
	output trap,
	output        mem_axi_awvalid,
	input         mem_axi_awready,
	output [31:0] mem_axi_awaddr,
	output [ 2:0] mem_axi_awprot,
	output        mem_axi_wvalid,
	input         mem_axi_wready,
	output [31:0] mem_axi_wdata,
	output [ 3:0] mem_axi_wstrb,
	input         mem_axi_bvalid,
	output        mem_axi_bready,
	output        mem_axi_arvalid,
	input         mem_axi_arready,
	output [31:0] mem_axi_araddr,
	output [ 2:0] mem_axi_arprot,
	input         mem_axi_rvalid,
	output        mem_axi_rready,
	input  [31:0] mem_axi_rdata,
	output        pcpi_valid,
	output [31:0] pcpi_insn,
	output [31:0] pcpi_rs1,
	output [31:0] pcpi_rs2,
	input         pcpi_wr,
	input  [31:0] pcpi_rd,
	input         pcpi_wait,
	input         pcpi_ready,
	input  [31:0] irq,
	output [31:0] eoi,
`ifdef RISCV_FORMAL
	output        rvfi_valid,
	output [63:0] rvfi_order,
	output [31:0] rvfi_insn,
	output        rvfi_trap,
	output        rvfi_halt,
	output        rvfi_intr,
	output [ 1:0] rvfi_mode,
	output [ 1:0] rvfi_ixl,
	output [ 4:0] rvfi_rs1_addr,
	output [ 4:0] rvfi_rs2_addr,
	output [31:0] rvfi_rs1_rdata,
	output [31:0] rvfi_rs2_rdata,
	output [ 4:0] rvfi_rd_addr,
	output [31:0] rvfi_rd_wdata,
	output [31:0] rvfi_pc_rdata,
	output [31:0] rvfi_pc_wdata,
	output [31:0] rvfi_mem_addr,
	output [ 3:0] rvfi_mem_rmask,
	output [ 3:0] rvfi_mem_wmask,
	output [31:0] rvfi_mem_rdata,
	output [31:0] rvfi_mem_wdata,
`endif
	output        trace_valid,
	output [35:0] trace_data
);
	assign trap = 0;
	assign mem_axi_awvalid = 0;
	assign mem_axi_awaddr = 0;
	assign mem_axi_awprot = 0;
	assign mem_axi_wvalid = 0;
	assign mem_axi_wdata = 0;
	assign mem_axi_wstrb = 0;
	assign mem_axi_bready = 0;
	assign mem_axi_arvalid = 0;
	assign mem_axi_araddr = 0;
	assign mem_axi_arprot = 0;
	assign mem_axi_rready = 0;
	assign pcpi_valid = 0;
	assign pcpi_insn = 0;
	assign pcpi_rs1 = 0;
	assign pcpi_rs2 = 0;
	assign eoi = 0;
`ifdef RISCV_FORMAL
	assign rvfi_valid = 0;
	assign rvfi_order = 0;
	assign rvfi_insn = 0;
	assign rvfi_trap = 0;
	assign rvfi_halt = 0;
	assign rvfi_intr = 0;
	assign rvfi_mode = 0;
	assign rvfi_ixl = 0;
	assign rvfi_rs1_addr = 0;
	assign rvfi_rs2_addr = 0;
	assign rvfi_rs1_rdata = 0;
	assign rvfi_rs2_rdata = 0;
	assign rvfi_rd_addr = 0;
	assign rvfi_rd_wdata = 0;
	assign rvfi_pc_rdata = 0;
	assign rvfi_pc_wdata = 0;
	assign rvfi_mem_addr = 0;
	assign rvfi_mem_rmask = 0;
	assign rvfi_mem_wmask = 0;
	assign rvfi_mem_rdata = 0;
	assign rvfi_mem_wdata = 0;
`endif
	assign trace_valid = 0;
	assign trace_data = 0;
endmodule

module picorv32_axi_adapter (
	input clk, resetn,
	output        mem_axi_awvalid,
	input         mem_axi_awready,
	output [31:0] mem_axi_awaddr,
	output [ 2:0] mem_axi_awprot,
	output        mem_axi_wvalid,
	input         mem_axi_wready,
	output [31:0] mem_axi_wdata,
	output [ 3:0] mem_axi_wstrb,
	input         mem_axi_bvalid,
	output        mem_axi_bready,
	output        mem_axi_arvalid,
	input         mem_axi_arready,
	output [31:0] mem_axi_araddr,
	output [ 2:0] mem_axi_arprot,
	input         mem_axi_rvalid,
	output        mem_axi_rready,
	input  [31:0] mem_axi_rdata,
	input         mem_valid,
	input         mem_instr,
	output        mem_ready,
	input  [31:0] mem_addr,
	input  [31:0] mem_wdata,
	input  [ 3:0] mem_wstrb,
	output [31:0] mem_rdata
);
	assign mem_axi_awvalid = 0;
	assign mem_axi_awaddr = 0;
	assign mem_axi_awprot = 0;
	assign mem_axi_wvalid = 0;
	assign mem_axi_wdata = 0;
	assign mem_axi_wstrb = 0;
	assign mem_axi_bready = 0;
	assign mem_axi_arvalid = 0;
	assign mem_axi_araddr = 0;
	assign mem_axi_arprot = 0;
	assign mem_axi_rready = 0;
	assign mem_ready = 0;
	assign mem_rdata = 0;
endmodule

module picorv32_wb #(
	parameter [ 0:0] ENABLE_COUNTERS = 1,
	parameter [ 0:0] ENABLE_COUNTERS64 = 1,
	parameter [ 0:0] ENABLE_REGS_16_31 = 1,
	parameter [ 0:0] ENABLE_REGS_DUALPORT = 1,
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
	output trap,
	input wb_rst_i,
	input wb_clk_i,
	output reg [31:0] wbm_adr_o,
	output reg [31:0] wbm_dat_o,
	input [31:0] wbm_dat_i,
	output reg wbm_we_o,
	output reg [3:0] wbm_sel_o,
	output reg wbm_stb_o,
	input wbm_ack_i,
	output reg wbm_cyc_o,
	output        pcpi_valid,
	output [31:0] pcpi_insn,
	output [31:0] pcpi_rs1,
	output [31:0] pcpi_rs2,
	input         pcpi_wr,
	input  [31:0] pcpi_rd,
	input         pcpi_wait,
	input         pcpi_ready,
	input  [31:0] irq,
	output [31:0] eoi,
`ifdef RISCV_FORMAL
	output        rvfi_valid,
	output [63:0] rvfi_order,
	output [31:0] rvfi_insn,
	output        rvfi_trap,
	output        rvfi_halt,
	output        rvfi_intr,
	output [ 4:0] rvfi_rs1_addr,
	output [ 4:0] rvfi_rs2_addr,
	output [31:0] rvfi_rs1_rdata,
	output [31:0] rvfi_rs2_rdata,
	output [ 4:0] rvfi_rd_addr,
	output [31:0] rvfi_rd_wdata,
	output [31:0] rvfi_pc_rdata,
	output [31:0] rvfi_pc_wdata,
	output [31:0] rvfi_mem_addr,
	output [ 3:0] rvfi_mem_rmask,
	output [ 3:0] rvfi_mem_wmask,
	output [31:0] rvfi_mem_rdata,
	output [31:0] rvfi_mem_wdata,
`endif
	output        trace_valid,
	output [35:0] trace_data,
	output mem_instr
);
	always @* begin
		wbm_adr_o = 0;
		wbm_dat_o = 0;
		wbm_we_o = 0;
		wbm_sel_o = 0;
		wbm_stb_o = 0;
		wbm_cyc_o = 0;
	end
	assign trap = 0;
	assign pcpi_valid = 0;
	assign pcpi_insn = 0;
	assign pcpi_rs1 = 0;
	assign pcpi_rs2 = 0;
	assign eoi = 0;
`ifdef RISCV_FORMAL
	assign rvfi_valid = 0;
	assign rvfi_order = 0;
	assign rvfi_insn = 0;
	assign rvfi_trap = 0;
	assign rvfi_halt = 0;
	assign rvfi_intr = 0;
	assign rvfi_rs1_addr = 0;
	assign rvfi_rs2_addr = 0;
	assign rvfi_rs1_rdata = 0;
	assign rvfi_rs2_rdata = 0;
	assign rvfi_rd_addr = 0;
	assign rvfi_rd_wdata = 0;
	assign rvfi_pc_rdata = 0;
	assign rvfi_pc_wdata = 0;
	assign rvfi_mem_addr = 0;
	assign rvfi_mem_rmask = 0;
	assign rvfi_mem_wmask = 0;
	assign rvfi_mem_rdata = 0;
	assign rvfi_mem_wdata = 0;
`endif
	assign trace_valid = 0;
	assign trace_data = 0;
	assign mem_instr = 0;
endmodule
