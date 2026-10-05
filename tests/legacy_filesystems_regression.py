"""Independent wire-format images for the native legacy filesystem readers.
Python authoring follows the documented layouts; expected file bytes are
created before directory/extent maps and are never derived from native output.
"""
import argparse, hashlib, json, pathlib, struct, subprocess

def put(b, at, code, *v): struct.pack_into(code, b, at, *v)
def payload(n, salt=11): return bytes((i*37+salt)%256 for i in range(n))
def rad(s):
    abc=' ABCDEFGHIJKLMNOPQRSTUVWXYZ$.%0123456789'
    return sum(abc.index(c)*40**(2-i) for i,c in enumerate(s.ljust(3)))

def rt11(prefix=False):
    b=bytearray(64*512); b[512+496:512+508]=b'DECRT11A    '; put(b,512+466,'<HH',1,6)
    put(b,6*512,'<5H',1,0,1,0,8); put(b,6*512+10,'<7H',0x400|(0x10 if prefix else 0),rad('HEL'),rad('LO'),rad('BIN'),2 if prefix else 1,0,0)
    put(b,6*512+24,'<H',0x800); data=payload(512); at=(9 if prefix else 8)*512; b[at:at+512]=data
    if prefix:b[8*512]=1
    return b, {'HELLO.BIN':data}

def lif():
    b=bytearray(64*256); put(b,0,'>H',0x8000); b[2:8]=b'VOLUME'; put(b,8,'>I',2); put(b,16,'>I',1)
    b[512:522]=b'HELLO     '; put(b,522,'>HII',1,4,2); put(b,512+32+10,'>H',0xffff)
    data=payload(512,17); b[1024:1536]=data; return b,{'HELLO':data}

def ecma(two=False):
    b=bytearray(2048+(35*(32 if two else 16)-16)*256); vol=bytearray(b' '*128); vol[:4]=b'VOL\x01'; vol[4:10]=b'ECMA67'; vol[71]=ord('M' if two else '1'); vol[75]=ord('1'); vol[79]=ord('1'); b[768:896]=vol
    h=bytearray(b' '*128); h[:4]=b'HDR1'; h[5:22]=b'HELLO.TXT        '; h[22:27]=b'00128'; h[28:33]=b'01001'; h[34:39]=b'01003'; h[74:79]=b'01003'; h[57:62]=b'00007'; b[896:1024]=h
    at=2048+((32 if two else 16)-16)*256; data=payload(249,19); b[at:at+128]=data[:128]; b[at+256:at+256+121]=data[128:]
    return b,{'HELLO.TXT':data}

def locus(be=False,small=False,longdir=False,indirect=False):
    bs=4096 if small else 1024; e='>' if be else '<'; b=bytearray(64*bs); put(b,bs,e+'III',0xffeeddcd,1,64); put(b,bs+36,e+'I',8); put(b,bs+42,e+'H',2); b[bs+71]=1 if small else 2
    isz=512 if small else 128
    def inode(n,mode,data,block,flags=0x12):
        at=2*bs+(n-1)*isz; put(b,at,e+'HH',mode,1); put(b,at+14,e+'H',flags); put(b,at+16,e+'I',len(data))
        if small and len(data)<=384:b[at+75]=1; b[at+128:at+128+len(data)]=data
        else:put(b,at+76,e+'I',block); b[block*bs:block*bs+len(data)]=data
        return at
    if longdir:
        root=bytearray(36); put(root,0,e+'IHH',3,20,9); root[8:17]=b'HELLO.BIN'; put(root,20,e+'IHH',4,16,3); root[28:31]=b'DIR'
    else:
        root=bytearray(32); put(root,0,e+'H',3); root[2:11]=b'HELLO.BIN'; put(root,16,e+'H',4); root[18:21]=b'DIR'
    inode(2,0x4000,root,15,0x52 if longdir else 0x12)
    data=payload(200 if small else 700,23); inode(3,0x8000,data,16)
    sub=bytearray(16); put(sub,0,e+'H',5); sub[2:11]=b'CHILD.TXT'; inode(4,0x4000,sub,17)
    child=payload(100,29); inode(5,0x8000,child,18)
    if indirect:
        data=payload(10*bs+77,31); at=inode(3,0x8000,b'',19); put(b,at+16,e+'I',len(data))
        for i in range(10):put(b,at+76+i*4,e+'I',19+i); b[(19+i)*bs:(20+i)*bs]=data[i*bs:(i+1)*bs]
        put(b,at+116,e+'I',30); put(b,30*bs,e+'I',31); b[31*bs:31*bs+77]=data[10*bs:]
    return b,{'HELLO.BIN':data,'DIR/CHILD.TXT':child}

