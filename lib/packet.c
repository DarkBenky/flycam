#include "packet.h"

#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zmq.h>
#include <jpeglib.h>

#define VIDEO_HEADER_SIZE 16  /* timestamp(4) + width(4) + height(4) + jpeg_size(4) */
#define META_HEADER_SIZE   8  /* timestamp(4) + count(4) */
#define META_ENTRY_SIZE   12  /* name[8] + float32(4) */

static inline uint32_t read_u32le(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* ---- JPEG decode -------------------------------------------------- */

/* Extended error manager that uses setjmp so JPEG errors don't abort(). */
struct jpeg_error_mgr_ex {
  struct jpeg_error_mgr base;
  jmp_buf               env;
};

static void jpeg_error_exit_cb(j_common_ptr cinfo) {
  struct jpeg_error_mgr_ex *err = (struct jpeg_error_mgr_ex *)cinfo->err;
  longjmp(err->env, 1);
}

/*
 * Decode a JPEG payload into the MiniFB pixel format (0x00BBGGRR).
 * expected_w / expected_h must match the JPEG dimensions.
 * Returns 0 on success, -1 on failure.
 */
static int decode_jpeg_to_pixels(const uint8_t *jpeg_data, uint32_t jpeg_size,
                                  uint32_t expected_w, uint32_t expected_h,
                                  uint32_t *out_pixels) {
  struct jpeg_decompress_struct cinfo;
  struct jpeg_error_mgr_ex      jerr;

  cinfo.err            = jpeg_std_error(&jerr.base);
  jerr.base.error_exit = jpeg_error_exit_cb;

  if (setjmp(jerr.env)) {
    jpeg_destroy_decompress(&cinfo);
    return -1;
  }

  jpeg_create_decompress(&cinfo);
  jpeg_mem_src(&cinfo, (unsigned char *)jpeg_data, (unsigned long)jpeg_size);

  if (jpeg_read_header(&cinfo, TRUE) != JPEG_HEADER_OK) {
    jpeg_destroy_decompress(&cinfo);
    return -1;
  }

  cinfo.out_color_space = JCS_RGB;
  jpeg_start_decompress(&cinfo);

  if (cinfo.output_width != expected_w || cinfo.output_height != expected_h) {
    fprintf(stderr, "decode_jpeg: size mismatch (got %ux%u, want %ux%u)\n",
            cinfo.output_width, cinfo.output_height, expected_w, expected_h);
    jpeg_abort_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    return -1;
  }

  uint32_t row_stride = expected_w * 3u;
  uint8_t *row_buf    = (uint8_t *)malloc(row_stride);
  if (!row_buf) {
    jpeg_abort_decompress(&cinfo);
    jpeg_destroy_decompress(&cinfo);
    return -1;
  }

  while (cinfo.output_scanline < cinfo.output_height) {
    JSAMPROW rows[1] = {(JSAMPROW)row_buf};
    jpeg_read_scanlines(&cinfo, rows, 1);

    uint32_t y = cinfo.output_scanline - 1;
    for (uint32_t x = 0; x < expected_w; x++) {
      uint8_t r = row_buf[x * 3u + 0u];
      uint8_t g = row_buf[x * 3u + 1u];
      uint8_t b = row_buf[x * 3u + 2u];
      /* MiniFB 0x00BBGGRR: R in the lowest byte */
      out_pixels[y * expected_w + x] =
          ((uint32_t)b << 16) | ((uint32_t)g << 8) | (uint32_t)r;
    }
  }

  free(row_buf);
  jpeg_finish_decompress(&cinfo);
  jpeg_destroy_decompress(&cinfo);
  return 0;
}

/* ---- Socket ------------------------------------------------------- */

struct flycam_socket {
  void     *zmq_ctx;
  void     *zmq_video;  /* SUB socket for video frames */
  void     *zmq_meta;   /* SUB socket for metadata (may be NULL) */
  int       timeout_ms;
  zmq_msg_t msg;
  int       msg_open;
  flycam_meta_entry_t cached_meta[FLYCAM_MAX_METADATA];
  int                 cached_meta_count;
};

flycam_socket_t *initSocket(const char *video_address,
                              const char *meta_address,
                              int         timeout_ms) {
  flycam_socket_t *sock = (flycam_socket_t *)calloc(1, sizeof(*sock));
  if (!sock)
    return NULL;

  sock->timeout_ms = timeout_ms;
  sock->zmq_ctx    = zmq_ctx_new();

  /* Video subscriber */
  sock->zmq_video = zmq_socket(sock->zmq_ctx, ZMQ_SUB);
  int conflate = 1, hwm = 1;
  zmq_setsockopt(sock->zmq_video, ZMQ_CONFLATE, &conflate, sizeof(conflate));
  zmq_setsockopt(sock->zmq_video, ZMQ_RCVHWM,   &hwm,      sizeof(hwm));

  if (zmq_connect(sock->zmq_video, video_address) != 0) {
    fprintf(stderr, "initSocket: failed to connect video to %s\n", video_address);
    freeSocket(sock);
    return NULL;
  }
  zmq_setsockopt(sock->zmq_video, ZMQ_SUBSCRIBE, "", 0);
  printf("initSocket: video connected to %s\n", video_address);

  /* Metadata subscriber (optional) */
  if (meta_address) {
    sock->zmq_meta = zmq_socket(sock->zmq_ctx, ZMQ_SUB);
    zmq_setsockopt(sock->zmq_meta, ZMQ_CONFLATE, &conflate, sizeof(conflate));
    zmq_setsockopt(sock->zmq_meta, ZMQ_RCVHWM,   &hwm,      sizeof(hwm));

    if (zmq_connect(sock->zmq_meta, meta_address) != 0) {
      fprintf(stderr, "initSocket: failed to connect meta to %s (continuing without)\n",
              meta_address);
      zmq_close(sock->zmq_meta);
      sock->zmq_meta = NULL;
    } else {
      zmq_setsockopt(sock->zmq_meta, ZMQ_SUBSCRIBE, "", 0);
      printf("initSocket: meta  connected to %s\n", meta_address);
    }
  }

  return sock;
}

/* Drain any queued metadata messages (non-blocking) and update cache. */
static void poll_meta(flycam_socket_t *sock) {
  if (!sock->zmq_meta)
    return;

  zmq_msg_t msg;
  zmq_msg_init(&msg);

  while (zmq_msg_recv(&msg, sock->zmq_meta, ZMQ_DONTWAIT) != -1) {
    const uint8_t *buf = (const uint8_t *)zmq_msg_data(&msg);
    size_t         len = zmq_msg_size(&msg);

    if (len < META_HEADER_SIZE) {
      zmq_msg_close(&msg);
      zmq_msg_init(&msg);
      continue;
    }

    uint32_t count = read_u32le(buf + 4);
    if (count > FLYCAM_MAX_METADATA)
      count = FLYCAM_MAX_METADATA;

    if (len < META_HEADER_SIZE + (size_t)count * META_ENTRY_SIZE) {
      zmq_msg_close(&msg);
      zmq_msg_init(&msg);
      continue;
    }

    sock->cached_meta_count = 0;
    const uint8_t *entry = buf + META_HEADER_SIZE;
    for (uint32_t i = 0; i < count; i++, entry += META_ENTRY_SIZE) {
      memcpy(sock->cached_meta[i].name, entry, FLYCAM_META_NAME_LEN);
      sock->cached_meta[i].name[FLYCAM_META_NAME_LEN] = '\0';
      memcpy(&sock->cached_meta[i].value, entry + FLYCAM_META_NAME_LEN,
             sizeof(float));
      sock->cached_meta_count++;
    }

    zmq_msg_close(&msg);
    zmq_msg_init(&msg);
  }
  zmq_msg_close(&msg);
}

frame_t *readSocket(flycam_socket_t *sock) {
  if (!sock)
    return NULL;

  if (sock->msg_open) {
    zmq_msg_close(&sock->msg);
    sock->msg_open = 0;
  }

  /* Drain any queued metadata first (non-blocking). */
  poll_meta(sock);

  /* Wait for the next video frame. */
  zmq_pollitem_t items[1] = {{sock->zmq_video, 0, ZMQ_POLLIN, 0}};
  int rc = zmq_poll(items, 1, sock->timeout_ms);
  if (rc <= 0)
    return NULL;

  zmq_msg_init(&sock->msg);
  if (zmq_msg_recv(&sock->msg, sock->zmq_video, 0) == -1) {
    zmq_msg_close(&sock->msg);
    return NULL;
  }
  sock->msg_open = 1;

  const uint8_t *buf       = (const uint8_t *)zmq_msg_data(&sock->msg);
  size_t         wire_size = zmq_msg_size(&sock->msg);

  if (wire_size < VIDEO_HEADER_SIZE) {
    fprintf(stderr, "readSocket: packet too small (%zu bytes)\n", wire_size);
    return NULL;
  }

  uint32_t ts        = read_u32le(buf + 0);
  uint32_t width     = read_u32le(buf + 4);
  uint32_t height    = read_u32le(buf + 8);
  uint32_t jpeg_size = read_u32le(buf + 12);

  if (width == 0 || height == 0) {
    fprintf(stderr, "readSocket: zero dimension (%ux%u)\n", width, height);
    return NULL;
  }

  size_t pixel_count = (size_t)width * height;
  if (pixel_count / width != height) { /* overflow check */
    fprintf(stderr, "readSocket: dimension overflow\n");
    return NULL;
  }

  if (wire_size < VIDEO_HEADER_SIZE + (size_t)jpeg_size) {
    fprintf(stderr, "readSocket: truncated JPEG (need %u, got %zu)\n",
            VIDEO_HEADER_SIZE + jpeg_size, wire_size);
    return NULL;
  }

  const uint8_t *jpeg_data = buf + VIDEO_HEADER_SIZE;

  frame_t *frame = (frame_t *)malloc(sizeof(*frame));
  if (!frame)
    return NULL;

  frame->pixels = (uint32_t *)malloc(pixel_count * sizeof(uint32_t));
  if (!frame->pixels) {
    free(frame);
    return NULL;
  }

  if (decode_jpeg_to_pixels(jpeg_data, jpeg_size, width, height,
                              frame->pixels) != 0) {
    fprintf(stderr, "readSocket: JPEG decode failed\n");
    free(frame->pixels);
    free(frame);
    return NULL;
  }

  frame->timestamp      = ts;
  frame->width          = width;
  frame->height         = height;
  frame->wire_size      = (uint32_t)wire_size;
  frame->metadata_count = sock->cached_meta_count;
  memcpy(frame->metadata, sock->cached_meta,
         (size_t)sock->cached_meta_count * sizeof(flycam_meta_entry_t));

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
  if (sock->zmq_video)
    zmq_close(sock->zmq_video);
  if (sock->zmq_meta)
    zmq_close(sock->zmq_meta);
  if (sock->zmq_ctx)
    zmq_ctx_destroy(sock->zmq_ctx);
  free(sock);
}
