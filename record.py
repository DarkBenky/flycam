DEBUG = True
DEBUG_VIDEO = "fpv.mp4"

import time
import struct
import threading
import queue
import cv2

if not DEBUG:
    from picamera2 import Picamera2

from env import GO_SERVER, GO_META_SERVER
import zmq

# JPEG quality (0-100).  75 is a good balance of quality, bandwidth,
# and encode speed on Raspberry Pi hardware.
JPEG_QUALITY = 75

H = 320
W = 320

# Video packet header: timestamp(4) + width(4) + height(4) + jpeg_size(4)
_VID_HDR_FMT = '<IIII'
_JPEG_PARAMS  = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
_META_KEYS    = ["exposure_time", "gain", "iso", "white_balance", "focus_distance"]

print(f"JPEG quality: {JPEG_QUALITY}  resolution: {W}x{H}")


def _make_video_packet(jpeg_bytes: bytes) -> bytes:
    """Prepend a 16-byte header to the raw JPEG payload."""
    ts = int(time.time()) & 0xFFFFFFFF
    return struct.pack(_VID_HDR_FMT, ts, W, H, len(jpeg_bytes)) + jpeg_bytes


def _make_meta_packet(metadata: dict) -> bytes:
    """Serialize metadata as: timestamp(4) + count(4) + count*(name[8]+float32)."""
    ts = int(time.time()) & 0xFFFFFFFF
    entries = [
        key.encode('ascii')[:8].ljust(8, b'\x00') +
        struct.pack('<f', float(metadata.get(key, 0.0)))
        for key in _META_KEYS
    ]
    return struct.pack('<II', ts, len(entries)) + b''.join(entries)


if __name__ == "__main__":
    context = zmq.Context()

    # Video socket — drop all but the latest frame.
    video_sock = context.socket(zmq.PUSH)
    video_sock.setsockopt(zmq.CONFLATE, 1)
    video_sock.setsockopt(zmq.SNDHWM, 1)
    video_sock.connect(GO_SERVER)

    # Metadata socket — separate channel, updated infrequently.
    meta_sock = context.socket(zmq.PUSH)
    meta_sock.setsockopt(zmq.CONFLATE, 1)
    meta_sock.setsockopt(zmq.SNDHWM, 1)
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
    # Capture thread — runs sensor capture independently so the main
    # thread never stalls waiting for the camera.  Queue depth = 1:
    # always process the latest frame, silently drop any that pile up.
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

    cap_thread = threading.Thread(target=_capture_loop, daemon=True)
    cap_thread.start()

    log_bytes  = 0
    log_frames = 0
    log_time   = time.time()

    META_INTERVAL   = 5.0
    cached_metadata = {k: 0.0 for k in _META_KEYS}
    meta_time       = 0.0

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

            video_sock.send(_make_video_packet(jpeg_bytes), copy=False)

            now = time.time()
            if not DEBUG and (now - meta_time >= META_INTERVAL):
                cam_meta = picam2.capture_metadata()
                cached_metadata = {
                    "exposure_time":  cam_meta.get("ExposureTime",    0),
                    "gain":           cam_meta.get("AnalogueGain",    0),
                    "iso":            cam_meta.get("ISOSpeedRatings", 0),
                    "white_balance":  cam_meta.get("WhiteBalance",    0),
                    "focus_distance": cam_meta.get("FocusDistance",   0),
                }
                meta_time = now
                meta_sock.send(_make_meta_packet(cached_metadata), copy=False)

            log_bytes  += len(jpeg_bytes)
            log_frames += 1

            now = time.time()
            if now - log_time >= 1.0:
                elapsed = now - log_time
                print(f"[py]  {log_bytes / elapsed / 1024:.1f} KB/s"
                      f"  {log_frames / elapsed:.1f} fps")
                log_bytes  = 0
                log_frames = 0
                log_time   = now

    except KeyboardInterrupt:
        pass
    finally:
        _stop_evt.set()
        cap_thread.join(timeout=2)
        if not DEBUG:
            picam2.stop()
