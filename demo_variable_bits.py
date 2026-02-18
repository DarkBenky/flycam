#!/usr/bin/env python3
"""
Demo script showing variable bit depth encoding with visual comparison
"""
import numpy as np
import cv2
import quant

def create_test_image():
    """Create a colorful test image"""
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    
    # Create color gradients in different regions
    # Red gradient
    for i in range(80):
        img[0:80, i*4:(i+1)*4, 0] = i * 3
    
    # Green gradient
    for i in range(80):
        img[80:160, i*4:(i+1)*4, 1] = i * 3
    
    # Blue gradient
    for i in range(80):
        img[160:240, i*4:(i+1)*4, 2] = i * 3
    
    # Add some color patches
    img[20:60, 20:60, :] = [255, 100, 100]  # Red patch
    img[100:140, 20:60, :] = [100, 255, 100]  # Green patch
    img[180:220, 20:60, :] = [100, 100, 255]  # Blue patch
    
    # Add mixed colors
    img[20:60, 100:140, :] = [255, 255, 0]  # Yellow
    img[100:140, 100:140, :] = [255, 0, 255]  # Magenta
    img[180:220, 100:140, :] = [0, 255, 255]  # Cyan
    
    return img

def process_and_compare():
    """Process image with both uniform and variable bit depths"""
    img = create_test_image()
    h, w, c = img.shape
    
    print("=" * 70)
    print("Variable Bit Depth Encoding Demo")
    print("=" * 70)
    
    # Uniform bit depth (7 bits per channel)
    uniform_bits = 7
    q_uniform = quant.quantize_bitdepth(img, uniform_bits)
    packed_uniform = quant.pack_bits(q_uniform, uniform_bits)
    unpacked_uniform = quant.unpack_bits(packed_uniform, uniform_bits, h, w, c)
    expanded_uniform = (unpacked_uniform << (8 - uniform_bits)).astype(np.uint8)
    
    # Variable bit depth (5, 8, 6 for R, G, B)
    channel_bits = [5, 8, 6]
    q_variable = quant.quantize_bitdepth_variable(img, channel_bits)
    packed_variable = quant.pack_bits_variable(q_variable, channel_bits)
    unpacked_variable = quant.unpack_bits_variable(packed_variable, channel_bits, h, w, c)
    expanded_variable = np.empty_like(img)
    for ch in range(c):
        expanded_variable[:, :, ch] = (unpacked_variable[:, :, ch] << (8 - channel_bits[ch])).astype(np.uint8)
    
    # Calculate statistics
    print(f"\nOriginal Image: {w}x{h}x{c} = {img.size} bytes")
    print()
    
    print("Uniform Bit Depth (7,7,7):")
    print(f"  Bits per pixel: {uniform_bits * c}")
    print(f"  Packed size: {len(packed_uniform)} bytes")
    print(f"  Compression ratio: {len(packed_uniform) / img.size * 100:.1f}%")
    
    diff_uniform = np.abs(img.astype(float) - expanded_uniform.astype(float))
    print(f"  Max error: {diff_uniform.max():.2f}")
    print(f"  Mean error: {diff_uniform.mean():.2f}")
    print()
    
    print("Variable Bit Depth (5,8,6) - More bits for Green:")
    print(f"  Bits per pixel: {sum(channel_bits)}")
    print(f"  Packed size: {len(packed_variable)} bytes")
    print(f"  Compression ratio: {len(packed_variable) / img.size * 100:.1f}%")
    
    diff_variable = np.abs(img.astype(float) - expanded_variable.astype(float))
    print(f"  Max error: {diff_variable.max():.2f}")
    print(f"  Mean error: {diff_variable.mean():.2f}")
    print()
    
    savings = len(packed_uniform) - len(packed_variable)
    savings_pct = (savings / len(packed_uniform)) * 100
    print(f"Bandwidth Savings: {savings} bytes ({savings_pct:.1f}%)")
    print()
    
    # Perceptual quality note
    print("Perceptual Quality:")
    print("  Green channel has 8 bits (vs 7) - better quality where eyes are sensitive")
    print("  Red channel has 5 bits (vs 7) - slight degradation, less noticeable")
    print("  Blue channel has 6 bits (vs 7) - minimal quality impact")
    print()
    
    # Create comparison visualization
    comparison = np.hstack([
        img,
        expanded_uniform,
        expanded_variable
    ])
    
    # Add labels
    labeled = np.zeros((260, 960, 3), dtype=np.uint8)
    labeled[20:260, :] = comparison
    
    # Add text labels using OpenCV
    cv2.putText(labeled, "Original", (10, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.putText(labeled, "Uniform (7,7,7)", (330, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cv2.putText(labeled, "Variable (5,8,6)", (650, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    cv2.putText(labeled, f"{len(packed_uniform)}B", (380, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    cv2.putText(labeled, f"{len(packed_variable)}B", (700, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    cv2.putText(labeled, f"-{savings_pct:.1f}%", (750, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    
    # Save comparison image
    cv2.imwrite("/home/runner/work/flycam/flycam/comparison.png", labeled)
    print("Saved comparison image to: comparison.png")
    
    print("=" * 70)

if __name__ == "__main__":
    process_and_compare()
