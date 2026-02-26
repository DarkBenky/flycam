#include "flycam.h"
#include "packet.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#define RAD2DEG (180.0f / (float)M_PI)

struct flycam {
  flycam_socket_t *sock;
};

flycam_t *flycam_create(const char *addr, int timeout_ms) {
  flycam_t *cam = (flycam_t *)calloc(1, sizeof(*cam));
  if (!cam)
    return NULL;
  cam->sock = initSocket(addr, timeout_ms);
  if (!cam->sock) {
    free(cam);
    return NULL;
  }
  return cam;
}

flycam_frame_t *flycam_poll(flycam_t *cam) {
  if (!cam)
    return NULL;

  frame_t *f = readSocket(cam->sock);
  if (!f)
    return NULL;

  flycam_frame_t *out = (flycam_frame_t *)malloc(sizeof(*out));
  if (!out) {
    freeFrame(f);
    return NULL;
  }

  out->timestamp = f->timestamp;
  out->width     = f->width;
  out->height    = f->height;
  out->wire_size = f->wire_size;
  out->pos_x = f->pos_x; out->pos_y = f->pos_y; out->pos_z = f->pos_z;
  out->vel_x = f->vel_x; out->vel_y = f->vel_y; out->vel_z = f->vel_z;
  out->acc_x = f->acc_x; out->acc_y = f->acc_y; out->acc_z = f->acc_z;
  out->gyr_x = f->gyr_x; out->gyr_y = f->gyr_y; out->gyr_z = f->gyr_z;
  out->rot_x = f->pitch;
  out->rot_y = f->roll;
  out->rot_z = f->yaw;
  out->gps_fix = f->gps_fix;
  out->pixels  = f->pixels;
  f->pixels    = NULL; /* transfer ownership */
  freeFrame(f);
  return out;
}

void flycam_frame_free(flycam_frame_t *frame) {
  if (!frame)
    return;
  free(frame->pixels);
  free(frame);
}

void flycam_destroy(flycam_t *cam) {
  if (!cam)
    return;
  freeSocket(cam->sock);
  free(cam);
}

void flycam_frame_print(const flycam_frame_t *f) {
  if (!f)
    return;
  if (f->gps_fix > 0.0f) {
    printf("[flycam] pos  : lat=%11.6f  lon=%11.6f  alt=%7.2f m  (GPS fix=%d)\n",
           f->pos_x, f->pos_y, f->pos_z, (int)f->gps_fix);
    printf("[flycam] vel  : %.2f kn  %.1f deg\n", f->vel_x, f->vel_y);
  } else {
    printf("[flycam] pos  : x=%8.3f m  y=%8.3f m  z=%8.3f m  (dead-reckoning)\n",
           f->pos_x, f->pos_y, f->pos_z);
    printf("[flycam] vel  : x=%7.3f  y=%7.3f  z=%7.3f m/s\n",
           f->vel_x, f->vel_y, f->vel_z);
  }
  printf("[flycam] rot  : pitch=%6.1f  roll=%6.1f  yaw=%6.1f deg\n",
         f->rot_x * RAD2DEG, f->rot_y * RAD2DEG, f->rot_z * RAD2DEG);
  printf("[flycam] acc  : x=%7.3f  y=%7.3f  z=%7.3f m/s^2\n",
         f->acc_x, f->acc_y, f->acc_z);
  printf("[flycam] gyr  : x=%7.3f  y=%7.3f  z=%7.3f rad/s\n",
         f->gyr_x, f->gyr_y, f->gyr_z);
}
