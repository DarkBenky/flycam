DEBUG = True

import time
import struct
import numpy as np

if DEBUG == False:
    from picamera2 import Picamera2
else:
    import random

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



CHANNEL_BITS = [4, 7, 5]

H = 1920
W = 1080
C = 3

print(f"Frame size kb: {H * W * (CHANNEL_BITS[0] + CHANNEL_BITS[1] + CHANNEL_BITS[2]) / 8 / 1024:.2f} KB")

class Packet:
    def __init__(self, frame, metadata: dict):
        self.timestamp = time.time()
        self.frame = frame
        self.metadata = metadata

    def serialize(self):
        # Pack timestamp as uint32 (4 bytes)
        timestamp_bytes = struct.pack('I', int(self.timestamp * 1000))  # milliseconds

        width = struct.pack('I', W)
        height = struct.pack('I', H)
        channels = struct.pack('B', C)  # uint8 for number of channels (3 for RGB)

        channel_bytes = struct.pack('B', CHANNEL_BITS[0]) + struct.pack('B', CHANNEL_BITS[1]) + struct.pack('B', CHANNEL_BITS[2])
        
        # Image data (already packed bytes)
        image_bytes = bytes(self.frame)
        image_size = struct.pack('I', len(image_bytes))

        
        # Pack 256 metadata variables: each has char[8] name + float32 value (12 bytes each)
        metadata_bytes = bytearray(256 * 12)
        for i, (name, value) in enumerate(list(self.metadata.items())[:256]):
            offset = i * 12
            # Pack name as 8-byte string (padded with null bytes)
            name_bytes = name.encode('ascii')[:8].ljust(8, b'\x00')
            metadata_bytes[offset:offset+8] = name_bytes
            # Pack value as float32 (4 bytes)
            struct.pack_into('f', metadata_bytes, offset+8, float(value))
        
        # Combine all parts
        return timestamp_bytes + width + height + channels + channel_bytes + image_size + image_bytes + bytes(metadata_bytes)

if __name__ == "__main__":
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(GO_SERVER)

    socket.setsockopt(zmq.SNDBUF, H * W * (CHANNEL_BITS[0] + CHANNEL_BITS[1] + CHANNEL_BITS[2]) // 8 * 2)  # Set send buffer size to accommodate large frames

    if DEBUG == False:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            main={"size": (W, H), "format": "RGB888"}
        )
        picam2.configure(config)
        picam2.start()

    while True:
        if DEBUG:
            frame = np.random.randint(0, 256, (H, W, C), dtype=np.uint8)
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

        packet = Packet(packed, metadata)
        serialized = packet.serialize()
        socket.send(serialized)



