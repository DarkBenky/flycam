#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include <MiniFB.h>

#include "lib/packet.h"

#define SERVER_ADDR "tcp://localhost:5556"
#define POLL_TIMEOUT 16

static double now_sec(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(void) {
  packet_receiver_t *rx = packet_receiver_create(SERVER_ADDR, POLL_TIMEOUT);
  if (!rx)
    return 1;

  struct mfb_window *window = NULL;
  uint32_t *fb = NULL;
  uint32_t fb_w = 0;
  uint32_t fb_h = 0;
  packet_t pkt;

  long log_bytes = 0;
  int log_frames = 0;
  double log_time = now_sec();

  while (1) {
    int rc = packet_recv(rx, &pkt);

    if (rc == 0) {
      if (!window || pkt.width != fb_w || pkt.height != fb_h) {
        if (window)
          mfb_close(window);
        free(fb);
        fb_w = pkt.width;
        fb_h = pkt.height;
        fb = malloc(fb_w * fb_h * sizeof(uint32_t));
        window = mfb_open_ex("flycam", fb_w, fb_h, WF_RESIZABLE);
        if (!window || !fb) {
          fprintf(stderr, "Failed to create window (%ux%u)\n", fb_w, fb_h);
          break;
        }
        packet_print_header(&pkt);
      }

      packet_unpack_argb(&pkt, fb);

      log_bytes += pkt.image_size;
      log_frames += 1;

      double t = now_sec();
      double elapsed = t - log_time;
      if (elapsed >= 1.0) {
        printf("[c]   %.1f KB/s  %.1f fps\n",
               (double)log_bytes / elapsed / 1024.0,
               (double)log_frames / elapsed);
        log_bytes = 0;
        log_frames = 0;
        log_time = t;
      }
    }

    if (window) {
      mfb_update_state state = mfb_update_ex(window, fb, fb_w, fb_h);
      if (state == STATE_EXIT || state == STATE_INVALID_WINDOW)
        break;
    }
  }

  if (window)
    mfb_close(window);
  free(fb);
  packet_receiver_destroy(rx);
  return 0;
}
