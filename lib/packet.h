#pragma once

#include <stdint.h>

/*
 * Packet layout (68-byte header + JPEG):
 *
 *  Offset | Field     | Type    | Size
 *  -------|-----------|---------|-----
 *  0      | timestamp | uint32  | 4
 *  4      | width     | uint32  | 4
 *  8      | height    | uint32  | 4
 *  12     | jpeg_size | uint32  | 4
 *  16     | pos_lat   | float32 | 4
 *  20     | pos_lon   | float32 | 4
 *  24     | pos_alt   | float32 | 4
 *  28     | vel_x     | float32 | 4
 *  32     | vel_y     | float32 | 4
 *  36     | vel_z     | float32 | 4
 *  40     | acc_x     | float32 | 4
 *  44     | acc_y     | float32 | 4
 *  48     | acc_z     | float32 | 4
 *  52     | gyr_x     | float32 | 4
 *  56     | gyr_y     | float32 | 4
 *  60     | gyr_z     | float32 | 4
 *  64     | gps_fix   | float32 | 4  (0=no fix)
 *  68     | jpeg_data | bytes   | jpeg_size
 */

#define FLYCAM_VIDEO_HEADER_SIZE 68

/* Decoded frame returned by readSocket.
 * pixels is a width*height buffer in MiniFB 0x00BBGGRR format.
 * Free with freeFrame(). */
typedef struct {
  uint32_t timestamp;
  uint32_t width;
  uint32_t height;
  uint32_t wire_size;
  float pos_lat, pos_lon, pos_alt;
  float vel_x, vel_y, vel_z;
  float acc_x, acc_y, acc_z;
  float gyr_x, gyr_y, gyr_z;
  float gps_fix;
  uint32_t *pixels;
} frame_t;

typedef struct flycam_socket flycam_socket_t;

/* video_address : ZMQ PUB address (e.g. "tcp://host:5556").
 * timeout_ms    : poll timeout in milliseconds before returning NULL. */
flycam_socket_t *initSocket(const char *video_address, int timeout_ms);
frame_t *readSocket(flycam_socket_t *sock);
void freeFrame(frame_t *frame);
void freeSocket(flycam_socket_t *sock);
