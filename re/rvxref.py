#!/usr/bin/env python3
"""Cross-reference scanner for the RV32IC os image (os_ram.bin, base 0x40000000).

Finds every way code or data can point at a target address range:
  - direct control flow: jal / c.jal / c.j / branches
  - pc-relative address math: auipc rX + addi/lw/sw/jalr/... (rX)
  - absolute address math: lui rX + addi/...
  - data words: any aligned or unaligned 32-bit LE word in the image equal to an address
    in the range (function-pointer tables, msh command table, thread entry args).
Linear sweep with 2-byte resync past undecodable (ArtInChip custom0) words, like rvdis.py.
Because it is a linear sweep it may also decode data as code; that can only ADD false
positives, never hide a real reference, as long as the code is reached by the sweep.
To make the sweep robust, it is run from every 2-byte phase start found by resync.

usage: rvxref.py os_ram.bin 0x40000000 <lo> <hi>      (targets lo <= addr < hi)
"""
import sys, re, struct
import capstone

def scan(d, base, lo, hi, code_end=None):
    md = capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV32 | capstone.CS_MODE_RISCVC)
    end = len(d) if code_end is None else code_end - base
    hits = []
    pos = 0
    regs = {}
    while pos < end:
        got = False
        for ins in md.disasm(d[pos:end], base + pos):
            got = True
            pos = ins.address - base + ins.size
            m, ops = ins.mnemonic, ins.op_str.split(', ')
            tgt = None
            if m in ('jal', 'c.jal', 'c.j', 'j') or m.startswith('b') or m in ('c.beqz', 'c.bnez'):
                try:
                    tgt = (ins.address + int(ops[-1], 0)) & 0xffffffff
                except ValueError:
                    tgt = None
                if tgt is not None and lo <= tgt < hi:
                    hits.append((ins.address, 'flow', '%s %s -> %#x' % (m, ins.op_str, tgt)))
            if m == 'auipc':
                regs[ops[0]] = (ins.address + (int(ops[1], 0) << 12)) & 0xffffffff
            elif m in ('lui', 'c.lui'):
                regs[ops[0]] = (int(ops[1], 0) << 12) & 0xffffffff
            elif m in ('addi', 'c.addi') and len(ops) == 3 and ops[1] in regs:
                v = (regs[ops[1]] + int(ops[2], 0)) & 0xffffffff
                if lo <= v < hi:
                    hits.append((ins.address, 'addr', '%s %s = %#x' % (m, ins.op_str, v)))
                regs[ops[0]] = v
            elif m == 'jalr' and ops:
                mm = re.match(r'(-?\w+)\((\w+)\)', ops[-1])
                if mm and mm.group(2) in regs:
                    v = (regs[mm.group(2)] + int(mm.group(1), 0)) & 0xffffffff
                    if lo <= v < hi:
                        hits.append((ins.address, 'flow', 'jalr %s -> %#x' % (ins.op_str, v)))
            else:
                mm = re.match(r'(-?\w+)\((\w+)\)', ops[-1]) if ops else None
                if mm and mm.group(2) in regs:
                    v = (regs[mm.group(2)] + int(mm.group(1), 0)) & 0xffffffff
                    if lo <= v < hi:
                        hits.append((ins.address, 'mem', '%s %s -> %#x' % (m, ins.op_str, v)))
                # any write to a tracked reg kills it
                if ops and ops[0] in regs and m not in ('sw', 'sb', 'sh', 'c.sw', 'c.swsp'):
                    regs.pop(ops[0], None)
            if m in ('ret', 'c.jr', 'jr', 'c.j', 'j', 'mret'):
                regs = {}
        if not got:
            pos += 2
            regs = {}
    for off in range(0, len(d) - 3):
        w = struct.unpack_from('<I', d, off)[0]
        if lo <= w < hi:
            hits.append((base + off, 'data', 'word %#x%s' % (w, '' if off % 4 == 0 else ' (unaligned)')))
    return sorted(set(hits))

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    base = int(sys.argv[2], 16)
    lo, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
    for a, k, s in scan(d, base, lo, hi):
        print('%08x %-4s %s' % (a, k, s))
