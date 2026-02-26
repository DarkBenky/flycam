DEBUG = False
DEBUG_VIDEO = "fpv.mp4"

import math
import time
import struct
import threading
import queue
import cv2

from gyro import read_gyro_records
from gps import GPSReader

if not DEBUG:
    from picamera2 import Picamera2

from env import GO_SERVER
import zmq

JPEG_QUALITY = 75
H = 480
W = 720
GPS_ANCHOR_INTERVAL = 60  # frames between GPS anchor attempts

# Zero-velocity update (ZUPT): if the IMU looks stationary, zero velocity
# to prevent bias double-integration drift.
ZUPT_ACC_THRESH = 0.3   # m/s² — max deviation of |acc| from G to be considered still
ZUPT_GYR_THRESH = 0.05  # rad/s — max gyro magnitude to be considered still

# Packet layout (80-byte header + JPEG):
#   [0]  timestamp  u32
#   [4]  width      u32
#   [8]  height     u32
#   [12] jpeg_size  u32
#   [16] pos_x      f32  (lat/lon/alt from GPS, or dead-reckoned metres)
#   [20] pos_y      f32
#   [24] pos_z      f32
#   [28] vel_x      f32  (m/s world frame, or speed_knots from GPS)
#   [32] vel_y      f32  (m/s, or course_deg from GPS)
#   [36] vel_z      f32
#   [40] acc_x      f32
#   [44] acc_y      f32
#   [48] acc_z      f32
#   [52] gyr_x      f32
#   [56] gyr_y      f32
#   [60] gyr_z      f32
#   [64] pitch      f32  (radians, complementary filter)
#   [68] roll       f32
#   [72] yaw        f32  (radians, gyro-integrated — drifts without magnetometer)
#   [76] gps_fix    f32  (0=no fix)
#   [80] jpeg bytes
_HDR_FMT  = '<IIII16f'
_HDR_SIZE = struct.calcsize(_HDR_FMT)  # 80
_JPEG_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

print(f"JPEG quality: {JPEG_QUALITY}  resolution: {W}x{H}  header: {_HDR_SIZE}B")


def _pack(jpeg_bytes: bytes, pos, vel, acc, gyr, pitch: float, roll: float, yaw: float, gps_fix: float) -> bytes:
    ts = int(time.time()) & 0xFFFFFFFF
    return struct.pack(
        _HDR_FMT, ts, W, H, len(jpeg_bytes),
        pos[0], pos[1], pos[2],
        vel[0], vel[1], vel[2],
        acc[0], acc[1], acc[2],
        gyr[0], gyr[1], gyr[2],
        pitch, roll, yaw,
        gps_fix,
    ) + jpeg_bytes


# Shared sensor state — class fields are mutable so inner functions can write
class _S:
    acc          = [0.0, 0.0, 0.0]
    gyr          = [0.0, 0.0, 0.0]
    vel          = [0.0, 0.0, 0.0]   # m/s world frame
    pos          = [0.0, 0.0, 0.0]   # metres from origin (or lat/lon/alt after GPS anchor)
    pitch        = 0.0               # radians, complementary filter
    roll         = 0.0
    yaw          = 0.0               # radians, gyro-integrated
    gps_fix      = 0.0               # 0 = never had fix
    gps_pending  = None              # latest GPS fix dict, set by GPS thread


_lock = threading.Lock()


