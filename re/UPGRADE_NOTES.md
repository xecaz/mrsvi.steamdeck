# 293S V3 (6603:1014, V3.HSV293S.02.009): how it gets into upgrade mode, and how to recover

## Verified on hardware (2026-10-03)

Test A from the end of this file was run once:
1. Baseline: `6603:1014`, feature report 1 = `V3.HSV293S.02.009`.
2. Sent one hidraw write: `00 'CRT' 00 00 'APPNEW'`, zero-padded to 1025 bytes.
3. At t+2 s the deck was `33c3:6677 Artinchip / "Artinchip Device"`, bcdDevice 1.01, no serial,
   interface class 0xFF, bulk EP 0x81 IN and 0x02 OUT (512 B). The screen went black. It stayed
   that way, unchanged, for the 20 s it was observed.
4. Unplug and replug: back as `6603:1014`, firmware `V3.HSV293S.02.009`, custom boot logo intact,
   commands accepted.

### GET_HWINFO in upgrade mode (2026-10-03)

Ran artinchip-flash (github.com/boa-w/artinchip-flash @ f382c57). It was built with
`serialport = { default-features = false }` because libudev-dev is not installed. Command:
`artinchip-flash info`. Only read queries were sent. The udev rule for 33c3:6677 is in
`70-mirabox-streamdock.rules`.

- GET_HWINFO returned CSW status 0 and a 108-byte payload:
  ```
  48 57 49 4e 46 4f 00 00  "HWINFO"
  32 30 32 33 2d 30 37 2d 31 39 20 30 38 3a 35 34 3a 31 31  "2023-07-19 08:54:11" (BROM build)
  13 00 ... 00
  @44: 42 50 d2 78 26 12 02 05 a2 0b 32 7e 04 00 70 04   chip ID
  @64: 36 00 00 00 07 00 00 00 03 00 03 16 ...           unknown
  ```
- The first 6 chip-ID bytes, `4250D2782612`, are the deck's USB serial number in normal mode.
- artinchip-flash's HwInfo parser assumes a different layout. It prints the date bytes as
  "Init mode / Current mode / Boot stage", and those values are meaningless.
- GET_STORAGE_MEDIA returned CSW status 1 (rejected). This is expected in the BROM stage, before
  the updater SPL is loaded.
- After a replug the deck was back as 6603:1014, V3.HSV293S.02.009, with the logo intact.

### Data-partition-only flash of the stock image (2026-10-03)

artinchip-flash was patched with `re/artinchip-flash-parts.patch` (applies to f382c57). The
patch adds `burn --parts <list>` and `burn --plan-only`. Upstream's CLI always writes
spl,env,os. Only selected target components are transferred (device.rs: the target loop
filters `c.selected`).

```
artinchip-flash burn --plan-only --parts data fw/V3.HSV293S.02.009.img   # check the plan offline
# send CRT APP, wait for 33c3:6677, then:
artinchip-flash burn --parts data fw/V3.HSV293S.02.009.img
```

Result:
- updater.psram and updater.spl went to RAM, CRC OK.
- The device re-enumerated as the updater (still 33c3:6677).
- The tool logged "Setting upgrade mode to FULL_DISK_UPGRADE". Despite the name, only the
  components sent were written.
- image.info (CRC 0x9c97cd3b), then image.target.data, 5 MB at offset 0x1ba800, CRC OK
  0xd87b78bd.
- SET_UPG_END, then an automatic reset.
- About 1 s later the deck was back as 6603:1014, V3.HSV293S.02.009. It booted with the stock
  logo, because the data partition was replaced. That shows spl and os were untouched and
  working.
- The custom logo was re-uploaded with LOG afterwards.

This proves the full Linux flashing path end to end, and that a data-only flash is safe and
self-resetting. Writing a modified data partition (e.g. extra frame files) works the same way:
build a littlefs image of the same geometry (4 KB blocks, 1280 blocks) and put it into an
.img with recomputed CRCs.

Everything below is the static analysis that predicted this. No USB or HID device was touched
during it.
Each claim is tagged [V] (verified in code or data) or [I] (inferred).

Working files (decompiles and binaries are in ../fw/upg/, which is gitignored; scripts are in re/):
- UpDateToolV3.c, FirmwareUpgradeTool.c, upgcmdHid.c: Ghidra decompiles of the Windows tools.
- pbp_target.bin / pbp.s / pbp.c: the Pre-Boot Program. This is stage 1 of image.target.spl, file 0..0x7010, PIC.
- spl_main.bin / spl.s / spl.c: the SPL proper. This is image.target.spl from file offset 0x7200, loaded at 0x406c0000.
- rvdis.py: a capstone RV32IC linear disassembler that annotates auipc/lui address math and strings.
- gscripts/SeedDump.java: seeds functions from jal targets, then decompiles everything.

