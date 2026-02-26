#pragma once

#include "packet.h"

typedef struct {
  float pos_x, pos_y, pos_z;   /* metres (dead-reckoned) or lat/lon/alt (GPS) */
  float vel_x, vel_y, vel_z;   /* m/s world frame (dead-reckoned) or knots/deg (GPS) */
  float acc_x, acc_y, acc_z;   /* raw body-frame m/s^2 */
  float gyr_x, gyr_y, gyr_z;   /* raw body-frame rad/s */
  float pitch, roll, yaw;       /* orientation radians (complementary filter) */
  float gps_fix;                /* 0=no fix  >0=fix quality */
  int   valid;
} flycam_sensor_t;

void sensor_from_frame(const frame_t *frame, flycam_sensor_t *out);
void sensor_print(const flycam_sensor_t *sensor);
