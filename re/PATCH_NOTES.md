# os boot-animation patch: findings so far

Status: stopped after step 1 (code cave). No patched image was built and no device was touched.
The data side is done: the animation frames (logo_jpg_dir/f00.jpg..f74.jpg) are already on the
device's data partition (see UPGRADE_NOTES.md). What remains is the OS change that plays them.

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
