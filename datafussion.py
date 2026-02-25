from gps import read_gps_records, GNSSRecord
from gyro import read_gyro_records, GyroRecord
from dataclasses import dataclass, field


@dataclass
class FusedRecord:
    raw_xyz_pos_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_xyz_vel_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_xyz_accel_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_xyz_gyro_sum: tuple[float, float, float] = (0.0, 0.0, 0.0)
    count: int = 0
    fused_xyz_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fused_xyz_vel: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fused_xyz_accel: tuple[float, float, float] = (0.0, 0.0, 0.0)

fused = FusedRecord()

def read_fused_records() -> list[FusedRecord]:
    gps_records = read_gps_records(count=1)
    gyro_records = read_gyro_records()

    if gps_records and gyro_records:
    

    return [fused]