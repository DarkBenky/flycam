import cv2
import numpy as np
from picamera2 import Picamera2

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

CHANNEL_BITS = [5, 8, 6]
USE_VARIABLE_BITS = True
BITS = 7

H = 320
W = 320
C = 3

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": (W, H), "format": "RGB888"}
)
picam2.configure(config)
picam2.start()

while True:
    frame = picam2.capture_array()

    if USE_VARIABLE_BITS:
        q = quant.quantize_bitdepth_variable(frame, CHANNEL_BITS)
        packed = quant.pack_bits_variable(q, CHANNEL_BITS)
        unpacked = quant.unpack_bits_variable(packed, CHANNEL_BITS, H, W, C)
        
        preview = np.empty_like(frame)
        for ch in range(C):
            preview[:, :, ch] = (unpacked[:, :, ch] << (8 - CHANNEL_BITS[ch])).astype(np.uint8)
    else:
        q = quant.quantize_bitdepth(frame, BITS)
        packed = quant.pack_bits(q, BITS)
        unpacked = quant.unpack_bits(packed, BITS, H, W, C)
        preview = (unpacked << (8 - BITS)).astype(np.uint8)

    cv2.imshow("Unpacked Preview", preview)

    if cv2.waitKey(1) == 27:
        break
