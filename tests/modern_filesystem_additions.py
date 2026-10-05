"""Independent on-disk fixtures from published structures, public-API checks.

Run with --probe pointing to volume_readers_probe.  These are specification
fixtures, not claims of third-party producer compatibility.  ReFS has a
separate authentic Windows corpus control in modern_refs_control.py.
"""
import argparse
import struct
import subprocess
from pathlib import Path
import tempfile
import zlib

def put(b, off, fmt, *values):
    struct.pack_into(fmt, b, off, *values)

def vxfs(be=False,typed=False):
    b=bytearray(128*1024); e='>' if be else '<'; bs=1024
    for off,val in [(0,0xa501fcf5),(4,1),(32,bs),(72,4),(88,0),(120,64),(152,32)]: put(b,1024+off,e+'I',val)
    def inode(id,mode,size,block=0,inline=None):
        at=4*bs+id*256; put(b,at,e+'I',mode);put(b,at+16,e+'Q',size)
        if inline is None: b[at+49]=1;put(b,at+96,e+'II',block,1)
        else: b[at+49]=2;b[at+80:at+80+len(inline)]=inline
    def directory(block,items):
        at=block*bs+4
        for id,name in items:
            name=name.encode();n=(10+len(name)+3)&~3;put(b,at,e+'IHHH',id,n,len(name),0);b[at+10:at+10+len(name)]=name;at+=n
    inode(2,0x41ed,bs,20);inode(3,0x81a4,5,inline=b'hello');inode(4,0x41ed,bs,21);inode(5,0x81a4,1536,30)
    # Second direct extent is explicitly a hole.
    put(b,4*bs+5*256+104,e+'II',0,1)
    directory(20,[(2,'.'),(3,'readme.txt'),(4,'sub')]);directory(21,[(5,'sparse.bin')]);b[30*bs:31*bs]=b'X'*bs
    expected=b'X'*bs+bytes(512)
    if typed:
        at=4*bs+5*256;b[at+49]=3;b[at+80:at+176]=bytes(96)
        put(b,at+80,e+'QII',(2<<56)|1,30,1);expected=bytes(bs)+b'X'*512
    return bytes(b),{'readme.txt':b'hello','sub/sparse.bin':expected}

def vmfs(inline=False):
    b=bytearray(32*1024*1024);base=0x1100000;bs=0x100000;fdc=base+0x400000
    put(b,0x100000,'<II',0xc001d00d,5 if inline else 3);put(b,0x100000+656,'<I',1)
    put(b,base+0x200000,'<I',0x2fabf15e);b[base+0x200000+8]=5 if inline else 3;put(b,base+0x200000+161,'<Q',bs)
    put(b,fdc,'<IIIIIII',4,1,512,2048,1024+4*2048,4,0)
    def inode(item,type,size,block=0,body=None):
        id=(item<<22)|4;at=fdc+512+1024+item*2048
        put(b,at,'<I',0x10c00001);put(b,at+512,'<IIII',id,0,1,type);put(b,at+532,'<QQ',size,bs)
        put(b,at+580,'<I',4305 if body is not None else 1)
        if body is not None: b[at+1024:at+1024+len(body)]=body
        else: put(b,at+1024,'<I',(block<<6)|1)
        return id
    root=inode(0,2,140,8);sub=inode(1,2,140,9);file=inode(2,3,12,10,body=b'VMFS payload' if inline else None)
    def ent(block,id,type,name):
        at=base+block*bs;put(b,at,'<III',type,id,0);b[at+12:at+12+len(name)]=name.encode()
    ent(8,sub,2,'sub');ent(9,file,3,'payload.bin')
    if not inline:b[base+10*bs:base+10*bs+12]=b'VMFS payload'
    return bytes(b),{'sub/payload.bin':b'VMFS payload'}

