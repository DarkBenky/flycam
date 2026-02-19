#pragma once

#include <stdint.h>

/*
 * Binary packet layout:
 *
 *  Offset  | Field        | Type    | Size
 *  --------|--------------|---------|-----
 *  0       | timestamp    | uint32  | 4
 *  4       | width        | uint32  | 4
 *  8       | height       | uint32  | 4
 *  12      | channels     | uint8   | 1
 *  13      | red_bits     | uint8   | 1
 *  14      | green_bits   | uint8   | 1
 *  15      | blue_bits    | uint8   | 1
 *  16      | compression  | uint8   | 1   (0=none, 1=lz4)
 *  17      | image_size   | uint32  | 4
 *  21      | image_data   | bytes   | image_size
 *  21+img  | metadata     | entry[] | 256 * 12
 *
 *  Metadata entry: char[8] name + float32 value
 */

#define FLYCAM_MAX_CHANNELS 3
#define FLYCAM_MAX_METADATA 256
#define FLYCAM_META_NAME_LEN 8

typedef struct {
  char name[FLYCAM_META_NAME_LEN + 1];
  float value;
} flycam_meta_entry_t;

/* Decoded frame returned by readSocket.
 * pixels is a width*height ARGB buffer owned by this struct.
 * Free with freeFrame(). */
typedef struct {
  uint32_t timestamp;
  uint32_t width;
  uint32_t height;
  uint8_t channels;
  uint8_t channel_bits[FLYCAM_MAX_CHANNELS];
  uint8_t compression;
  uint32_t image_size;
  flycam_meta_entry_t metadata[FLYCAM_MAX_METADATA];
  uint32_t *pixels;
} frame_t;

typedef struct flycam_socket flycam_socket_t;

flycam_socket_t *initSocket(const char *address, int timeout_ms);
frame_t        *readSocket(flycam_socket_t *sock);
void            freeFrame(frame_t *frame);
void            freeSocket(flycam_socket_t *sock);
