from copy import copy
from gps import GNSSRecord
from gyro import GyroRecord
from dataclasses import dataclass
import threading


@dataclass
class FusedRecord:
    raw_xyz_pos_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_xyz_vel_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_xyz_accel_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_xyz_gyro_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    count: int = 0
    imu_count: int = 0
    last_gps_fix: int = 0
    fused_xyz_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fused_xyz_vel: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fused_xyz_accel: tuple[float, float, float] = (0.0, 0.0, 0.0)

_fused = FusedRecord()
_lock = threading.Lock()

def update_imu(gyro: GyroRecord) -> None:
    with _lock:
        _fused.raw_xyz_accel_sum = (
            _fused.raw_xyz_accel_sum[0] + gyro.acceleration[0],
            _fused.raw_xyz_accel_sum[1] + gyro.acceleration[1],
            _fused.raw_xyz_accel_sum[2] + gyro.acceleration[2],
        )
        _fused.raw_xyz_gyro_sum = (
            _fused.raw_xyz_gyro_sum[0] + gyro.gyro[0],
            _fused.raw_xyz_gyro_sum[1] + gyro.gyro[1],
            _fused.raw_xyz_gyro_sum[2] + gyro.gyro[2],
        )
        _fused.imu_count += 1


def update_gps(gps: GNSSRecord) -> None:
    with _lock:
        _fused.last_gps_fix = gps.fix_quality or 0

        if gps.fix_quality and gps.fix_quality > 0:
            _fused.raw_xyz_pos_sum = (
                _fused.raw_xyz_pos_sum[0] + (gps.latitude or 0.0),
                _fused.raw_xyz_pos_sum[1] + (gps.longitude or 0.0),
                _fused.raw_xyz_pos_sum[2] + (gps.altitude_m or 0.0),
            )
            _fused.raw_xyz_vel_sum = (
                _fused.raw_xyz_vel_sum[0] + (gps.speed_knots or 0.0),
                _fused.raw_xyz_vel_sum[1] + (gps.course_deg or 0.0),
                _fused.raw_xyz_vel_sum[2] + 0.0,
            )
            _fused.count += 1
        elif _fused.count > 0:
            # GPS lost: dead reckon using last average velocity + IMU acceleration
            n = _fused.count
            ni = max(_fused.imu_count, 1)
            last_vel = (
                _fused.raw_xyz_vel_sum[0] / n,
                _fused.raw_xyz_vel_sum[1] / n,
                _fused.raw_xyz_vel_sum[2] / n,
            )
            avg_accel = (
                _fused.raw_xyz_accel_sum[0] / ni,
                _fused.raw_xyz_accel_sum[1] / ni,
                _fused.raw_xyz_accel_sum[2] / ni,
            )
            _fused.raw_xyz_vel_sum = (
                _fused.raw_xyz_vel_sum[0] + avg_accel[0],
                _fused.raw_xyz_vel_sum[1] + avg_accel[1],
                _fused.raw_xyz_vel_sum[2] + avg_accel[2],
            )
            _fused.raw_xyz_pos_sum = (
                _fused.raw_xyz_pos_sum[0] + last_vel[0],
                _fused.raw_xyz_pos_sum[1] + last_vel[1],
                _fused.raw_xyz_pos_sum[2] + last_vel[2],
            )
            _fused.count += 1


def get_fused() -> FusedRecord:
    with _lock:
        n = max(_fused.count, 1)
        ni = max(_fused.imu_count, 1)
        _fused.fused_xyz_pos = (
            _fused.raw_xyz_pos_sum[0] / n,
            _fused.raw_xyz_pos_sum[1] / n,
            _fused.raw_xyz_pos_sum[2] / n,
        )
        _fused.fused_xyz_vel = (
            _fused.raw_xyz_vel_sum[0] / n,
            _fused.raw_xyz_vel_sum[1] / n,
            _fused.raw_xyz_vel_sum[2] / n,
        )
        _fused.fused_xyz_accel = (
            _fused.raw_xyz_accel_sum[0] / ni,
            _fused.raw_xyz_accel_sum[1] / ni,
            _fused.raw_xyz_accel_sum[2] / ni,
        )
        return copy(_fused)
