"""Minimal driver for the Mirabox Stream Dock 293S V3 (USB 6603:1014) over Linux hidraw.

Wire protocol (from the vendor SDK's libtransport.so and the mirajazz crate):
every OUT report is 1025 bytes: report-id 0x00 + 1024 payload bytes, zero padded.
Commands start with b"CRT\\0\\0" followed by the command name.

Physical layout as hardware indices (keys 16-18 are display-only side screens):

     13 10  7  4  1 | 16
     14 11  8  5  2 | 17
     15 12  9  6  3 | 18
"""
import glob
import io
import os
import select
import threading
import time

from PIL import Image

VID, PID = 0x6603, 0x1014
PAYLOAD = 1024
KEY_SIZE = 96
SIDE_SIZE = 80
BG_SIZE = (854, 480)
COLS, ROWS = 5, 3


def key_index(col, row):
    """Hardware index of the main key at (col, row), 0-based from the top-left."""
    return (COLS - 1 - col) * ROWS + row + 1


def key_position(index):
    """(col, row) of a main key hardware index 1..15."""
    return COLS - 1 - (index - 1) // ROWS, (index - 1) % ROWS


def find_hidraw():
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        with open(os.path.join(path, "device/uevent")) as f:
            uevent = f.read()
        if f"HID_ID=0003:{VID:08X}:{PID:08X}" not in uevent:
            continue
        # The vendor interface has a 1024-byte output report; the boot keyboard does not.
        with open(os.path.join(path, "device/report_descriptor"), "rb") as f:
            if f.read()[:3] == b"\x06\xa0\xff":
                return "/dev/" + os.path.basename(path)
    raise FileNotFoundError("Stream Dock 293S V3 not found")


def encode_jpeg(img, size, quality=90):
    img = img.convert("RGB")
    if img.size != size:
        img = img.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    img.rotate(90, expand=True).save(buf, "JPEG", quality=quality, subsampling=0)
    return buf.getvalue()


class StreamDock:
    def __init__(self, path=None, heartbeat=True):
        self.path = path or find_hidraw()
        self.fd = os.open(self.path, os.O_RDWR)
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._hb = None
        self.init()
        if heartbeat:
            self._hb = threading.Thread(target=self._heartbeat, daemon=True)
            self._hb.start()

    # -- transport ---------------------------------------------------------
    def _write(self, payload):
        assert len(payload) <= PAYLOAD
        os.write(self.fd, b"\x00" + payload.ljust(PAYLOAD, b"\x00"))

    def cmd(self, name, args=b""):
        with self.lock:
            self._write(b"CRT\x00\x00" + name + args)

    def _send_blob(self, header, data):
        with self.lock:
            self._write(header)
            for i in range(0, len(data), PAYLOAD):
                self._write(data[i:i + PAYLOAD])

    def _heartbeat(self):
        while not self._stop.wait(10):
            self.cmd(b"CONNECT")

    # -- commands ----------------------------------------------------------
    def init(self):
        self.cmd(b"DIS")
        self.brightness(100)
        self.clear()
        self.refresh()

    def brightness(self, percent):
        self.cmd(b"LIG", bytes([0, 0, max(0, min(100, percent))]))

    def clear(self, index=0xFF):
        self.cmd(b"CLE", bytes([0, 0, 0, index]))

    def refresh(self):
        self.cmd(b"STP")

    def set_key_jpeg(self, index, jpeg):
        # Don't put anything after the index byte: extra header bytes hung the firmware.
        header = b"CRT\x00\x00BAT" + len(jpeg).to_bytes(4, "big") + bytes([index])
        self._send_blob(header, jpeg)

    def set_key_image(self, index, img, quality=90):
        size = SIDE_SIZE if index > 15 else KEY_SIZE
        self.set_key_jpeg(index, encode_jpeg(img, (size, size), quality))

    def set_background(self, img, quality=85):
        """Full-screen 854x480 image (LOG). May be stored in flash: don't call in a loop."""
        jpeg = encode_jpeg(img, BG_SIZE, quality)
        header = b"CRT\x00\x00LOG" + len(jpeg).to_bytes(4, "big") + b"\x01"
        self._send_blob(header, jpeg)
        time.sleep(1.4)

    def read_event(self, timeout=None):
        """Return (index, pressed) for a key event, or None on timeout/other report."""
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return None
        data = os.read(self.fd, 1024)
        if data[:3] != b"ACK" or len(data) < 11 or not 1 <= data[9] <= 15:
            return None
        return data[9], data[10] == 0x01

    def close(self, sleep=False):
        self._stop.set()
        if sleep:
            self.cmd(b"CLE", b"\x00\x00DC")
            self.cmd(b"HAN")
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
