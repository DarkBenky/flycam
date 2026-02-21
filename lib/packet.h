#pragma once

#include <stdint.h>

/*
 * Video packet layout (JPEG encoding):
 *
 *  Offset  | Field     | Type   | Size
 *  --------|-----------|--------|-----
 *  0       | timestamp | uint32 | 4
 *  4       | width     | uint32 | 4
 *  8       | height    | uint32 | 4
 *  12      | jpeg_size | uint32 | 4
 *  16      | jpeg_data | bytes  | jpeg_size
 *
 * Metadata packet layout (separate ZMQ channel, ports 5557/5558):
 *
 *  Offset    | Field      | Type    | Size
 *  ----------|------------|---------|-----
 *  0         | timestamp  | uint32  | 4
 *  4         | count      | uint32  | 4
 *  8 + i*12  | name[i]    | char[8] | 8  (ASCII, null-padded)
 *  16 + i*12 | value[i]   | float32 | 4
 */

#define FLYCAM_VIDEO_HEADER_SIZE 16
#define FLYCAM_META_HEADER_SIZE   8
#define FLYCAM_META_ENTRY_SIZE   12
#define FLYCAM_MAX_METADATA      32
#define FLYCAM_META_NAME_LEN      8

typedef struct {
  char  name[FLYCAM_META_NAME_LEN + 1];
  float value;
} flycam_meta_entry_t;

/* Decoded frame returned by readSocket.
 * pixels is a width*height buffer in MiniFB 0x00BBGGRR format owned by this
 * struct.  Free with freeFrame(). */
typedef struct {
  uint32_t            timestamp;
  uint32_t            width;
  uint32_t            height;
  uint32_t            wire_size;     /* raw JPEG bytes received over the wire */
  flycam_meta_entry_t metadata[FLYCAM_MAX_METADATA];
  int                 metadata_count;
  uint32_t           *pixels;
} frame_t;

typedef struct flycam_socket flycam_socket_t;

/* video_address : ZMQ PUB address for video frames (e.g. "tcp://host:5556").
 * meta_address  : ZMQ PUB address for metadata     (e.g. "tcp://host:5558").
 *                 Pass NULL to disable the metadata channel.
 * timeout_ms    : poll timeout in milliseconds before returning NULL. */
flycam_socket_t *initSocket(const char *video_address,
                             const char *meta_address,
                             int         timeout_ms);
frame_t         *readSocket(flycam_socket_t *sock);
void             freeFrame(frame_t *frame);
void             freeSocket(flycam_socket_t *sock);
