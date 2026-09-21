module arithmetic(input clk, input [31:0] u, output reg [31:0] q = 0);
  always @(posedge clk) q <= u + 32'hffffffff;
endmodule

module delayed_bug(input clk, output q);
  reg [2:0] count = 0;
  always @(posedge clk) count <= count + 3'd1;
  assign q = count == 3'd3;
endmodule
