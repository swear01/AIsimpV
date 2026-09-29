`timescale 1ns/1ps
module tb_rvfi_trace;
  reg clk = 0;
  always #5 clk = ~clk;
  reg resetn = 0;
  wire trap, mem_valid, mem_instr;
  wire [31:0] mem_addr;
  reg [31:0] mem_rdata;
  wire rvfi_valid;
  wire [63:0] rvfi_order;
  wire [31:0] rvfi_insn, rvfi_pc_rdata, rvfi_pc_wdata, rvfi_rd_wdata;
  wire [4:0] rvfi_rd_addr;

  always @* begin
    case (mem_addr)
      32'h00: mem_rdata = 32'h00500093; // addi x1, x0, 5
      32'h04: mem_rdata = 32'h00708113; // addi x2, x1, 7
      32'h08: mem_rdata = 32'h002081b3; // add  x3, x1, x2
      32'h0c: mem_rdata = 32'h40118233; // sub  x4, x3, x1
      32'h10: mem_rdata = 32'h00324293; // xori x5, x4, 3
      32'h14: mem_rdata = 32'h00128313; // addi x6, x5, 1
      32'h18: mem_rdata = 32'h0000006f; // jal  x0, 0
      default: mem_rdata = 32'h00000013;
    endcase
  end

  picorv32 #(
    .COMPRESSED_ISA(1), .ENABLE_FAST_MUL(1), .ENABLE_DIV(1), .BARREL_SHIFTER(1)
  ) dut (
    .clk(clk), .resetn(resetn), .trap(trap),
    .mem_valid(mem_valid), .mem_instr(mem_instr), .mem_ready(1'b1),
    .mem_addr(mem_addr), .mem_wdata(), .mem_wstrb(), .mem_rdata(mem_rdata),
    .mem_la_read(), .mem_la_write(), .mem_la_addr(), .mem_la_wdata(), .mem_la_wstrb(),
    .pcpi_valid(), .pcpi_insn(), .pcpi_rs1(), .pcpi_rs2(),
    .pcpi_wr(1'b0), .pcpi_rd(32'b0), .pcpi_wait(1'b0), .pcpi_ready(1'b0),
    .irq(32'b0), .eoi(),
    .rvfi_valid(rvfi_valid), .rvfi_order(rvfi_order), .rvfi_insn(rvfi_insn),
    .rvfi_pc_rdata(rvfi_pc_rdata), .rvfi_pc_wdata(rvfi_pc_wdata),
    .rvfi_rd_addr(rvfi_rd_addr), .rvfi_rd_wdata(rvfi_rd_wdata),
    .trace_valid(), .trace_data()
  );

  integer cycles = 0, retired = 0;
  initial begin
    repeat (4) @(negedge clk);
    resetn = 1;
  end
  always @(posedge clk) begin
    #1;
    cycles = cycles + 1;
    if (trap || cycles > 200) $fatal(1, "Core trapped or timed out");
    if (rvfi_valid) begin
      $display("TRACE %0d %08h %08h %08h %0d %08h",
               rvfi_order, rvfi_insn, rvfi_pc_rdata, rvfi_pc_wdata,
               rvfi_rd_addr, rvfi_rd_wdata);
      retired = retired + 1;
      if (retired == 7) $finish;
    end
  end
endmodule
