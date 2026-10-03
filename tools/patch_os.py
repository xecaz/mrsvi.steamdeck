#!/usr/bin/env python3
"""Build an AIC.FW image whose os plays /data/logo_jpg_dir/f00.jpg..f74.jpg at boot.

usage: patch_os.py <stock.img> <out.img>

Patches (all in os seg0, see re/PATCH_NOTES.md):
  1. FUN_ram_40032700 (show boot logo) takes its path from a1 instead of the fixed string.
  2. Its only caller (BOOT_IMAGE_READ, jal at 0x400327f2) is redirected to `anim` in the code
     cave (body of msh cmd test_clock, 0x40026dc8..0x40027068). On the boot pass
     (DAT_ram_4009f3b8 == -1) anim shows 75 frames from a stack buffer path, then falls
     through to the stock call with the default path. Later calls pass straight through.
  3. The msh table entry of test_clock is repointed at `version` so the cave can't be run by name.
Then seg0 crc32/md5 in the FIT, and the os META crc in the AIC.FW header are recomputed.
"""
import hashlib
import struct
import sys
import zlib

import capstone

BASE = 0x40000000
OS_OFF, OS_SIZE = 0x81000, 0xA1800          # image.target.os in the .img
META_OS_CRC = 0x800 + 5 * 512 + 144         # META entry #5 crc field
SEG0_OFF = 0x800                            # seg0 data in the os blob (after the FIT header)
SEG0_SIZE = 0x9E3E8

CAVE, CAVE_END = 0x40026DC8, 0x40027068
SHOW = 0x40032700
CALL_SITE = 0x400327F2
DEFAULT_PATH = 0x4007FBB4
FLAG = 0x4009F3B8                           # DAT_ram_4009f3b8, -1 until the host says DIS
MDELAY = 0x40011E5A
TEST_CLOCK_FN = 0x40077FD0                  # func word of msh entry test_clock
VERSION_FN = 0x40020C18

NFRAMES = 75
DELAY_MS = 20
PREFIX = b"/data/logo_jpg_dir/f"          # digits go at +20, +21


# -- tiny RV32I encoder -------------------------------------------------------
R = {f"x{i}": i for i in range(32)}
R.update(zero=0, ra=1, sp=2, t0=5, t1=6, t2=7, s0=8, s1=9, a0=10, a1=11, a2=12, s2=18, s3=19)


def r(n):
    return R[n]


def i_type(op, f3, rd, rs1, imm):
    assert -2048 <= imm < 2048, imm
    return ((imm & 0xFFF) << 20) | (r(rs1) << 15) | (f3 << 12) | (r(rd) << 7) | op


