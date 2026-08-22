module forward_reference(crc, data, next_crc);
input [31:0] crc;
input [63:0] data;
output [31:0] next_crc;
wire n0;
wire n1;
assign n1 = n0 ^ crc[0];
assign n0 = crc[1] ^ data[0];
assign next_crc[0] = n1;
endmodule
