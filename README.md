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
| image_size  | uint32      | 4            | 16              | Size of compressed image data in bytes       |
| image_data  | bytes       | variable     | 20              | Packed/quantized image data                  |
| metadata    | struct[256] | 3072         | 20 + image_size | Array of 256 metadata entries                |

## Metadata Entry Structure (12 bytes each)

| Field Name  | Data Type | Size (bytes) | Description                  |
|-------------|-----------|--------------|------------------------------|
| name        | char[8]   | 8            | ASCII string, null-padded    |
| value       | float32   | 4            | Floating point value         |

## Total Packet Size

```
Header: 20 bytes
Image Data: variable (typically ~4,050 bytes with 4-7-5 bit quantization for 1920x1080)
Metadata: 3,072 bytes (256 entries × 12 bytes)
Total: 20 + image_size + 3,072 bytes
```