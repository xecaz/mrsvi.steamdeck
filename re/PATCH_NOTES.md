# os boot-animation patch

Status (2026-10-03): **done and working on hardware.** [V] The patched os
(`fw/out/V3.HSV293S.02.009-bootanim-os.img`, built by `tools/patch_os.py`) was flashed with
`--parts os`. The deck plays the 75 figure-8 frames from the data partition at power-on, then
shows the static logo, and still enumerates as 6603:1014 with HID working. Steps 1-3 below record
how it got there. `fw/patch/PATCH_NOTES.md` is an older, stale copy of this file.

Summary of the result:
- The data partition holds the frames `logo_jpg_dir/f00.jpg..f74.jpg` plus `test_logo.jpg`
  (`tools/build_boot_anim.py`, flashed earlier, see UPGRADE_NOTES.md).
- The os patch changes 697 bytes of the .img: three edits in seg0, the FIT crc32/md5 and the
  META crc. It needs no signature: FIT and META only use crc32/md5. [V]
- Rebuilding from the stock 02.009 .img with `patch_os.py` reproduces the flashed image
  byte for byte (rechecked 2026-10-03). [V]
- Per-frame time = HW JPEG decode of one 854x480 frame + `DELAY_MS` (20 ms in the flashed image,
  `li a0,0x14` before the mdelay call). [V] Total animation length on the device was not measured.
- USB comes up only after the splash's boot pass. That is now the animation plus the stock
  mdelay(1500), so enumeration is later than with the stock os by roughly the animation length. [I]
- `NFRAMES` in patch_os.py (75) must equal build_boot_anim.py's `--fig8 + --zoom` (60 + 15). The
  frame number is two ASCII digits, so 100 frames is the upper limit. If frames are missing,
  show() fails and returns, and the loop moves on. [I, from the code; not tested on the device]

### Rollback [I, same procedure as the verified flashes]
Send `CRT APP`, wait for 33c3:6677, then `burn --parts os fw/V3.HSV293S.02.009.img`. Add
`--parts data` with the same image to restore the stock logo and remove the frames. This works only
while the patched os still enumerates and answers APP, which it does (verified).

## Verified facts so far
- FUN_ram_4002b5da registers the HID report descriptors and then runs the USB controller init (FUN_ram_4002a114).
  Its only caller is the splash thread at 0x40032828. USB only comes up after the splash's boot pass.
- The boot_logo semaphore (0x400a41d8) is created with a count of 0. It is released by init-table entry FUN_ram_40032570
  (table slot 0x40078244), by CLE 'C', and after a LOG write.
- DAT_ram_4009f3b8 starts at -1 (initialized data). So on the boot pass the thread goes show -> mdelay(1500) -> USB init.
- FUN_ram_40032700 returns a value < 0 on open failure and on decode_pic failure.

## More verified facts (second session)
- The backlight comes on at boot from the st7701s panel enable path (0x40036546 -> 0x40035a68). It sets pwm ch2 to
  period 1,000,000 and pulse 800,000 (80%), then enables it, after mdelay(150). No splash code is involved.
- WDT: the hardware enable (FUN_ram_4004062a with a0 != 0) is reachable only from the wdt device control op
  (0x400385e0, ops table at 0x4009f8b8). The only rt_device_find("wdt") call is the reboot routine 0x40024db2.
  In the SPL the WDT is enabled only on its reboot paths.
- The CMA buffer _DAT_ram_400a41f4 is shared. The recv thread memcpy's completed LOG data into it (0x40032cc6) and
  completed BAT data into it (0x40032df0). The ICON thread then decodes BAT from it (0x40032f26).
- The screen-info cache 0x400a8190 is filled lazily inside each decode function. Nothing depends on the boot decode.

## Code cave candidates checked before step 1
- The xref scan (re/rvxref.py) flags 0x40038652 as "unreferenced", but it sits right after the wdt control op,
  which dispatches through a relative jump table (0x4008126c). The scanner cannot see such tables, so any cave
  candidate must also be checked against relative jump tables.
  Unverified candidates (newlib-like): 0x4000b274, 0x4000b682, 0x4000b788, 0x4000c032, 0x40000bf4, 0x4005efb2.