def fossil():
    bs=1024; b=bytearray(512*bs);labels=132;data=140;epoch=2
    put(b,131072,'>IHHIIII',0x3776ae89,1,bs,130,labels,data,512)
    put(b,130*bs,'>IHII',0x2340a3b1,1,1,epoch);put(b,130*bs+22,'>I',0)
    def block(id,type,tag,content):
        put(b,labels*bs+id*14,'>BBIII',1,type,1,0,tag);b[(data+id)*bs:(data+id)*bs+len(content)]=content
    def entry(id,size,tag,type=0):
        p=bytearray(40);put(p,4,'>HH',1000,bs);p[8]=1|32|type;put(p,14,'>HI',size>>32,size&0xffffffff);put(p,32,'>II',tag,id);return p
    def meta(name,index,dir=False):
        name=name.encode();p=bytearray(struct.pack('>IHH',0x1c4d9072,9,len(name))+name+struct.pack('>IIIIQ',index,0,index+1,0,1)+b'\0\0'*3+struct.pack('>IIIII',0,0,0,0,0x8000 if dir else 0))
        out=bytearray(bs);put(out,0,'>IHHHHHH',0x5656fc79,16+len(p),0,1,1,16,len(p));out[16:16+len(p)]=p;return out
    block(0,8,1,entry(1,120,2,2));block(1,8,2,entry(2,80,3,2)+entry(3,bs,4)+entry(8,0,9))
    block(2,8,3,entry(4,80,5,2)+entry(5,bs,6));block(3,0,4,meta('sub',0,True))
    block(4,8,5,entry(6,13,7)+entry(8,0,9));block(5,0,6,meta('payload.txt',0));block(6,0,7,b'Fossil bytes!')
    return bytes(b),{'sub/payload.txt':b'Fossil bytes!'}

def crc32c(data):
    crc=0xffffffff
    for x in data:
        crc^=x
        for _ in range(8):crc=(crc>>1)^(0x82f63b78 if crc&1 else 0)
    return crc^0xffffffff

def hammer(version=6):
    b=bytearray(256*1024);begin=8192;records=[];offset=8192;crc=crc32c if version>=7 else zlib.crc32
    def record(obj,key,type,otype,body):
        nonlocal offset
        at=offset;offset=(offset+len(body)+15)&~15;b[begin+at:begin+at+len(body)]=body
        p=bytearray(64);put(p,0,'<QQQQHBBI',obj,key,1,0,type,otype,ord('R'),0);put(p,48,'<QII',(10<<60)|at,len(body),crc(body[:112] if type==1 else body));records.append(p)
    def inode(obj,type,size):
        p=bytearray(128);put(p,0,'<HH',1,0o755 if type==1 else 0o644);p[64]=type;put(p,72,'<Q',1);put(p,80,'<Q',size);record(obj,0,1,type,p)
    inode(1,1,0);inode(2,1,0);inode(3,2,20)
    record(1,1,0x11,1,struct.pack('<QII',2,0,0)+b'sub');record(2,1,0x11,1,struct.pack('<QII',3,0,0)+b'sparse.txt');record(3,20,0x10,2,b'HAMMER data')
    node=bytearray(4096);put(node,16,'<I',len(records));node[20]=ord('L')
    for i,r in enumerate(sorted(records,key=lambda r:struct.unpack_from('<Q',r)[0]*65536+struct.unpack_from('<H',r,32)[0])):node[64+i*64:128+i*64]=r
    put(node,0,'<I',crc(node[4:]));b[begin:begin+4096]=node
    put(b,0,'<Q',0xc8414d4dc5523031);put(b,24,'<QQ',begin,len(b));put(b,148,'<II',1,version);put(b,240,'<Q',8<<60)
    put(b,156,'<I',crc(b[:156])^crc(b[160:1928]))
    return bytes(b),{'sub/sparse.txt':bytes(9)+b'HAMMER data'}