## 1. Host side: the bytes that switch a running deck into upgrade mode

FirmwareUpgradeTool.exe FUN_14002c440 [V]:
- `hid_open(vid,pid)`, then builds a 0x201-byte buffer, all zeros, and calls `hid_write(h, buf, 0x201)`. This is an OUTPUT report sent over the interrupt OUT pipe. It is not a feature report.
- `buf[0]` = report ID = 0x00. It is 0x04 only when VID:PID is 1200:2000.
- `buf[1..]` = "CRT" 00 00 "APPNEW", zero-padded.

UpDateToolV3.exe FUN_140011510, "TryToBootloader" [V]:
- Same idea. Disassembly 0x14001177e:
  `mov dword [rbp-0x50],0x54524304 ; mov dword [rbp-0x4a],0x4e505041 ; mov word [rbp-0x46],0x5745`
  This gives `04 'C' 'R' 'T' 00 00 'A' 'P' 'P' 'N' 'E' 'W'`.
- On Windows 8+ (`QSysInfo::windowsVersion() > 0x90`) the tool HARD-CODES report ID 0x04. This is meant for the "Duo" keyboards. On Windows 7 or older, the buffer starts with "CRT" directly.
- Length is 0x201. Windows hidapi pads to OutputReportByteLength, so the log shows "write res: 1025". That matches UPDLog.txt ("write res: 1025CommandKind: 1IsDuoDev: 1").
- No handshake comes before it. The only earlier step is hid_open.

SDLibrary1.dll and StreamDock.exe have no bootloader command (PDB symbols and strings checked) [V].

For 6603:1014 on Linux hidraw, the equivalent write is [I]:

    00 43 52 54 00 00 41 50 50 4E 45 57 00 ... (1025 bytes total)

That is report ID 0, then "CRT\0\0APPNEW", padded with zeros to 1024 bytes. It is identical in form to normal CRT commands.

The firmware only checks report[0..2]="CRT" and report[5..7]="APP". "NEW" and the rest are ignored.

## 2. Device side: what the os does with it

1. CRT dispatcher FUN_ram_40033272: `report[5..7]=="APP"` sets `DAT_ram_400a41fa = 1` [V].
   - re/NOTES.md calls this an "app handshake / firmware version print". **That is wrong: APP reboots the deck into upgrade mode.** Never send it casually.
   - No host library in scratchpad (mirajazz, opendeck, the SDK) sends APP [V].
2. Main thread FUN_ram_4003289c polls the flag every 1000 ms [V]:
   - It builds the string `"aicupg \n"` on the stack (lui/addi 0x75636961, 0x0a206770).
   - It calls FUN_ram_4003298e (backlight off), then `msh_exec(buf, strlen(buf))` (FUN_ram_4002082c = RT-Thread msh_exec).
3. The msh command table entry at 0x4007804c is `{ "aicupg", "Reboot to the upgrade mode", 0x4003878e }` [V].
4. cmd_aicupg FUN_ram_4003878e [V]:
   - `aicupg gotobl` sets reason 5.
   - `aicupg hid` sets reason 6.
   - Anything else, including our "aicupg" with argument "\n", sets reason 4.
   - It then calls FUN_ram_40024db2: print "Restarting system", wait 100 ms, set reason 1 (ignored because one is already set), watchdog reset.
5. set_reboot_reason FUN_ram_4004079a [V]:
   - If `RTC[0x19030100] & 0xF0 == 0`, it writes `(reason<<4)|old` to RTC SYS_BAK at 0x19030100.
   - It unlocks with 0xAC at 0x190300FC, then relocks.
   - **This is an RTC register. It is not flash or env.** No flash write happens anywhere on this path.
6. After the reset, the PBP (stage 1 of the SPL image in NOR), FUN_00004416(boot_dev, priv) [V]:
   - If `boot_dev==7` (USB/UART), it returns.
   - sw check FUN_17de: `(RTC[0x19030100]>>4)==4`. If true, it clears the high nibble (one-shot), prints "Enter upgrade mode by software", and calls FUN_42e8.
   - hw check FUN_11fa, with config from PBP private data type 4. If true, it prints "Enter upgrade mode by hardware PIN" and calls FUN_42e8. See section 4.
   - FUN_42e8 saves the registers and calls `(*(*[0x4f80]) + 0xA4)()`, which is a function pointer in the Boot ROM API table.
   - [I] This is the BROM's USB/UART upgrade loop. Supporting evidence:
     - The vendor flow then pushes image.updater.psram (ram 0x30044000, "run") and image.updater.spl (ram 0x40100000, "run") first. Only a BROM-stage target needs those.
     - upgcmd prints "Boot stage: Boot ROM / U-Boot", and its "continue" is described as "Boot ROM exit USB loop and try to boot again".
