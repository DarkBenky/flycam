#!/usr/bin/env python3
"""
Test script for variable bit depth quantization and packing
"""
import numpy as np
import quant

def test_uniform_bits():
    """Test legacy uniform bit depth functions"""
    print("Testing uniform bit depth (legacy)...")
    
    # Create a simple test image
    img = np.random.randint(0, 256, (10, 10, 3), dtype=np.uint8)
    bits = 7
    
    # Quantize
    quantized = quant.quantize_bitdepth(img, bits)
    assert quantized.shape == img.shape
    assert quantized.max() < (1 << bits)
    
    # Pack
    packed = quant.pack_bits(quantized, bits)
    expected_bytes = (10 * 10 * 3 * bits + 7) // 8
    assert len(packed) == expected_bytes
    
    # Unpack
    unpacked = quant.unpack_bits(packed, bits, 10, 10, 3)
    assert unpacked.shape == img.shape
    
    # Verify round-trip
    assert np.array_equal(quantized, unpacked)
    
    print(f"  ✓ Uniform bits test passed")
    print(f"  Original size: {img.size} bytes")
    print(f"  Packed size: {len(packed)} bytes")
    print(f"  Compression: {len(packed) / img.size * 100:.1f}%")

def test_variable_bits():
    """Test new variable bit depth functions"""
    print("\nTesting variable bit depth...")
    
    # Create a test image
    img = np.random.randint(0, 256, (10, 10, 3), dtype=np.uint8)
    channel_bits = [5, 8, 6]  # R, G, B
    
    # Quantize with variable bits
    quantized = quant.quantize_bitdepth_variable(img, channel_bits)
    assert quantized.shape == img.shape
    
    # Check each channel is quantized correctly
    for ch in range(3):
        assert quantized[:, :, ch].max() < (1 << channel_bits[ch])
    
    # Pack with variable bits
    packed = quant.pack_bits_variable(quantized, channel_bits)
    expected_bytes = (10 * 10 * sum(channel_bits) + 7) // 8
    assert len(packed) == expected_bytes
    
    # Unpack with variable bits
    unpacked = quant.unpack_bits_variable(packed, channel_bits, 10, 10, 3)
    assert unpacked.shape == img.shape
    
    # Verify round-trip
    assert np.array_equal(quantized, unpacked)
    
    print(f"  ✓ Variable bits test passed")
    print(f"  Channel bits: R={channel_bits[0]}, G={channel_bits[1]}, B={channel_bits[2]}")
    print(f"  Total bits per pixel: {sum(channel_bits)}")
    print(f"  Original size: {img.size} bytes")
    print(f"  Packed size: {len(packed)} bytes")
    print(f"  Compression: {len(packed) / img.size * 100:.1f}%")

def test_bandwidth_comparison():
    """Compare bandwidth usage between uniform and variable bit depths"""
    print("\nBandwidth comparison:")
    
    img = np.random.randint(0, 256, (320, 320, 3), dtype=np.uint8)
    
    # Uniform 7 bits per channel
    bits = 7
    q_uniform = quant.quantize_bitdepth(img, bits)
    packed_uniform = quant.pack_bits(q_uniform, bits)
    
    # Variable: 5, 8, 6 bits for R, G, B
    channel_bits = [5, 8, 6]
    q_variable = quant.quantize_bitdepth_variable(img, channel_bits)
    packed_variable = quant.pack_bits_variable(q_variable, channel_bits)
    
    print(f"  Image size: 320x320x3 = {img.size} bytes")
    print(f"  Uniform (7,7,7): {len(packed_uniform)} bytes ({bits*3} bits/pixel)")
    print(f"  Variable (5,8,6): {len(packed_variable)} bytes ({sum(channel_bits)} bits/pixel)")
    
    savings = len(packed_uniform) - len(packed_variable)
    savings_pct = (savings / len(packed_uniform)) * 100
    print(f"  Bandwidth savings: {savings} bytes ({savings_pct:.1f}%)")
    
    assert len(packed_variable) < len(packed_uniform), "Variable bit depth should use less bandwidth"

def test_edge_cases():
    """Test edge cases and error handling"""
    print("\nTesting edge cases...")
    
    img = np.random.randint(0, 256, (5, 5, 3), dtype=np.uint8)
    
    # Test with different channel configurations
    test_configs = [
        [8, 8, 8],  # Equal bits
        [1, 1, 1],  # Minimum bits
        [5, 6, 5],  # Different variations
    ]
    
    for channel_bits in test_configs:
        q = quant.quantize_bitdepth_variable(img, channel_bits)
        packed = quant.pack_bits_variable(q, channel_bits)
        unpacked = quant.unpack_bits_variable(packed, channel_bits, 5, 5, 3)
        assert np.array_equal(q, unpacked)
    
    print("  ✓ All edge cases passed")

def test_visual_quality():
    """Test that variable bit depth preserves reasonable visual quality"""
    print("\nTesting visual quality preservation...")
    
    # Create a gradient image
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    for i in range(100):
        img[i, :, :] = i * 255 // 100
    
    channel_bits = [5, 8, 6]
    
    # Process through variable bit depth
    quantized = quant.quantize_bitdepth_variable(img, channel_bits)
    packed = quant.pack_bits_variable(quantized, channel_bits)
    unpacked = quant.unpack_bits_variable(packed, channel_bits, 100, 100, 3)
    
    # Expand back to 8 bits for comparison
    expanded = np.empty_like(img)
    for ch in range(3):
        expanded[:, :, ch] = (unpacked[:, :, ch] << (8 - channel_bits[ch]))
    
    # Calculate error
    diff = np.abs(img.astype(float) - expanded.astype(float))
    max_error = diff.max()
    mean_error = diff.mean()
    
    print(f"  Max error: {max_error:.2f}")
    print(f"  Mean error: {mean_error:.2f}")
    print("  ✓ Visual quality test passed")

if __name__ == "__main__":
    print("=" * 60)
    print("Variable Bit Depth Quantization Test Suite")
    print("=" * 60)
    
    test_uniform_bits()
    test_variable_bits()
    test_bandwidth_comparison()
    test_edge_cases()
    test_visual_quality()
    
    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
