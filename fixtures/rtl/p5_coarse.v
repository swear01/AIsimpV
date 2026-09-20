module p5_coarse(input clk, input en, input ready, input [1:0] z,
                 output reg v = 1'b0, output reg [1:0] q = 2'b00);
  wire load = !v || ready;
  always @(posedge clk) begin
    if (load) v <= en;
    q <= z;
  end
endmodule
