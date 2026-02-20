# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True

import numpy as np
cimport numpy as np

ctypedef np.uint8_t u8

def quantize_bitdepth(np.ndarray[u8, ndim=3] img, int bits):
    cdef int h = img.shape[0]
    cdef int w = img.shape[1]
    cdef int c = img.shape[2]

    cdef int shift = 8 - bits

    cdef np.ndarray[u8, ndim=3] out = np.empty_like(img)

    cdef int x, y, ch

    for y in range(h):
        for x in range(w):
            for ch in range(c):
                out[y, x, ch] = img[y, x, ch] >> shift

    return out

def quantize_bitdepth_variable(np.ndarray[u8, ndim=3] img, list channel_bits):
    cdef int h = img.shape[0]
    cdef int w = img.shape[1]
    cdef int c = img.shape[2]
    
    if len(channel_bits) != c:
        raise ValueError(f"channel_bits length ({len(channel_bits)}) must match image channels ({c})")

    cdef np.ndarray[u8, ndim=3] out = np.empty_like(img)
    cdef int x, y, ch
    cdef int shift

    for y in range(h):
        for x in range(w):
            for ch in range(c):
                shift = 8 - channel_bits[ch]
                out[y, x, ch] = img[y, x, ch] >> shift

    return out

def pack_bits(np.ndarray[u8, ndim=3] img, int bits):
    cdef Py_ssize_t total_vals = img.size
    cdef Py_ssize_t total_bits = total_vals * bits
    cdef Py_ssize_t total_bytes = (total_bits + 7) // 8

    cdef np.ndarray[u8, ndim=1] packed = np.zeros(total_bytes, dtype=np.uint8)

    cdef u8[:] flat = img.reshape(-1)
    cdef u8[:] out = packed

    cdef Py_ssize_t i
    cdef Py_ssize_t bit_pos = 0
    cdef Py_ssize_t byte_idx, offset
    cdef u8 value

    for i in range(total_vals):
        value = flat[i]

        byte_idx = bit_pos // 8
        offset = bit_pos % 8

        out[byte_idx] |= (value << offset) & 0xFF

        if offset + bits > 8:
            out[byte_idx + 1] |= value >> (8 - offset)

        bit_pos += bits

    return packed

def pack_bits_variable(np.ndarray[u8, ndim=3] img, list channel_bits):
    cdef int h = img.shape[0]
    cdef int w = img.shape[1]
    cdef int c = img.shape[2]
    
    if len(channel_bits) != c:
        raise ValueError(f"channel_bits length ({len(channel_bits)}) must match image channels ({c})")
    
    cdef Py_ssize_t bits_per_pixel = sum(channel_bits)
    cdef Py_ssize_t total_pixels = h * w
    cdef Py_ssize_t total_bits = total_pixels * bits_per_pixel
    cdef Py_ssize_t total_bytes = (total_bits + 7) // 8
    
    cdef np.ndarray[u8, ndim=1] packed = np.zeros(total_bytes, dtype=np.uint8)
    cdef u8[:] out = packed
    
    cdef Py_ssize_t bit_pos = 0
    cdef Py_ssize_t byte_idx, offset
    cdef u8 value
    cdef int x, y, ch
    cdef int ch_bits
    
    for y in range(h):
        for x in range(w):
            for ch in range(c):
                value = img[y, x, ch]
                ch_bits = channel_bits[ch]
                
                byte_idx = bit_pos // 8
                offset = bit_pos % 8
                
                out[byte_idx] |= (value << offset) & 0xFF
                
                if offset + ch_bits > 8:
                    out[byte_idx + 1] |= value >> (8 - offset)
                
                bit_pos += ch_bits
    
    return packed


def unpack_bits(
    np.ndarray[u8, ndim=1] packed,
    int bits,
    int height,
    int width,
    int channels
):
    cdef Py_ssize_t total_vals = height * width * channels

    cdef np.ndarray[u8, ndim=1] flat = np.zeros(total_vals, dtype=np.uint8)
    cdef u8[:] out = flat
    cdef u8[:] src = packed

    cdef Py_ssize_t i
    cdef Py_ssize_t bit_pos = 0
    cdef Py_ssize_t byte_idx, offset

    cdef u8 mask = (1 << bits) - 1
    cdef u8 value

    for i in range(total_vals):
        byte_idx = bit_pos // 8
        offset = bit_pos % 8

        value = (src[byte_idx] >> offset) & mask

        if offset + bits > 8:
            value |= (src[byte_idx + 1] << (8 - offset)) & mask

        out[i] = value
        bit_pos += bits

    return flat.reshape((height, width, channels))

def quantize_and_pack(np.ndarray[u8, ndim=3] img, list channel_bits):
    """
    Quantize each channel to its target bit depth and pack into a flat byte
    array in a single pass — equivalent to calling quantize_bitdepth_variable
    followed by pack_bits_variable but without the intermediate array.
    """
    cdef int h = img.shape[0]
    cdef int w = img.shape[1]
    cdef int c = img.shape[2]

    if len(channel_bits) != c:
        raise ValueError(
            f"channel_bits length ({len(channel_bits)}) must match image channels ({c})"
        )

    cdef Py_ssize_t bits_per_pixel = sum(channel_bits)
    cdef Py_ssize_t total_bits = <Py_ssize_t>h * w * bits_per_pixel
    cdef Py_ssize_t total_bytes = (total_bits + 7) // 8

    cdef np.ndarray[u8, ndim=1] packed = np.zeros(total_bytes, dtype=np.uint8)
    cdef u8[:] out = packed

    cdef Py_ssize_t bit_pos = 0
    cdef Py_ssize_t byte_idx, offset_bits
    cdef u8 value
    cdef int x, y, ch, ch_bits, shift

    for y in range(h):
        for x in range(w):
            for ch in range(c):
                ch_bits = channel_bits[ch]
                shift = 8 - ch_bits
                # quantize: drop the low bits
                value = img[y, x, ch] >> shift

                # pack into output bitstream
                byte_idx = bit_pos // 8
                offset_bits = bit_pos % 8

                out[byte_idx] |= (value << offset_bits) & 0xFF

                if offset_bits + ch_bits > 8:
                    out[byte_idx + 1] |= value >> (8 - offset_bits)

                bit_pos += ch_bits

    return packed


def unpack_bits_variable(
    np.ndarray[u8, ndim=1] packed,
    list channel_bits,
    int height,
    int width,
    int channels
):
    if len(channel_bits) != channels:
        raise ValueError(f"channel_bits length ({len(channel_bits)}) must match channels ({channels})")
    
    cdef np.ndarray[u8, ndim=3] img = np.zeros((height, width, channels), dtype=np.uint8)
    cdef u8[:] src = packed
    
    cdef Py_ssize_t bit_pos = 0
    cdef Py_ssize_t byte_idx, offset
    cdef u8 value, mask
    cdef int x, y, ch
    cdef int ch_bits
    
    for y in range(height):
        for x in range(width):
            for ch in range(channels):
                ch_bits = channel_bits[ch]
                mask = (1 << ch_bits) - 1
                
                byte_idx = bit_pos // 8
                offset = bit_pos % 8
                
                value = (src[byte_idx] >> offset) & mask
                
                if offset + ch_bits > 8:
                    value |= (src[byte_idx + 1] << (8 - offset)) & mask
                
                img[y, x, ch] = value
                bit_pos += ch_bits
    
    return img
