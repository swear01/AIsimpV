module abstract_design(
  input wire i_clk,
  input wire i_reset,
  input wire i_valid,
  input wire [7:0] i_data,
  input wire i_ready,
  input wire [7:0] z,
  output wire o_ready,
  output reg o_valid = 1'b0,
  output reg [7:0] o_data = 8'h00
);
  reg r_valid = 1'b0;

  assign o_ready = !r_valid;

  always @(posedge i_clk) begin
    if (i_reset) begin
      r_valid <= 1'b0;
      o_valid <= 1'b0;
    end else begin
      if (i_valid && !r_valid && o_valid && !i_ready)
        r_valid <= 1'b1;
      else if (i_ready)
        r_valid <= 1'b0;

      if (!o_valid || i_ready)
        o_valid <= i_valid || r_valid;
    end

    if (!o_valid || i_ready)
      o_data <= r_valid ? z : i_data;
  end
endmodule
