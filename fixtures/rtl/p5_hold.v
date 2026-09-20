module p5_hold(input clk, input en, input ready, input [1:0] z,
               output reg v = 1'b0, output reg [1:0] q = 2'b00);
  wire load = !v || ready;
  always @(posedge clk) begin
    if (load) v <= en;
    if (load && en) q <= z;
  end
endmodule
