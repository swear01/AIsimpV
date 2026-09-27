// Derived single-property task for the freestyle rewrite experiment.
// This is not the upstream axilxbar formal suite.
module axilxbar_read_hold_property (
    input wire clk,
    input wire resetn,
    input wire rvalid,
    input wire rready,
    input wire [31:0] rdata,
    input wire [1:0] rresp
);
    reg f_past_valid = 1'b0;
    always @(posedge clk) begin
        f_past_valid <= 1'b1;
        if (f_past_valid && $past(resetn && rvalid && !rready) && resetn)
            assert(rvalid && rdata == $past(rdata) && rresp == $past(rresp));
    end
endmodule