if __name__ == "__main__":
    context = zmq.Context()
    sock = context.socket(zmq.PUSH)
    sock.setsockopt(zmq.SNDHWM, 2)
    sock.setsockopt(zmq.SNDTIMEO, 0)
    sock.setsockopt(zmq.LINGER, 0)
    sock.connect(GO_SERVER)

    if not DEBUG:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            main={"size": (W, H), "format": "BGR888"},
            controls={"FrameDurationLimits": (16666, 16666)},
        )
        picam2.configure(config)
        picam2.start()
    else:
        cap = cv2.VideoCapture(DEBUG_VIDEO)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open debug video: {DEBUG_VIDEO}")
        print(f"Debug mode: reading from '{DEBUG_VIDEO}'")

    _frame_q: queue.Queue = queue.Queue(maxsize=1)
    _stop_evt = threading.Event()

    def _capture_loop():
        if not DEBUG:
            while not _stop_evt.is_set():
                frame = picam2.capture_array()
                if _frame_q.full():
                    try:
                        _frame_q.get_nowait()
                    except queue.Empty:
                        pass
                _frame_q.put(frame)
        else:
            while not _stop_evt.is_set():
                ret, raw = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, raw = cap.read()
                raw = cv2.resize(raw, (W, H))
                if _frame_q.full():
                    try:
                        _frame_q.get_nowait()
                    except queue.Empty:
                        pass
                _frame_q.put(raw)

    def _imu_loop():
        # Complementary filter coefficient: 0.98 = trust gyro 98 %, acc 2 %.
        # Acc corrects long-term tilt drift; gyro handles fast motion.
        ALPHA = 0.98
        G = 9.80665
        t_last = 0.0
        print("[imu] thread started", flush=True)
        while not _stop_evt.is_set():
            try:
                rec = read_gyro_records()[0]
                ax, ay, az = rec.acceleration
                gx, gy, gz = rec.gyro
                now = time.time()
                dt  = now - t_last if t_last > 0.0 else 0.0
                t_last = now

                with _lock:
                    _S.acc[:] = [ax, ay, az]
                    _S.gyr[:] = [gx, gy, gz]

                    if 0.0 < dt < 0.1:
                        # --- Orientation (complementary filter) ---
                        mag = math.sqrt(ax*ax + ay*ay + az*az)
                        if 0.5 * G < mag < 2.0 * G:
                            acc_pitch = math.atan2(-ax, math.sqrt(ay*ay + az*az))
                            acc_roll  = math.atan2(ay, az)
                            _S.pitch = ALPHA * (_S.pitch + gy * dt) + (1.0 - ALPHA) * acc_pitch
                            _S.roll  = ALPHA * (_S.roll  + gx * dt) + (1.0 - ALPHA) * acc_roll
                        else:
                            _S.pitch += gy * dt
                            _S.roll  += gx * dt
                        _S.yaw += gz * dt

                        # --- Dead-reckoning (always runs; GPS anchor resets pos/vel) ---
                        cp = math.cos(_S.pitch); sp = math.sin(_S.pitch)
                        cr = math.cos(_S.roll);  sr = math.sin(_S.roll)
                        cy = math.cos(_S.yaw);   sy = math.sin(_S.yaw)

                        # Remove gravity from body-frame acceleration.
                        lax = ax - (-G * sp)
                        lay = ay - ( G * cp * sr)
                        laz = az - ( G * cp * cr)

                        # Rotate to world frame: R = Rz(yaw)*Ry(pitch)*Rx(roll)
                        wx = cy*cp*lax + (cy*sp*sr - sy*cr)*lay + (cy*sp*cr + sy*sr)*laz
                        wy = sy*cp*lax + (sy*sp*sr + cy*cr)*lay + (sy*sp*cr - cy*sr)*laz
                        wz =   -sp*lax +        cp*sr*lay       +        cp*cr*laz

                        _S.vel[0] += wx * dt
                        _S.vel[1] += wy * dt
                        _S.vel[2] += wz * dt

                        # ZUPT: if stationary, zero velocity to stop bias drift.
                        gyr_mag = math.sqrt(gx*gx + gy*gy + gz*gz)
                        if abs(mag - G) < ZUPT_ACC_THRESH and gyr_mag < ZUPT_GYR_THRESH:
                            _S.vel[:] = [0.0, 0.0, 0.0]

                        _S.pos[0] += _S.vel[0] * dt
                        _S.pos[1] += _S.vel[1] * dt
                        _S.pos[2] += _S.vel[2] * dt
            except Exception:
                pass

    def _gps_loop():
        print("[gps] thread started", flush=True)
        reader: GPSReader | None = None
        while not _stop_evt.is_set():
            try:
                if reader is None:
                    reader = GPSReader()
                rec = reader.read_one()
                if rec is not None and rec.fix_quality and rec.fix_quality > 0:
                    # Store the fix for the main loop to consume every 60 frames.
                    with _lock:
                        _S.gps_pending = {
                            'lat': rec.latitude   or 0.0,
                            'lon': rec.longitude  or 0.0,
                            'alt': rec.altitude_m or 0.0,
                            'spd': rec.speed_knots or 0.0,
                            'crs': rec.course_deg  or 0.0,
                            'fix': float(rec.fix_quality),
                        }
                elif rec is None:
                    reader.close()
                    reader = None
            except Exception:
                if reader is not None:
                    reader.close()
                    reader = None
        if reader is not None:
            reader.close()

    cap_thread = threading.Thread(target=_capture_loop, daemon=True)
    imu_thread = threading.Thread(target=_imu_loop,     daemon=True)
    gps_thread = threading.Thread(target=_gps_loop,     daemon=True)
    cap_thread.start()
    imu_thread.start()
    gps_thread.start()

    log_bytes   = 0
    log_frames  = 0
    log_time    = time.time()
    frame_count = 0

    try:
        while True:
            frame = _frame_q.get()

            ok, jpeg_buf = cv2.imencode('.jpg', frame, _JPEG_PARAMS)
            if not ok:
                continue
            jpeg_bytes = jpeg_buf.tobytes()

            frame_count += 1

            with _lock:
                # Every GPS_ANCHOR_INTERVAL frames: anchor pos/vel from GPS if a fix is pending.
                if frame_count % GPS_ANCHOR_INTERVAL == 0 and _S.gps_pending is not None:
                    g = _S.gps_pending
                    _S.pos[:] = [g['lat'], g['lon'], g['alt']]
                    # Convert GPS speed (knots) + course (degrees clockwise from North)
                    # to world-frame velocity (East, North, Up) in m/s.
                    speed_ms   = g['spd'] * 0.514444
                    course_rad = math.radians(g['crs'])
                    _S.vel[:] = [
                        speed_ms * math.sin(course_rad),
                        speed_ms * math.cos(course_rad),
                        0.0,
                    ]
                    _S.gps_fix = g['fix']
                    _S.gps_pending = None
                    print(f"[gps] anchor  lat={g['lat']:.5f}  lon={g['lon']:.5f}"
                          f"  alt={g['alt']:.1f}m  fix={int(g['fix'])}", flush=True)

                pkt = _pack(jpeg_bytes, _S.pos, _S.vel, _S.acc, _S.gyr,
                            _S.pitch, _S.roll, _S.yaw, _S.gps_fix)

            try:
                sock.send(pkt, copy=False)
            except zmq.Again:
                pass

            now = time.time()
            log_bytes  += len(jpeg_bytes)
            log_frames += 1
            if now - log_time >= 1.0:
                elapsed = now - log_time
                gfix = "fix" if _S.gps_fix > 0 else "none"
                print(
                    f"[py]  {log_bytes / elapsed / 1024:.1f} KB/s"
                    f"  {log_frames / elapsed:.1f} fps"
                    f"  gps={gfix}",
                    flush=True,
                )
                log_bytes  = 0
                log_frames = 0
                log_time   = now

    except KeyboardInterrupt:
        pass
    finally:
        _stop_evt.set()
        cap_thread.join(timeout=2)
        imu_thread.join(timeout=1)
        gps_thread.join(timeout=2)
        if not DEBUG:
            picam2.stop()
        sock.close()
        context.term()
