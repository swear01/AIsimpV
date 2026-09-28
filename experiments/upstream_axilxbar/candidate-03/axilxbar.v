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

    localparam LGNM = (NM > 1) ? $clog2(NM) : 1;
    localparam LGNS = (NS > 1) ? $clog2(NS+1) : 1;
    localparam DW = C_AXI_DATA_WIDTH;

    reg [NS:0] rgrant [0:NM-1];
    wire srgrant [0:NM-1];
    reg [LGNS-1:0] srindex [0:NM-1];
    reg [NS:0] rrequest [0:NM-1];

    reg [NS-1:0] busy;
    reg [NS-1:0] mrgrant;
    reg [LGNM-1:0] mrindex [0:NS-1];

    integer i, j, k;
    reg can;

    reg [NS-1:0] m_arvalid;
    reg [NS*AW-1:0] m_araddr;
    reg [NS*3-1:0] m_arprot;
    reg [NS-1:0] m_rready;
    reg [NM-1:0] s_arready;
    reg [NM-1:0] s_rvalid;
    reg [NM*DW-1:0] s_rdata;
    reg [NM*2-1:0] s_rresp;

    reg [NM-1:0] s_awready, s_wready, s_bvalid;
    reg [NM*2-1:0] s_bresp;
    reg [NM-1:0] awpend, wpend, bpend;

    assign S_AXI_AWREADY = s_awready;
    assign S_AXI_WREADY = s_wready;
    assign S_AXI_BVALID = s_bvalid;
    assign S_AXI_BRESP = s_bresp;
    assign S_AXI_ARREADY = s_arready;
    assign S_AXI_RVALID = s_rvalid;
    assign S_AXI_RDATA = s_rdata;
    assign S_AXI_RRESP = s_rresp;

    assign M_AXI_AWADDR = 0;
    assign M_AXI_AWPROT = 0;
    assign M_AXI_AWVALID = 0;
    assign M_AXI_WDATA = 0;
    assign M_AXI_WSTRB = 0;
    assign M_AXI_WVALID = 0;
    assign M_AXI_BREADY = 0;

    assign M_AXI_ARADDR = m_araddr;
    assign M_AXI_ARPROT = m_arprot;
    assign M_AXI_ARVALID = m_arvalid;
    assign M_AXI_RREADY = m_rready;

    genvar gN, gM;
    generate for (gN=0; gN<NM; gN=gN+1) begin : DECODE_READ
        integer kk;
        reg found;
        always @(*) begin
            rrequest[gN] = 0;
            found = 0;
            if (S_AXI_ARVALID[gN]) begin
                for (kk=0; kk<NS; kk=kk+1) begin
                    if (!found && (((S_AXI_ARADDR[gN*AW +: AW] ^ SLAVE_ADDR[kk*AW +: AW]) & SLAVE_MASK[kk*AW +: AW]) == 0)) begin
                        rrequest[gN] = (1 << kk);
                        found = 1;
                    end
                end
                if (!found) rrequest[gN][NS] = 1;
            end
        end
    end endgenerate

    generate for (gN=0; gN<NM; gN=gN+1) begin : SRGRANT
        assign srgrant[gN] = |rgrant[gN];
    end endgenerate

    always @(*) begin
        for (i=0; i<NS; i=i+1) begin
            busy[i] = 0;
            mrgrant[i] = 0;
            mrindex[i] = 0;
        end
        for (i=0; i<NM; i=i+1) begin
            for (j=0; j<NS; j=j+1) begin
                if (rgrant[i][j]) begin
                    busy[j] = 1;
                    mrgrant[j] = 1;
                    mrindex[j] = i;
                end
            end
        end
    end

    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            for (i=0; i<NM; i=i+1) begin
                rgrant[i] <= 0;
                srindex[i] <= 0;
            end
        end else begin
            for (i=0; i<NM; i=i+1) begin
                if (srgrant[i] && S_AXI_RVALID[i] && S_AXI_RREADY[i]) begin
                    rgrant[i] <= 0;
                    srindex[i] <= 0;
                end else if (!srgrant[i] && rrequest[i] != 0) begin
                    if (rrequest[i][NS]) begin
                        rgrant[i] <= (1 << NS);
                        srindex[i] <= NS;
                    end else begin
                        for (j=0; j<NS; j=j+1) begin
                            if (rrequest[i][j]) begin
                                can = 1;
                                if (busy[j]) can = 0;
                                for (k=0; k<i; k=k+1) begin
                                    if (!srgrant[k] && rrequest[k][j]) can = 0;
                                end
                                if (can) begin
                                    rgrant[i] <= (1 << j);
                                    srindex[i] <= j;
                                end
                            end
                        end
                    end
                end
            end
        end
    end

    always @(*) begin
        m_arvalid = 0;
        m_araddr = 0;
        m_arprot = 0;
        m_rready = 0;
        s_arready = 0;
        s_rvalid = 0;
        s_rdata = 0;
        s_rresp = 0;

        for (j=0; j<NS; j=j+1) begin
            for (i=0; i<NM; i=i+1) begin
                if (rgrant[i][j] && S_AXI_ARVALID[i]) begin
                    m_arvalid[j] = 1;
                    m_araddr[j*AW +: AW] = S_AXI_ARADDR[i*AW +: AW];
                    m_arprot[j*3 +: 3] = S_AXI_ARPROT[i*3 +: 3];
                end
                if (rgrant[i][j] && S_AXI_RREADY[i]) begin
                    m_rready[j] = 1;
                end
            end
        end

        for (i=0; i<NM; i=i+1) begin
            if (srgrant[i]) begin
                if (srindex[i] == NS) begin
                    s_arready[i] = 1;
                    s_rvalid[i] = 1;
                    s_rresp[i*2 +: 2] = 2'b11;
                    s_rdata[i*DW +: DW] = 0;
                end else begin
                    s_arready[i] = M_AXI_ARREADY[srindex[i]];
                    s_rvalid[i] = M_AXI_RVALID[srindex[i]];
                    s_rresp[i*2 +: 2] = M_AXI_RRESP[srindex[i]*2 +: 2];
                    s_rdata[i*DW +: DW] = M_AXI_RDATA[srindex[i]*DW +: DW];
                end
            end else begin
                s_arready[i] = 0;
                s_rvalid[i] = 0;
                s_rresp[i*2 +: 2] = 0;
                s_rdata[i*DW +: DW] = 0;
            end
        end
    end

    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            awpend <= 0;
            wpend <= 0;
            bpend <= 0;
        end else begin
            for (i=0; i<NM; i=i+1) begin
                if (S_AXI_AWVALID[i] && s_awready[i]) awpend[i] <= 1;
                if (S_AXI_WVALID[i] && s_wready[i]) wpend[i] <= 1;
                if (awpend[i] && wpend[i] && !bpend[i]) begin
                    bpend[i] <= 1;
                    awpend[i] <= 0;
                    wpend[i] <= 0;
                end
                if (bpend[i] && S_AXI_BREADY[i]) bpend[i] <= 0;
            end
        end
    end

    always @(*) begin
        for (i=0; i<NM; i=i+1) begin
            s_awready[i] = !awpend[i] && !bpend[i];
            s_wready[i] = !wpend[i] && !bpend[i];
            s_bvalid[i] = bpend[i];
            s_bresp[i*2 +: 2] = 2'b11;
        end
    end

`ifdef FORMAL
    generate for (gN=0; gN<NM; gN=gN+1) begin : CHECK_MASTER_GRANTS
        integer kk;
        always @(*) begin
            for (kk=0; kk<=NS; kk=kk+1) begin
                if (rgrant[gN][kk]) begin
                    assert((rgrant[gN] ^ (1<<kk)) == 0);
                    assert(srgrant[gN]);
                    assert(srindex[gN] == kk);
                    if (kk < NS) begin
                        assert(mrgrant[kk]);
                        assert(mrindex[kk] == gN);
                    end
                end
            end
            if (srgrant[gN]) assert(rgrant[gN] != 0);
            if (rrequest[gN][NS]) assert(rrequest[gN][NS-1:0] == 0);
        end
    end endgenerate
`endif

endmodule
`ifndef YOSYS
`default_nettype wire
`endif
