module tb_mul_engines;
  reg clk = 0;
  always #5 clk = ~clk;

  reg resetn = 0;
  reg valid = 0;
  reg [31:0] insn = 0, rs1 = 0, rs2 = 0;
  wire fast_ready, slow_ready;
  wire [31:0] fast_data, slow_data;

  picorv32_pcpi_fast_mul fast_mul (
    .clk(clk), .resetn(resetn), .pcpi_valid(valid), .pcpi_insn(insn),
    .pcpi_rs1(rs1), .pcpi_rs2(rs2), .pcpi_wr(), .pcpi_rd(fast_data),
    .pcpi_wait(), .pcpi_ready(fast_ready)
  );
  picorv32_pcpi_mul #(.STEPS_AT_ONCE(8)) slow_mul (
    .clk(clk), .resetn(resetn), .pcpi_valid(valid), .pcpi_insn(insn),
    .pcpi_rs1(rs1), .pcpi_rs2(rs2), .pcpi_wr(), .pcpi_rd(slow_data),
    .pcpi_wait(), .pcpi_ready(slow_ready)
  );

  task check_case(input [2:0] funct3, input [31:0] a, b);
    integer cycle;
    reg got_fast, got_slow;
    reg [31:0] first_fast, first_slow;
    begin
      @(negedge clk);
      resetn = 0;
      valid = 0;
      repeat (4) @(negedge clk);
      insn = 32'h02000033 | (funct3 << 12);
      rs1 = a;
      rs2 = b;
      resetn = 1;
      valid = 1;
      got_fast = 0;
      got_slow = 0;
      for (cycle = 0; cycle < 20; cycle = cycle + 1) begin
        @(posedge clk);
        #1;
        if (fast_ready && !got_fast) begin
          first_fast = fast_data;
          got_fast = 1;
        end
        if (slow_ready && !got_slow) begin
          first_slow = slow_data;
          got_slow = 1;
        end
      end
      if (!got_fast || !got_slow || first_fast !== first_slow)
        $fatal(1, "MUL mismatch funct3=%0d a=%h b=%h fast=%h slow=%h seen=%b%b",
               funct3, a, b, first_fast, first_slow, got_fast, got_slow);
    end
  endtask

  integer op;
  initial begin
    for (op = 0; op < 4; op = op + 1) begin
      check_case(op[2:0], 32'h00000001, 32'h00000002);
      check_case(op[2:0], 32'hffffffff, 32'h00000007);
      check_case(op[2:0], 32'h80000000, 32'h7fffffff);
      check_case(op[2:0], 32'hdeadcafe, 32'h12345678);
    end
    $display("PASS: 16 MUL/MULH/MULHSU/MULHU comparisons within 20 cycles");
    $finish;
  end
endmodule
