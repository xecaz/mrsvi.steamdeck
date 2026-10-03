import capstone,sys
fn=sys.argv[1]; base=int(sys.argv[2],16); start=int(sys.argv[3],16); end=int(sys.argv[4],16)
d=open(fn,'rb').read()
md=capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV32|capstone.CS_MODE_RISCVC)
pos=start-base; endp=end-base
regs={}
while pos<endp:
    got=False
    for ins in md.disasm(d[pos:endp], base+pos):
        note=''
        ops=ins.op_str.split(', ')
        if ins.mnemonic=='auipc':
            regs[ops[0]]=ins.address+(int(ops[1],0)<<12)
        elif ins.mnemonic=='lui':
            regs[ops[0]]=(int(ops[1],0)<<12)&0xffffffff
        elif ins.mnemonic in('addi','c.addi') and len(ops)==3 and ops[1] in regs:
            v=(regs[ops[1]]+int(ops[2],0))&0xffffffff; note='  ; =%#x'%v; regs[ops[0]]=v
            if base<=v<base+len(d):
                s=d[v-base:v-base+48].split(b'\0')[0]
                if len(s)>3 and all(32<=c<127 for c in s): note+=' "%s"'%s.decode()
        elif ins.mnemonic in('lw','sw','c.lw','c.sw','lbu','lb','sb','lh','lhu','sh') :
            import re
            m=re.match(r'(-?\w+)\((\w+)\)',ops[-1])
            if m and m.group(2) in regs:
                note='  ; [%#x]'%((regs[m.group(2)]+int(m.group(1),0))&0xffffffff)
        print("%08x %-10s %s%s"%(ins.address, ins.mnemonic, ins.op_str,note)); pos=ins.address-base+ins.size; got=True
        if ins.mnemonic in ('ret','c.jr','jr','c.j','j','mret'): regs={}
    if not got:
        w=int.from_bytes(d[pos:pos+4],'little')
        print("%08x .insn      0x%08x"%(base+pos,w)); pos+=2
