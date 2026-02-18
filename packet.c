#include "packet.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zmq.h>

static inline uint32_t read_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
         ((uint32_t)p[3] << 24);
}

int packet_parse(const uint8_t *buf, size_t buf_len, packet_t *out) {
  const size_t meta_size =
      PACKET_MAX_METADATA * (PACKET_META_NAME_LEN + sizeof(float));
  if (buf_len < PACKET_HEADER_SIZE + meta_size) {
    fprintf(stderr, "packet_parse: buffer too small (%zu bytes)\n", buf_len);
    return -1;
  }

  out->timestamp = read_u32(buf + 0);
  out->width = read_u32(buf + 4);
  out->height = read_u32(buf + 8);
  out->channels = buf[12];

  if (out->channels > PACKET_MAX_CHANNELS) {
    fprintf(stderr, "packet_parse: too many channels (%u)\n", out->channels);
    return -1;
  }

  out->channel_bits[0] = buf[13];
  out->channel_bits[1] = buf[14];
  out->channel_bits[2] = buf[15];
  out->image_size = read_u32(buf + 16);

  size_t expected = PACKET_HEADER_SIZE + out->image_size + meta_size;
  if (buf_len < expected) {
    fprintf(stderr, "packet_parse: buffer too small (need %zu, got %zu)\n",
            expected, buf_len);
    return -1;
  }

  out->image_data = buf + PACKET_HEADER_SIZE;

  const uint8_t *meta_ptr = buf + PACKET_HEADER_SIZE + out->image_size;
  for (int i = 0; i < PACKET_MAX_METADATA; i++) {
    const uint8_t *entry = meta_ptr + i * 12;
    memcpy(out->metadata[i].name, entry, PACKET_META_NAME_LEN);
    out->metadata[i].name[PACKET_META_NAME_LEN] = '\0';
    memcpy(&out->metadata[i].value, entry + PACKET_META_NAME_LEN,
           sizeof(float));
  }

  return 0;
}

int packet_unpack_rgb(const packet_t *pkt, uint8_t *out_rgb) {
  if (!pkt || !out_rgb || !pkt->image_data)
    return -1;

  const uint8_t *src = pkt->image_data;
  uint32_t w = pkt->width;
  uint32_t h = pkt->height;
  uint8_t ch_n = pkt->channels;
  size_t bit_pos = 0;

  for (uint32_t y = 0; y < h; y++) {
    for (uint32_t x = 0; x < w; x++) {
      for (uint8_t ch = 0; ch < ch_n; ch++) {
        uint8_t ch_bits = pkt->channel_bits[ch];
        uint8_t mask = (uint8_t)((1u << ch_bits) - 1u);
        size_t byte_idx = bit_pos / 8;
        uint8_t offset = (uint8_t)(bit_pos % 8);
        uint8_t value = (src[byte_idx] >> offset) & mask;

        if ((offset + ch_bits) > 8)
          value |= (uint8_t)((src[byte_idx + 1] << (8u - offset)) & mask);

        out_rgb[(y * w + x) * ch_n + ch] = (uint8_t)(value << (8u - ch_bits));
        bit_pos += ch_bits;
      }
    }
  }

  return 0;
}

int packet_unpack_argb(const packet_t *pkt, uint32_t *out_argb) {
  if (!pkt || !out_argb || !pkt->image_data)
    return -1;

  const uint8_t *src = pkt->image_data;
  uint32_t w = pkt->width;
  uint32_t h = pkt->height;
  uint8_t ch_n = pkt->channels;
  size_t bit_pos = 0;
  uint8_t rgb[3];

  for (uint32_t y = 0; y < h; y++) {
    for (uint32_t x = 0; x < w; x++) {
      for (uint8_t ch = 0; ch < ch_n && ch < 3; ch++) {
        uint8_t ch_bits = pkt->channel_bits[ch];
        uint8_t mask = (uint8_t)((1u << ch_bits) - 1u);
        size_t byte_idx = bit_pos / 8;
        uint8_t offset = (uint8_t)(bit_pos % 8);
        uint8_t value = (src[byte_idx] >> offset) & mask;

        if ((offset + ch_bits) > 8)
          value |= (uint8_t)((src[byte_idx + 1] << (8u - offset)) & mask);

        rgb[ch] = (uint8_t)(value << (8u - ch_bits));
        bit_pos += ch_bits;
      }

      out_argb[y * w + x] =
          ((uint32_t)rgb[0] << 16) | ((uint32_t)rgb[1] << 8) | (uint32_t)rgb[2];
    }
  }

  return 0;
}

void packet_print_header(const packet_t *pkt) {
  printf("timestamp    : %u\n", pkt->timestamp);
  printf("resolution   : %ux%u  channels: %u\n", pkt->width, pkt->height,
         pkt->channels);
  printf("channel bits : R=%u G=%u B=%u\n", pkt->channel_bits[0],
         pkt->channel_bits[1], pkt->channel_bits[2]);
  printf("image size   : %u bytes\n", pkt->image_size);
  for (int i = 0; i < PACKET_MAX_METADATA; i++) {
    if (pkt->metadata[i].name[0] != '\0')
      printf("meta %-8s : %g\n", pkt->metadata[i].name, pkt->metadata[i].value);
  }
}

struct packet_receiver {
  void *zmq_ctx;
  void *zmq_sub;
  int timeout_ms;
  zmq_msg_t msg;
  int msg_open;
};

packet_receiver_t *packet_receiver_create(const char *addr, int timeout_ms) {
  packet_receiver_t *rx = calloc(1, sizeof(*rx));
  if (!rx)
    return NULL;

  rx->timeout_ms = timeout_ms;
  rx->zmq_ctx = zmq_ctx_new();
  rx->zmq_sub = zmq_socket(rx->zmq_ctx, ZMQ_SUB);

  if (zmq_connect(rx->zmq_sub, addr) != 0) {
    fprintf(stderr, "packet_receiver: failed to connect to %s\n", addr);
    packet_receiver_destroy(rx);
    return NULL;
  }

  zmq_setsockopt(rx->zmq_sub, ZMQ_SUBSCRIBE, "", 0);
  printf("packet_receiver: connected to %s\n", addr);
  return rx;
}

int packet_recv(packet_receiver_t *rx, packet_t *pkt) {
  if (rx->msg_open) {
    zmq_msg_close(&rx->msg);
    rx->msg_open = 0;
  }

  zmq_pollitem_t items[1] = {{rx->zmq_sub, 0, ZMQ_POLLIN, 0}};
  int rc = zmq_poll(items, 1, rx->timeout_ms);
  if (rc == 0)
    return 1;
  if (rc < 0)
    return -1;

  zmq_msg_init(&rx->msg);
  if (zmq_msg_recv(&rx->msg, rx->zmq_sub, 0) == -1) {
    zmq_msg_close(&rx->msg);
    return -1;
  }
  rx->msg_open = 1;

  return packet_parse(zmq_msg_data(&rx->msg), zmq_msg_size(&rx->msg), pkt);
}

void packet_receiver_destroy(packet_receiver_t *rx) {
  if (!rx)
    return;
  if (rx->msg_open)
    zmq_msg_close(&rx->msg);
  if (rx->zmq_sub)
    zmq_close(rx->zmq_sub);
  if (rx->zmq_ctx)
    zmq_ctx_destroy(rx->zmq_ctx);
  free(rx);
}
