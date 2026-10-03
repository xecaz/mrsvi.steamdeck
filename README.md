# MRSVI / Mirabox Stream Dock 293S V3 on Linux

Reverse-engineering and driving a MRSVI-branded stream deck from Linux without the vendor
software. The hardware is a Mirabox **Stream Dock 293S V3** (USB `6603:1014`, reports as
`HOTSPOTEKUSB HID DEMO`, firmware `V3.HSV293S.02.009`), also sold under other names.

What works:

- Key images on all 15 keys, plus the tall display strip on the right
- Key press and release events
- Brightness, clear and sleep
- A persistent custom boot picture
- A figure-8 scroller that moves one large image across the keys and the strip as if they
  were windows onto a single screen

## Hardware

```
 13 10  7  4  1 | 16
 14 11  8  5  2 | 17
 15 12  9  6  3 | 18
```

- **15 LCD keys** in a 5×3 grid. The numbers above are the hardware indices for images and
  presses: column by column, starting from the top right.
- **A tall display strip on the right** with no buttons. Slots 16–18 each draw into it, starting
  level with key rows 1–3.
- **Behind the faceplate is a single 854×480 panel**, natively 480×854 portrait. The keys and
  the strip are windows onto it.
- **The SoC is an ArtInChip D13x (RISC-V)** running RT-Thread / Luban-Lite, with 16 MB of SPI NOR
  flash.

## Setup

Requirements: Python 3 with Pillow and NumPy. No hidapi needed; the driver talks to `/dev/hidraw*`
directly.

Give your user access to the device, then replug it:

```sh
sudo cp 70-mirabox-streamdock.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

## Usage

```sh
# Figure-8 scroller: the image is 2x the deck's height, 10 s per loop, runs until Ctrl+C
python3 tools/fig8.py deckbg.png --height 2 --period 10

# Set the boot picture (854x480; "contain" letterboxes, "cover" crops)
python3 tools/set_boot.py deckbg.png --fit contain

# Show each key's hardware index and log presses
python3 tools/keymap_test.py
```

From Python:

```python
from PIL import Image
from streamdock import StreamDock

with StreamDock() as dock:          # finds the device, sends init, starts the keep-alive
    dock.set_key_image(13, Image.open("icon.png"))   # top-left key
    dock.refresh()
    while True:
        ev = dock.read_event(1.0)   # (index, pressed) or None
        if ev:
            print(ev)
```

For the right-hand strip, use `encode_jpeg()` + `set_key_jpeg()` with the slice sizes from
`panel.py`. `set_key_image()` forces slots 16–18 to 80×80.

## Files

| File | Purpose |
|---|---|
| `streamdock.py` | Driver: device discovery, init, keep-alive, key images, boot picture, input events |
| `panel.py` | Measured position of every key and strip slice in a shared pixel layout |
| `tools/fig8.py` | Figure-8 scroller (`--height`/`--zoom` for image size, `--period` for speed) |
| `tools/set_boot.py` | Upload a persistent boot picture (LOG command) |
| `tools/keymap_test.py` | Number every screen and log key presses |
| `tools/layout_test.py` | Labelled stripes across the whole layout, for checking `panel.py` |
| `tools/strip_split_test.py` | Fill the strip with three labelled slices |
| `tools/strip_test.py`, `tools/strip_columns.py` | Oversized single-slot strip probes (see the warning below) |
| `tools/listen.py` | Dump raw input reports |
| `70-mirabox-streamdock.rules` | udev rule for non-root access |
| `calib_grid.png` | Coordinate grid used to measure the layout as a boot picture |

## Protocol

These are the parts we use, confirmed on the device. They come from the vendor SDK's
`libtransport.so`, the open-source [mirajazz](https://github.com/4ndv/mirajazz) crate, and
analysis of the firmware.

**Framing.** Every write to the vendor interface (usage page `0xFFA0`) is 1025 bytes: a `0x00`
report ID, then 1024 payload bytes, zero-padded. Commands start with `CRT\0\0` followed by
the command name.

| Command | Payload | Effect |
|---|---|---|
| `DIS` | — | Wake the display and end the boot splash |
| `LIG` | `[10]` = 0–100 | Brightness |
| `CLE` | `[11]` = key index, or `0xFF` for all | Clear |
| `STP` | — | Commit/refresh |
| `CONNECT` | — | Keep-alive; the driver sends it every 10 s |
| `HAN` | — | Sleep (backlight off) |
| `BAT` | `[8..11]` JPEG length (BE32), `[12]` key index | Key image header; the JPEG follows in 1024-byte chunks |
| `LOG` | `[8..11]` JPEG length (BE32), `[12]` = `0x01` | Boot picture, written to flash; the JPEG follows in 1024-byte chunks |

**Init sequence.** `DIS`, `LIG 100`, `CLE 0xFF`, `STP`.

**Images.** Baseline JPEGs, rotated 90° counter-clockwise before encoding. Keys are 96×96; the
boot picture is 854×480.

**Input.** 512-byte reports starting with `ACK`. `[9]` is the key index and `[10]` is `1` for a
press, `0` for a release.

**Gotchas we hit:**

- **Large images only partly decode.** The firmware's decode buffer for one key image is small.
  A single 80×440 image in slot 16 draws only partly, and oversized images can leave the deck
  unresponsive until you replug it. The strip is therefore driven as three slices: 80×152,
  80×152 and 80×120 in slots 16, 17 and 18.
- **Use multiples of 8.** Image dimensions that aren't multiples of 8 decode with garbage along
  one edge.
- **Never put bytes after the index in a `BAT` header.** It hung the deck's command handling.
- **Key images hide the boot picture.** As soon as any key image is set, the boot picture is no
  longer visible anywhere, including the gaps in the strip.
- **Don't write the boot picture in a loop.** `LOG` writes to flash, so frequent writes wear it
  out. Key images are RAM-only and can be animated freely.

## Firmware notes

- **Availability:** the official firmware images are on the vendor CDN
  (`https://cdn1.key123.vip/StreamDock/firmware/download/V3.HSV293S.02.009.img`). They are
  ArtInChip `AIC.FW` packages.
- **Partitions:** `spl`, `env`, `os` (FIT image, CRC32 + MD5, unsigned), `rodata` (FAT12) and
  `data` (littlefs v2, 5 MB, about 4.4 MB free).
- **Boot picture:** stored as `/data/logo_jpg_dir/test_logo.jpg` and shown for about 2 s. The
  firmware has no multi-frame or animation support.
- **Boot animation idea:** a 3-second figure-8 boot animation would need a small OS patch that
  loops over frame files in the data partition.
- **Status:** not attempted yet. The recovery path is still unknown: the ArtInChip boot-ROM USB
  upgrade mode, and which pin or button triggers it on this board. So a bad OS image could brick
  the device.
