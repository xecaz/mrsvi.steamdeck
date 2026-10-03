# 293S V3 (V3.HSV293S.02.009) boot-logo / HID / animation notes

Files referenced below (firmware images, extracted parts, os_ram.bin, os_decomp.c, the Ghidra
project gproj/) are in ../fw/, which is gitignored. Scripts are next to this file;
aicimg.py unpacks an AIC.FW .img into its parts.

Caution: the BAT header field meanings below (bytes 13..20 as w/h/x/y) did NOT hold on the
device. Sending them changed nothing visible and then hung the deck's command input.

Static analysis only. os payload loaded at 0x40000000 (FIT seg0 load/entry=0x40000000,
seg1 load=0x4009e400). RAM image: os_ram.bin. Ghidra decomp: os_decomp.c
(RISCV:LE:32, cspec gcc). Disasm helper: disasm_tool.py (resyncs past ArtInChip custom0 ops).

MTD layout (from image.target.env):
  512k(spl),128k(env),128k(env_r),2m(os),6m(rodata),5m(data)
Note: os FIT payload is only 0xa1800 (646 KB) inside a 2 MB MTD partition.

## Threads (created in FUN_ram_400329c2, started from FUN_ram_4003308c = usbd_hid_custom_init)
  USB_ICON_DISPLAY  entry 0x40032fc0
  BOOT_IMAGE_READ   entry FUN_ram_400327a0   (shows the splash)
  BOOT_IMAGE_WRITE  entry FUN_ram_4003262c   (persists test_logo.jpg from "LOG")
  KEYBOARD_SCAN     entry FUN_ram_400321bc
  USB DATA RECEIVE  entry FUN_ram_40032af0   (HID OUT reader + CRT parser driver)

## Boot-logo display path
FUN_ram_40032700(stack): open "/data/logo_jpg_dir/test_logo.jpg" (FUN_ram_40014712,flags=2),
  stat (40014944) -> read whole file into _DAT_ram_400a41f4 (CMA buf, 0x80020 bytes),
  decode+blit via thunk_FUN_ram_4006bec4(buf,size, x=0,y=0, w=0x1e0=480, h=0x356=854, layer=1).
FUN_ram_4006bec4 = MPP "decode_pic": checks FF D8 (JPEG->codec 0x1002) / "PNG" (0x1001);
  HW decoder via MPP (packages/artinchip/mpp). Frame rendered to DE layer (0x4662 get screen
  info, FUN_ram_400575ac put_frame). Framebuffer is 480x854 portrait (native).
Timing (FUN_ram_40011e5a = ms delay): loop shows logo, backlight on (pwm ch2, FUN_ram_40032926),
  mdelay(500), backlight off. DAT_ram_400a41f8 is preset=1 at init, so first pass falls through
  to mdelay(0x5dc=1500) then cleanup FUN_ram_4002b5da. ~2 s total.
Ends when DAT_ram_4009f3b8 != 0, set by host "DIS" command (FUN_ram_40033272). So the HOST
  connecting and issuing DIS ends the splash; otherwise it self-terminates after the 1.5 s branch.
1.jpg/2.jpg/4-9.jpg/213.jpg: NOT referenced anywhere in os (grep). They are host-side key
  default images shipped in the FS. test_logo.jpg == 2.jpg (md5), 6.jpg==213.jpg.
No GIF/multi-frame/animation feature exists.

## HID CRT dispatcher = FUN_ram_40033272(char* report). Header "CRT\0\0", opcode at report[5..].
  Compare is literal bytes, no table. Commands found (this firmware):
  CLE  report[5..7]="CLE": clear; FUN_ram_40031a28(report[0xb]); if report[0xb]=='C' also
       release boot_logo sem (re-show) + flags. (region/color select by report[0xb])
  CONNECT report[5..11]="CONNECT": set DAT_ram_400a41e4=1 (host-present flag)
  STP  "STP": stop/commit host-draw, DE ioctl 0x4643 (FUN_ram_40031d38)
  DRA  "DRA": state=3; expects a framed payload, 24-bit len at report[9..0xb]
  DIS  "DIS": enter display mode; clear screen (40031a28(0xff)), backlight on, f3b8=1
  LOG  "LOG": state=4 -> rewrites /data/logo_jpg_dir/test_logo.jpg (BOOT_IMAGE_WRITE)
  LIG  "LIG": backlight level = report[10] (DAT_ram_4009f3b0); pwm ch2 duty = level*2000
  BAT  "BAT": state=5 -> key/icon image upload (see below)
  KEY  "KEY": copies 8 bytes report[1..8], FUN_ram_4002a414(0x81,...) (key event inject)
  HAN  "HAN": backlight off (4003298e), f3b4=0
  APP  "APP": DAT_ram_400a41fa=1 -> main thread runs "aicupg" = REBOOT INTO USB UPGRADE MODE
       (corrected; see UPGRADE_NOTES.md). Never send it casually.
  No BGPIC / BGCLE / BGCLE / COLOR / CPOS / LLUM / LMOD / SETLB / DELED / QUCMD / MOD / M_V
  in THIS firmware. Those strings live only in the host SDLibrary1.dll; the device ignores them.

