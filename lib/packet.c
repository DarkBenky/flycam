#include "packet.h"

#include <limits.h>
#include <lz4.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zmq.h>

#define PACKET_HEADER_SIZE 21

/* Internal raw packet as parsed from the wire buffer. */
typedef struct {
  uint32_t timestamp;
  uint32_t width;
  uint32_t height;
  uint8_t channels;
  uint8_t channel_bits[FLYCAM_MAX_CHANNELS];
  uint8_t compression;
  uint32_t image_size;
  const uint8_t *image_data;
  flycam_meta_entry_t metadata[FLYCAM_MAX_METADATA];
} raw_packet_t;

static inline uint32_t read_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
         ((uint32_t)p[3] << 24);
}

static int parse_packet(const uint8_t *buf, size_t buf_len, raw_packet_t *out) {
  const size_t meta_size =
      FLYCAM_MAX_METADATA * (FLYCAM_META_NAME_LEN + sizeof(float));
  if (buf_len < PACKET_HEADER_SIZE + meta_size) {
    fprintf(stderr, "parse_packet: buffer too small (%zu bytes)\n", buf_len);
    return -1;
  }

  out->timestamp = read_u32(buf + 0);
  out->width = read_u32(buf + 4);
  out->height = read_u32(buf + 8);
  out->channels = buf[12];

  if (out->channels > FLYCAM_MAX_CHANNELS) {
    fprintf(stderr, "parse_packet: too many channels (%u)\n", out->channels);
    return -1;
  }

  out->channel_bits[0] = buf[13];
  out->channel_bits[1] = buf[14];
  out->channel_bits[2] = buf[15];
  out->compression = buf[16];
  out->image_size = read_u32(buf + 17);

  size_t expected = PACKET_HEADER_SIZE + out->image_size + meta_size;
  if (buf_len < expected) {
    fprintf(stderr, "parse_packet: buffer too small (need %zu, got %zu)\n",
            expected, buf_len);
    return -1;
  }

  out->image_data = buf + PACKET_HEADER_SIZE;

  const uint8_t *meta_ptr = buf + PACKET_HEADER_SIZE + out->image_size;
  for (int i = 0; i < FLYCAM_MAX_METADATA; i++) {
    const uint8_t *entry = meta_ptr + i * 12;
    memcpy(out->metadata[i].name, entry, FLYCAM_META_NAME_LEN);
    out->metadata[i].name[FLYCAM_META_NAME_LEN] = '\0';
    memcpy(&out->metadata[i].value, entry + FLYCAM_META_NAME_LEN,
           sizeof(float));
  }

  return 0;
}

static int unpack_argb(const raw_packet_t *pkt, uint32_t *out_argb) {
  if (!pkt || !pkt->image_data || !out_argb)
    return -1;

  const uint8_t *src = pkt->image_data;
  uint32_t w = pkt->width;
  uint32_t h = pkt->height;
  uint8_t ch_n = pkt->channels;
  size_t bit_pos = 0;
  size_t image_bytes = pkt->image_size;
  uint8_t rgb[3];

  for (uint32_t y = 0; y < h; y++) {
    for (uint32_t x = 0; x < w; x++) {
      for (uint8_t ch = 0; ch < ch_n && ch < 3; ch++) {
        uint8_t ch_bits = pkt->channel_bits[ch];
        uint8_t mask = (uint8_t)((1u << ch_bits) - 1u);
        size_t byte_idx = bit_pos / 8;
        uint8_t offset = (uint8_t)(bit_pos % 8);

        if (byte_idx >= image_bytes)
          return -1;

        uint8_t value = (src[byte_idx] >> offset) & mask;

        if ((offset + ch_bits) > 8) {
          if (byte_idx + 1 >= image_bytes)
            return -1;
          value |= (uint8_t)((src[byte_idx + 1] << (8u - offset)) & mask);
        }

        rgb[ch] = (uint8_t)(value << (8u - ch_bits));
        bit_pos += ch_bits;
      }

      out_argb[y * w + x] =
          ((uint32_t)rgb[0] << 16) | ((uint32_t)rgb[1] << 8) | (uint32_t)rgb[2];
    }
  }

  return 0;
}

struct flycam_socket {
  void *zmq_ctx;
  void *zmq_sub;
  int timeout_ms;
  zmq_msg_t msg;
  int msg_open;
  uint8_t *decomp_buf;
  size_t decomp_buf_size;
};

