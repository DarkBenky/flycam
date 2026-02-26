DEBUG = False
DEBUG_VIDEO = "fpv.mp4"

import time
import struct
import threading
import queue
import cv2

from datafussion import update_imu, update_gps, get_fused, FusedRecord
from gyro import read_gyro_records
from gps import GPSReader

if not DEBUG:
    from picamera2 import Picamera2

from env import GO_SERVER, GO_META_SERVER
import zmq

# JPEG quality (0-100).  75 is a good balance of quality, bandwidth,
# and encode speed on Raspberry Pi hardware.
JPEG_QUALITY = 75

H = 480
W = 720

# Video packet header: timestamp(4) + width(4) + height(4) + jpeg_size(4)
_VID_HDR_FMT = '<IIII'
_JPEG_PARAMS  = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
_CAM_META_KEYS = ["exposure_time", "gain", "iso", "white_balance", "focus_distance"]

# How often each metadata source is sent.
CAM_META_INTERVAL    = 5.0   # camera settings change slowly
SENSOR_META_INTERVAL = 0.1   # sensor fusion at ~10 Hz

print(f"JPEG quality: {JPEG_QUALITY}  resolution: {W}x{H}")


def _make_video_packet(jpeg_bytes: bytes) -> bytes:
    ts = int(time.time()) & 0xFFFFFFFF
    return struct.pack(_VID_HDR_FMT, ts, W, H, len(jpeg_bytes)) + jpeg_bytes


def _make_meta_packet(cam_meta: dict, fused: FusedRecord) -> bytes:
    """Unified packet: camera fields + sensor fusion fields."""
    ts = int(time.time()) & 0xFFFFFFFF
    ni = max(fused.imu_count, 1)
    sensor_values = {
        "pos_lat": fused.fused_xyz_pos[0],
        "pos_lon": fused.fused_xyz_pos[1],
        "pos_alt": fused.fused_xyz_pos[2],
        "vel_x":   fused.fused_xyz_vel[0],
        "vel_y":   fused.fused_xyz_vel[1],
        "vel_z":   fused.fused_xyz_vel[2],
        "acc_x":   fused.fused_xyz_accel[0],
        "acc_y":   fused.fused_xyz_accel[1],
        "acc_z":   fused.fused_xyz_accel[2],
        "gyr_x":   fused.raw_xyz_gyro_sum[0] / ni,
        "gyr_y":   fused.raw_xyz_gyro_sum[1] / ni,
        "gyr_z":   fused.raw_xyz_gyro_sum[2] / ni,
        "gps_fix": float(fused.last_gps_fix),
    }
    all_entries = list(_CAM_META_KEYS) + list(sensor_values.keys())
    entries = [
        key.encode('ascii')[:8].ljust(8, b'\x00') +
        struct.pack('<f', float(
            cam_meta.get(key, sensor_values.get(key, 0.0))
            if key in _CAM_META_KEYS else sensor_values[key]
        ))
        for key in all_entries
    ]
    return struct.pack('<II', ts, len(entries)) + b''.join(entries)


