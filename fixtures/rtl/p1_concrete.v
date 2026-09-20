module p1_concrete(input clk, output done);
  reg [1:0] x = 2'b00;
  always @(posedge clk)
    x <= x == 2'b11 ? x : x + 2'b01;
  assign done = x == 2'b11;
endmodule
