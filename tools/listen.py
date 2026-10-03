#!/usr/bin/env python3
"""Passively dump input reports from the Stream Dock's vendor HID interface."""
import os, select, sys, time

dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/hidraw0"
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 60
fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
end = time.time() + duration
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.5)
    if r:
        data = os.read(fd, 1024)
        nz = data.rstrip(b"\0")
        print(f"{time.strftime('%H:%M:%S')} len={len(data)} {nz[:32].hex(' ')}  {nz[:32]!r}", flush=True)
