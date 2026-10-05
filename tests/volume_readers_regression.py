"""Independent on-disk fixtures for volume metadata, maps and decoders."""
import argparse,hashlib,json,lzma,struct,subprocess,zlib
from pathlib import Path

def put(b,at,fmt,*values): struct.pack_into(fmt,b,at,*values)
def tag(b,at,value): b[at:at+len(value)]=value
def raw_crc(b): return zlib.crc32(b,0xF597A6CF^0xFFFFFFFF)^0xFFFFFFFF
def seg(name,data=b'',flags=0):
    n=name.encode(); return b'AFF\0'+struct.pack('>III',len(n),len(data),flags)+n+data+b'ATT\0'+struct.pack('>I',24+len(n)+len(data))
def var(n):
    b=n.to_bytes(max(1,(n.bit_length()+7)//8),'big'); return bytes([len(b)])+b
def string(t):
    b=t.encode(); return bytes([len(b)])+b

def fixtures():
    result=[]
    def add(name,type,b,expected=None,geometry=None): result.append(dict(name=name,type=type,data=bytes(b),expected=expected,geometry=geometry))
    def fs(name,type,offset,magic,fmt='<I',size=65536,setup=None):
        b=bytearray(size); put(b,offset,fmt,magic)
        if setup: setup(b)
        add(name,type,b)
    for typ,name,at,m in [(2520,'atheos',1024,0x41465331),(2521,'beos',512,0x42465331)]:
        b=bytearray(8192); put(b,at+32,'<I',m); put(b,at+68,'<I',0xDD121031); put(b,at+112,'<I',0x15B6830E); put(b,at+40,'<I',1024); put(b,at+48,'<Q',8); tag(b,at,b'Volume1'); add(name,typ,b)
    b=bytearray(8192); tag(b,512+484,b'nonamenopack'); add('coherent',2522,b)
    for typ,name,magic in [(2523,'ods2',b'DECFILE11A  '),(2524,'rt11',b'DECRT11A    ')]:
        b=bytearray(8192); tag(b,1008,magic); add(name,typ,b)
    b=bytearray(8192); tag(b,768,b'VOL\x01VOL001'); b[843]=0x31; add('ecma67',2525,b)
    fs('f2fs',2526,1024,0xF2F52010,setup=lambda b:(put(b,1024+16,'<I',12),put(b,1024+36,'<Q',16)))
    fs('fossil',2527,131072,0x3776AE89,'>I',262144,lambda b:(put(b,131078,'>H',4096),put(b,131080,'>I',2),put(b,131092,'>I',64)))
    fs('hammer',2528,0,0xC8414D4DC5523031,'<Q')
    b=bytearray(8192); tag(b,54,b'HPOFS   '); put(b,11,'<H',512); put(b,32,'<I',16); add('hpofs',2529,b)
    fs('hp-lif',2530,0,0x8000,'>H',8192,lambda b:(put(b,8,'>I',2),put(b,16,'>I',1)))
    fs('jfs',2531,32768,0x3153464A,setup=lambda b:put(b,32784,'<I',4096))
    fs('linux-ext',2532,1080,0x137D,'<H',8192,lambda b:put(b,1028,'<I',8))
    fs('locus',2533,512,0xFFEEDDCD)
    fs('hpfs',2534,8192,0xF995E849,setup=lambda b:(put(b,8196,'<I',0xFA53E9C5),put(b,8208,'<I',128)))
    b=bytearray(8192); tag(b,3,b'ReFS\0\0\0\0'); tag(b,16,b'FSRS'); put(b,24,'<QII',16,512,1); add('refs',2535,b)
    fs('nilfs2',2536,1030,0x3434,'<H',8192,lambda b:(put(b,1032,'<H',256),put(b,1056,'<Q',8192)))
    fs('amiga-pfs',2537,1024,0x50465302,'>I')
    b=bytearray(8192); tag(b,512,b'/');
    for i in range(3): put(b,512+i*64+16,'<II',512,3); b[512+i*64+63]=1
    add('qnx4',2538,b)
    b=bytearray(131072); tag(b,65588,b'ReIsEr2Fs'); put(b,65536,'<I',32); put(b,65580,'<H',4096); add('reiserfs',2539,b)
    fs('sgi-efs',2540,540,0x72959,'>I',8192,lambda b:put(b,512,'>I',16))
    fs('amiga-sfs',2541,0,0x53465302,'>I')
    b=bytearray(8192); b[37]=0x29; tag(b,53,b'SOL_FS  '); add('solar',2542,b)
    fs('unicos',2543,0,0x6E6331667331636E,'>Q')
    fs('sysv',2544,1016,0xFD187E20)
    b=bytearray(8192); put(b,512,'<HIH',3,16,1); put(b,720,'<H',1); put(b,1088,'<HH',0x41ed,2); put(b,1096,'<I',32); add('unix-v7',2545,b)
    fs('unix-bfs',2546,0,0x1BADFACE,setup=lambda b:put(b,4,'<II',512,65535))
    fs('vxfs',2547,1024,0xA501FCF5)
    fs('vmfs',2548,1048576,0xC001D00D,size=2097152)
    fs('xenix',2549,1008,0x002B5544)
    fs('xia',2550,572,0x012FD16D,setup=lambda b:put(b,512,'<II',1024,64))
    b=bytearray(65536); tag(b,0,b'XFSB'); put(b,4,'>I',4096); put(b,8,'>Q',16); put(b,100,'>H',4); add('xfs',2551,b)
    fs('zfs',2552,8664,0x0210DA7AB10C7A11,'<Q')
    # Simple and hashed GFS2 directories, stuffed and direct file contents.
    def inode(b,number,mode,data=b'',height=0,flags=0):
        at=number*4096; put(b,at,'>II',0x01161970,4); put(b,at+24,'>QQI',number,number,mode); put(b,at+56,'>Q',len(data)); put(b,at+128,'>I',flags); put(b,at+138,'>H',height); tag(b,at+232,data)
    def dirent(number,name,record):
        n=name.encode(); b=bytearray(record); put(b,0,'>QQIHHHH',number,number,0,record,len(n),8,0); tag(b,40,n); return b
    for hashed in (False,True):
        b=bytearray(32*4096); put(b,65536,'>IIII',0x01161970,1,0,0); put(b,65560,'>I',1801); put(b,65572,'>I',4096); put(b,65624,'>Q',17)
        payload=b'GFS2 fixture content\n'; inode(b,18,0x81A4,payload)
        if not hashed: inode(b,17,0x41ED,dirent(17,'.',48)+dirent(17,'..',48)+dirent(18,'payload.txt',3744))
        else:
            inode(b,17,0x41ED,struct.pack('>QQ',19,19),flags=2); put(b,19*4096,'>II',0x01161970,6); tag(b,19*4096+104,dirent(18,'payload.txt',3992))
        add('gfs2-hash' if hashed else 'gfs2-stuffed',2553,b,{'payload.txt':payload})
    b=bytearray(32*4096); put(b,65536,'>IIII',0x01161970,1,0,0); put(b,65560,'>I',1801); put(b,65572,'>I',4096); put(b,65624,'>Q',17)
    inode(b,17,0x41ED,dirent(17,'.',48)+dirent(17,'..',48)+dirent(18,'sparse.bin',56)+dirent(22,'journal.bin',3688))
    sparse=b'A'*4096+b'\0'*4096+b'B'*1234; inode(b,18,0x81A4,struct.pack('>Q',19),height=2); put(b,18*4096+56,'>Q',len(sparse))
    put(b,19*4096,'>II',0x01161970,5); put(b,19*4096+24,'>QQQ',20,0,21); tag(b,20*4096,b'A'*4096); tag(b,21*4096,b'B'*1234)
    journal=b'J'*4500; inode(b,22,0x81A4,struct.pack('>QQ',23,24),height=1,flags=1); put(b,22*4096+56,'>Q',len(journal))
    for index,body in [(23,journal[:4072]),(24,journal[4072:])]: put(b,index*4096,'>II',0x01161970,7); tag(b,index*4096+24,body)
    add('gfs2-indirect-sparse-journal',2553,b,{'sparse.bin':sparse,'journal.bin':journal})
    # COFF/TE section extraction.
    b=bytearray(96); put(b,0,'<HHIIIHH',0x8664,1,0,0,0,0,0); tag(b,20,b'.text'); put(b,36,'<II',8,64); tag(b,64,b'COFFDATA'); add('coff',2502,b,{'0000-section-00-.text.bin':b'COFFDATA'})
    b=bytearray(96); put(b,0,'<HHBBH',0x5A56,0x8664,1,10,0x100); tag(b,40,b'.text'); put(b,56,'<II',8,296); tag(b,80,b'TE-DATA!'); add('te',2503,b,{'0000-section-00-.text.bin':b'TE-DATA!'})
    # Android LP checksummed metadata: two linear sectors around a zero sector.
    b=bytearray(32768); geom=bytearray(52); put(geom,0,'<II',0x616C4467,52); put(geom,40,'<III',4096,1,4096); tag(geom,8,hashlib.sha256(geom).digest()); tag(b,4096,geom); tag(b,8192,geom)
    tables=bytearray(236); tag(tables,0,b'system'); put(tables,36,'<IIII',1,0,3,0)
    for i,(num,kind,source) in enumerate([(1,0,32),(1,1,0),(1,0,34)]): put(tables,52+i*24,'<QIQI',num,kind,source,0)
    tag(tables,124,b'default'); put(tables,172,'<QIIQ',32,512,0,32768); tag(tables,196,b'super')
    header=bytearray(128); put(header,0,'<IHHI',0x414C5030,10,0,128); put(header,44,'<I',236); tag(header,48,hashlib.sha256(tables).digest())
    for offset,values in [(80,(0,1,52)),(92,(52,3,24)),(104,(124,1,48)),(116,(172,1,64))]: put(header,offset,'<III',*values)
    tag(header,12,hashlib.sha256(header).digest()); tag(b,12288,header+tables); tag(b,16384,b'A'*512); tag(b,17408,b'B'*512); add('android-lp',2500,b,{'0000-system':b'A'*512+b'\0'*512+b'B'*512})
    # LVM2 arbitrary VG name and two source extents in reversed physical order.
    b=bytearray(32768); identity='abcdefghijklmnopqrstuvwx12345678'
    text=f'''contents = "Text Format Volume Group"
researchvg {{ extent_size = 4
physical_volumes {{ pv0 {{ id = "{identity}" pe_start = 32 pe_count = 4 }} }}
logical_volumes {{ data {{ segment_count = 2
segment1 {{ start_extent = 0 extent_count = 1 type = "striped" stripe_count = 1 stripes = ["pv0", 1] }}
segment2 {{ start_extent = 1 extent_count = 1 type = "striped" stripe_count = 1 stripes = ["pv0", 0] }} }} }} }}
'''.encode()+b'\0'
    label=bytearray(512); tag(label,0,b'LABELONE'); put(label,8,'<Q',1); put(label,20,'<I',32); tag(label,24,b'LVM2 001'); tag(label,32,identity.encode()); put(label,64,'<Q',32768); put(label,72,'<QQ',16384,8192); put(label,104,'<QQ',4096,4096); put(label,16,'<I',raw_crc(label[20:])); tag(b,512,label)
    md=bytearray(512); tag(md,4,b' LVM2 x[5A%r0N*>'); put(md,20,'<IQQ',1,4096,4096); put(md,40,'<QQII',512,len(text),raw_crc(text),0); put(md,0,'<I',raw_crc(md[4:])); tag(b,4096,md); tag(b,4608,text); tag(b,16384,b'P'*2048); tag(b,18432,b'Q'*2048); add('lvm2',2501,b,{'0000-data.img':b'Q'*2048+b'P'*2048})
    # AFF stored, zlib, LZMA and zero pages, and a revised stored page.
    pages=[b'A'*512,b'ZLIB'*128,b'LZMA'*128,b'\0'*512]
    aff=b'AFF10\r\n\0'+seg('pagesize',flags=512)+seg('imagesize',struct.pack('>II',2048,0),2)+seg('page0',b'old'*170+b'xx')+seg('page0',pages[0])+seg('page1',zlib.compress(pages[1]),1)+seg('page2',lzma.compress(pages[2],format=lzma.FORMAT_ALONE),0x21)+seg('page3',struct.pack('>I',512),0x31)
    # AFF producers use a known output size rather than LZMA-alone's unknown marker.
    index=aff.index(b'page2')+5; a=bytearray(aff); put(a,index+5,'<Q',512); add('aff',2580,a,{'0000-image.raw':b''.join(pages)})
    # MD RAID1 clean synchronized component.
    b=bytearray(16384); put(b,0,'<III',0xA92B4EFC,1,0); tag(b,32,b'array-fixture'); put(b,72,'<IIQII',1,0,4,0,2); put(b,128,'<QQQ',16,16,0); put(b,208,'<Q',0xFFFFFFFFFFFFFFFF); put(b,220,'<I',2); put(b,256,'<HH',0,1)
    checksum=sum(struct.unpack('<65I',b[:260])); put(b,216,'<I',(checksum&0xFFFFFFFF)+(checksum>>32)); tag(b,8192,b'M'*2048); add('md-raid1',2581,b,{'0000-array.img':b'M'*2048})
    for endian in ('<','>'):
        b=bytearray(262144); sb=bytearray(4096); put(sb,0,endian+'III',0xA92B4EFC,0,90); put(sb,28,endian+'IIII',1,8,2,2); put(sb,132,endian+'I',1); put(sb,3980,endian+'II',0,6)
        checksum=sum(struct.unpack(endian+'1024I',sb)); put(sb,152,endian+'I',(checksum&0xFFFFFFFF)+(checksum>>32)); tag(b,196608,sb); tag(b,0,b'R'*8192)
        add('md90-be' if endian=='>' else 'md90-le',2581,b,{'0000-array.img':b'R'*8192})
    # LDM v2.12 committed database, two noncontiguous physical segments.
    b=bytearray(49152); disk_uuid='12345678-1234-5678-9abc-123456789abc'
    tag(b,3072,b'PRIVHEAD'); put(b,3084,'>HH',2,12); tag(b,3120,disk_uuid.encode()); put(b,3355,'>QQQQ',16,32,64,32)
    toc=bytearray(512); tag(toc,0,b'TOCBLOCK'); tag(toc,36,b'config\0'); put(toc,46,'>QQ',17,14); tag(toc,70,b'log\0'); put(toc,80,'>QQ',31,1); tag(b,65*512,toc); tag(b,66*512,toc)
    vm=64*512+17*512; tag(b,vm,b'VMDB'); put(b,vm+4,'>IIIHHH',9,128,512,1,4,10)
    def record(typ,identity,name):
        p=bytearray(128); tag(p,0,b'VBLK'); put(p,14,'>H',1); p[19]=typ; values=var(identity)+string(name); tag(p,24,values); return p,24+len(values)
    disk,at=record(0x34,1,'disk'); values=string(disk_uuid)+string('disk'); tag(disk,at,values); put(disk,20,'>I',12+at+len(values)-24)
    component,at=record(0x32,3,'component'); tag(component,at,string('ACTIVE')); at+=7; component[at]=2; tag(component,at+5,var(2)); tag(component,at+23,var(2)); put(component,20,'>I',22+(at-24)+4)
    volume,at=record(0x51,2,'data'); tag(volume,at,string('gen')+string('')); at+=5; tag(volume,at+21,var(1)); tag(volume,at+39,var(3)); put(volume,20,'>I',58+(at+4-24))
    def partition(identity,start,logical,size):
        p,at=record(0x33,identity,'part'); put(p,at+12,'>QQ',start,logical); values=var(size)+var(3)+var(1); tag(p,at+28,values); put(p,20,'>I',28+(at-24)+len(values)); return p
    for index,p in enumerate([disk,component,volume,partition(4,8,0,2),partition(5,2,2,1)]): tag(b,vm+512+index*128,p)
    tag(b,24*512,b'L'*1024); tag(b,18*512,b'D'*512); add('ldm-spanned',2582,b,{'0000-data.img':b'L'*1024+b'D'*512})
    # Partition-map specimens use independently placed payload markers.
    def part(name,type,at,setup,size=65536,geometry=None):
        b=bytearray(size); setup(b); tag(b,32768,b'partition-data'); add(name,type,b,geometry=geometry)
    part('dec-label',2563,15872,lambda b:(put(b,16312,'<II',0x032957,1),put(b,16320,'<II',1,64)))
    def bsd64(b):
        put(b,512,'<IIII',0xC4464C59,0,512,1); put(b,712,'<QQ',32768,512); put(b,516,'<I',zlib.crc32(b[512:776]))
    part('bsd64',2564,0,bsd64)
    part('human68k',2565,2048,lambda b:(tag(b,2048,b'X68K'),tag(b,2064,b'Human'),put(b,2072,'>II',32,1)))
    part('minix',2566,0,lambda b:(put(b,510,'<H',0xAA55),tag(b,450,b'\x81'),put(b,454,'<II',64,1)))
    part('next',2568,0,lambda b:(tag(b,0,b'dlV3'),put(b,92,'>I',512),put(b,190,'>II',64,1)))
    part('plan9',2569,512,lambda b:tag(b,512,b'part data 64 65\n'))
    part('rio-karma',2570,0,lambda b:(put(b,510,'<H',0xAB56),tag(b,274,b'M'),put(b,278,'<II',64,1)))
    def sgi(b):
        put(b,0,'>I',0x0BE5A941); put(b,40,'>H',512); put(b,312,'>III',1,64,10); checksum=sum(struct.unpack('>128I',b[:512]))&0xFFFFFFFF; put(b,504,'>I',(-checksum)&0xFFFFFFFF)
    part('sgi-header',2571,0,sgi)
    part('xenix-table',2573,42*512,lambda b:(put(b,21504,'<H',0x1234),put(b,21506,'<II',0,1)),size=1048576)
    part('atari-ahdi',2562,0,lambda b:(put(b,450,'>I',128),tag(b,454,b'\x01GEM'),put(b,458,'>II',64,1)))
    b=bytearray(65536); put(b,450,'>I',128); tag(b,454,b'\x01XGM'); put(b,458,'>II',16,64)
    tag(b,16*512+454,b'\x01GEM'); put(b,16*512+458,'>II',48,1); tag(b,16*512+466,b'\x01XGM'); put(b,16*512+470,'>II',2,48)
    tag(b,18*512+454,b'\x01GEM'); put(b,18*512+458,'>II',50,1); tag(b,32768,b'X'*512); tag(b,34816,b'Y'*512)
    add('atari-xgm-chain',2562,b,{'0000-partition-00-GEM.img':b'X'*512,'0001-partition-01-GEM.img':b'Y'*512})
    def apricot(b):
        b[8]=1; b[11]=2; b[12]=1; b[13]=1; put(b,14,'<HHI',512,8,8); b[22]=2; put(b,320,'<H',512); put(b,328,'<H',1); put(b,334,'<H',64)
    part('apricot-table',2561,0,apricot)
    def acorn(b):
        b[3520]=9; b[3521]=8; b[3522]=2; b[3580]=9; put(b,3581,'<H',1); total=0
        for v in b[3072:3583]: total=(total&255)+(total>>8)+v
        total=(total&255)+(total>>8); b[3583]=total&255; put(b,8192,'<III',0xDEAFA1DE,48,1)
    part('acorn-linux',2560,3072,acorn)
    def pc98(b):
        put(b,510,'<H',0xAA55); b[512]=0xA0; b[513]=0x81; put(b,522,'<H',4); put(b,526,'<H',4); tag(b,528,b'PC98')
    part('pc98-table',2567,512,pc98,geometry=(512,2,8))
    return result

def main():
    p=argparse.ArgumentParser(); p.add_argument('--probe',required=True); p.add_argument('--root',required=True); p.add_argument('--unpacker'); a=p.parse_args(); root=Path(a.root); root.mkdir(parents=True,exist_ok=True)
    checks=[]
    def run(args,success,name):
        r=subprocess.run(args,capture_output=True,text=True,timeout=60); good=(r.returncode==0)==success
        checks.append(dict(name=name,passed=good,returncode=r.returncode,stderr=r.stderr[-2048:],stdout=r.stdout[-1024:] if not good else ''))
        return good
    for fixture in fixtures():
        name=fixture['name']; path=root/(name+'.img'); path.write_bytes(fixture['data']); geom=['']+[str(x) for x in fixture['geometry']] if fixture['geometry'] else []
        # These deliberately contain identity fields only. File traversal is
        # covered by the separate filesystem suites; missing trees must fail.
        identity_only_types=set(range(2520,2553))-{2530,2545}  # Valid empty LIF/V7 directories.
        mode='i' if fixture['type'] in identity_only_types else 't'
        run([a.probe,mode,str(fixture['type']),str(path)]+geom,True,name+(' identity' if mode=='i' else ' RAM test'))
        if fixture['type'] not in (2522,2545,2561,2566,2567): run([a.probe,'d',str(fixture['type']),str(path)]+geom,True,name+' detection gate')
        if mode=='i': run([a.probe,'t',str(fixture['type']),str(path)]+geom,False,name+' incomplete filesystem rejected')
        if fixture['expected']:
            dest=root/(name+'-output'); dest.mkdir(exist_ok=True)
            if run([a.probe,'x',str(fixture['type']),str(path),str(dest)]+(geom[1:] if geom else []),True,name+' extract'):
                for file,data in fixture['expected'].items(): checks.append(dict(name=name+' bytes '+file,passed=(dest/file).exists() and (dest/file).read_bytes()==data))
        # A truncated image cannot claim intact extents or expected page outputs.
        if fixture['type'] in (2500,2501,2502,2503,2580,2581,2553):
            bad=root/(name+'-truncated.img'); bad.write_bytes(fixture['data'][:len(fixture['data'])//2]); run([a.probe,'t',str(fixture['type']),str(bad)],False,name+' truncated')
        if name=='gfs2-hash':
            bad=root/'gfs2-leaf-self-cycle.img'; data=bytearray(fixture['data']); put(data,19*4096+32,'>Q',19); bad.write_bytes(data)
            run([a.probe,'t','2553',str(bad)],False,'GFS2 next-leaf cycle rejected')
        if name=='ldm-spanned':
            for offset in (513,7679):
                bad=root/f'ldm-unaligned-vblk-{offset}.img'; data=bytearray(fixture['data']); put(data,64*512+17*512+12,'>I',offset); bad.write_bytes(data)
                run([a.probe,'t','2582',str(bad)],False,'LDM partial/unaligned VBLK rejected '+str(offset))
        if name=='lvm2':
            for label,old,new in [('missing-segment',b'segment_count = 2',b'segment_count = 3'),('duplicate-segment',b'segment2 {',b'segment1 {')]:
                data=bytearray(fixture['data']); length=struct.unpack_from('<Q',data,4096+48)[0]
                metadata=bytes(data[4608:4608+length]); assert old in metadata; metadata=metadata.replace(old,new,1)
                data[4608:4608+length]=metadata; put(data,4096+56,'<I',raw_crc(metadata)); put(data,4096,'<I',raw_crc(data[4100:4608]))
                bad=root/f'lvm-{label}.img'; bad.write_bytes(data)
                run([a.probe,'t','2501',str(bad)],False,'LVM checksummed '+label+' rejected')
    report=dict(verified=all(c['passed'] for c in checks),checks=checks,count=len(checks),failed=sum(not c['passed'] for c in checks))
    (root/'verification.json').write_text(json.dumps(report,indent=2)); print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
    for c in checks:
        if not c['passed']: print(c)
    return 0 if report['verified'] else 1
if __name__=='__main__': raise SystemExit(main())
