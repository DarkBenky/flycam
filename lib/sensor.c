#include "sensor.h"

#include <stdio.h>
#include <string.h>

/* Map a metadata entry name to the matching float field inside flycam_sensor_t.
 * Returns NULL when the name is not a sensor key. */
static float *_field(flycam_sensor_t *s, const char *name) {
  if (!strcmp(name, "pos_lat"))
    return &s->pos_lat;
  if (!strcmp(name, "pos_lon"))
    return &s->pos_lon;
  if (!strcmp(name, "pos_alt"))
    return &s->pos_alt;
  if (!strcmp(name, "vel_x"))
    return &s->vel_x;
  if (!strcmp(name, "vel_y"))
    return &s->vel_y;
  if (!strcmp(name, "vel_z"))
    return &s->vel_z;
  if (!strcmp(name, "acc_x"))
    return &s->acc_x;
  if (!strcmp(name, "acc_y"))
    return &s->acc_y;
  if (!strcmp(name, "acc_z"))
    return &s->acc_z;
  if (!strcmp(name, "gyr_x"))
    return &s->gyr_x;
  if (!strcmp(name, "gyr_y"))
    return &s->gyr_y;
  if (!strcmp(name, "gyr_z"))
    return &s->gyr_z;
  if (!strcmp(name, "gps_fix"))
    return &s->gps_fix;
  return NULL;
}

void sensor_from_frame(const frame_t *frame, flycam_sensor_t *out) {
  memset(out, 0, sizeof(*out));
  for (int i = 0; i < frame->metadata_count; i++) {
    const flycam_meta_entry_t *e = &frame->metadata[i];
    float *dst = _field(out, e->name);
    if (dst) {
      *dst = e->value;
      out->valid = 1;
    }
  }
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
