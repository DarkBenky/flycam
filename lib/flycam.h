#pragma once

/*
 * flycam receiver library — single header to include.
 *
 * Typical usage:
 *
 *   flycam_t *cam = flycam_create("tcp://host:5556", 16);
 *   while (running) {
 *       flycam_frame_t *f = flycam_poll(cam);
 *       if (f) {
 *           // f->pixels  — decoded ARGB image (width * height elements)
 *           // f->pos_*   — world-space position (metres from origin, or lat/lon/alt w/ GPS)
 *           // f->vel_*   — world-space velocity (m/s per axis)
 *           // f->rot_*   — orientation radians: pitch, roll, yaw
 *           // f->gps_fix — 0 = no fix
 *           flycam_frame_free(f);
 *       }
 *   }
 *   flycam_destroy(cam);
 */

#include <stdint.h>

typedef struct {
  uint32_t timestamp;
  uint32_t width;
  uint32_t height;
  uint32_t wire_size;

  /* World-space position (metres from origin, or lat/lon/alt when GPS fix > 0) */
  float pos_x, pos_y, pos_z;
  /* World-space velocity (m/s each axis) */
  float vel_x, vel_y, vel_z;
  /* Raw body-frame acceleration (m/s^2) */
  float acc_x, acc_y, acc_z;
  /* Raw body-frame angular rate (rad/s) */
  float gyr_x, gyr_y, gyr_z;
  /* Orientation in radians (complementary filter) */
  float rot_x; /* pitch */
  float rot_y; /* roll  */
  float rot_z; /* yaw   */
  /* GPS fix quality; 0 = no fix */
  float gps_fix;

  /* Decoded pixel buffer: 0x00BBGGRR, width*height elements. */
  uint32_t *pixels;
} flycam_frame_t;

typedef struct flycam flycam_t;

/* Connect to the ZMQ publisher at addr (e.g. "tcp://host:5556").
 * timeout_ms is the poll timeout per call to flycam_poll.
 * Returns NULL on failure. */
flycam_t *flycam_create(const char *addr, int timeout_ms);

/* Receive the next frame. Returns NULL when no frame is available within
 * the configured timeout. The caller must free the result with
 * flycam_frame_free. */
flycam_frame_t *flycam_poll(flycam_t *cam);

/* Release a frame returned by flycam_poll. */
void flycam_frame_free(flycam_frame_t *frame);

/* Disconnect and free all resources. */
void flycam_destroy(flycam_t *cam);

/* Print a one-line summary of frame telemetry to stdout. */
void flycam_frame_print(const flycam_frame_t *frame);
