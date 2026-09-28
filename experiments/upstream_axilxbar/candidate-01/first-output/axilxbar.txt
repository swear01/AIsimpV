Patch to upstream/rtl/axilxbar.v: keep the file unchanged except replace the read-grant checking block inside `CHECK_MASTER_GRANTS` (the section beginning with `// Read grant checking` and ending before its `end endgenerate`) with the following:

```verilog
`ifdef FORMAL
    generate for (N=0; N<NM; N=N+1)
    begin : CHECK_MASTER_GRANTS_READ_SIMPLE
        always @(*)
        begin
            // Grant and valid must agree for the read channel.
            assert(srgrant[N] == (rgrant[N] != 0));

            if (srgrant[N])
            begin
                // Index must be a valid route index: 0..NS inclusive.
                assert(srindex[N] <= NS);

                // Exactly one selected route, and it matches srindex.
                assert(rgrant[N] == ({{(NS){1'b0}}, 1'b1} << srindex[N]));

                // If a real slave is selected, reciprocal slave-side
                // grant/index must agree.
                if (srindex[N] < NS)
                begin
                    assert(mrgrant[srindex[N]]);
                    assert(mrindex[srindex[N]] == N);
                end
            end

            // Error route is exclusive of real slave routes.
            if (rrequest[N][NS])
                assert(rrequest[N][NS-1:0] == 0);
        end
    end endgenerate
`endif
```

Rest of upstream/rtl/axilxbar.v is unchanged.