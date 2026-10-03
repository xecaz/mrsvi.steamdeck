import sys,struct,os,zlib
def s(b): return b.split(b'\0')[0].decode(errors='replace')
p=sys.argv[1]; d=open(p,'rb').read(); out=sys.argv[2] if len(sys.argv)>2 else None
h=d[:2048]
print('magic',s(h[0:8]),'platform',s(h[8:72]),'product',s(h[72:136]),'version',s(h[136:200]),'media',s(h[200:264]),'devid',struct.unpack('<I',h[264:268])[0],'mediaid?',s(h[268:332]))
mo,ms,fo,fs=struct.unpack('<4I',h[332:348]); print('meta_off %#x meta_size %#x file_off %#x file_size %#x total %#x'%(mo,ms,fo,fs,len(d)))
for i in range(ms//512):
    m=d[mo+512*i:mo+512*i+512]
    off,sz,crc,ram=struct.unpack('<4I',m[136:152])
    print('%-24s part=%-10s off=%#09x size=%#09x crc=%#010x ram=%#x attr=%s'%(s(m[8:72]),s(m[72:136]),off,sz,crc,ram,s(m[152:216])))
    if out:
        os.makedirs(out,exist_ok=True); open(os.path.join(out,s(m[8:72])),'wb').write(d[off:off+sz])
