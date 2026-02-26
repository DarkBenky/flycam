#pragma once

#include <stdint.h>

/*
 * Packet layout (80-byte header + JPEG):
 *
 *  Offset | Field     | Type    | Size
 *  -------|-----------|---------|-----
 *  0      | timestamp | uint32  | 4
 *  4      | width     | uint32  | 4
 *  8      | height    | uint32  | 4
 *  12     | jpeg_size | uint32  | 4
 *  16     | pos_x     | float32 | 4  (lat/lon/alt with GPS, metres without)
 *  20     | pos_y     | float32 | 4
 *  24     | pos_z     | float32 | 4
 *  28     | vel_x     | float32 | 4
 *  32     | vel_y     | float32 | 4
 *  36     | vel_z     | float32 | 4
 *  40     | acc_x     | float32 | 4
 *  44     | acc_y     | float32 | 4
 *  48     | acc_z     | float32 | 4
 *  52     | gyr_x     | float32 | 4
 *  56     | gyr_y     | float32 | 4
 *  60     | gyr_z     | float32 | 4
 *  64     | pitch     | float32 | 4  (radians, complementary filter)
 *  68     | roll      | float32 | 4
 *  72     | yaw       | float32 | 4  (gyro-integrated, drifts without mag)
 *  76     | gps_fix   | float32 | 4  (0=no fix)
 *  80     | jpeg_data | bytes   | jpeg_size
 */

#define FLYCAM_VIDEO_HEADER_SIZE 80

typedef struct {
  uint32_t timestamp;
  uint32_t width;
  uint32_t height;
  uint32_t wire_size;
  float pos_x, pos_y, pos_z;
  float vel_x, vel_y, vel_z;
  float acc_x, acc_y, acc_z;
  float gyr_x, gyr_y, gyr_z;
  float pitch, roll, yaw;
  float gps_fix;
  uint32_t *pixels;
} frame_t;

typedef struct flycam_socket flycam_socket_t;

flycam_socket_t *initSocket(const char *video_address, int timeout_ms);
frame_t *readSocket(flycam_socket_t *sock);
void freeFrame(frame_t *frame);
void freeSocket(flycam_socket_t *sock);
