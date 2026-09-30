module tb(input clk, input resetn,
          output rvfi_valid, output [31:0] rvfi_insn,
          output [31:0] rvfi_pc_rdata, output [31:0] rvfi_rs1_rdata,
          output [31:0] rvfi_rs2_rdata, output [4:0] rvfi_rd_addr,
          output [31:0] rvfi_rd_wdata);
  wire mem_valid, mem_instr;
  wire [31:0] mem_addr;
  wire [31:0] mem_rdata = mem_addr == 0 ? 32'h00500093 :
                          mem_addr == 4 ? 32'h00700113 :
                          mem_addr == 8 ? 32'h002081b3 :
                          32'h00100073;
  picorv32 #(.COMPRESSED_ISA(1), .ENABLE_FAST_MUL(1),
             .ENABLE_DIV(1), .BARREL_SHIFTER(1)) dut (
    .clk(clk), .resetn(resetn), .mem_valid(mem_valid),
    .mem_instr(mem_instr), .mem_ready(mem_valid), .mem_addr(mem_addr),
    .mem_rdata(mem_rdata), .irq(32'b0), .pcpi_wr(1'b0),
    .pcpi_rd(32'b0), .pcpi_wait(1'b0), .pcpi_ready(1'b0),
    .rvfi_valid(rvfi_valid), .rvfi_insn(rvfi_insn),
    .rvfi_pc_rdata(rvfi_pc_rdata), .rvfi_rs1_rdata(rvfi_rs1_rdata),
    .rvfi_rs2_rdata(rvfi_rs2_rdata), .rvfi_rd_addr(rvfi_rd_addr),
    .rvfi_rd_wdata(rvfi_rd_wdata));
endmodule