if __name__ == "__main__":
    context = zmq.Context()

    # Video socket — non-blocking PUSH. CONFLATE is only valid on receivers
    # (SUB/PULL); on PUSH it is silently ignored, so SNDHWM=1 without a send
    # timeout would block the main loop the moment Go can't keep up.
    video_sock = context.socket(zmq.PUSH)
    video_sock.setsockopt(zmq.SNDHWM, 2)
    video_sock.setsockopt(zmq.SNDTIMEO, 0)  # never block, drop stale frames
    video_sock.setsockopt(zmq.LINGER, 0)
    video_sock.connect(GO_SERVER)

    # Metadata socket — non-blocking PUSH, small HWM.
    meta_sock = context.socket(zmq.PUSH)
    meta_sock.setsockopt(zmq.SNDHWM, 4)
    meta_sock.setsockopt(zmq.SNDTIMEO, 0)
    meta_sock.setsockopt(zmq.LINGER, 0)
    meta_sock.connect(GO_META_SERVER)

    if not DEBUG:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            # BGR888 matches OpenCV's native byte order so imencode needs no conversion.
            main={"size": (W, H), "format": "BGR888"},
            controls={"FrameDurationLimits": (16666, 16666)}  # 60 fps
        )
        picam2.configure(config)
        picam2.start()
    else:
        cap = cv2.VideoCapture(DEBUG_VIDEO)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open debug video: {DEBUG_VIDEO}")
        print(f"Debug mode: reading from '{DEBUG_VIDEO}'")

    # ------------------------------------------------------------------
    # Threads:
    #   camera  — buffers latest frame (queue depth 1, drops stale)
    #   IMU     — reads MPU6050 as fast as I2C allows (~1 kHz)
    #   GPS     — blocks on each NMEA sentence (~1-10 Hz)
    # ------------------------------------------------------------------
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
                # OpenCV reads BGR — resize directly, no color conversion needed.
                raw = cv2.resize(raw, (W, H))
                if _frame_q.full():
                    try:
                        _frame_q.get_nowait()
                    except queue.Empty:
                        pass
                _frame_q.put(raw)

    def _imu_loop():
        print("[imu]  thread started", flush=True)
        while not _stop_evt.is_set():
            try:
                update_imu(read_gyro_records()[0])
            except Exception:
                pass

    def _gps_loop():
        print("[gps]  thread started", flush=True)
        reader: GPSReader | None = None
        while not _stop_evt.is_set():
            try:
                if reader is None:
                    reader = GPSReader()
                rec = reader.read_one()
                if rec is not None:
                    update_gps(rec)
                else:
                    # serial error — reopen on next iteration
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
    meta_sent  = 0
    meta_log_time = time.time()

    cached_cam_meta = {k: 0.0 for k in _CAM_META_KEYS}
    cam_meta_time   = time.time()  # don't call capture_metadata on the first frame
    sensor_meta_time = 0.0

    try:
        while True:
            frame = _frame_q.get()  # block only until the next captured frame

            # JPEG encode: much faster than custom bit-packing on Raspberry Pi
            # and requires no intermediate buffers.  OpenCV handles BGR→YCbCr
            # internally so the output is a standard decodable JPEG.
            ok, jpeg_buf = cv2.imencode('.jpg', frame, _JPEG_PARAMS)
            if not ok:
                continue
            jpeg_bytes = jpeg_buf.tobytes()

            try:
                video_sock.send(_make_video_packet(jpeg_bytes), copy=False)
            except zmq.Again:
                pass  # downstream full, drop this frame

            now = time.time()
            if not DEBUG and (now - cam_meta_time >= CAM_META_INTERVAL):
                raw = picam2.capture_metadata()
                cached_cam_meta = {
                    "exposure_time":  raw.get("ExposureTime",    0),
                    "gain":           raw.get("AnalogueGain",    0),
                    "iso":            raw.get("ISOSpeedRatings", 0),
                    "white_balance":  raw.get("WhiteBalance",    0),
                    "focus_distance": raw.get("FocusDistance",   0),
                }
                cam_meta_time = now

            if now - sensor_meta_time >= SENSOR_META_INTERVAL:
                try:
                    meta_sock.send(_make_meta_packet(cached_cam_meta, get_fused()), copy=False)
                    meta_sent += 1
                except zmq.Again:
                    pass
                sensor_meta_time = now

            log_bytes  += len(jpeg_bytes)
            log_frames += 1

            now = time.time()
            if now - log_time >= 1.0:
                elapsed = now - log_time
                meta_rate = meta_sent / (now - meta_log_time)
                print(f"[py]  {log_bytes / elapsed / 1024:.1f} KB/s"
                      f"  {log_frames / elapsed:.1f} fps"
                      f"  meta {meta_rate:.1f}/s")
                log_bytes  = 0
                log_frames = 0
                log_time   = now
                meta_sent  = 0
                meta_log_time = now

    except KeyboardInterrupt:
        pass
    finally:
        _stop_evt.set()
        cap_thread.join(timeout=2)
        imu_thread.join(timeout=1)
        gps_thread.join(timeout=1)
        if not DEBUG:
            picam2.stop()
