module undefined_signal(crc, data, next_crc);
input [31:0] crc;
input [63:0] data;
output [31:0] next_crc;
assign next_crc[0] = missing_signal;
endmodule