## BAT / key-image upload + placement (recv thread FUN_ram_40032af0 tail, disasm 0x40032c80..0x40033084)
  State 5 accumulates 1024-byte HID chunks into _DAT_ram_400a41f0 (buf, 0x80020 cap).
  Completion = last byte of chunk == 0xD9 (JPEG EOI) [code @0x40032d88..0x40032d92].
  On completion the 0x20-byte header is parsed [code @0x40032f22..0x40032fba]:
    report[9..0xb]   = 24-bit big-endian JPEG length  -> global +0x10
    report[0xd],[0xe] = LE16 field A -> struct+0x08
    report[0xf],[0x10]= LE16 field B -> struct+0x0c
    report[0x11],[0x12]=LE16 field C -> struct+0x00
    report[0x13],[0x14]=LE16 field D -> struct+0x04
    global struct base = 0x400A418C
  Then jumps to decode thunk with a0=buf+0x20, a1=len-0x20:
    decode_pic(jpeg_at+0x20, len-0x20). Geometry (x,y,w,h) taken from the global struct, so the
    DESTINATION RECTANGLE IS SUPPLIED BY THE HOST, not a firmware per-slot table.
  struct order [+0,+4,+8,+0xc] = [report0x11, report0x13, report0xd, report0xf].
  INFERRED mapping x=+0, y=+4, w=+8, h=+0xc (i.e. w,h at report 0xd/0xf; x,y at 0x11/0x13).
  Blit is 1:1 (no scaling); image anchored at (x,y); clipped to panel 480x854. This matches the
  observed "placement depends on image width / partial strip / black margins" behaviour.

## Free space
  data (littlefs v2, 4 KB blocks, 1280 blocks=5 MB): 145 blocks used = 0.57 MB; 1135 free = 4.43 MB.
  os FIT uses 0xa161c of the 2 MB MTD os partition -> ~1.37 MB unused in the partition.

## Minimal animation hook (concept only; NOT built)
  Option A (no os patch, data only): replace test_logo.jpg with frame 0; cannot loop without
    code change. Not sufficient alone.
  Option B (os patch): in FUN_ram_40032700 the path pointer is
    s__data_logo_jpg_dir_test_logo_jpg (0x4007fbb4). Patch BOOT_IMAGE_READ (FUN_ram_400327a0 /
    FUN_ram_40032700) to iterate "/data/logo_jpg_dir/fNN.jpg": build the name in a stack buffer
    (sprintf-style via existing FUN_ram_40001b7e-type helper or manual 2-digit write), call
    FUN_ram_40032700 for each N=0..74 with a short FUN_ram_40011e5a(40) between frames (3 s /75).
    The display primitive and buffer are already in place; only the filename source and the loop
    counter/delay change. The spare 1.37 MB in the os partition and 4.43 MB in data are ample.
  Patching os requires recomputing: seg0 crc32+md5 and seg1 crc32+md5 in the FIT (offsets of the
    hash nodes), then the image.target.os per-entry CRC32 in the AIC.FW metadata (0x800 table).

## Flashing (AICUPG over HID)
  UpDateToolV3.exe exposes "Select partition and flash" with rodata/data/os entries; upgcmdHid.exe
  burns per-FWC with per-component CRC verification ("get fwc crc failed expect/got", "FWC burn
  result OK"). image.info marks env/rodata/data as "optional", spl/os as "required".
  => The data partition can be reflashed alone without touching spl/os. A patched os would need the
  FIT hashes + AIC.FW entry CRC fixed or it is rejected at burn ("FWC CRC is OK" gate). No signature
  node in the FIT (crc32/md5 only) so no cryptographic signing blocks a rebuild.
