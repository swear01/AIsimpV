// Authored gold fixture; COARSE removes the data-hold relation deliberately.
`default_nettype none
module skid_abstract #(
    parameter DW = 8,
    parameter COARSE = 0
) (
    input wire i_clk, i_reset,
    input wire i_valid, i_ready,
    input wire [DW-1:0] i_data,
    input wire [DW-1:0] z,
    output wire o_ready, o_valid,
    output reg [DW-1:0] o_data = 0
);
    reg [1:0] n = 0;
    assign o_ready = n != 2;
    assign o_valid = n != 0;

    always @(posedge i_clk)
        if (i_reset)
            n <= 0;
        else if (n == 0)
            n <= i_valid ? 1 : 0;
        else if (n == 1)
            n <= i_ready ? (i_valid ? 1 : 0) : (i_valid ? 2 : 1);
        else if (n == 2)
            n <= i_ready ? 1 : 2;
        else
            n <= 0;

    always @(posedge i_clk)
        if (COARSE)
            o_data <= z;
        else if (n == 0 || i_ready)
            o_data <= n == 2 ? z : i_data;
endmodule
