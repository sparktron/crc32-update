module crc32_reference(crc, data, next_crc);
    input [31:0] crc;
    input [63:0] data;
    output reg [31:0] next_crc;

    integer bit_index;
    reg [31:0] state;

    always @* begin
        state = crc;
        for (bit_index = 0; bit_index < 64; bit_index = bit_index + 1) begin
            state = (state >> 1)
                ^ (32'hEDB88320 & {32{state[0] ^ data[bit_index]}});
        end
        next_crc = state;
    end
endmodule