def reiser4():
    bs=4096;b=bytearray(128*bs);stamp=0x12345678;b[65536:65543]=b'ReIsEr4';put(b,65536+18,'<H',bs)
    sb=65536+bs;put(b,sb,'<QQQ',128,64,20);put(b,sb+48,'<I',stamp);b[sb+52:sb+65]=b'ReIsEr40FoRmAt';put(b,sb+68,'<HHQ',1,0,1)
    items=[]
    def item(loc,obj,pid,body,offset=0,ordering=0):items.append((loc,obj,pid,body,offset,ordering))
    def stat(loc,obj,mode,size):item(loc,obj,0,struct.pack('<HHIQ',1,mode,1,size))
    def cde(parent,name,loc,obj):
        name=name.encode();body=bytearray(struct.pack('<HQQQH',1,1<<56,0,0,28)+struct.pack('<QQQ',loc<<4,0,obj)+name+b'\0');item(parent,0,2,body)
    stat(0x29,0x2a,0x41ed,1);stat(0x2a,0x30,0x41ed,1);stat(0x30,0x31,0x81a4,12);cde(0x2a,'sub',0x2a,0x30);cde(0x30,'payload.txt',0x30,0x31);item(0x30,0x31,6,b'Reiser4 data')
    node=bytearray(bs);pos=28;put(node,2,'<H',len(items));put(node,8,'<II',0x52344653,stamp);node[26]=1
    for i,(loc,obj,pid,body,off,order) in enumerate(items):
        node[pos:pos+len(body)]=body;put(node,bs-(i+1)*38,'<QQQQHHH',loc<<4,order,obj,off,pos,0,pid);pos+=len(body)
    put(node,4,'<HH',bs-len(items)*38-pos,pos);b[20*bs:21*bs]=node
    return bytes(b),{'sub/payload.txt':b'Reiser4 data'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--lifecycle-probe');p.add_argument('--work');a=p.parse_args();work=Path(a.work or tempfile.mkdtemp(prefix='xfu-modern-fixtures-'));work.mkdir(parents=True,exist_ok=True)
    tests=[('vxfs-le',2547,vxfs()),('vxfs-be',2547,vxfs(True)),('vxfs-typed',2547,vxfs(typed=True)),('vmfs3',2548,vmfs()),('vmfs5-inline',2548,vmfs(True)),('fossil',2527,fossil()),('hammer6',2528,hammer()),('hammer7',2528,hammer(7)),('reiser4',2539,reiser4())]
    for name,id,(data,expected) in tests:
        source=work/(name+'.img');source.write_bytes(data);out=work/(name+'-out');out.mkdir(exist_ok=True)
        for op in ['l','t','x']:
            cmd=[a.probe,op,str(id),str(source)]+([str(out)] if op=='x' else []);r=subprocess.run(cmd,capture_output=True,text=True)
            if r.returncode:raise AssertionError((name,op,r.stdout,r.stderr))
        actual={str(f.relative_to(out)).replace('\\','/'):f.read_bytes() for f in out.rglob('*') if f.is_file()}
        assert actual==expected,(name,actual.keys(),expected.keys())
        # Corrupt each indispensable magic; metadata-only success is forbidden.
        bad=bytearray(data);at={'vxfs-le':1024,'vxfs-be':1024,'vxfs-typed':1024,'vmfs3':0x1100000+0x200000,'vmfs5-inline':0x1100000+0x200000,'fossil':140*1024+32,'hammer6':8192,'hammer7':8192,'reiser4':20*4096+8}[name];bad[at]^=0x80;source.write_bytes(bad)
        assert subprocess.run([a.probe,'l',str(id),str(source)],capture_output=True).returncode,(name,'corrupt accepted')
        if name=='vxfs-typed':
            bad=bytearray(data);put(bad,4*1024+5*256+80,'<Q',(2<<56)|(1<<54));source.write_bytes(bad)
            assert subprocess.run([a.probe,'l',str(id),str(source)],capture_output=True).returncode,'overflowing typed offset accepted'
        source.write_bytes(data)
        if a.lifecycle_probe:
            r=subprocess.run([a.lifecycle_probe,str(id),str(source)],capture_output=True,text=True)
            assert r.returncode==0,(name,'lifecycle',r.stdout,r.stderr)
        print(name,'names, extraction bytes, RAM-only TEST and corruption checks passed',flush=True)

if __name__=='__main__':main()


