module fsm_coarse(input clk, input advance, input [1:0] z,
                  output idle, output busy, output done);
  (* keep, fsm_encoding = "none" *) reg [1:0] state = 2'b00;
  always @(posedge clk)
    state <= z;
  assign idle = state == 2'b00;
  assign busy = state == 2'b01;
  assign done = state == 2'b10;
endmodule
