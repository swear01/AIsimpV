module p1_abstract(input clk, input z, output done);
  reg d = 1'b0;
  always @(posedge clk)
    d <= d | z;
  assign done = d;
endmodule
