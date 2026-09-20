module fsm_good(input clk, input advance,
                output idle, output busy, output done);
  (* keep, fsm_encoding = "none" *) reg [1:0] state = 2'b00;
  always @(posedge clk)
    if (advance)
      state <= state == 2'b00 ? 2'b01 :
               state == 2'b01 ? 2'b10 : 2'b00;
  assign idle = state == 2'b00;
  assign busy = state == 2'b01;
  assign done = state == 2'b10;
endmodule
