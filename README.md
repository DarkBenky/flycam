# Packet Structure

## Video Packet Format

Sent from the Pi to the Go server (port 5555) and forwarded to clients (port 5556).

| Field Name | Data Type | Size (bytes) | Offset (bytes) | Description                          |
|------------|-----------|--------------|----------------|--------------------------------------|
| timestamp  | uint32    | 4            | 0              | Seconds since epoch (low 32 bits)    |
| width      | uint32    | 4            | 4              | Image width in pixels                |
| height     | uint32    | 4            | 8              | Image height in pixels               |
| jpeg_size  | uint32    | 4            | 12             | Size of JPEG payload in bytes        |
| jpeg_data  | bytes     | jpeg_size    | 16             | Standard JPEG image data             |

**Total:** 16 + jpeg_size bytes per frame

## Metadata Packet Format

Sent on a **separate** ZMQ channel (Pi → port 5557, clients subscribe on port 5558).
Updated infrequently (every few seconds) so it never blocks the video path.

| Field Name | Data Type | Size (bytes)  | Offset (bytes) | Description                   |
|------------|-----------|---------------|----------------|-------------------------------|
| timestamp  | uint32    | 4             | 0              | Seconds since epoch           |
| count      | uint32    | 4             | 4              | Number of metadata entries    |
| name[i]    | char[8]   | 8             | 8 + i×12       | ASCII key, null-padded        |
| value[i]   | float32   | 4             | 16 + i×12      | Floating-point value          |

**Total:** 8 + count × 12 bytes per metadata message

## Port Map

| Port | Direction        | Content           |
|------|------------------|-------------------|
| 5555 | Pi → Go (PUSH/PULL) | Video frames   |
| 5556 | Go → clients (PUB/SUB) | Video frames |
| 5557 | Pi → Go (PUSH/PULL) | Metadata       |
| 5558 | Go → clients (PUB/SUB) | Metadata     |

## Pipeline

```
Pi camera (BGR888) → JPEG encode (cv2, quality 75) → ZMQ PUSH :5555
                                                              ↓
                                               Go server PULL :5555 → PUB :5556
                                                              ↓
                                         C client SUB :5556 → libjpeg decode → MiniFB display

Pi camera metadata → ZMQ PUSH :5557
                             ↓
              Go server PULL :5557 → PUB :5558
                             ↓
          C client SUB :5558 → cached in socket, attached to next frame
```

## Encoding Choice: JPEG

JPEG is used instead of H.264 for the following reasons:

- **Minimum latency**: JPEG is intra-frame only — no B-frames, no GOP buffering. Each
  frame decodes independently in microseconds.
- **Raspberry Pi friendly**: OpenCV's JPEG encoder offloads work efficiently; quality 75
  gives ~10:1 compression with negligible CPU overhead on a Pi 4/5.
- **Simplicity**: No codec state to maintain — every frame is self-contained so packet
  loss or reorder causes at most one bad frame.

Typical bandwidth at 320×320, JPEG quality 75: **~3–8 KB/frame** vs. ~150 KB raw or
~50–100 KB with the old bit-packing + LZ4 approach.