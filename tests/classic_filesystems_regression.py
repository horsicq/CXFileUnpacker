"""Independent wire encoders and SHA-256 oracle for nine classic filesystems.

The native probe loads fixtures before entering a RAM-only mutation scope,
then exercises short reads, nonzero base, cursor preservation and cancellation.
Filesystem TEST and decoding create no files. Fixture production is explicit.
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, struct, subprocess

TYPES={'coherent':2522,'ext':2532,'qnx4':2538,'efs':2540,'sysv':2544,'v7':2545,'bfs':2546,'xenix':2549,'xia':2550}
EMPTY=hashlib.sha256(b'').hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def u16(b,at,v,order='le'):struct.pack_into('>H' if order=='be' else '<H',b,at,v)
def u32(b,at,v,order='le'):
    if order=='pdp':struct.pack_into('<HH',b,at,v>>16,v&65535)
    else:struct.pack_into('>I' if order=='be' else '<I',b,at,v)
def u24(b,at,v,order='le'):
    b[at:at+3]=bytes((v>>16,v&255,(v>>8)&255)) if order=='pdp' else v.to_bytes(3,'big' if order=='be' else 'little')
class Image:
    def __init__(self,bs=512,count=512):self.bs=bs;self.count=count;self.b=bytearray(bs*count);self.next=24;self.expected={}
    def block(self,data=b''):
        n=self.next;self.next+=1;self.b[n*self.bs:n*self.bs+len(data)]=data;return n
    def expect(self,path,data):self.expected[path]=(0,sha(data))
    def folder(self,path):self.expected[path]=(1,EMPTY)

def fixed_dir(entries,order='le'):
    b=bytearray()
    for ino,name in entries:
        e=bytearray(16);u16(e,0,ino,order);e[2:2+len(name)]=name.encode();b+=e
    return b
def variable_dir(entries,bs,xia=False):
    b=bytearray(bs);at=0
    for index,(ino,name) in enumerate(entries):
        s=name.encode();head=7 if xia else 8;n=(head+len(s)+3)&~3
        if index==len(entries)-1:n=bs-at
        u32(b,at,ino);u16(b,at+4,n)
        if xia:b[at+6]=len(s)
        else:u16(b,at+6,len(s))
        b[at+head:at+head+len(s)]=s;at+=n
    return b
def unix_image(kind,order='le',bs=512,r4=False):
    x=Image(bs);direct=10;itable=2*bs;firstdata=8
    if kind=='ext':direct=9;bs=1024;x=Image(bs);itable=2048;firstdata=8;root=1
    elif kind=='xia':direct=8;itable=3*bs;firstdata=8;root=1
    else:root=2
    inode_offset=lambda ino:itable+(ino-1)*64
    def inode(ino,mode,size,pointers):
        at=inode_offset(ino);u16(x.b,at,mode,order);u16(x.b,at+2,1,order)
        if kind=='ext':u32(x.b,at+4,size);start=16
        else:u32(x.b,at+8,size,order);start=24 if kind=='xia' else 12
        for index,p in enumerate(pointers):
            if kind in ('ext','xia'):u32(x.b,at+start+4*index,p | (0x40000000 if kind=='xia' else 0),order)
            else:u24(x.b,at+start+3*index,p,order)
    ids={'root':root,'dir':root+1,'file':root+2,'empty':root+3,'sparse':root+4,'single':root+5,'double':root+6,'triple':root+7,'link':root+8}
    entries=[(root,'.'),(root,'..'),(ids['dir'],'folder'),(ids['empty'],'empty'),(ids['sparse'],'sparse.bin'),(ids['single'],'single.bin'),(ids['double'],'double.bin'),(ids['link'],'link'),(ids['file'],'hardlink.txt')]
    if kind!='xia':entries.append((ids['triple'],'triple.bin'))
    directory=lambda es:variable_dir(es,bs,kind=='xia') if kind in ('ext','xia') else fixed_dir(es,order)
    rootdata=directory(entries);rootblock=x.block(rootdata);inode(root,0x41ed,len(rootdata),[rootblock])
    nested=directory([(ids['dir'],'.'),(root,'..'),(ids['file'],'hello.txt')]);nblock=x.block(nested);inode(ids['dir'],0x41ed,len(nested),[nblock]);x.folder('folder')
    content=b'Classic filesystem native extraction\n';dblock=x.block(content);inode(ids['file'],0x81a4,len(content),[dblock]);x.expect('folder/hello.txt',content);x.expect('hardlink.txt',content)
    empty=directory([(ids['empty'],'.'),(root,'..')]);inode(ids['empty'],0x41ed,len(empty),[x.block(empty)]);x.folder('empty')
    content=b'left'+bytes(bs-4)+bytes(bs)+b'right';p=[x.block(b'left'),0,x.block(b'right')];inode(ids['sparse'],0x81a4,len(content),p);x.expect('sparse.bin',content)
    fan=bs//4
    for label,height in [('single',1),('double',2),('triple',3)]:
        if kind=='xia' and height==3:continue
        leaf=b'Indirect level '+str(height).encode();last=x.block(leaf);p=last
        for level in range(height):
            ptrs=bytearray(bs);u32(ptrs,0,p,order);p=x.block(ptrs)
        logical=direct+sum(fan**i for i in range(1,height));size=logical*bs+len(leaf)
        pointers=[0]*direct+[0]*(height-1)+[p];inode(ids[label],0x81a4,size,pointers);x.expect(label+'.bin',bytes(logical*bs)+leaf)
    target=b'folder/hello.txt';inode(ids['link'],0xa1ff,len(target),[x.block(target)]);x.expect('link',target)
    if kind=='ext':
        u32(x.b,1024,64);u32(x.b,1028,x.count);u32(x.b,1048,firstdata);u16(x.b,1080,0x137d)
    elif kind=='xia':
        for at,v in [(512,bs),(516,x.count),(520,64),(524,x.count-firstdata),(528,1),(532,1),(536,firstdata),(540,{1024:0,2048:1,4096:2}[bs]),(572,0x012fd16d)]:u32(x.b,at,v)
    else:
        sb=1024 if kind=='xenix' else 512;u16(x.b,sb,firstdata,order);u32(x.b,sb+(4 if r4 else 2),x.count,order)
        if r4:u32(x.b,sb+420,946684800,order)
        if kind=='coherent':x.b[sb+484:sb+496]=b'nonamenopack'
        elif kind=='v7':u16(x.b,sb+6,0,order);u16(x.b,sb+208,0,order)
        else:
            magicat=1016 if kind=='xenix' else 504;u32(x.b,sb+magicat,0x2b5544 if kind=='xenix' else 0xfd187e20,order);u32(x.b,sb+magicat+4,{512:1,1024:2,2048:3}[bs],order)
    x.inode_offset=inode_offset;x.root=root;x.file=ids['file'];x.rootblock=rootblock;x.order=order
    return x

def bfs_image():
    x=Image();u32(x.b,0,0x1badface);u32(x.b,4,8192);u32(x.b,8,len(x.b)-1)
    def inode(ino,kind,data):
        block=x.block(data) if data else 0;at=512+(ino-2)*64;u16(x.b,at,ino);u32(x.b,at+4,block);u32(x.b,at+8,block);u32(x.b,at+12,block*512+len(data)-1 if data else 0);u32(x.b,at+16,kind);return block
    rootdata=fixed_dir([(2,'.'),(2,'..'),(3,'hello.txt'),(4,'empty.bin')]);x.rootblock=inode(2,2,rootdata)
    content=b'SVR4 BFS contiguous data\n';inode(3,1,content);inode(4,1,b'');x.expect('hello.txt',content);x.expect('empty.bin',b'');return x
def qnx_image():
    x=Image();rootdir=x.block();nested=x.block();xblock=x.block();data=x.block(b'first'+bytes(507));second=x.block(b'second')
    def inode(at,name,mode,size,first,n=1,extra=0,extents=1):
        x.b[at:at+len(name)]=name.encode();u32(x.b,at+16,size);u32(x.b,at+20,first+1);u32(x.b,at+24,n);u32(x.b,at+28,extra+1 if extra else 0);u16(x.b,at+48,extents);u16(x.b,at+50,mode);x.b[at+63]=1
    inode(512,'/',0x41ed,512,rootdir);inode(576,'.inodes',0x81a4,512,30);inode(640,'.boot',0x81a4,512,31)
    inode(rootdir*512,'.',0x41ed,512,rootdir);inode(rootdir*512+64,'..',0x41ed,512,rootdir)
    inode(rootdir*512+128,'folder',0x41ed,512,nested);x.folder('folder')
    inode(nested*512,'.',0x41ed,512,nested);inode(nested*512+64,'..',0x41ed,512,rootdir)
    content=b'QNX4 inline inode file\n';inode(nested*512+128,'hello.txt',0x81a4,len(content),x.block(content));x.expect('folder/hello.txt',content)
    inode(rootdir*512+192,'chain.bin',0x81a4,518,data,extra=xblock,extents=2);x.b[xblock*512+8]=1;u32(x.b,xblock*512+16,second+1);u32(x.b,xblock*512+20,1);x.b[xblock*512+496:xblock*512+504]=b'IamXblk\0';x.expect('chain.bin',b'first'+bytes(507)+b'second')
    link=rootdir*512+256;name='long linked filename which has thirty characters';x.b[link:link+len(name)]=name.encode();u32(x.b,link+48,nested+1);x.b[link+52]=2;x.b[link+63]=8;x.expect(name,content)
    x.rootblock=rootdir;x.xblock=xblock;return x
def efs_image(indirect=False):
    x=Image();u32(x.b,512,x.count,'be');u32(x.b,516,4,'be');u32(x.b,520,508,'be');u16(x.b,524,4,'be');u16(x.b,530,1,'be');u32(x.b,540,0x72959,'be')
    def extent(block,count,offset):return b'\0'+block.to_bytes(3,'big')+bytes([count])+offset.to_bytes(3,'big')
    def inode(ino,mode,size,exts):
        at=4*512+ino*128;u16(x.b,at,mode,'be');u16(x.b,at+2,1,'be');u32(x.b,at+8,size,'be');u16(x.b,at+28,len(exts),'be');x.b[at+32:at+32+8*len(exts)]=b''.join(exts)
    def directory(entries):
        b=bytearray(512);u16(b,0,0xbeef,'be');b[3]=len(entries);end=512
        for index,(ino,name) in enumerate(entries):
            n=name.encode();end-=(5+len(n)+1)&~1;b[4+index]=end//2;u32(b,end,ino,'be');b[end+4]=len(n);b[end+5:end+5+len(n)]=n
        b[2]=end//2;return b
    rootdata=directory([(2,'.'),(2,'..'),(3,'folder'),(5,'empty'),(6,'sparse.bin'),(7,'indirect.bin')]);rb=x.block(rootdata);inode(2,0x41ed,512,[extent(rb,1,0)])
    nb=x.block(directory([(3,'.'),(2,'..'),(4,'hello.txt')]));inode(3,0x41ed,512,[extent(nb,1,0)]);x.folder('folder')
    content=b'SGI EFS extent content\n';inode(4,0x81a4,len(content),[extent(x.block(content),1,0)]);x.expect('folder/hello.txt',content)
    inode(5,0x41ed,512,[extent(x.block(directory([(5,'.'),(2,'..')])),1,0)]);x.folder('empty')
    first=x.block(b'left');last=x.block(b'right');inode(6,0x81a4,1029,[extent(first,1,0),extent(last,1,2)]);x.expect('sparse.bin',b'left'+bytes(508)+bytes(512)+b'right')
    exts=[];content=b''
    for index in range(13):
        chunk=bytes([index+1])*512;exts.append(extent(x.block(chunk),1,index));content+=chunk
    container=x.block(b''.join(exts));at=4*512+7*128;u16(x.b,at,0x81a4,'be');u16(x.b,at+2,1,'be');u32(x.b,at+8,len(content),'be');u16(x.b,at+28,13,'be');x.b[at+32:at+40]=extent(container,1,1);x.expect('indirect.bin',content)
    x.rootblock=rb;x.container=container;return x

def main():
    p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--root',required=True);a=p.parse_args();root=pathlib.Path(a.root);root.mkdir(parents=True,exist_ok=True);results=[]
    fixtures=[]
    for kind in ('coherent','ext','sysv','v7','xenix','xia'):
        orders=('pdp',) if kind=='coherent' else ('le','be','pdp') if kind=='v7' else ('le','be') if kind in ('sysv','xenix') else ('le',)
        sizes=(1024,2048,4096) if kind=='xia' else (1024,) if kind in ('ext','xenix') else (512,1024,2048) if kind=='sysv' else (512,)
        for order in orders:
            for bs in sizes:fixtures.append((f'{kind}-{order}-{bs}',kind,unix_image(kind,order,bs)))
    fixtures.append(('sysv-r4','sysv',unix_image('sysv','le',1024,True)))
    fixtures.extend([('bfs','bfs',bfs_image()),('qnx4','qnx4',qnx_image()),('efs','efs',efs_image())])
    def run(name,kind,data,expected,success=True,*limits):
        path=root/(name+'.img');path.write_bytes(data);before=sha(data);r=subprocess.run([a.probe,str(TYPES[kind]),str(path),*(str(n) for n in limits)],capture_output=True,text=True)
        actual={}
        if r.returncode==0:
            for line in r.stdout.splitlines():
                n,folder,digest=line.split('\t');
                if 'volume-info.txt' not in n:actual[n]=(int(folder),digest)
        ok=(r.returncode==0)==success and (not success or actual==expected) and sha(path.read_bytes())==before
        results.append({'name':name,'ok':ok,'returncode':r.returncode,'members':len(actual),'source_sha256':before})
        if not ok:print(name,'FAILED',r.returncode,'expected',expected,'actual',actual,'stderr',r.stderr)
    for name,kind,x in fixtures:
        run(name,kind,x.b,x.expected)
        run(name+'-low-memory',kind,x.b,{},False,4096)
        run(name+'-member-limit',kind,x.b,{},False,1048576,1)
        run(name+'-truncated',kind,x.b[:4096],{},False)
        corrupt=bytearray(x.b)
        if kind=='qnx4':corrupt[x.xblock*512+496]=0
        elif kind=='efs':corrupt[x.container*512]=1
        elif kind=='bfs':u32(corrupt,512+4,511)
        else:
            ino=x.inode_offset(x.file);ptr=24 if kind=='xia' else 16 if kind=='ext' else 12
            if kind in ('ext','xia'):u32(corrupt,ino+ptr,x.count+1,x.order)
            else:u24(corrupt,ino+ptr,x.count+1,x.order)
        run(name+'-bad-allocation',kind,corrupt,{},False)
        cycle=bytearray(x.b)
        if kind=='qnx4':u32(cycle,x.rootblock*512+256+48,2);cycle[x.rootblock*512+256+52]=0
        elif kind=='efs':
            entry=cycle[x.rootblock*512+6]*2;u32(cycle,x.rootblock*512+entry,2,'be')
        elif kind=='bfs':u16(cycle,x.rootblock*512+32,2)
        elif kind in ('ext','xia'):u32(cycle,x.rootblock*x.bs+24,x.root)
        else:u16(cycle,x.rootblock*x.bs+32,x.root,x.order)
        run(name+'-directory-cycle',kind,cycle,{},False)
    report={'checks':len(results),'passed':sum(r['ok'] for r in results),'families':sorted(TYPES),'results':results};(root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ('checks','passed','families')}));return 0 if report['passed']==report['checks'] else 1
if __name__=='__main__':raise SystemExit(main())
