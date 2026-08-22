module forbidden_gate(crc, data, next_crc);
input [31:0] crc;
input [63:0] data;
output [31:0] next_crc;
and g0 (.a(crc[0]), .b(data[0]), .y(next_crc[0]));
endmodule
