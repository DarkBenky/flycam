# Variable Bit Depth Quantization

This repository implements efficient image quantization and packing with support for variable bit depths per color channel.

## Features

### Variable Bit Depth Support
- Allocate different numbers of bits to each color channel (R, G, B)
- Optimize bandwidth usage based on human color perception
- Default configuration: **R:5 bits, G:8 bits, B:6 bits**
  - Human eyes are most sensitive to green → allocate more bits
  - Total: 19 bits/pixel vs 21 bits/pixel uniform → **9.5% bandwidth savings**

### Backward Compatibility
- Legacy uniform bit depth functions remain available
- Easy toggle between variable and uniform modes
- No breaking changes to existing code

## API

### Variable Bit Depth Functions

```python
import quant
import numpy as np

# Image array (H, W, C)
img = np.random.randint(0, 256, (320, 320, 3), dtype=np.uint8)

# Define bits per channel [Red, Green, Blue]
channel_bits = [5, 8, 6]

# Quantize with variable bit depths
quantized = quant.quantize_bitdepth_variable(img, channel_bits)

# Pack into compact byte array
packed = quant.pack_bits_variable(quantized, channel_bits)

# Unpack back to image
unpacked = quant.unpack_bits_variable(packed, channel_bits, 320, 320, 3)

# Expand to 8-bit for display
expanded = np.empty_like(img)
for ch in range(3):
    expanded[:, :, ch] = (unpacked[:, :, ch] << (8 - channel_bits[ch]))
```

### Legacy Uniform Bit Depth Functions

```python
# All channels use same bit depth
bits = 7
quantized = quant.quantize_bitdepth(img, bits)
packed = quant.pack_bits(quantized, bits)
unpacked = quant.unpack_bits(packed, bits, 320, 320, 3)
```

## Usage Example

The `record.py` script demonstrates real-time encoding:

```python
# Enable variable bit depth mode
USE_VARIABLE_BITS = True
CHANNEL_BITS = [5, 8, 6]  # R, G, B

# Or use uniform mode
USE_VARIABLE_BITS = False
BITS = 7
```

## Benefits

1. **Bandwidth Efficiency**: Save ~9.5% bandwidth with default (5,8,6) configuration
2. **Perceptual Quality**: Better quality where it matters (green channel)
3. **Flexibility**: Easy to adjust bit allocation for different use cases
4. **Performance**: Optimized Cython implementation for speed

## Testing

Run the test suite:
```bash
python test_variable_bits.py
```

Run the visual comparison demo:
```bash
python demo_variable_bits.py
```

## Building

```bash
python setup.py build_ext --inplace
```

## Installation

```bash
pip install -r requirements.txt
python setup.py build_ext --inplace
```

## Technical Details

### Bit Allocation Rationale

Human vision sensitivity by wavelength:
- **Green (~555nm)**: Peak sensitivity → allocate 8 bits
- **Red (~700nm)**: Moderate sensitivity → allocate 5 bits
- **Blue (~440nm)**: Lower sensitivity → allocate 6 bits

This allocation matches the human visual system better than uniform distribution, providing better perceptual quality with less data.

### Packing Algorithm

The variable bit depth packing algorithm:
1. Processes pixels in raster order (row by row, left to right)
2. Within each pixel, processes channels in order (R, G, B)
3. Packs bits tightly across byte boundaries
4. Uses efficient bit manipulation for minimal overhead

Example with (5,8,6) bit configuration:
- Pixel 1: R(5 bits) + G(8 bits) + B(6 bits) = 19 bits
- Spans 3 bytes with some partial bytes
- Next pixel continues immediately, no padding

### Performance

The Cython implementation provides:
- Zero-copy memory views for efficiency
- Optimized C loops with no Python overhead
- Compiler optimizations (-O3 -march=native -ffast-math)

## License

See repository license.
