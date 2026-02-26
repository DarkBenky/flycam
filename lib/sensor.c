#include "sensor.h"

#include <stdio.h>

void sensor_from_frame(const frame_t *frame, flycam_sensor_t *out) {
  out->pos_lat = frame->pos_lat;
  out->pos_lon = frame->pos_lon;
  out->pos_alt = frame->pos_alt;
  out->vel_x = frame->vel_x;
  out->vel_y = frame->vel_y;
  out->vel_z = frame->vel_z;
  out->acc_x = frame->acc_x;
  out->acc_y = frame->acc_y;
  out->acc_z = frame->acc_z;
  out->gyr_x = frame->gyr_x;
  out->gyr_y = frame->gyr_y;
  out->gyr_z = frame->gyr_z;
  out->gps_fix = frame->gps_fix;
  out->valid = 1;
}

void sensor_print(const flycam_sensor_t *s) {
  if (!s->valid)
    return;
  printf("[sensor] pos : lat=%11.6f  lon=%11.6f  alt=%7.2f m\n", s->pos_lat,
         s->pos_lon, s->pos_alt);
  printf("[sensor] vel : x=%8.3f kn  y=%8.3f deg  z=%8.3f\n", s->vel_x,
         s->vel_y, s->vel_z);
  printf("[sensor] acc : x=%7.3f  y=%7.3f  z=%7.3f m/s^2\n", s->acc_x, s->acc_y,
         s->acc_z);
  printf("[sensor] gyr : x=%7.3f  y=%7.3f  z=%7.3f rad/s  fix=%d\n", s->gyr_x,
         s->gyr_y, s->gyr_z, (int)s->gps_fix);
}
