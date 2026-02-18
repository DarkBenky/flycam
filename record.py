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

# Variable bit depth per channel (R, G, B)
# Human eye is more sensitive to green, so allocate more bits to green
# This uses 5+8+6 = 19 bits per pixel vs 7+7+7 = 21 bits
# Saving ~9.5% bandwidth while maintaining better perceptual quality
CHANNEL_BITS = [5, 8, 6]  # R=5 bits, G=8 bits, B=6 bits

# Legacy mode: set USE_VARIABLE_BITS = False to use uniform bit depth
USE_VARIABLE_BITS = True
BITS = 7  # Only used if USE_VARIABLE_BITS = False

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
        # Variable bit depth quantization and packing
        q = quant.quantize_bitdepth_variable(frame, CHANNEL_BITS)
        packed = quant.pack_bits_variable(q, CHANNEL_BITS)
        unpacked = quant.unpack_bits_variable(packed, CHANNEL_BITS, H, W, C)
        
        # Expand each channel appropriately for preview
        preview = np.empty_like(frame)
        for ch in range(C):
            preview[:, :, ch] = (unpacked[:, :, ch] << (8 - CHANNEL_BITS[ch])).astype(np.uint8)
    else:
        # Legacy uniform bit depth
        q = quant.quantize_bitdepth(frame, BITS)
        packed = quant.pack_bits(q, BITS)
        unpacked = quant.unpack_bits(packed, BITS, H, W, C)
        preview = (unpacked << (8 - BITS)).astype(np.uint8)

    cv2.imshow("Unpacked Preview", preview)

    if cv2.waitKey(1) == 27:
        break
