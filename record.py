DEBUG = True
DEBUG_VIDEO = "fpv.mp4"

import time
import struct
import threading
import queue
import numpy as np
import cv2
import lz4.block

if not DEBUG:
    from picamera2 import Picamera2

from env import GO_SERVER
import zmq

try:
    import quant
except ImportError:
    import subprocess
    import sys
    print("Building Cython extension quant...")
    subprocess.run(
        [sys.executable, "setup.py", "build_ext", "--inplace"],
        check=True
    )
    import quant



CHANNEL_BITS = [3, 5, 4]

H = 320
W = 320
C = 3

USE_COMPRESSION = True

print(f"Frame size: {H * W * (CHANNEL_BITS[0] + CHANNEL_BITS[1] + CHANNEL_BITS[2]) / 8 / 1024:.2f} KB")

# ---------------------------------------------------------------------------
# Fast serialization — fixed header fields written once at startup.
# Per frame we only update: timestamp (4 B), compression flag (1 B),
# image_size (4 B), image bytes, and 5 metadata float values.
# ---------------------------------------------------------------------------
_HEADER_SIZE = 21          # 4+4+4+1+3+1+4
_IMAGE_MAX   = (H * W * sum(CHANNEL_BITS) + 7) // 8
_META_KEYS   = ["exposure_time", "gain", "iso", "white_balance", "focus_distance"]
_META_SIZE   = 256 * 12    # keep protocol-compatible with C decoder

_out_buf = bytearray(_HEADER_SIZE + _IMAGE_MAX + 64 + _META_SIZE)

# Write constant header fields once
struct.pack_into('I', _out_buf,  4, W)
struct.pack_into('I', _out_buf,  8, H)
struct.pack_into('B', _out_buf, 12, C)
_out_buf[13] = CHANNEL_BITS[0]
_out_buf[14] = CHANNEL_BITS[1]
_out_buf[15] = CHANNEL_BITS[2]

# Pre-populate metadata name fields (only float values change per frame)
_meta_buf = bytearray(_META_SIZE)
for _i, _key in enumerate(_META_KEYS):
    _off = _i * 12
    _meta_buf[_off:_off + 8] = _key.encode('ascii')[:8].ljust(8, b'\x00')


def _serialize(packed_frame, metadata: dict) -> bytes:
    """Serialize into the shared buffer and return an immutable bytes copy."""
    ts = int(time.time()) & 0xFFFFFFFF

    raw = bytes(packed_frame)
    if USE_COMPRESSION:
        img_data = lz4.block.compress(raw, store_size=False)
        _out_buf[16] = 1
    else:
        img_data = raw
        _out_buf[16] = 0

    img_len = len(img_data)
    struct.pack_into('I', _out_buf, 0,  ts)
    struct.pack_into('I', _out_buf, 17, img_len)
    _out_buf[_HEADER_SIZE : _HEADER_SIZE + img_len] = img_data

    meta_start = _HEADER_SIZE + img_len
    _out_buf[meta_start : meta_start + _META_SIZE] = _meta_buf
    for i, key in enumerate(_META_KEYS):
        struct.pack_into('f', _out_buf, meta_start + i * 12 + 8,
                         float(metadata.get(key, 0.0)))

    return bytes(_out_buf[:meta_start + _META_SIZE])

if __name__ == "__main__":
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    # Drop all but the latest frame: never queue stale frames.
    socket.setsockopt(zmq.CONFLATE, 1)
    socket.setsockopt(zmq.SNDHWM, 1)
    socket.connect(GO_SERVER)
    socket.setsockopt(zmq.SNDBUF, H * W * (CHANNEL_BITS[0] + CHANNEL_BITS[1] + CHANNEL_BITS[2]) // 8 * 2)

    if not DEBUG:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            main={"size": (W, H), "format": "RGB888"},
            controls={"FrameDurationLimits": (16666, 16666)}  # 60fps
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
                raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
                raw = cv2.resize(raw, (W, H))
                raw = np.asarray(raw, dtype=np.uint8)
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
    meta_time = 0.0

    try:
        while True:
            frame = _frame_q.get()  # block only until the next captured frame

            # Single-pass quantize + pack (was two separate Cython calls)
            packed = quant.quantize_and_pack(frame, CHANNEL_BITS)

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

            serialized = _serialize(packed, cached_metadata)
            # copy=False: ZMQ won't make an extra internal copy of the
            # already-immutable bytes object
            socket.send(serialized, copy=False)

            log_bytes  += len(serialized)
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
