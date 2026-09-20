module p5_bug(input clk, input en, input ready,
              output reg v = 1'b0, output reg [1:0] q = 2'b00);
  reg [1:0] x = 2'b00;
  wire load = !v || ready;
  always @(posedge clk) begin
    x <= x + 2'b01;
    if (load) v <= en;
    if (en) q <= x ^ 2'b11;
  end
endmodule