7. USB ID afterwards:
   - [I] BROM: 33C3:6677. ArtInChip standard. Windows needs a driver, which is why UpDateToolV3 installs the libusbK "Artinchip_SoC.inf" first.
   - [V] The updater SPL that the BROM then runs (identical file to image.target.spl) sees boot_dev 7. FUN_406cf134 then selects mode 1 if a USB host is attached within 500 ms, so it runs "aicupg usb 0". That re-enumerates with this descriptor (from spl_main @0x406e78bc):
     `12 01 00 02 00 00 00 40 C3 33 77 66 ...` = 33C3:6677, interface class FF/FF/FF, bulk EP 0x81 IN / 0x02 OUT, 512 B.
   - [V] The SPL also has an HID upgrade gadget, 33C3:8899 (HID class, interrupt EP 0x83/0x04, 1024 B, report descriptor 0x22 bytes). It is used only for "aicupg hid 0", i.e. reboot reason 6 (`aicupg hid` in the os shell). The APP path does not use it.

## 3. Leaving upgrade mode without flashing; does anything persist?

- The only state written is the RTC SYS_BAK nibble [V]. The PBP clears it before calling the BROM. The SPL (FUN_406e2fd8) also shifts it out.
- Nothing is written to NOR until the updater SPL receives image.target.* FWCs [V for os/PBP/SPL code paths; I for BROM internals].
- So a plain unplug/replug (power loss) should go to a normal flash boot [I]. Even a warm reset finds no flag.
- How the vendor tool exits [V]:
  - Flash: `upgcmdHid.exe image <dev.img>`, retried up to 10 times while it returns -3.
  - Then optionally `upgcmdHid.exe shcmd reset`. That is UPG CMD_RUN_SHELL_STR(0x05) "reset", and it is handled by the updater SPL.
  - `upgcmd continue` exists for the BROM stage.
- env partition (image.target.env) [V]: MTD layout, osAB_*=A, rodataAB/dataAB=A, upgrade_available=0, bootlimit=5, bootcount=0, partname vars. It has no upgrade_mode-type variable. The APP path never touches env.
- bootcount/upgrade_available only matter for A/B OTA. There is no os_r MTD partition here; the SPL falls back to "os" ("Aic get os fail, startup from os default").

## 4. Recovery when the os is broken (no board access)

### Hardware upgrade pin [V]

PBP private data type 4, identical in the PBP and SPL copies, and also the code default:

    {cfg_reg=0x18700080 (PA0 PIN_CFG), cfg_val=0x00010321, in_reg=0x18700000 (GPIOA input), mask=0x1, expected=0, delay=500}

So: **PA0, active LOW.**
- [I] cfg 0x10321 = GPIO function 1, input enable, pull-up.
- When it is sampled: on every flash boot (cold, warm or watchdog), at the very start of the PBP. The PBP waits ~500 (udelay), reads 4 times, and all 4 must read 0.
- The os pinmux table (0x400a01d0) has PA.0 = func 5 and PA.1 = func 5 pull-up. [I] That is UART0 TX/RX, so the PBP's UART config (type 2, PA0/PA1 = 0x335) matches.
- The upgrade pin is therefore the UART0 TX pad. It is internal, so the case must be opened.

### Key matrix (os, KEYBOARD_SCAN, FUN_ram_40031d60/40031e06/40031ea8) [V]

- Drive lines: PC.0, PB.2, PB.1 (output, driven low one at a time).
- Sense lines: PC.5, PC.4, PC.3, PC.2, PC.1 (inputs).
- That is 3x5 = 15 keys.
- **PA0 is not a key line.** Neither the PBP nor the SPL reads PB or PC, so holding a key while plugging in does nothing for upgrade mode.

### Other ways into upgrade mode (SPL FUN_406cf134/406cf262, main FUN_406cdf94) [V]

- Reboot reasons 5/6 (set only by a running os) give USB/UART or HID upgrade.
- Boot device 7 (BROM USB/UART) gives "aicupg usb 0" / "aicupg uart 0".
- Otherwise the SPL brings up the USB host controller at 0x10210000 and looks for a U-disk. If one is found it runs "aicupg fat udisk 0".
  - [I] That port is unlikely to be wired as host on this deck, so it is not usable.