def pfs(split=False,reserved=512,superindex=False):
    b=bytearray(128*512); root=1024; put(b,root,'>II',0x50465302,(2 if split else 0)|(128|32 if superindex else 0)|16)
    put(b,root+52,'>IIIHH',31,2,15,reserved,reserved//512); put(b,root+84,'>II',128,10 if superindex else 0)
    put(b,root+116,'>I',4); put(b,4*512,'>H',0x4942); put(b,4*512+12,'>I',6); put(b,6*512,'>H',0x4142)
    if superindex:
        put(b,10*512,'>H',0x4558); put(b,10*512+64,'>I',12); put(b,12*512,'>H',0x5342); put(b,12*512+12,'>I',4)
    def anode(n,count,start,next=0):put(b,6*512+16+n*12,'>III',count,start,next)
    anode(5,reserved//512,40); anode(6,1,50,8); anode(8,1,52); anode(7,reserved//512,42); anode(9,1,54)
    def directory(block,entries):
        at=block*512; put(b,at,'>H',0x4442); p=at+20
        for name,n,size,t in entries:
            nm=name.encode(); length=(19+len(nm)+1)&~1; b[p]=length; b[p+1]=t&255; put(b,p+2,'>II',n,size); b[p+17]=len(nm); b[p+18:p+18+len(nm)]=nm; p+=length
    data=payload(700,43); child=payload(70,47); b[50*512:51*512]=data[:512]; b[52*512:52*512+188]=data[512:]; b[54*512:54*512+70]=child
    directory(40,[('HELLO.BIN',6,700,-3),('DIR',7,0,2)]); directory(42,[('CHILD.TXT',9,70,-3)])
    return b,{'HELLO.BIN':data,'DIR/CHILD.TXT':child}

def hpofs(gap=False):
    b=bytearray(128*512); put(b,11,'<H',512); put(b,32,'<I',128); b[54:62]=b'HPOFS   '; b[13*512:13*512+8]=b'MEDINFO '; b[14*512:14*512+8]=b'VOLINFO '
    put(b,6*512,'>I',3); put(b,6*512+76,'>I',21); b[21*512:21*512+4]=b'SUBF'; put(b,21*512+16,'>H',1); put(b,21*512+32,'>HHI',4,0,24)
    b[24*512:24*512+4]=b'DATA'; p=24*512+36
    def entry(name,size,start,count,subf=0xffffffff,directory=False):
        nonlocal p
        key=struct.pack('>I',123)+name.encode(); rec=bytearray(220); put(rec,0,'>III',40,40,1); rec[12]=0x20; rec[14]=0x10 if directory else 0x20; put(rec,64,'>H',count); put(rec,68,'>I',start); put(rec,76,'>I',subf); put(rec,88,'>I',size)
        put(b,p,'>HH',len(key),len(rec)); b[p+4:p+4+len(key)]=key; b[p+4+len(key):p+4+len(key)+len(rec)]=rec; p+=4+len(key)+len(rec)
    data=payload(700,53); child=payload(85,59); entry('HELLO.BIN',700,60,1,30); entry('DIR',0,0,0,directory=True); entry('DIR/CHILD.TXT',85,64,1)
    b[30*512:30*512+4]=b'SUBF'; put(b,30*512+16,'>H',1); put(b,30*512+32,'>HHI',1,0,62)
    b[60*512:61*512]=data[:512]; b[62*512:62*512+188]=data[512:]; b[64*512:64*512+85]=child
    if gap:
        subf=bytes(b[30*512:31*512])
        b[28*512:32*512]=b[24*512:28*512]; b[24*512:28*512]=bytes(2048); b[24*512:24*512+4]=b'INDX'; put(b,24*512+20,'>H',1)
        b[32*512:32*512+4]=b'DATA'; put(b,21*512+16,'>H',2); put(b,21*512+40,'>HHI',4,0,32)
        # The file's SUBF at sector30 overlapped the newly authored leaf.
        b[36*512:37*512]=subf
        first_record=28*512+36+4+4+len('HELLO.BIN'); put(b,first_record+76,'>I',36)
    return b,{'HELLO.BIN':data,'DIR/CHILD.TXT':child}

def ods(extension=False,pointer=2,fragmented_index=False):
    b=bytearray(128*512); hb=512; put(b,hb,'<IIIHHHHHHIIHH',1,2,3,0x201,1,2,3,4,9,8,64,1,5); b[hb+496:hb+508]=b'DECFILE11B  '
    def checksum(at):put(b,at+510,'<H',sum(struct.unpack('<255H',b[at:at+510]))&65535)
    put(b,hb+58,'<H',sum(struct.unpack('<29H',b[hb:hb+58]))&65535); checksum(hb)
    def header(fid,seq,size,extents,directory=False,ext=0,segment=0):
        at=(8+fid)*512; b[at:at+4]=bytes([40,100,140,255]); put(b,at+4,'<HHHHBBHHBB',segment,0x201,fid,seq,0,0,ext,1 if ext else 0,0,0); put(b,at+24,'<HH',0,128 if fid==1 else (size+511)//512)
        put(b,at+28,'<HHH',0,size//512+1,size%512); put(b,at+52,'<I',0x2000 if directory else 0); width={1:4,2:6,3:8}[pointer]; b[at+58]=width//2*len(extents)
        for i,(count,lbn) in enumerate(extents):
            if pointer==1:put(b,at+200+i*width,'<HH',0x4000+((lbn>>16)<<8)+count-1,lbn&65535)
            elif pointer==2:put(b,at+200+i*width,'<HI',0x8000+count-1,lbn)
            else:put(b,at+200+i*width,'<HHI',0xc000+((count-1)>>16),(count-1)&65535,lbn)
        checksum(at)
    header(1,1,128*512,[(128,0)]); header(4,1,512,[(1,40)],True); header(6,1,700,[(1,50),(1,52)] if not extension else [(1,50)],ext=8 if extension else 0); header(7,1,512,[(1,42)],True); header(9,1,85,[(1,54)])
    if extension:header(8,1,0,[(1,52)],segment=1)
    def directory(at,entries):
        p=at*512
        for name,fid in entries:
            nm=name.encode(); body=bytearray(4+((len(nm)+1)&~1)+8); body[3]=len(nm); body[4:4+len(nm)]=nm; put(body,4+((len(nm)+1)&~1),'<HHHBB',1,fid,1,0,0); put(b,p,'<H',len(body)); b[p+2:p+2+len(body)]=body; p+=len(body)+2
        put(b,p,'<H',65535)
    directory(40,[('HELLO.BIN',6),('DIR.DIR',7)]); directory(42,[('CHILD.TXT',9)]); data=payload(700,61); child=payload(85,67); b[50*512:51*512]=data[:512]; b[52*512:52*512+188]=data[512:]; b[54*512:54*512+85]=child
    if fragmented_index:
        b[80*512:81*512]=b[17*512:18*512]; b[17*512:18*512]=bytes(512); header(1,1,65*512,[(17,0),(48,80)]); put(b,9*512+26,'<H',65); checksum(9*512)
    return b,{'HELLO.BIN;1':data,'DIR.DIR;1/CHILD.TXT;1':child}

def unicos():
    b=bytearray(64*4096); put(b,0,'>Q',0x6e6331667331636e); put(b,32,'>Q',64); put(b,112,'>Q',2); put(b,152,'>Q',1); put(b,192,'>II',0,64); put(b,200,'>HHI',0,4,12)
    def inode(n,mode,size,extents):
        p=13*4096+n*256; put(b,p,'>II',mode,1); put(b,p+24,'>Q',size); b[p+88]=1
        for i,(count,start) in enumerate(extents):put(b,p+128+i*8,'>II',count,start)
    def dir(block,entries):
        p=block*4096
        for idx,(name,child) in enumerate(entries):
            nm=name.encode(); size=((len(nm)+7)//8+3)*8; stride=4096-p%4096 if idx==len(entries)-1 else size; put(b,p,'>QQQ',child,0,(stride<<10)|len(nm)); b[p+24:p+24+len(nm)]=nm; p+=stride
    inode(2,0x4000,4096,[(1,20)]); inode(3,0x8000,5000,[(1,24),(1,26)]); inode(4,0x4000,4096,[(1,22)]); inode(5,0x8000,80,[(1,28)]); dir(20,[('HELLO.BIN',3),('DIR',4)]); dir(22,[('CHILD.TXT',5)])
    data=payload(5000,71); child=payload(80,73); b[24*4096:25*4096]=data[:4096]; b[26*4096:26*4096+904]=data[4096:]; b[28*4096:28*4096+80]=child
    return b,{'HELLO.BIN':data,'DIR/CHILD.TXT':child}

def malformed():
    cases=[]
    def case(name,typ,producer,at,code,*values):
        b,_=producer(); put(b,at,code,*values); cases.append((name,typ,b))
    case('rt11-directory-cycle',2524,rt11,6*512+2,'<H',1)
    case('rt11-live-outside-image',2524,rt11,6*512+18,'<H',64)
    case('rt11-invalid-rad50',2524,rt11,6*512+12,'<H',65535)
    case('lif-file-outside-image',2530,lif,512+12,'>I',64)
    case('lif-directory-outside-image',2530,lif,8,'>I',64)
    case('ecma-invalid-block-size',2525,ecma,896+22,'5s',b'00257')
    case('ecma-multivolume',2525,ecma,896+44,'B',ord('M'))
    case('ecma-replacement-sector',2525,ecma,512,'6s',b'ERMAP1')
    case('locus-file-outside-image',2533,locus,2*1024+2*128+76,'<I',64)
    case('locus-directory-cycle',2533,locus,17*1024,'<H',2)
    case('locus-remote-file',2533,locus,2*1024+2*128+14,'<H',0x10)
    case('pfs-anode-cycle',2537,pfs,6*512+16+6*12+8,'>I',6)
    case('pfs-file-outside-image',2537,pfs,6*512+16+6*12+4,'>I',128)
    case('pfs-directory-cycle',2537,pfs,40*512+20+28+2,'>I',5)
    case('hpofs-subf-outside-image',2529,hpofs,30*512+36,'>I',128)
    case('hpofs-invalid-key-size',2529,hpofs,24*512+36,'>H',2048)
    case('hpofs-mismatched-descriptor',2529,hpofs,24*512+36+4+13+4,'>I',41)
    case('ods-bad-home-checksum',2523,ods,512+58,'<H',0)
    case('ods-bad-file-checksum',2523,ods,14*512+510,'<H',0)
    case('unicos-file-outside-image',2543,unicos,13*4096+3*256+132,'>I',64)
    case('unicos-external-partition',2543,unicos,152,'>Q',2)
    case('unicos-migrated-file',2543,unicos,13*4096+3*256+81,'B',1)
    case('unicos-indirect-file',2543,unicos,13*4096+3*256+238,'>H',1)
    case('unicos-directory-cycle',2543,unicos,22*4096,'>Q',2)
    return cases

def main():
    a=argparse.ArgumentParser(); a.add_argument('--probe',required=True); a.add_argument('--root',required=True); a.add_argument('--lifecycle-probe'); q=a.parse_args(); root=pathlib.Path(q.root); root.mkdir(parents=True,exist_ok=True); checks=[]; lifecycle_checks=0
    fixtures=[('rt11',2524,rt11()),('rt11-prefix',2524,rt11(True)),('lif',2530,lif()),('ecma67',2525,ecma()),('ecma67-double',2525,ecma(True)),('locus-le',2533,locus()),('locus-be',2533,locus(True)),('locus-small',2533,locus(small=True)),('locus-long',2533,locus(longdir=True)),('locus-indirect',2533,locus(indirect=True)),('pfs',2537,pfs()),('pfs-split',2537,pfs(True)),('pfs-large-index',2537,pfs(True,1024,True)),('hpofs',2529,hpofs()),('hpofs-gap-leaf',2529,hpofs(True)),('ods2',2523,ods()),('ods2-extended',2523,ods(True)),('ods2-map1',2523,ods(pointer=1)),('ods2-map3',2523,ods(pointer=3)),('ods2-fragmented-index',2523,ods(fragmented_index=True)),('unicos',2543,unicos())]
    for name,typ,(image,files) in fixtures:
        source=root/(name+'.img'); source.write_bytes(image); digest=hashlib.sha256(image).hexdigest(); dest=root/(name+'-output'); dest.mkdir(exist_ok=True)
        for mode in ('t','x'):
            cmd=[q.probe,mode,str(typ),str(source)];
            if mode=='x':cmd.append(str(dest))
            r=subprocess.run(cmd,capture_output=True,text=True); assert r.returncode==0,(name,mode,r.stdout,r.stderr); checks.append(name+'-'+mode)
        for path,data in files.items():
            got=(dest/path).read_bytes(); assert got==data,(name,path,len(got),len(data)); checks.append(name+'-exact-'+path)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest; checks.append(name+'-source-unchanged')
        if q.lifecycle_probe:
            r=subprocess.run([q.lifecycle_probe,str(typ),str(source)],capture_output=True,text=True); assert r.returncode==0,(name,'lifecycle',r.stdout,r.stderr); lifecycle_checks+=int(r.stdout.split()[0]); checks.append(name+'-lifecycle')
        broken=root/(name+'-truncated.img'); broken.write_bytes(image[:1280]); r=subprocess.run([q.probe,'t',str(typ),str(broken)],capture_output=True,text=True); assert r.returncode!=0,(name,'truncation accepted'); checks.append(name+'-truncated')
    for name,typ,image in malformed():
        source=root/(name+'.img'); source.write_bytes(image); r=subprocess.run([q.probe,'t',str(typ),str(source)],capture_output=True,text=True); assert r.returncode!=0,(name,'malformed image accepted',r.stdout,r.stderr); checks.append(name+'-rejected')
    report={'checks':checks,'passed':len(checks),'lifecycle_controls':lifecycle_checks,'fixtures':len(fixtures),'probe':q.probe}; (root/'verification.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report))

if __name__=='__main__':main()

