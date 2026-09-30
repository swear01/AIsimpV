if {![info exists ::env(PICO_RTL)] || ![info exists ::env(PICO_DB)] || ![info exists ::env(PICO_PARAMS)]} {
    puts stderr "Set PICO_RTL, PICO_DB, and PICO_PARAMS before running dc_shell."
    exit 2
}

set target_library [list $::env(PICO_DB)]
set link_library [concat * $target_library]
define_design_lib WORK -path ./WORK

set defines {RISCV_FORMAL DEBUGNETS}
if {[info exists ::env(PICO_DEFINES)]} {
    set defines $::env(PICO_DEFINES)
}
if {$defines eq ""} {
    set analyzed [analyze -format sverilog $::env(PICO_RTL)]
} else {
    set analyzed [analyze -format sverilog -define [split $defines] $::env(PICO_RTL)]
}
if {$analyzed != 1} {
    puts stderr "RTL analysis failed."
    exit 2
}
if {[elaborate picorv32 -parameters $::env(PICO_PARAMS)] != 1} {
    puts stderr "Top elaboration failed."
    exit 2
}
link
check_design
create_clock -period 20 [get_ports clk]
compile -map_effort medium -area_effort high -ungroup_all

puts "MAPPED_CELL_COUNT=[sizeof_collection [get_cells -hierarchical *]]"
report_area
report_reference
exit
