"""QOI ("Quite OK Image") encoder, for SpruceOS box art."""

import struct

_END = b"\x00\x00\x00\x00\x00\x00\x00\x01"


def encode(image):
    """Return `image` (any PIL mode) as a 4-channel QOI file."""
    width, height = image.size
    if width == 0 or height == 0:
        raise ValueError("cannot encode an empty image")
    data = image.convert("RGBA").tobytes()
    out = bytearray(b"qoif" + struct.pack(">II", width, height) + b"\x04\x00")
    index = [(0, 0, 0, 0)] * 64
    prev = (0, 0, 0, 255)
    run = 0
    last = width * height - 1
    for i in range(width * height):
        px = tuple(data[i * 4 : i * 4 + 4])
        if px == prev:
            run += 1
            if run == 62 or i == last:
                out.append(0xC0 | (run - 1))
                run = 0
            continue
        if run:
            out.append(0xC0 | (run - 1))
            run = 0
        r, g, b, a = px
        h = (r * 3 + g * 5 + b * 7 + a * 11) % 64
        if index[h] == px:
            out.append(h)
        else:
            index[h] = px
            if a != prev[3]:
                out += bytes((0xFF, r, g, b, a))
            else:
                dr = ((r - prev[0] + 128) & 255) - 128
                dg = ((g - prev[1] + 128) & 255) - 128
                db = ((b - prev[2] + 128) & 255) - 128
                if -2 <= dr <= 1 and -2 <= dg <= 1 and -2 <= db <= 1:
                    out.append(0x40 | (dr + 2) << 4 | (dg + 2) << 2 | (db + 2))
                else:
                    drg = dr - dg
                    dbg = db - dg
                    if -32 <= dg <= 31 and -8 <= drg <= 7 and -8 <= dbg <= 7:
                        out += bytes((0x80 | (dg + 32), (drg + 8) << 4 | (dbg + 8)))
                    else:
                        out += bytes((0xFE, r, g, b))
        prev = px
    return bytes(out) + _END
