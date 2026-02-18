import cv2
import numpy as np
from picamera2 import Picamera2

try:
    import quant
except ImportError:
    import os
    import subprocess
    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    setup_py = os.path.join(script_dir, "setup.py")
    try:
        subprocess.run([sys.executable, setup_py, "build_ext", "--inplace"],
                       check=True, cwd=script_dir)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "Failed to build the Cython extension. "
            "Make sure build dependencies are installed (run install.sh)."
        ) from e
    import quant

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

    # Quantize
    q = quant.quantize_bitdepth(frame, BITS)

    # Pack
    packed = quant.pack_bits(q, BITS)

    # Unpack
    unpacked = quant.unpack_bits(packed, BITS, H, W, C)

    # Expand for preview
    preview = (unpacked << (8 - BITS)).astype(np.uint8)

    cv2.imshow("Unpacked Preview", preview)

    if cv2.waitKey(1) == 27:
        break
