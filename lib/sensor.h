#pragma once

#include "packet.h"

/*
 * Sensor fusion fields embedded in the metadata packet.
 * All position/velocity/acceleration values are the running averages
 * computed by datafussion.py.
 *
 * Metadata key mapping (8-char ASCII):
 *   pos_lat  pos_lon  pos_alt   -- fused lat/lon/alt
 *   vel_x    vel_y    vel_z     -- fused velocity (knots / deg / 0)
 *   acc_x    acc_y    acc_z     -- fused acceleration (m/s^2)
 *   gyr_x    gyr_y    gyr_z     -- fused gyro (rad/s)
 *   gps_fix                     -- GPS fix quality (0 = no fix)
 */
typedef struct {
    float pos_lat, pos_lon, pos_alt;
    float vel_x, vel_y, vel_z;
    float acc_x, acc_y, acc_z;
    float gyr_x, gyr_y, gyr_z;
    float gps_fix;
    int   valid;  /* 1 once any sensor entry has been received */
} flycam_sensor_t;

/* Populate *out by scanning frame->metadata for sensor keys.
 * Fields not present in the frame are left at 0. */
void sensor_from_frame(const frame_t *frame, flycam_sensor_t *out);

/* Print all sensor fields to stdout. No-op when out->valid == 0. */
void sensor_print(const flycam_sensor_t *sensor);
