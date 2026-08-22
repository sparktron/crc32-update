module cycle(crc, data, next_crc);
input [31:0] crc;
input [63:0] data;
output [31:0] next_crc;
wire n0;
wire n1;
assign n0 = n1 ^ crc[0];
assign n1 = n0 ^ data[0];
assign next_crc[0] = n1;
endmodule
