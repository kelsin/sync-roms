import io
import struct
import unittest

from PIL import Image

from sync_roms import qoi


def decode(data):
    """Reference QOI decoder, straight from the spec."""
    assert data[:4] == b"qoif"
    width, height = struct.unpack(">II", data[4:12])
    total = width * height
    out = bytearray()
    index = [(0, 0, 0, 0)] * 64
    r, g, b, a = 0, 0, 0, 255
    pos = 14
    run = 0
    for _ in range(total):
        if run > 0:
            run -= 1
        else:
            byte = data[pos]
            pos += 1
            if byte == 0xFE:
                r, g, b = data[pos : pos + 3]
                pos += 3
            elif byte == 0xFF:
                r, g, b, a = data[pos : pos + 4]
                pos += 4
            elif byte >> 6 == 0b00:
                r, g, b, a = index[byte]
            elif byte >> 6 == 0b01:
                r = (r + ((byte >> 4) & 3) - 2) & 255
                g = (g + ((byte >> 2) & 3) - 2) & 255
                b = (b + (byte & 3) - 2) & 255
            elif byte >> 6 == 0b10:
                second = data[pos]
                pos += 1
                dg = (byte & 0x3F) - 32
                r = (r + dg - 8 + (second >> 4)) & 255
                g = (g + dg) & 255
                b = (b + dg - 8 + (second & 15)) & 255
            else:
                run = byte & 0x3F
            index[(r * 3 + g * 5 + b * 7 + a * 11) % 64] = (r, g, b, a)
        out += bytes((r, g, b, a))
    assert data[pos : pos + 8] == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert len(data) == pos + 8
    return width, height, bytes(out)


class QoiTests(unittest.TestCase):
    def check(self, image):
        width, height, pixels = decode(qoi.encode(image))
        self.assertEqual((width, height), image.size)
        self.assertEqual(pixels, image.convert("RGBA").tobytes())

    def test_flat_color_round_trip(self):
        self.check(Image.new("RGBA", (8, 8), (10, 200, 30, 255)))

    def test_gradient_round_trip(self):
        image = Image.new("RGB", (64, 48))
        image.putdata(
            [((x * 4) % 256, (y * 5 + x) % 256, (x * y) % 256) for y in range(48) for x in range(64)]
        )
        self.check(image)

    def test_alpha_round_trip(self):
        image = Image.new("RGBA", (16, 16))
        image.putdata([(x * 15, y * 15, 7, (x * 16 + y) % 256) for y in range(16) for x in range(16)])
        self.check(image)

    def test_palette_with_transparency_round_trip(self):
        image = Image.new("P", (8, 8), 0)
        image.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255])
        image.putpixel((3, 3), 1)
        image.putpixel((4, 4), 2)
        image.info["transparency"] = 0
        self.check(image)

    def test_grayscale_and_16bit_become_rgba(self):
        gray = Image.new("L", (8, 8))
        gray.putdata(list(range(64)))
        self.check(gray)
        deep = Image.new("I;16", (4, 4))
        deep.putdata([i * 1000 for i in range(16)])
        self.check(deep)

    def test_pillow_reads_our_output(self):
        image = Image.new("RGBA", (32, 24))
        image.putdata([(x * 8, y * 10, (x * y) % 256, 255 - x * 4) for y in range(24) for x in range(32)])
        Image.init()
        with Image.open(io.BytesIO(qoi.encode(image))) as read:
            self.assertEqual(read.format, "QOI")
            self.assertEqual(read.convert("RGBA").tobytes(), image.tobytes())

    def test_header(self):
        data = qoi.encode(Image.new("RGBA", (5, 7)))
        self.assertEqual(data[:4], b"qoif")
        self.assertEqual(data[4:8], (5).to_bytes(4, "big"))
        self.assertEqual(data[8:12], (7).to_bytes(4, "big"))
        self.assertEqual(data[12], 4)
        self.assertEqual(data[13], 0)
        self.assertTrue(data.endswith(b"\x00\x00\x00\x00\x00\x00\x00\x01"))

    def test_long_run_is_split_at_62(self):
        self.check(Image.new("RGBA", (200, 1), (1, 2, 3, 255)))

    def test_zero_size_raises(self):
        with self.assertRaises(ValueError):
            qoi.encode(Image.new("RGBA", (0, 5)))


if __name__ == "__main__":
    unittest.main()