- Ctrl-C on the UART console gives the tinySPL shell. That needs UART.

### Corrupt os [V]

- nor_boot (FUN_406cf756) verifies the FIT CRC32 ("APP crc32 error: expect/got") and returns -1 on failure.
- Main loop: `while(1){ while(console_loop()!=-2); console_run_cmd("aicupg usb 0"); }`.
- console_loop re-runs the bootcmd "nor_boot" and only drops to "aicupg usb 0" when the bootcmd returns -2 (CONSOLE_QUIT). Every failure path in nor_boot/spl_load_image returns -1 or a positive value, never -2.
- **So an os that fails its CRC leaves the SPL retrying nor_boot forever on the UART console. It does NOT enumerate on USB.**
- An os that passes CRC but crashes, or breaks the HID/APP path, also gives no USB.
- Recovery then needs PA0 to GND at power-on, or UART. Both need the case open.

### Corrupt SPL stage 2 (PBP intact)

PBP prints "SPL head verify failed / Load SPL image failed", then "PBP return", and returns to the BROM.

### BROM fallback when nothing valid is in NOR

- This is BROM code, which we do not have. It cannot be settled offline.
- [I] ArtInChip BROMs fall back to USB upgrade (33C3:6677) when no bootable image is found. I could not confirm this from docs (web search found nothing D13x-specific).
- If true, a fully corrupted SPL header (offset 0 of NOR) would paradoxically be recoverable over USB. **A corrupted os would not.**

## 5. What upgcmdHid.exe sends, and whether Linux can do the same

upgcmdHid.exe is an ArtInChip upgcmd build on libusb (with a Windows HID backend) [V]:
- upg_usb_dev_open FUN_0040e3xx: opens 33C3:6677, else 33C3:8899. It checks bInterfaceClass:
  - Class 3 (HID): transfers are 1024-byte interrupt chunks (libusb_interrupt_transfer, expects 0x401 including report ID). PID is tagged as 8899.
  - Otherwise: libusb_bulk_transfer on EP 0x02/0x81.
- The protocol is the same in both cases: CBW/CSW-framed AICUPG commands.

Command sequence, from the strings, the log and the artinchip-flash mirror [V/I]:
1. GET_HWINFO(0x00).
2. For the BROM stage, for each image.updater.*:
   - SET_FWC_META(0x10), GET_BLOCK_SIZE(0x11)
   - SEND_FWC_DATA(0x12) start/update/final
   - GET_FWC_CRC(0x13), GET_FWC_RUN_RESULT(0x15). The psram one is run, then the spl one is run.
3. The device re-enumerates as the updater SPL (6677 bulk).
4. SET_UPG_CFG(0x0A, mode). Then for image.info and each image.target.* (spl, env, os, rodata, data):
   - SET_FWC_META, then SEND_FWC_DATA in ≤1 MB blocks
   - GET_FWC_CRC, GET_FWC_BURN_RESULT(0x14)
5. SET_UPG_END(0x0B).
6. Optional RUN_SHELL_STR(0x05) "reset".

Linux:
- artinchip-flash (Rust/rusb) implements the same command set (src/protocol/commands.rs) on 33C3:6677 bulk EP 0x02/0x81. It handles the updater stage and reconnect, has `--no-reset`, and has partition selection.
- It does not implement the HID (8899) transport. The 293S APP path does not need it [V for SPL; I for BROM].
- On Linux no driver is needed, only a udev rule for 33c3:6677. Windows needs WinUSB/libusbK, which is what Artinchip_SoC.inf is.

## Tests that would settle the open points (NOT done; each needs user approval)

### A. Confirm the APP path and the BROM USB ID

- Write the one 1025-byte hidraw output report from section 1. Then watch `lsusb`/dmesg: 6603:1014 should drop and 33C3:6677 should appear within about 1–3 s.
- Then optionally run read-only `artinchip-flash info` (GET_HWINFO). It should show "Boot stage: Boot ROM".
- Then unplug and replug.
- Risk: low. No flash writes on any path we can see. The RTC flag is cleared before the BROM loop.
- Residual unknowns are BROM internals, and whether a replug fully resets on this board. Worst case: a power cycle and the PA0 path.

### B. Confirm a replug returns to normal firmware

After A, replug and check that 6603:1014 enumerates with the same firmware version.

### C. Check the BROM fallback with an empty NOR

Only possible by erasing the SPL. **Do not do this:** it is destructive and only recoverable if the inference holds.
