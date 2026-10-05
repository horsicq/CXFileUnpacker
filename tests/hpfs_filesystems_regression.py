"""Independent HPFS wire fixtures; exact bytes, bounded borrowed source TEST."""
import argparse, hashlib, json, pathlib, struct, subprocess
def u16(b,at,n): struct.pack_into('<H',b,at,n)
def u32(b,at,n): struct.pack_into('<I',b,at,n)
def sha(b): return hashlib.sha256(b).hexdigest()
def split_tree(image):
    b=bytearray(image);at=26*512;b[at+60]=10;b[at+61]=2;u16(b,at+62,24);u32(b,at+64,1);u32(b,at+68,48);u32(b,at+72,0xffffffff);u32(b,at+76,49)
    b[48*512+16]=39;b[48*512+17]=1;u16(b,48*512+18,20)
    at=49*512;u32(b,at,0x37e40aae);u32(b,at+4,49);u32(b,at+8,26);b[at+12]=0x20;b[at+16]=39;b[at+17]=1;u16(b,at+18,20);u32(b,at+20,1);u32(b,at+24,1);u32(b,at+28,96)
    return b
def symlink(image,kind,target=b'../folder/hello.txt'):
    b=bytearray(image);at=28*512;flags=3 if kind=='indirect-anode' else 1 if kind=='indirect' else 0;value=struct.pack('<II',len(target),148 if flags==3 else 150) if flags else target
    ea=struct.pack('<BBH',flags,7,len(value))+b'SYMLINK\0'+value
    def anode(n,extents):
        p=n*512;u32(b,p,0x37e40aae);u32(b,p+4,n);u32(b,p+8,28);b[p+12]=0x20;b[p+16]=40-len(extents);b[p+17]=len(extents);u16(b,p+18,8+12*len(extents))
        for i,(logical,count,disk) in enumerate(extents):u32(b,p+20+i*12,logical);u32(b,p+24+i*12,count);u32(b,p+28+i*12,disk)
    if kind in ('external','external-anode'):
        if kind=='external-anode':
            # Unrelated EA places target across two noncontiguous sectors.
            ea=struct.pack('<BBH',0,1,485)+b'X\0'+bytes(485)+ea;u16(b,at+54,2);anode(140,[(0,1,144),(1,1,146)]);b[144*512:145*512]=ea[:512];b[146*512:146*512+len(ea)-512]=ea[512:]
        else:b[140*512:140*512+len(ea)]=ea
        u32(b,at+44,len(ea));u32(b,at+48,140)
    else:
        u16(b,at+184,196);u16(b,at+52,len(ea));b[at+196:at+196+len(ea)]=ea
        if flags:b[150*512:150*512+len(target)]=target
        if flags==3:anode(148,[(0,(len(target)+511)//512,150)])
    return b,target
def fixture():
    b=bytearray(256*512); expected={}
    def entry(name,fnode=0,size=0,flags=0,attrs=0,down=0):
        n=name if isinstance(name,bytes) else name.encode(); z=(31+len(n)+(4 if down else 0)+3)&~3;e=bytearray(z);u16(e,0,z);e[2]=flags|(4 if down else 0);e[3]=attrs;u32(e,4,fnode);u32(e,12,size);e[30]=len(n);e[31:31+len(n)]=n
        if down:u32(e,z-4,down)
        return e
    def dnode(sector,entries,parent):
        data=b''.join([entry(b'\1\1',flags=1),*entries,entry(b'\xff',flags=8)]);at=sector*512;u32(b,at,0x77e40aae);u32(b,at+4,20+len(data));b[at+8]=1;u32(b,at+12,parent);u32(b,at+16,sector);b[at+20:at+20+len(data)]=data
    def fnode(sector,size=0,directory=0,extents=(),child=0):
        at=sector*512;u32(b,at,0xf7e40aae);u16(b,at+54,0x100 if directory else 0);u32(b,at+160,size)
        if directory:extents=[(0,4,directory)]
        b[at+56]=0x80 if child else 0;b[at+60]=(12 if child else 8)-(1 if child else len(extents));b[at+61]=1 if child else len(extents);u16(b,at+62,16 if child else 8+12*len(extents))
        if child:u32(b,at+64,0xffffffff);u32(b,at+68,child)
        for i,(logical,count,disk) in enumerate(extents):u32(b,at+64+12*i,logical);u32(b,at+68+12*i,count);u32(b,at+72+12*i,disk)
    u32(b,8192,0xf995e849);u32(b,8196,0xfa53e9c5);b[8200]=2;u32(b,8204,24);u32(b,8208,256)
    u32(b,8704,0xf9911849);u32(b,8708,0xfa5229c5)
    fnode(24,directory=32);fnode(25,directory=36);fnode(27,directory=40);fnode(28);fnode(26,700,child=48)
    at=48*512;u32(b,at,0x37e40aae);u32(b,at+4,48);u32(b,at+8,26);b[at+12]=0x20;b[at+16]=38;b[at+17]=2;u16(b,at+18,32)
    for i,disk in enumerate((80,96)):u32(b,at+20+i*12,i);u32(b,at+24+i*12,1);u32(b,at+28+i*12,disk)
    b[80*512:81*512]=b'A'*512;b[96*512:97*512]=b'B'*512;expected['fragmented.bin']=(0,sha(b'A'*512+b'B'*188))
    content=b'HPFS nested file content\n';fnode(29,len(content),extents=[(0,1,100)]);b[100*512:100*512+len(content)]=content;expected['folder/hello.txt']=(0,sha(content))
    content=b'HPFS directory child tree\n';fnode(30,len(content),extents=[(0,1,112)]);b[112*512:112*512+len(content)]=content;expected['btree.txt']=(0,sha(content))
    dnode(32,[entry('folder',25,attrs=16,down=44),entry('empty',27,attrs=16),entry('zero.bin',28),entry('fragmented.bin',26,700)],24)
    dnode(36,[entry('hello.txt',29,len(b'HPFS nested file content\n'))],25);dnode(40,[],27);dnode(44,[entry('btree.txt',30,len(b'HPFS directory child tree\n'))],32)
    expected['folder']=(1,sha(b''));expected['empty']=(1,sha(b''));expected['zero.bin']=(0,sha(b''));return b,expected
def main():
    p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--root',required=True);p.add_argument('--lifecycle-probe');a=p.parse_args();root=pathlib.Path(a.root);root.mkdir(parents=True,exist_ok=True);b,expected=fixture();checks=[];lifecycle_controls=0
    def run(name,data,ok=True,*limits,oracle=None):
        nonlocal lifecycle_controls
        path=root/(name+'.img');path.write_bytes(data);before=sha(data);r=subprocess.run([a.probe,'2534',str(path),*map(str,limits)],capture_output=True,text=True);actual={}
        if r.returncode==0:
            for line in r.stdout.splitlines():
                n,folder,digest=line.split('\t')
                if 'volume-info.txt' not in n:actual[n]=(int(folder),digest)
        good=(r.returncode==0)==ok and (not ok or actual==(expected if oracle is None else oracle)) and before==sha(path.read_bytes());checks.append({'name':name,'ok':good,'returncode':r.returncode,'members':len(actual)})
        if not good:print(name,r.returncode,r.stderr,actual,expected)
        if ok and a.lifecycle_probe:
            life=subprocess.run([a.lifecycle_probe,'2534',str(path)],capture_output=True,text=True);assert life.returncode==0,(name,life.stdout,life.stderr);lifecycle_controls+=int(life.stdout.split()[0])
    run('hpfs',b);run('memory-limit',b,False,4096);run('member-limit',b,False,32*1024*1024,1);run('truncated',b[:8192],False)
    remapped=bytearray(b);u32(remapped,8704+12,128);u32(remapped,8704+16,2);u32(remapped,8704+20,4)
    for i,(original,replacement) in enumerate(((80,120),(32,124))):
        remapped[replacement*512:(replacement+1)*512]=remapped[original*512:(original+1)*512];remapped[original*512:(original+1)*512]=bytes(512);u32(remapped,128*512+i*4,original);u32(remapped,128*512+(4+i)*4,replacement)
    run('hotfix-remapped-metadata-and-file',remapped)
    run('bounded-memory-success',b,True,600000)
    two=split_tree(b);run('two-child-allocation-tree',two)
    for name,at,fmt,value in [('internal-key-unreachable',26*512+64,'<I',0),('nonfinal-key-too-large',26*512+64,'<I',2),('final-key-too-small',26*512+72,'<I',1),('invalid-fnode-first-free',26*512+62,'<H',65535),('invalid-anode-first-free',48*512+18,'<H',65535),('invalid-free-count',26*512+60,'B',0),('invalid-directory-first-free',24*512+62,'<H',65535),('invalid-empty-file-first-free',28*512+62,'<H',500)]:
        broken=bytearray(two);struct.pack_into(fmt,broken,at,value);run(name,broken,False)
    for kind in ('resident','external','external-anode','indirect','indirect-anode'):
        link,target=symlink(b,kind);wanted=dict(expected);wanted['zero.bin']=(0,sha(target));run('symlink-'+kind,link,oracle=wanted)
    link,target=symlink(b,'resident');wanted=dict(expected);wanted['zero.bin']=(0,sha(target));mapped=bytearray(link);mapped[152*512:153*512]=mapped[28*512:29*512];mapped[28*512:29*512]=bytes(512);u32(mapped,8704+12,128);u32(mapped,8704+16,1);u32(mapped,8704+20,4);u32(mapped,128*512,28);u32(mapped,128*512+16,152);run('symlink-hotfix-resident',mapped,oracle=wanted)
    for name,kind,at,fmt,value in [('symlink-invalid-name-terminator','resident',28*512+207,'B',88),('symlink-resident-value-overrun','resident',28*512+198,'<H',65535),('symlink-indirect-target-outside-image','indirect',28*512+212,'<I',256),('symlink-anode-extent-outside-image','indirect-anode',148*512+28,'<I',256),('external-ea-too-large','external',28*512+44,'<I',16*1024*1024+1)]:
        bad,_=symlink(b,kind);struct.pack_into(fmt,bad,at,value);run(name,bad,False)
    bad,_=symlink(b,'indirect-anode');bad[148*512+12]=0x80;bad[148*512+16]=59;u16(bad,148*512+18,16);u32(bad,148*512+20,0xffffffff);u32(bad,148*512+24,148);run('symlink-anode-cycle',bad,False)
    bad,target=symlink(b,'resident');ea=struct.pack('<BBH',0,7,len(target))+b'SYMLINK\0'+target;u32(bad,28*512+44,len(ea));u32(bad,28*512+48,140);bad[140*512:140*512+len(ea)]=ea;run('duplicate-symlink-EA',bad,False)
    bad,_=symlink(b,'indirect',b'X'*1500);run('symlink-member-limit',bad,False,32*1024*1024,1000)
    for name,at,value in [('anode-cycle',26*512+68,26),('allocation-out-of-bounds',48*512+28,300),('dnode-cycle',32*512+20+36+((31+6+4+3)&~3)-4,32),('bad-file-size',26*512+160,701),('invalid-dnode-self',32*512+16,36),('hotfix-map-needed',8704+16,1)]:
        broken=bytearray(b);u32(broken,at,value);run(name,broken,False)
    report={'checks':len(checks),'passed':sum(c['ok'] for c in checks),'lifecycle_controls':lifecycle_controls,'results':checks};(root/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));return 0 if report['checks']==report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
