import struct,sys,zlib,hashlib
d=open(sys.argv[1],'rb').read()
magic,tot,offs,offm,offr,ver,lc,bp,sstr,sst=struct.unpack('>10I',d[:40])
strs=d[offm:offm+sstr]
def name(o): return strs[o:strs.index(b'\0',o)].decode()
p=offs;depth=0;props={};path=[]
while True:
    t=struct.unpack('>I',d[p:p+4])[0];p+=4
    if t==1:
        e=d.index(b'\0',p);n=d[p:e].decode();path.append(n);p=(e+1+3)&~3
    elif t==2: path.pop()
    elif t==3:
        l,no=struct.unpack('>II',d[p:p+8]);p+=8;v=d[p:p+l];p=(p+l+3)&~3
        k='/'.join(path)+':'+name(no);props[k]=v
        print(k, v.hex() if l<=32 and not v.rstrip(b'\0').isascii() or l==4 else v)
    elif t==9: break
print('totalsize',hex(tot))
for seg in ('seg0','seg1'):
    b='/images/'+seg
    off=struct.unpack('>I',props['%s:data-offset'%b.lstrip('/')] if ('%s:data-offset'%b.lstrip('/')) in props else props['/'+b[1:]+':data-offset'])[0] if False else None
