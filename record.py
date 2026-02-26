DEBUG = False
DEBUG_VIDEO = "fpv.mp4"

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

# Packet layout (68-byte header + JPEG):
#   [0]  timestamp  u32
#   [4]  width      u32
#   [8]  height     u32
#   [12] jpeg_size  u32
#   [16] pos_lat    f32
#   [20] pos_lon    f32
#   [24] pos_alt    f32
#   [28] vel_x      f32
#   [32] vel_y      f32
#   [36] vel_z      f32
#   [40] acc_x      f32
#   [44] acc_y      f32
#   [48] acc_z      f32
#   [52] gyr_x      f32
#   [56] gyr_y      f32
#   [60] gyr_z      f32
#   [64] gps_fix    f32  (0=no fix)
#   [68] jpeg bytes
_HDR_FMT  = '<IIII13f'
_HDR_SIZE = struct.calcsize(_HDR_FMT)  # 68
_JPEG_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]

print(f"JPEG quality: {JPEG_QUALITY}  resolution: {W}x{H}  header: {_HDR_SIZE}B")


def _pack(jpeg_bytes: bytes, pos, vel, acc, gyr, gps_fix: float) -> bytes:
    ts = int(time.time()) & 0xFFFFFFFF
    return struct.pack(
        _HDR_FMT, ts, W, H, len(jpeg_bytes),
        pos[0], pos[1], pos[2],
        vel[0], vel[1], vel[2],
        acc[0], acc[1], acc[2],
        gyr[0], gyr[1], gyr[2],
        gps_fix,
    ) + jpeg_bytes


# Shared sensor state — class fields are mutable so inner functions can write
class _S:
    acc     = [0.0, 0.0, 0.0]
    gyr     = [0.0, 0.0, 0.0]
    vel     = [0.0, 0.0, 0.0]
    pos     = [0.0, 0.0, 0.0]
    gps_fix = 0.0
    imu_t   = 0.0


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
        print("[imu] thread started", flush=True)
        while not _stop_evt.is_set():
            try:
                rec = read_gyro_records()[0]
                now = time.time()
                with _lock:
                    dt = now - _S.imu_t if _S.imu_t > 0 else 0.0
                    _S.imu_t = now
                    _S.acc[:] = rec.acceleration
                    _S.gyr[:] = rec.gyro
                    if 0 < dt < 0.05:
                        _S.vel[0] += _S.acc[0] * dt
                        _S.vel[1] += _S.acc[1] * dt
                        _S.vel[2] += _S.acc[2] * dt
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
                    with _lock:
                        _S.pos[:] = [
                            rec.latitude   or 0.0,
                            rec.longitude  or 0.0,
                            rec.altitude_m or 0.0,
                        ]
                        _S.vel[:] = [0.0, 0.0, 0.0]
                        _S.gps_fix = float(rec.fix_quality)
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

    log_bytes  = 0
    log_frames = 0
    log_time   = time.time()

    try:
        while True:
            frame = _frame_q.get()

            ok, jpeg_buf = cv2.imencode('.jpg', frame, _JPEG_PARAMS)
            if not ok:
                continue
            jpeg_bytes = jpeg_buf.tobytes()

            with _lock:
                pkt = _pack(jpeg_bytes, _S.pos, _S.vel, _S.acc, _S.gyr, _S.gps_fix)

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
