#pragma once

#include <stddef.h>
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

#define PACKET_MAX_CHANNELS 3
#define PACKET_MAX_METADATA 256
#define PACKET_META_NAME_LEN 8
#define PACKET_HEADER_SIZE 21

typedef struct {
  char name[PACKET_META_NAME_LEN + 1];
  float value;
} packet_meta_entry_t;

typedef struct {
  uint32_t timestamp;
  uint32_t width;
  uint32_t height;
  uint8_t channels;
  uint8_t channel_bits[PACKET_MAX_CHANNELS];
  uint8_t compression;
  uint32_t image_size;
  const uint8_t *image_data;
  packet_meta_entry_t metadata[PACKET_MAX_METADATA];
} packet_t;

int packet_parse(const uint8_t *buf, size_t buf_len, packet_t *out);
int packet_unpack_rgb(const packet_t *pkt, uint8_t *out_rgb);
int packet_unpack_argb(const packet_t *pkt, uint32_t *out_argb);
void packet_print_header(const packet_t *pkt);

typedef struct packet_receiver packet_receiver_t;

packet_receiver_t *packet_receiver_create(const char *addr, int timeout_ms);
int packet_recv(packet_receiver_t *rx, packet_t *pkt);
void packet_receiver_destroy(packet_receiver_t *rx);
