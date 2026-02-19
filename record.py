DEBUG = True
DEBUG_VIDEO = "fpv.mp4"

import time
import struct
import numpy as np
import cv2
import lz4.block

if not DEBUG:
    from picamera2 import Picamera2

from env import SECRET, GO_SERVER
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



CHANNEL_BITS = [2, 4, 3]

H = 480
W = 720
C = 3

USE_COMPRESSION = True

print(f"Frame size: {H * W * (CHANNEL_BITS[0] + CHANNEL_BITS[1] + CHANNEL_BITS[2]) / 8 / 1024:.2f} KB")


class Packet:
    def __init__(self, frame, metadata: dict):
        self.timestamp = time.time()
        self.frame = frame
        self.metadata = metadata

    def serialize(self):
        timestamp_bytes = struct.pack('I', int(self.timestamp) & 0xFFFFFFFF)
        width = struct.pack('I', W)
        height = struct.pack('I', H)
        channels = struct.pack('B', C)
        channel_bytes = struct.pack('B', CHANNEL_BITS[0]) + struct.pack('B', CHANNEL_BITS[1]) + struct.pack('B', CHANNEL_BITS[2])

        raw_image = bytes(self.frame)
        if USE_COMPRESSION:
            image_bytes = lz4.block.compress(raw_image, store_size=False)
            compression_flag = struct.pack('B', 1)
        else:
            image_bytes = raw_image
            compression_flag = struct.pack('B', 0)

        image_size = struct.pack('I', len(image_bytes))

        metadata_bytes = bytearray(256 * 12)
        for i, (name, value) in enumerate(list(self.metadata.items())[:256]):
            offset = i * 12
            name_bytes = name.encode('ascii')[:8].ljust(8, b'\x00')
            metadata_bytes[offset:offset+8] = name_bytes
            struct.pack_into('f', metadata_bytes, offset+8, float(value))

        return timestamp_bytes + width + height + channels + channel_bytes + compression_flag + image_size + image_bytes + bytes(metadata_bytes)

if __name__ == "__main__":
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(GO_SERVER)
    socket.setsockopt(zmq.SNDBUF, H * W * (CHANNEL_BITS[0] + CHANNEL_BITS[1] + CHANNEL_BITS[2]) // 8 * 2)

    if not DEBUG:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            main={"size": (W, H), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()
    else:
        cap = cv2.VideoCapture(DEBUG_VIDEO)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open debug video: {DEBUG_VIDEO}")
        print(f"Debug mode: reading from '{DEBUG_VIDEO}'")

    log_interval = 60
    log_bytes = 0
    log_frames = 0
    log_time = time.time()

    while True:
        if DEBUG:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (W, H))
            frame = np.asarray(frame, dtype=np.uint8)
        else:
            frame = picam2.capture_array()

        q = quant.quantize_bitdepth_variable(frame, CHANNEL_BITS)
        packed = quant.pack_bits_variable(q, CHANNEL_BITS)

        metadata = {
            "exposure_time": picam2.capture_metadata().get("ExposureTime", 0) if not DEBUG else 0,
            "gain": picam2.capture_metadata().get("AnalogueGain", 0) if not DEBUG else 0,
            "iso": picam2.capture_metadata().get("ISOSpeedRatings", 0) if not DEBUG else 0,
            "white_balance": picam2.capture_metadata().get("WhiteBalance", 0) if not DEBUG else 0,
            "focus_distance": picam2.capture_metadata().get("FocusDistance", 0) if not DEBUG else 0,
        }

        serialized = Packet(packed, metadata).serialize()
        socket.send(serialized)
        log_bytes += len(serialized)
        log_frames += 1

        now = time.time()
        if now - log_time >= 1.0:
            elapsed = now - log_time
            print(f"[py]  {log_bytes / elapsed / 1024:.1f} KB/s  {log_frames / elapsed:.1f} fps")
            log_bytes = 0
            log_frames = 0
            log_time = now

        time.sleep(0.032)  # Limit to ~30 FPS
