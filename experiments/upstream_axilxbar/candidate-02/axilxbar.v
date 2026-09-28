`default_nettype none
module axilxbar #(
    parameter integer C_AXI_DATA_WIDTH = 32,
    parameter integer C_AXI_ADDR_WIDTH = 32,
    parameter NM = 4,
    parameter NS = 8,
    localparam AW = C_AXI_ADDR_WIDTH,
    parameter [NS*AW-1:0] SLAVE_ADDR = {
        3'b111, {(AW-3){1'b0}},
        3'b110, {(AW-3){1'b0}},
        3'b101, {(AW-3){1'b0}},
        3'b100, {(AW-3){1'b0}},
        3'b011, {(AW-3){1'b0}},
        3'b010, {(AW-3){1'b0}},
        4'b0001, {(AW-4){1'b0}},
        4'b0000, {(AW-4){1'b0}} },
    parameter [NS*AW-1:0] SLAVE_MASK =
        (NS <= 1) ? {4'b1111, {(AW-4){1'b0}}}
        : { {(NS-2){3'b111, {(AW-3){1'b0}}}},
            {(2){4'b1111, {(AW-4){1'b0}}}} },
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
    localparam LGNM = (NM>1) ? $clog2(NM) : 1;
    localparam LGNS = (NS>1) ? $clog2(NS+1) : 1;
    localparam DW = C_AXI_DATA_WIDTH;

    assign S_AXI_AWREADY = 0;
    assign S_AXI_WREADY = 0;
    assign S_AXI_BVALID = 0;
    assign S_AXI_BRESP = 0;
    assign S_AXI_ARREADY = 0;
    assign S_AXI_RVALID = 0;
    assign S_AXI_RDATA = 0;
    assign S_AXI_RRESP = 0;

    assign M_AXI_AWADDR = 0;
    assign M_AXI_AWPROT = 0;
    assign M_AXI_AWVALID = 0;
    assign M_AXI_WDATA = 0;
    assign M_AXI_WSTRB = 0;
    assign M_AXI_WVALID = 0;
    assign M_AXI_BREADY = 0;
    assign M_AXI_ARADDR = 0;
    assign M_AXI_ARPROT = 0;
    assign M_AXI_ARVALID = 0;
    assign M_AXI_RREADY = 0;

    wire [NS:0] rrequest [0:NM-1];
    genvar N;
    generate for (N=0; N<NM; N=N+1) begin : GEN_ADDRDECODE
        addrdecode #(
            .AW(AW), .DW(3), .NS(NS),
            .SLAVE_ADDR(SLAVE_ADDR),
            .SLAVE_MASK(SLAVE_MASK),
            .OPT_REGISTERED(0)
        ) rddec (
            .i_clk(S_AXI_ACLK),
            .i_reset(!S_AXI_ARESETN),
            .i_valid(S_AXI_ARVALID[N]),
            .o_stall(),
            .i_addr(S_AXI_ARADDR[N*AW +: AW]),
            .i_data(S_AXI_ARPROT[N*3 +: 3]),
            .o_valid(),
            .i_stall(1'b0),
            .o_decode(rrequest[N]),
            .o_addr(),
            .o_data()
        );
    end endgenerate

    reg [NS:0] rgrant [0:NM-1];
    reg srgrant [0:NM-1];
    reg [LGNS-1:0] srindex [0:NM-1];
    reg [NS-1:0] mrgrant;
    reg [LGNM-1:0] mrindex [0:NS-1];

    integer iN, iM;
    reg taken;
    always @(*) begin
        for (iN=0; iN<NM; iN=iN+1) begin
            rgrant[iN] = 0;
            srgrant[iN] = 0;
            srindex[iN] = 0;
        end
        for (iM=0; iM<NS; iM=iM+1) begin
            mrgrant[iM] = 0;
            mrindex[iM] = 0;
        end

        for (iN=0; iN<NM; iN=iN+1) begin
            if (rrequest[iN][NS]) begin
                rgrant[iN][NS] = 1'b1;
                srgrant[iN] = 1'b1;
                srindex[iN] = NS;
            end
        end

        for (iM=0; iM<NS; iM=iM+1) begin
            taken = 0;
            for (iN=0; iN<NM; iN=iN+1) begin
                if (!taken && rrequest[iN][iM]) begin
                    rgrant[iN][iM] = 1'b1;
                    srgrant[iN] = 1'b1;
                    srindex[iN] = iM;
                    taken = 1;
                    mrindex[iM] = iN;
                    mrgrant[iM] = 1'b1;
                end
            end
        end
    end

`ifdef FORMAL
    initial assert(NS >= 1);
    initial assert(NM >= 1);

    generate for (N=0; N<NM; N=N+1) begin : CHECK_MASTER_GRANTS
        integer iM_prop;
        always @(*) begin
            for (iM_prop=0; iM_prop<=NS; iM_prop=iM_prop+1) begin
                if (rgrant[N][iM_prop]) begin
                    assert((rgrant[N] ^ (1 << iM_prop)) == 0);
                    assert(srgrant[N]);
                    assert(srindex[N] == iM_prop);
                    if (iM_prop < NS) begin
                        assert(mrgrant[iM_prop]);
                        assert(mrindex[iM_prop] == N);
                    end
                end
            end
        end

        always @(*) if (srgrant[N]) assert(rgrant[N] != 0);
        always @(*) if (rrequest[N][NS]) assert(rrequest[N][NS-1:0] == 0);
    end endgenerate
`endif

endmodule
`default_nettype wire
