// Correct over-approximation that drops the sum relation between the views.
module pipeline_coarse(
    input clock, reset,
    input [31:0] dataIn, c1, c2, z, z2,
    output reg [31:0] dataOut = 0,
    output reg [31:0] tmp_stageOne = 0,
    output reg [31:0] tmp_stageTwo = 0
);
    reg [31:0] sum = 0;
    always @(posedge clock) begin
        sum <= (dataIn + c1) + (z & c2);
        dataOut <= reset ? 32'b0 : sum;
        tmp_stageOne <= z;
        tmp_stageTwo <= z2;
    end
endmodule
