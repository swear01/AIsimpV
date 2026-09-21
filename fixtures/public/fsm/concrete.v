module fsm_concrete(input clk, input advance,
                    output idle, output busy, output done);
  (* keep, fsm_encoding = "none" *) reg [2:0] state = 3'b001;
  always @(posedge clk)
    if (advance)
      state <= state == 3'b001 ? 3'b010 :
               state == 3'b010 ? 3'b100 : 3'b001;
  assign idle = state == 3'b001;
  assign busy = state == 3'b010;
  assign done = state == 3'b100;
endmodule
