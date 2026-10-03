import capstone,sys
d=open('os_ram.bin','rb').read(); base=0x40000000
md=capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV32|capstone.CS_MODE_RISCVC)
start=int(sys.argv[1],16)-base; n=int(sys.argv[2],16) if len(sys.argv)>2 else 0x200
pos=start; end=start+n
while pos<end:
    got=False
    for ins in md.disasm(d[pos:end], base+pos):
        print("%08x %-10s %s"%(ins.address, ins.mnemonic, ins.op_str)); pos=ins.address-base+ins.size; got=True
    if not got:
        w=int.from_bytes(d[pos:pos+4],'little')
        print("%08x .insn      0x%08x  (undecoded)"%(base+pos,w))
        pos+=2  # resync at 2-byte for RVC
