#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include <MiniFB.h>

#include "lib/packet.h"

#define SERVER_ADDR_DEFAULT "tcp://91.98.145.193:5556"
#define POLL_TIMEOUT 16

static double now_sec(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(void) {
  const char *server_addr = getenv("FLYCAM_SERVER");
  if (!server_addr)
    server_addr = SERVER_ADDR_DEFAULT;
  flycam_socket_t *sock = initSocket(server_addr, POLL_TIMEOUT);
  if (!sock)
    return 1;

  struct mfb_window *window = NULL;
  uint32_t win_w = 0;
  uint32_t win_h = 0;

  long log_bytes = 0;
  int log_frames = 0;
  double log_time = now_sec();

  while (1) {
    frame_t *frame = readSocket(sock);

    if (frame) {
      if (!window || frame->width != win_w || frame->height != win_h) {
        if (window)
          mfb_close(window);
        win_w = frame->width;
        win_h = frame->height;
        window = mfb_open_ex("flycam", win_w, win_h, WF_RESIZABLE);
        if (!window) {
          fprintf(stderr, "Failed to create window (%ux%u)\n", win_w, win_h);
          freeFrame(frame);
          break;
        }
        printf("timestamp    : %u\n", frame->timestamp);
        printf("resolution   : %ux%u  channels: %u\n", frame->width,
               frame->height, frame->channels);
        printf("channel bits : R=%u G=%u B=%u\n", frame->channel_bits[0],
               frame->channel_bits[1], frame->channel_bits[2]);
        printf("compression  : %s\n", frame->compression ? "lz4" : "none");
        printf("image size   : %u bytes\n", frame->image_size);
        for (int i = 0; i < FLYCAM_MAX_METADATA; i++) {
          if (frame->metadata[i].name[0] != '\0')
            printf("meta %-8s : %g\n", frame->metadata[i].name,
                   frame->metadata[i].value);
        }
      }

      log_bytes += frame->wire_size;
      log_frames += 1;

      mfb_update_ex(window, frame->pixels, win_w, win_h);
      freeFrame(frame);

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
    } else {
      if (window) {
        mfb_update_state state = mfb_update_ex(window, NULL, win_w, win_h);
        if (state == STATE_EXIT || state == STATE_INVALID_WINDOW)
          break;
      }
    }
  }

  if (window)
    mfb_close(window);
  freeSocket(sock);
  return 0;
}