flycam_socket_t *initSocket(const char *address, int timeout_ms) {
  flycam_socket_t *sock = calloc(1, sizeof(*sock));
  if (!sock)
    return NULL;

  sock->timeout_ms = timeout_ms;
  sock->zmq_ctx = zmq_ctx_new();
  sock->zmq_sub = zmq_socket(sock->zmq_ctx, ZMQ_SUB);

  if (zmq_connect(sock->zmq_sub, address) != 0) {
    fprintf(stderr, "initSocket: failed to connect to %s\n", address);
    freeSocket(sock);
    return NULL;
  }

  zmq_setsockopt(sock->zmq_sub, ZMQ_SUBSCRIBE, "", 0);
  printf("initSocket: connected to %s\n", address);
  return sock;
}

frame_t *readSocket(flycam_socket_t *sock) {
  if (!sock)
    return NULL;

  if (sock->msg_open) {
    zmq_msg_close(&sock->msg);
    sock->msg_open = 0;
  }

  zmq_pollitem_t items[1] = {{sock->zmq_sub, 0, ZMQ_POLLIN, 0}};
  int rc = zmq_poll(items, 1, sock->timeout_ms);
  if (rc <= 0)
    return NULL;

  zmq_msg_init(&sock->msg);
  if (zmq_msg_recv(&sock->msg, sock->zmq_sub, 0) == -1) {
    zmq_msg_close(&sock->msg);
    return NULL;
  }
  sock->msg_open = 1;

  size_t wire_size = zmq_msg_size(&sock->msg);

  raw_packet_t pkt;
  if (parse_packet(zmq_msg_data(&sock->msg), wire_size, &pkt) != 0)
    return NULL;

  if (pkt.compression == 1) {
    size_t total_bits =
        (size_t)pkt.width * pkt.height *
        (pkt.channel_bits[0] + pkt.channel_bits[1] + pkt.channel_bits[2]);
    size_t decomp_size = (total_bits + 7) / 8;

    if (decomp_size > sock->decomp_buf_size) {
      uint8_t *buf = realloc(sock->decomp_buf, decomp_size);
      if (!buf) {
        fprintf(stderr, "readSocket: out of memory for decompression\n");
        return NULL;
      }
      sock->decomp_buf = buf;
      sock->decomp_buf_size = decomp_size;
    }

    if (decomp_size > (size_t)INT_MAX || pkt.image_size > (uint32_t)INT_MAX) {
      fprintf(stderr, "readSocket: image size too large for LZ4\n");
      return NULL;
    }

    int result = LZ4_decompress_safe((const char *)pkt.image_data,
                                     (char *)sock->decomp_buf,
                                     (int)pkt.image_size, (int)decomp_size);

    if (result < 0) {
      fprintf(stderr, "readSocket: LZ4 decompression failed (%d)\n", result);
      return NULL;
    }

    pkt.image_data = sock->decomp_buf;
    pkt.image_size = (uint32_t)result;
  }

  frame_t *frame = malloc(sizeof(*frame));
  if (!frame)
    return NULL;

  frame->timestamp = pkt.timestamp;
  frame->width = pkt.width;
  frame->height = pkt.height;
  frame->channels = pkt.channels;
  frame->channel_bits[0] = pkt.channel_bits[0];
  frame->channel_bits[1] = pkt.channel_bits[1];
  frame->channel_bits[2] = pkt.channel_bits[2];
  frame->compression = pkt.compression;
  frame->image_size = pkt.image_size;
  frame->wire_size = (uint32_t)wire_size;
  memcpy(frame->metadata, pkt.metadata, sizeof(frame->metadata));

  size_t pixel_count = (size_t)pkt.width * pkt.height;
  if (pkt.width != 0 && pixel_count / pkt.width != pkt.height) {
    free(frame);
    return NULL;
  }

  frame->pixels = malloc(pixel_count * sizeof(uint32_t));
  if (!frame->pixels) {
    free(frame);
    return NULL;
  }

  if (unpack_argb(&pkt, frame->pixels) != 0) {
    free(frame->pixels);
    free(frame);
    return NULL;
  }

  return frame;
}

void freeFrame(frame_t *frame) {
  if (!frame)
    return;
  free(frame->pixels);
  free(frame);
}

void freeSocket(flycam_socket_t *sock) {
  if (!sock)
    return;
  if (sock->msg_open)
    zmq_msg_close(&sock->msg);
  if (sock->zmq_sub)
    zmq_close(sock->zmq_sub);
  if (sock->zmq_ctx)
    zmq_ctx_destroy(sock->zmq_ctx);
  free(sock->decomp_buf);
  free(sock);
}
