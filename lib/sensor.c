#include "sensor.h"

#include <math.h>
#include <stdio.h>

void sensor_from_frame(const frame_t *frame, flycam_sensor_t *out) {
  out->pos_x = frame->pos_x;
  out->pos_y = frame->pos_y;
  out->pos_z = frame->pos_z;
  out->vel_x = frame->vel_x;
  out->vel_y = frame->vel_y;
  out->vel_z = frame->vel_z;
  out->acc_x = frame->acc_x;
  out->acc_y = frame->acc_y;
  out->acc_z = frame->acc_z;
  out->gyr_x = frame->gyr_x;
  out->gyr_y = frame->gyr_y;
  out->gyr_z = frame->gyr_z;
  out->pitch = frame->pitch;
  out->roll = frame->roll;
  out->yaw = frame->yaw;
  out->gps_fix = frame->gps_fix;
  out->valid = 1;
}

#define RAD2DEG (180.0f / 3.14159265f)

void sensor_print(const flycam_sensor_t *s) {
  if (!s->valid)
    return;
  if (s->gps_fix > 0.0f) {
    printf(
        "[sensor] pos  : lat=%11.6f  lon=%11.6f  alt=%7.2f m  (GPS fix=%d)\n",
        s->pos_x, s->pos_y, s->pos_z, (int)s->gps_fix);
    printf("[sensor] vel  : %.2f kn  %.1f deg\n", s->vel_x, s->vel_y);
  } else {
    printf(
        "[sensor] pos  : x=%8.3f m  y=%8.3f m  z=%8.3f m  (dead-reckoning)\n",
        s->pos_x, s->pos_y, s->pos_z);
    printf("[sensor] vel  : x=%7.3f  y=%7.3f  z=%7.3f m/s\n", s->vel_x,
           s->vel_y, s->vel_z);
  }
  printf("[sensor] ori  : pitch=%6.1f  roll=%6.1f  yaw=%6.1f deg\n",
         s->pitch * RAD2DEG, s->roll * RAD2DEG, s->yaw * RAD2DEG);
  printf("[sensor] acc  : x=%7.3f  y=%7.3f  z=%7.3f m/s^2\n", s->acc_x,
         s->acc_y, s->acc_z);
  printf("[sensor] gyr  : x=%7.3f  y=%7.3f  z=%7.3f rad/s\n", s->gyr_x,
         s->gyr_y, s->gyr_z);
}
