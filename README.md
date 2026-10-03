# MRSVI / Mirabox Stream Dock 293S V3 on Linux

Reverse-engineering and driving a MRSVI-branded stream deck from Linux without the vendor
software. The hardware is a Mirabox **Stream Dock 293S V3** (USB `6603:1014`, reports as
`HOTSPOTEKUSB HID DEMO`, firmware `V3.HSV293S.02.009`), also sold under other names.

What works:

- Key images on all 15 keys, plus the tall display strip on the right
- Key press and release events
- Brightness, clear and sleep
- A persistent custom boot picture
- A boot animation: 75 frames played at power-on, using a small patch to the deck's OS
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
| `tools/build_boot_anim.py` | Build a data partition with boot-animation frames and pack it into a flashable `.img` (needs `littlefs-python`) |
| `tools/patch_os.py` | Patch the stock OS so it plays those frames at boot; writes a flashable `.img` (needs `capstone`) |
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

Analysis notes and helper scripts are in `re/` (`re/NOTES.md`, `re/aicimg.py` to unpack an
`.img`). Local copies of the firmware images, extracted partitions and the Ghidra project live
in `fw/`, which is gitignored because those files belong to the vendor.

- **Availability:** the official firmware images are on the vendor CDN
  (`https://cdn1.key123.vip/StreamDock/firmware/download/V3.HSV293S.02.009.img`). They are
  ArtInChip `AIC.FW` packages.
- **Partitions:** `spl`, `env`, `os` (FIT image, CRC32 + MD5, unsigned), `rodata` (FAT12) and
  `data` (littlefs v2, 5 MB, about 4.4 MB free).
- **Boot picture:** stored as `/data/logo_jpg_dir/test_logo.jpg` and shown for about 2 s. The
  stock firmware has no multi-frame or animation support.
- **Boot animation (working on the device since 2026-10-03):** a patched OS plays
  `f00.jpg`..`f74.jpg` from the data partition, then the normal boot picture. See
  [Boot animation](#boot-animation) below and `re/PATCH_NOTES.md`.

### Upgrade mode and recovery

Details and evidence: `re/UPGRADE_NOTES.md`.

- **Entering upgrade mode (verified on the device):** send `CRT\0\0APPNEW` as a normal 1025-byte
  hidraw write. The firmware runs its `aicupg` shell command, which sets a one-shot reboot flag in
  an RTC register (not flash) and resets.
  - About 2 seconds later the deck re-enumerates as **`33c3:6677` "Artinchip Device"**: the
    D13x boot ROM's USB upgrade mode. It has a vendor-specific interface with bulk endpoints
    `0x81` IN and `0x02` OUT. The screen goes black.
- **Leaving it without flashing (verified):** unplug and replug. The deck boots normally as
  `6603:1014`, firmware `V3.HSV293S.02.009`, with the custom boot picture intact.
- **Flashing (verified for the data partition):** in that mode the deck speaks ArtInChip's
  AICUPG protocol over bulk USB.
  - The Linux tool [artinchip-flash](https://github.com/boa-w/artinchip-flash) works with it,
    using the udev rule in this repo.
  - With `re/artinchip-flash-parts.patch` (adds `burn --parts` and `--plan-only`), the stock
    `data` partition was flashed on its own. The deck reset and booted normally, with the stock
    boot picture.
  - Upstream's CLI always writes `spl,env,os`, so check the plan with `--plan-only` first.
- **Custom data partition (verified):** `tools/build_boot_anim.py` builds a data partition holding
  the logo plus 75 figure-8 animation frames, and packs it into a flashable `.img`. The deck boots
  normally from it. The stock OS ignores the frames; `tools/patch_os.py` makes it play them.
- **Patched OS (verified):** the boot-animation OS was flashed with `--parts os`. The deck
  boots, plays the animation, enumerates as `6603:1014` and still answers `APP`, so it can
  still be reflashed over USB.
- **No key is a recovery button.** The bootloader's hardware upgrade pin is PA0, active low, and on
  this board PA0 is the internal UART0 TX pad. The 15 keys are a matrix on port B/C pins.
- **A broken OS can't be recovered over USB.** If a modified OS fails its CRC check, the
  bootloader retries forever on the serial console and never enters USB upgrade mode. The same
  goes for an OS that boots but crashes or loses the `APP` handler. Either case means opening the
  case to reach PA0 or the UART.
  - Any OS patch must therefore keep the HID `APP` path working. Changing only the `data`
    partition, while keeping the stock OS, is the low-risk option.
- **Never send `APP` casually.** It isn't a handshake: it reboots the deck into upgrade mode.

### Boot animation

The deck can play a short animation at power-on. This needs two flashes: a data partition that
holds the frames, and a patched OS that plays them. **Flashing the OS is the one step that can
brick the deck:** an OS that crashes before USB starts can only be recovered by opening the case
(see above). Use the patch below as-is, and check every changed version offline first.

```sh
# 1. Frames + boot picture -> fw/out/V3.HSV293S.02.009-anim.img (data partition)
python3 tools/build_boot_anim.py fw/V3.HSV293S.02.009.img deckbg.png

# 2. Patched OS -> fw/out/V3.HSV293S.02.009-bootanim-os.img (os partition)
python3 tools/patch_os.py fw/V3.HSV293S.02.009.img fw/out/V3.HSV293S.02.009-bootanim-os.img

# 3. For each image: send CRT APP (upgrade mode, 33c3:6677), check the plan, then flash
artinchip-flash burn --plan-only --parts data fw/out/V3.HSV293S.02.009-anim.img
artinchip-flash burn --parts data fw/out/V3.HSV293S.02.009-anim.img
artinchip-flash burn --plan-only --parts os fw/out/V3.HSV293S.02.009-bootanim-os.img
artinchip-flash burn --parts os fw/out/V3.HSV293S.02.009-bootanim-os.img
```

After each flash, the deck resets itself and comes back as `6603:1014` in about 10 s.

What the patch does, all inside the OS's first code segment (details in `re/PATCH_NOTES.md`):

1. The function that shows the boot logo (`0x40032700`) now takes the file path as an argument,
   instead of using a fixed string.
2. The splash thread's call to it (`0x400327f2`) is redirected into a code cave: the body of the
   unused `test_clock` console test command (`0x40026dc8`, 672 bytes). On the first pass after
   power-on, the cave shows `f00`..`f74` with a 20 ms delay between frames, then shows
   `test_logo.jpg` as before. Later calls (`CLE`, after `LOG`) behave exactly like the stock OS.
3. The `test_clock` console command now points at `version`, so the cave can't be run by name.

The script then recomputes the FIT crc32/md5 and the package's META crc, since the firmware has no
signatures. It asserts that the stock bytes are what it expects before writing anything, and
prints a disassembly of the result for review.

Knobs: `DELAY_MS` and `NFRAMES` in `patch_os.py`. `NFRAMES` has to match the frame count from
`build_boot_anim.py` (`--fig8` + `--zoom`, 60 + 15 by default), and can be at most 100. USB
starts only after the animation, so a longer animation delays enumeration by the same amount.

**Rollback:** flash the stock `fw/V3.HSV293S.02.009.img` with `--parts os`. Add `--parts data`
too to restore the stock logo.

`artinchip-flash` is [boa-w/artinchip-flash](https://github.com/boa-w/artinchip-flash) at
`f382c57` plus `re/artinchip-flash-parts.patch`. Build it with the `serialport` crate's default
features turned off.
