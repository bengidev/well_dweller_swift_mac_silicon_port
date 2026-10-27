# NSO segment decompression: LZ4 (legacy) or ZBIC (Switch 22.0.0+, NSO flag bit 7).
NSO_FLAG_ZBIC = 0x80


def decompress_segment(raw, uncompressed_size, flags, segment_index):
    if not (flags >> segment_index & 1):
        return raw
    if flags & NSO_FLAG_ZBIC:
        try:
            import zbic
        except ImportError:
            raise ImportError('ZBIC-compressed NSO segments need the zbic package (pip install zbic)')
        out = zbic.decompress(raw)
        if len(out) != uncompressed_size:
            raise ValueError(f'ZBIC segment {segment_index}: got {len(out)} bytes, expected {uncompressed_size}')
        return out
    import lz4.block
    return lz4.block.decompress(raw, uncompressed_size=uncompressed_size)
