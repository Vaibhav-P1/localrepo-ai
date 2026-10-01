"""Generate build/icon.png: cream tile, black border, dark-red offset shadow, black L."""
import os
import struct
import zlib

N = 512
INK, CREAM, RED, BLUE, CLEAR = (20, 17, 15, 255), (244, 236, 216, 255), (143, 29, 29, 255), (29, 78, 216, 255), (0, 0, 0, 0)


def px(x, y):
    col = RED if (90 <= x < 470 and 90 <= y < 470) else CLEAR
    if 40 <= x < 420 and 40 <= y < 420:
        col = INK
        if 58 <= x < 402 and 58 <= y < 402:
            col = CREAM
            if (130 <= x < 190 and 120 <= y < 330) or (130 <= x < 320 and 270 <= y < 330):
                col = INK
            if 300 <= x < 350 and 120 <= y < 170:
                col = BLUE
    return col


def chunk(t, d):
    c = struct.pack(">I", len(d)) + t + d
    return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


raw = b"".join(b"\x00" + b"".join(bytes(px(x, y)) for x in range(N)) for y in range(N))
png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "icon.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "wb").write(png)
print("wrote", out)
