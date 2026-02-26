#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include <MiniFB.h>

#include "lib/flycam.h"

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

  flycam_t *cam = flycam_create(server_addr, POLL_TIMEOUT);
  if (!cam)
    return 1;

  struct mfb_window *window = NULL;
  uint32_t win_w = 0;
  uint32_t win_h = 0;

  long log_bytes = 0;
  int log_frames = 0;
  double log_time = now_sec();

  while (1) {
    flycam_frame_t *frame = flycam_poll(cam);

    if (frame) {
      if (!window || frame->width != win_w || frame->height != win_h) {
        if (window)
          mfb_close(window);
        win_w = frame->width;
        win_h = frame->height;
        window = mfb_open_ex("flycam", win_w, win_h, WF_RESIZABLE);
        if (!window) {
          fprintf(stderr, "Failed to create window (%ux%u)\n", win_w, win_h);
          flycam_frame_free(frame);
          break;
        }
        printf("timestamp  : %u\n", frame->timestamp);
        printf("resolution : %ux%u\n", frame->width, frame->height);
      }

      log_bytes += frame->wire_size;
      log_frames += 1;

      mfb_update_ex(window, frame->pixels, win_w, win_h);

      double t = now_sec();
      double elapsed = t - log_time;
      if (elapsed >= 1.0) {
        printf("[c]   %.1f KB/s  %.1f fps\n",
               (double)log_bytes / elapsed / 1024.0,
               (double)log_frames / elapsed);
        flycam_frame_print(frame);
        log_bytes = 0;
        log_frames = 0;
        log_time = t;
      }

      flycam_frame_free(frame);
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
  flycam_destroy(cam);
  return 0;
}
