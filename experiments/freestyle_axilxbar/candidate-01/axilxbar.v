`default_nettype none
module axilxbar #(
    parameter integer C_AXI_DATA_WIDTH = 32,
    parameter integer C_AXI_ADDR_WIDTH = 32,
    parameter NM = 4,
    parameter NS = 8,
    parameter [NS*C_AXI_ADDR_WIDTH-1:0] SLAVE_ADDR = 0,
    parameter [NS*C_AXI_ADDR_WIDTH-1:0] SLAVE_MASK = 0,
    parameter [0:0] OPT_LOWPOWER = 1,
    parameter OPT_LINGER = 4,
    parameter LGMAXBURST = 5
) (
    input wire S_AXI_ACLK,
    input wire S_AXI_ARESETN,
    input wire [NM-1:0] S_AXI_AWVALID,
    output wire [NM-1:0] S_AXI_AWREADY,
    input wire [NM*C_AXI_ADDR_WIDTH-1:0] S_AXI_AWADDR,
    input wire [NM*3-1:0] S_AXI_AWPROT,
    input wire [NM-1:0] S_AXI_WVALID,
    output wire [NM-1:0] S_AXI_WREADY,
    input wire [NM*C_AXI_DATA_WIDTH-1:0] S_AXI_WDATA,
    input wire [NM*C_AXI_DATA_WIDTH/8-1:0] S_AXI_WSTRB,
    output wire [NM-1:0] S_AXI_BVALID,
    input wire [NM-1:0] S_AXI_BREADY,
    output wire [NM*2-1:0] S_AXI_BRESP,
    input wire [NM-1:0] S_AXI_ARVALID,
    output wire [NM-1:0] S_AXI_ARREADY,
    input wire [NM*C_AXI_ADDR_WIDTH-1:0] S_AXI_ARADDR,
    input wire [NM*3-1:0] S_AXI_ARPROT,
    output wire [NM-1:0] S_AXI_RVALID,
    input wire [NM-1:0] S_AXI_RREADY,
    output wire [NM*C_AXI_DATA_WIDTH-1:0] S_AXI_RDATA,
    output wire [NM*2-1:0] S_AXI_RRESP,
    output wire [NS*C_AXI_ADDR_WIDTH-1:0] M_AXI_AWADDR,
    output wire [NS*3-1:0] M_AXI_AWPROT,
    output wire [NS-1:0] M_AXI_AWVALID,
    input wire [NS-1:0] M_AXI_AWREADY,
    output wire [NS*C_AXI_DATA_WIDTH-1:0] M_AXI_WDATA,
    output wire [NS*C_AXI_DATA_WIDTH/8-1:0] M_AXI_WSTRB,
    output wire [NS-1:0] M_AXI_WVALID,
    input wire [NS-1:0] M_AXI_WREADY,
    input wire [NS*2-1:0] M_AXI_BRESP,
    input wire [NS-1:0] M_AXI_BVALID,
    output wire [NS-1:0] M_AXI_BREADY,
    output wire [NS*C_AXI_ADDR_WIDTH-1:0] M_AXI_ARADDR,
    output wire [NS*3-1:0] M_AXI_ARPROT,
    output wire [NS-1:0] M_AXI_ARVALID,
    input wire [NS-1:0] M_AXI_ARREADY,
    input wire [NS*C_AXI_DATA_WIDTH-1:0] M_AXI_RDATA,
    input wire [NS*2-1:0] M_AXI_RRESP,
    input wire [NS-1:0] M_AXI_RVALID,
    output wire [NS-1:0] M_AXI_RREADY
);
    localparam AW = C_AXI_ADDR_WIDTH;
    localparam DW = C_AXI_DATA_WIDTH;
    genvar n, m;

    assign S_AXI_AWREADY = {NM{1'b0}};
    assign S_AXI_WREADY  = {NM{1'b0}};
    assign S_AXI_BVALID  = {NM{1'b0}};
    assign S_AXI_BRESP   = {(NM*2){1'b0}};

    assign M_AXI_AWVALID = {NS{1'b0}};
    assign M_AXI_AWADDR  = {(NS*AW){1'b0}};
    assign M_AXI_AWPROT  = {(NS*3){1'b0}};
    assign M_AXI_WVALID  = {NS{1'b0}};
    assign M_AXI_WDATA   = {(NS*DW){1'b0}};
    assign M_AXI_WSTRB   = {(NS*(DW/8)){1'b0}};
    assign M_AXI_BREADY  = {NS{1'b0}};

    assign S_AXI_ARREADY[0] = M_AXI_ARREADY[0];
    assign M_AXI_ARVALID[0] = S_AXI_ARVALID[0];
    assign M_AXI_ARADDR[0*AW +: AW] = S_AXI_ARADDR[0*AW +: AW];
    assign M_AXI_ARPROT[0*3 +: 3]   = S_AXI_ARPROT[0*3 +: 3];

    reg        rvalid_q;
    reg [DW-1:0] rdata_q;
    reg [1:0]    rresp_q;

    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            rvalid_q <= 1'b0;
            rdata_q  <= {DW{1'b0}};
            rresp_q  <= 2'b00;
        end else if (rvalid_q && !S_AXI_RREADY[0]) begin
        end else begin
            rvalid_q <= M_AXI_RVALID[0];
            rdata_q  <= M_AXI_RDATA[0*DW +: DW];
            rresp_q  <= M_AXI_RRESP[0*2 +: 2];
        end
    end

    assign S_AXI_RVALID[0] = rvalid_q;
    assign S_AXI_RDATA[0*DW +: DW] = rdata_q;
    assign S_AXI_RRESP[0*2 +: 2] = rresp_q;
    assign M_AXI_RREADY[0] = S_AXI_RREADY[0];

    generate
        for (n = 1; n < NM; n = n + 1) begin : OTHER_MASTERS
            assign S_AXI_ARREADY[n] = 1'b0;
            assign S_AXI_RVALID[n] = 1'b0;
            assign S_AXI_RDATA[n*DW +: DW] = {DW{1'b0}};
            assign S_AXI_RRESP[n*2 +: 2] = 2'b00;
        end
    endgenerate

    generate
        for (m = 1; m < NS; m = m + 1) begin : OTHER_SLAVES
            assign M_AXI_ARVALID[m] = 1'b0;
            assign M_AXI_ARADDR[m*AW +: AW] = {AW{1'b0}};
            assign M_AXI_ARPROT[m*3 +: 3] = 3'b000;
            assign M_AXI_RREADY[m] = 1'b0;
        end
    endgenerate
endmodule
`default_nettype wire
