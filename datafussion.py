import math
import threading
from dataclasses import dataclass

from gps import GNSSRecord
from gyro import GyroRecord

ALPHA           = 0.98    # complementary filter: trust gyro 98 %, accel tilt 2 %
G               = 9.80665 # standard gravity m/s^2
ZUPT_ACC_THRESH = 0.3     # |acc| deviation from G below which we consider stationary
ZUPT_GYR_THRESH = 0.05    # gyro magnitude below which we consider stationary
GPS_VEL_INTERVAL = 60     # every N GPS readings update velocity from GPS


@dataclass
class FusedState:
    # World-space position (metres from origin; z = altitude in metres)
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    # World-space velocity (m/s, each axis; not normalised)
    vel_x: float = 0.0
    vel_y: float = 0.0
    vel_z: float = 0.0
    # Orientation in radians
    rot_x: float = 0.0  # pitch
    rot_y: float = 0.0  # roll
    rot_z: float = 0.0  # yaw
    gps_fix: int = 0
    valid: bool = False


class _State:
    pos        = [0.0, 0.0, 0.0]
    vel        = [0.0, 0.0, 0.0]
    pitch      = 0.0
    roll       = 0.0
    yaw        = 0.0
    gps_fix    = 0
    gps_count  = 0
    t_last_imu = 0.0


_s    = _State()
_lock = threading.Lock()


def update_imu(rec: GyroRecord) -> None:
    ax, ay, az = rec.acceleration
    gx, gy, gz = rec.gyro
    now = rec.timestamp

    with _lock:
        dt = now - _s.t_last_imu if _s.t_last_imu > 0.0 else 0.0
        _s.t_last_imu = now

        if not (0.0 < dt < 0.5):
            return

        # --- Orientation (complementary filter) ---
        acc_mag = math.sqrt(ax * ax + ay * ay + az * az)
        if 0.5 * G < acc_mag < 2.0 * G:
            acc_pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))
            acc_roll  = math.atan2(ay, az)
            _s.pitch = ALPHA * (_s.pitch + gy * dt) + (1.0 - ALPHA) * acc_pitch
            _s.roll  = ALPHA * (_s.roll  + gx * dt) + (1.0 - ALPHA) * acc_roll
        else:
            _s.pitch += gy * dt
            _s.roll  += gx * dt
        _s.yaw += gz * dt

        # --- Remove gravity from body-frame acceleration ---
        sp = math.sin(_s.pitch); cp = math.cos(_s.pitch)
        sr = math.sin(_s.roll);  cr = math.cos(_s.roll)
        cy = math.cos(_s.yaw);   sy = math.sin(_s.yaw)
        lax = ax - (-G * sp)
        lay = ay - ( G * cp * sr)
        laz = az - ( G * cp * cr)

        # --- Rotate linear acceleration to world frame: R = Rz(yaw)*Ry(pitch)*Rx(roll) ---
        wx = cy*cp*lax + (cy*sp*sr - sy*cr)*lay + (cy*sp*cr + sy*sr)*laz
        wy = sy*cp*lax + (sy*sp*sr + cy*cr)*lay + (sy*sp*cr - cy*sr)*laz
        wz =   -sp*lax +       cp*sr*lay         +       cp*cr*laz

        # --- ZUPT: zero velocity when stationary to stop bias drift ---
        gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)
        if abs(acc_mag - G) < ZUPT_ACC_THRESH and gyro_mag < ZUPT_GYR_THRESH:
            _s.vel[:] = [0.0, 0.0, 0.0]
        else:
            _s.vel[0] += wx * dt
            _s.vel[1] += wy * dt
            _s.vel[2] += wz * dt

        _s.pos[0] += _s.vel[0] * dt
        _s.pos[1] += _s.vel[1] * dt
        _s.pos[2] += _s.vel[2] * dt


def update_gps(rec: GNSSRecord) -> None:
    if not rec.fix_quality or rec.fix_quality <= 0:
        return

    with _lock:
        _s.gps_fix = rec.fix_quality
        _s.gps_count += 1

        # Periodically anchor velocity from GPS to limit dead-reckoning drift.
        if _s.gps_count % GPS_VEL_INTERVAL == 1:
            speed_ms   = (rec.speed_knots or 0.0) * 0.514444
            course_rad = math.radians(rec.course_deg or 0.0)
            # Course is clockwise from North; map to (East, North, Up) world frame.
            _s.vel[:] = [
                speed_ms * math.sin(course_rad),
                speed_ms * math.cos(course_rad),
                0.0,
            ]

        # On the very first fix set altitude so z = 0 at the launch site.
        if _s.gps_count == 1:
            _s.pos[2] = rec.altitude_m or 0.0


def get_fused() -> FusedState:
    with _lock:
        return FusedState(
            pos_x=_s.pos[0], pos_y=_s.pos[1], pos_z=_s.pos[2],
            vel_x=_s.vel[0], vel_y=_s.vel[1], vel_z=_s.vel[2],
            rot_x=_s.pitch,  rot_y=_s.roll,   rot_z=_s.yaw,
            gps_fix=_s.gps_fix,
            valid=True,
        )