def s_type(f3, rs2, rs1, imm):
    assert -2048 <= imm < 2048
    return (((imm >> 5) & 0x7F) << 25) | (r(rs2) << 20) | (r(rs1) << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | 0x23


def addi(rd, rs, imm): return i_type(0x13, 0, rd, rs, imm)
def lw(rd, imm, rs): return i_type(0x03, 2, rd, rs, imm)
def sw(rs2, imm, rs1): return s_type(2, rs2, rs1, imm)
def sb(rs2, imm, rs1): return s_type(0, rs2, rs1, imm)
def lui(rd, imm20): return (imm20 << 12) | (r(rd) << 7) | 0x37
def auipc(rd, imm20): return (imm20 << 12) | (r(rd) << 7) | 0x17
def mv(rd, rs): return addi(rd, rs, 0)
def li(rd, imm): return addi(rd, "zero", imm)


def jal(rd, off):
    assert off % 2 == 0 and -(1 << 20) <= off < (1 << 20)
    return (((off >> 20) & 1) << 31) | (((off >> 1) & 0x3FF) << 21) | (((off >> 11) & 1) << 20) \
        | (((off >> 12) & 0xFF) << 12) | (r(rd) << 7) | 0x6F


def branch(f3, rs1, rs2, off):
    assert off % 2 == 0 and -4096 <= off < 4096
    return (((off >> 12) & 1) << 31) | (((off >> 5) & 0x3F) << 25) | (r(rs2) << 20) | (r(rs1) << 15) \
        | (f3 << 12) | (((off >> 1) & 0xF) << 8) | (((off >> 11) & 1) << 7) | 0x63


def bne(a, b, off): return branch(1, a, b, off)


def hi_lo(addr, pc):
    off = addr - pc
    hi = (off + 0x800) >> 12
    return hi & 0xFFFFF, off - (hi << 12)


class Asm:
    def __init__(self, base):
        self.base, self.w, self.labels, self.fix = base, [], {}, []

    @property
    def pc(self): return self.base + 4 * len(self.w)

    def emit(self, *ws): self.w.extend(ws)
    def label(self, n): self.labels[n] = self.pc
    def bne(self, a, b, lab): self.fix.append((len(self.w), lab, a, b)); self.w.append(0)

    def jal_abs(self, rd, target): self.emit(jal(rd, target - self.pc))

    def la(self, rd, addr):
        hi, lo = hi_lo(addr, self.pc)
        self.emit(auipc(rd, hi), addr_i(rd, lo))

    def done(self):
        for idx, lab, a, b in self.fix:
            self.w[idx] = bne(a, b, self.labels[lab] - (self.base + 4 * idx))
        return b"".join(struct.pack("<I", x) for x in self.w)


def addr_i(rd, lo): return addi(rd, rd, lo)


def build_cave():
    a = Asm(CAVE)
    FR = 48  # buf 0..31, saves 32..47
    a.emit(addi("sp", "sp", -FR), sw("ra", 44, "sp"), sw("s0", 40, "sp"), sw("s2", 36, "sp"), sw("s3", 32, "sp"))
    a.emit(mv("s0", "a0"))
    a.emit(lui("t0", FLAG >> 12), lw("t0", FLAG & 0xFFF, "t0"), li("t1", -1))
    a.bne("t0", "t1", "final")
    # copy 28-byte path template (patched in after assembly) from the cave data to the stack
    tmpl_idx = len(a.w)
    a.la("t0", 0)  # placeholder, fixed below
    for k in range(7):
        a.emit(lw("t1", 4 * k, "t0"), sw("t1", 4 * k, "sp"))
    a.emit(li("s2", ord("0")), li("s3", ord("0")))
    a.label("loop")
    a.emit(sb("s2", 20, "sp"), sb("s3", 21, "sp"), mv("a0", "s0"), addi("a1", "sp", 0))
    a.jal_abs("ra", SHOW)
    a.emit(li("a0", DELAY_MS))
    a.jal_abs("ra", MDELAY)
    a.emit(addi("s3", "s3", 1), li("t0", ord("9") + 1))
    a.bne("s3", "t0", "nowrap")
    a.emit(li("s3", ord("0")), addi("s2", "s2", 1))
    a.label("nowrap")
    a.emit(li("t0", ord("0") + NFRAMES // 10))
    a.bne("s2", "t0", "loop")
    a.emit(li("t0", ord("0") + NFRAMES % 10))
    a.bne("s3", "t0", "loop")
    a.label("final")
    a.emit(mv("a0", "s0"))
    a.la("a1", DEFAULT_PATH)
    a.emit(lw("ra", 44, "sp"), lw("s0", 40, "sp"), lw("s2", 36, "sp"), lw("s3", 32, "sp"), addi("sp", "sp", FR))
    a.jal_abs("zero", SHOW)  # tail call
    # fix template address, then append data
    code_len = 4 * len(a.w)
    tmpl_addr = CAVE + code_len
    hi, lo = hi_lo(tmpl_addr, CAVE + 4 * tmpl_idx)
    a.w[tmpl_idx], a.w[tmpl_idx + 1] = auipc("t0", hi), addi("t0", "t0", lo)
    blob = a.done() + (PREFIX + b"00.jpg").ljust(28, b"\0")
    assert len(blob) <= CAVE_END - CAVE, len(blob)
    return blob


def main(src, dst):
    img = bytearray(open(src, "rb").read())
    os_ = bytearray(img[OS_OFF:OS_OFF + OS_SIZE])
    assert zlib.crc32(os_) == struct.unpack("<I", img[META_OS_CRC:META_OS_CRC + 4])[0], "stock crc mismatch"
    seg0 = bytearray(os_[SEG0_OFF:SEG0_OFF + SEG0_SIZE])

    def put(addr, data):
        o = addr - BASE
        seg0[o:o + len(data)] = data

    def get(addr, n): return bytes(seg0[addr - BASE:addr - BASE + n])

    # sanity: the things we overwrite are what the analysis says they are
    assert get(CALL_SITE, 4) == struct.pack("<I", jal("ra", SHOW - CALL_SITE)), "call site"
    assert get(SHOW + 4, 12).hex() == "8945" "2a89" "17d50400" "1305c54a", get(SHOW + 4, 12).hex()
    assert get(TEST_CLOCK_FN, 4) == struct.pack("<I", CAVE)

    # 1. show(a0=stat, a1=path): c.mv s2,a0 ; c.mv a0,a1 ; c.li a1,2 ; nops
    put(SHOW + 4, struct.pack("<6H", 0x892A, 0x852E, 0x4589, 0x0001, 0x0001, 0x0001))
    # 2. cave + call-site redirect
    cave = build_cave()
    put(CAVE, cave.ljust(CAVE_END - CAVE, b"\0"))
    put(CALL_SITE, struct.pack("<I", jal("ra", CAVE - CALL_SITE)))
    # 3. harden test_clock
    put(TEST_CLOCK_FN, struct.pack("<I", VERSION_FN))

    os_[SEG0_OFF:SEG0_OFF + SEG0_SIZE] = seg0
    # FIT hashes live in the 0x800 header: find and replace the old values
    old_crc = zlib.crc32(img[OS_OFF + SEG0_OFF:OS_OFF + SEG0_OFF + SEG0_SIZE]).to_bytes(4, "big")
    old_md5 = hashlib.md5(img[OS_OFF + SEG0_OFF:OS_OFF + SEG0_OFF + SEG0_SIZE]).digest()
    hdr = bytes(os_[:SEG0_OFF])
    assert hdr.count(old_crc) == 1 and hdr.count(old_md5) == 1
    new_crc = zlib.crc32(seg0).to_bytes(4, "big")
    os_[:SEG0_OFF] = hdr.replace(old_crc, new_crc).replace(old_md5, hashlib.md5(seg0).digest())

    img[OS_OFF:OS_OFF + OS_SIZE] = os_
    img[META_OS_CRC:META_OS_CRC + 4] = struct.pack("<I", zlib.crc32(os_))
    open(dst, "wb").write(img)
    print("cave", len(cave), "bytes; os crc", hex(zlib.crc32(os_)), "seg0 crc", new_crc.hex())

    # disassemble the result for review
    md = capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV32 | capstone.CS_MODE_RISCVC)
    for ins in md.disasm(bytes(seg0[CAVE - BASE:CAVE - BASE + len(cave) - 28]), CAVE):
        print(f"{ins.address:08x} {ins.mnemonic:8s} {ins.op_str}")
    for ins in md.disasm(bytes(seg0[SHOW - BASE:SHOW - BASE + 0x1c]), SHOW):
        print(f"{ins.address:08x} {ins.mnemonic:8s} {ins.op_str}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
