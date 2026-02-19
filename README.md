# Packet Structure

## Binary Format Specification

| Field Name  | Data Type   | Size (bytes) | Offset (bytes)  | Description                                  |
|-------------|-------------|--------------|-----------------|----------------------------------------------|
| timestamp   | uint32      | 4            | 0               | Timestamp in seconds since epoch             |
| width       | uint32      | 4            | 4               | Image width in pixels                        |
| height      | uint32      | 4            | 8               | Image height in pixels                       |
| channels    | uint8       | 1            | 12              | Number of color channels (3 for RGB)         |
| red_bits    | uint8       | 1            | 13              | Bit depth for red channel                    |
| green_bits  | uint8       | 1            | 14              | Bit depth for green channel                  |
| blue_bits   | uint8       | 1            | 15              | Bit depth for blue channel                   |
| compression | uint8       | 1            | 16              | Compression flag: 0=none, 1=lz4              |
| image_size  | uint32      | 4            | 17              | Size of image data in bytes (after compression) |
| image_data  | bytes       | variable     | 21              | Packed/quantized image data                  |
| metadata    | struct[256] | 3072         | 21 + image_size | Array of 256 metadata entries                |

## Metadata Entry Structure (12 bytes each)

| Field Name  | Data Type | Size (bytes) | Description                  |
|-------------|-----------|--------------|------------------------------|
| name        | char[8]   | 8            | ASCII string, null-padded    |
| value       | float32   | 4            | Floating point value         |

## Total Packet Size

```
Header: 21 bytes
Image Data: variable (compressed with LZ4 when compression=1)
Metadata: 3,072 bytes (256 entries x 12 bytes)
Total: 21 + image_size + 3,072 bytes
```

## Pipeline

```
Pi camera -> quantize (reduce bit depth per channel) -> LZ4 compress -> send via ZMQ PUSH
Go server -> receive PULL -> forward via ZMQ PUB
C client  -> receive SUB -> check compression flag -> LZ4 decompress if needed -> unpack bits -> display
```