## Step 1: code cave chosen and proven
Cave: body of msh command `test_clock` ("Test CMU CLK"), 0x40026dc8..0x40027068 (672 bytes, exclusive).
- Entry 0x40026dc8 is referenced only by its msh table entry (data word at 0x40077fd0). rvxref, full body
  range: no flow/addr/data references from outside the body except to 0x40027068, which is a separate
  DMA-test callback (`auipc a0,..; "DMA complete, callback"; j ...`), used by test_dma_*. Excluded from the cave.
- Brute-force relative-offset scan (every 2-aligned 32-bit word w at T with T+w in body, even targets):
  only the 19-entry table at 0x4007dd6c..0x4007ddb4. That table is referenced only by test_clock itself
  (auipc/addi at 0x40026e22 -> 0x4007dd6c), so it's an internal switch table. Odd-target hits are noise.
- rvdis: the body ends with `c.j` at 0x40027066; the callback starts at 0x40027068.
- Side effect: typing `test_clock` on the UART console would run the patch code. That's unreachable with
  the case closed. Optional hardening: repoint that msh entry's func word (entry at 0x40077fc8, func word
  at 0x40077fd0) to `version` (0x40020c18).

## Step 2: patch built and checked offline (no device touched)
`tools/patch_os.py fw/V3.HSV293S.02.009.img fw/out/V3.HSV293S.02.009-bootanim-os.img`
(pure-Python RV32 encoder, no toolchain needed; capstone only for the printed listing)
Changes in os seg0:
1. FUN_40032700 @0x40032704..0f: `c.mv s2,a0; c.mv a0,a1; c.li a1,2; 3x c.nop` (path now comes in a1
   instead of the auipc/addi of the fixed string). Its only caller is the jal at 0x400327f2.
2. That jal now goes to `anim` at 0x40026dc8 (240 bytes incl. a 28-byte path template, cave limit 672).
   If DAT_4009f3b8 == -1 (boot pass): copy "/data/logo_jpg_dir/f00.jpg" to the stack, loop 00..74 calling
   show(stat, stackpath) + mdelay(DELAY_MS; 10 in this offline run, 20 in the flashed build). Then, always, tail-call show(stat, 0x4007fbb4) = the stock path.
   So the last thing on screen is still test_logo.jpg, and later calls (CLE 'C', after LOG) are unchanged.
   Path lives on the stack: no writes to rodata/text.
3. msh `test_clock` func word 0x40077fd0 -> `version` (0x40020c18).
Then seg0 crc32+md5 in the FIT header and the os META crc (img 0x1290) recomputed.
Output differs from stock in 697 bytes (os partition + that one META crc).
Verification: unicorn run of the cave with show/mdelay hooked: flag=-1 -> f00..f74 each followed by
d10 (the delay at that time), then 0x4007fbb4; flag=0 -> only 0x4007fbb4. sp balanced, a0 preserved. FIT/META crcs re-verified.
Not verified: real timing/tearing (HW decode per frame), PMP/MPU behaviour (none needed: no writes).
If the frame files are missing (stock data partition) show() just returns, so the cost is ~0.75 s of black.

## Flashing plan (needs user go-ahead; this is the only step that can brick)
- data partition on the deck should already hold f00..f74 (fw/out/...-anim.img, flashed earlier). Re-flash it
  if the deck was later returned to stock data.
- `artinchip-flash burn --plan-only --parts os fw/out/V3.HSV293S.02.009-bootanim-os.img`, then CRT APP, then
  `burn --parts os ...`. Rollback with the stock .img, `--parts os`, if the deck still enumerates.
- Failure mode: os that passes CRC but crashes before USB init gives no USB; recovery = open case, PA0 low.

## Step 3: flashed on hardware (2026-10-03) - WORKS
`burn --parts os fw/out/V3.HSV293S.02.009-bootanim-os.img` after CRT APP: "Burn completed successfully!",
deck re-enumerated as 6603:1014 within ~10 s, hidraw present, and the user confirmed the boot animation plays.
Stock rollback image: fw/V3.HSV293S.02.009.img with `--parts os` (and `--parts data` for the stock logo).
