#!/usr/bin/env python3
"""Independent native Apple/archive/filesystem fixtures; payloads are never run.

The C probe enters the library's RAM-only I/O scope before opening the source,
verifies every member with a NULL destination, then hashes a RAM extraction.
Each expected byte string below is generated independently of reader code.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib


HELLO = b"HELLO"
def put(b, at, value, fmt="<H"):
    struct.pack_into(fmt, b, at, value)
def crc16(b, seed=0):
    c = seed
    for x in b:
        c ^= x << 8
        for _ in range(8):
            c = ((c << 1) ^ (0x1021 if c & 0x8000 else 0)) & 65535
    return c
def mutation(b, at, new):
    c = bytearray(b); c[at:at+len(new)] = new; return bytes(c)
def high(s, n):
    return bytes(x | 128 for x in s.ljust(n, b" "))


def dos(tracks=35, sectors=16, payload=HELLO):
    b = bytearray(tracks * sectors * 256)
    v = 17 * sectors * 256
    b[v+1:v+4] = bytes((17, sectors-1, 2 if sectors == 13 else 3))
    b[v+6] = 254; b[v+39] = 122; b[v+48:v+50] = bytes((18, 1))
    b[v+52:v+54] = bytes((tracks, sectors)); put(b, v+54, 256)
    e = (17*sectors + sectors-1)*256 + 11
    t = tracks-1 if tracks == 80 else 18
    b[e:e+3] = bytes((t, 1, 0)); b[e+3:e+33] = high(b"HELLO", 30); put(b,e+33,2)
    a = (t*sectors+1)*256
    b[a+12:a+14] = bytes((t,2))
    a = (t*sectors+2)*256
    b[a:a+len(payload)] = payload
    return bytes(b)


def pascal(blocks=8, payload=HELLO):
    b=bytearray(blocks*512); a=1024
    put(b,a+2,6); b[a+6:a+12]=b"\x05PTEST"; put(b,a+14,blocks); put(b,a+16,1)
    a+=26; put(b,a,6); put(b,a+2,7); put(b,a+4,3)
    b[a+6:a+12]=b"\x05HELLO"; put(b,a+22,len(payload))
    b[3072:3072+len(payload)]=payload; return bytes(b)


def prodos(blocks=16, ppm=False):
    b=bytearray(blocks*512); a=1024
    b[a+4:a+9]=b"\xf4TEST"; b[a+35:a+37]=b"\x27\x0d"
    put(b,a+37,2 if ppm else 1); put(b,a+39,3); put(b,a+41,blocks)
    e=a+43; b[e:e+6]=b"\x15HELLO"; b[e+16]=6; put(b,e+17,4); put(b,e+19,1)
    b[e+21:e+24]=b"\x05\0\0"; put(b,e+37,2); b[2048:2053]=HELLO
    if ppm:
        e+=39; b[e:e+12]=b"\x4bPASCAL.AREA"; b[e+16]=0xef
        put(b,e+17,8); put(b,e+19,10); b[e+21:e+24]=(5120).to_bytes(3,"little"); put(b,e+37,2)
        a=4096; put(b,a,10); put(b,a+2,1); b[a+4:a+8]=b"\x03PPM"
        put(b,a+16,10); put(b,a+18,8); b[5120:9216]=pascal()
    return bytes(b)


def cpm_hybrid(empty=False, reserved=False):
    """Apple CP/M directory uses its independently documented DOS sector skew.
    File sizes retain CP/M's 128-byte record granularity and its padding.
    """
    b=bytearray(dos()); order=(0,6,12,3,9,15,14,5,11,2,8,7,13,4,10,1)
    directory=bytearray(b"\xe5"*2048)
    if not empty:
        directory[:32]=b"\0"*32; directory[1:12]=b"HELLO   TXT"; directory[15]=1
        directory[16]=1 if reserved else 2
    for logical in range(8):
        at=(3*16+order[logical])*256; b[at:at+256]=directory[logical*256:(logical+1)*256]
    at=(3*16+order[8])*256; b[at:at+128]=HELLO.ljust(128,b"\0")
    return bytes(b)


def hfs():
    """One-file HFS with an empty extents tree and a three-record catalog."""
    b=bytearray(20*512); a=1024
    put(b,a,0x4244,">H"); put(b,a+12,1,">H"); put(b,a+14,3,">H")
    put(b,a+18,16,">H"); put(b,a+20,512,">I"); put(b,a+28,4,">H")
    put(b,a+34,12,">H"); b[a+36:a+41]=b"\x04TEST"; put(b,a+84,1,">I")
    put(b,a+130,512,">I"); put(b,a+134,0,">H"); put(b,a+136,1,">H")
    put(b,a+146,1024,">I"); put(b,a+150,1,">H"); put(b,a+152,2,">H")
    b[1536]=0xf0
    def tree_header(nodes, catalog):
        h=bytearray(512); h[8]=1; put(h,10,3,">H")
        if catalog:
            put(h,14,1,">H"); put(h,16,1,">I"); put(h,20,3,">I")
            put(h,24,1,">I"); put(h,28,1,">I")
        put(h,32,512,">H"); put(h,34,37 if catalog else 7,">H"); put(h,36,nodes,">I")
        h[248]=0xc0 if catalog else 0x80
        for i,v in enumerate((14,120,248,504)): put(h,510-2*i,v,">H")
        return h
    b[2048:2560]=tree_header(1,False); b[2560:3072]=tree_header(2,True)
    def key(parent,name):
        n=len(name); raw=bytearray(((n+6+2)//2)*2)
        raw[0]=n+6; put(raw,2,parent,">I"); raw[6]=n; raw[7:7+n]=name; return raw
    directory=bytearray(70); put(directory,0,0x100,">H"); put(directory,4,1,">H"); put(directory,6,2,">I")
    thread=bytearray(46); put(thread,0,0x300,">H"); put(thread,10,1,">I"); thread[14:19]=b"\x04TEST"
    f=bytearray(102); put(f,0,0x200,">H"); put(f,20,16,">I")
    put(f,26,5,">I"); put(f,30,512,">I"); put(f,74,3,">H"); put(f,76,1,">H")
    records=(key(1,b"TEST")+directory,key(2,b"")+thread,key(2,b"HELLO")+f)
    node=bytearray(512); node[8:10]=b"\xff\x01"; put(node,10,3,">H"); at=14
    for i,r in enumerate(records):
        put(node,510-2*i,at,">H"); node[at:at+len(r)]=r; at+=len(r)
    put(node,504,at,">H"); b[3072:3584]=node; b[3584:3589]=HELLO
    return bytes(b)


def acu(payload=HELLO, squeezed=False, name=b"HELLO",flush=b""):
    h=bytearray(20); put(h,0,1); h[4:9]=b"fZink"; h[9]=1; put(h,10,54)
    r=bytearray(54); packed=payload
    if squeezed:
        # Two leaves encode literal A and EOF; five zero bits followed by one.
        assert payload == b"AAAAA"
        packed=struct.pack("<HhhB",1,-66,-257,32)+flush; r[1]=3
    put(r,4,crc16(payload)); put(r,18,len(packed),"<I"); put(r,38,len(payload),"<I")
    put(r,32,1); put(r,50,len(name)); put(r,52,crc16(r[:52]+name))
    return bytes(h+r+name+packed)


def nufx(payload=HELLO, method=0, packed=None, version=3):
    if packed is None: packed=payload
    h=bytearray(48); h[:6]=b"N\xf5F\xe9l\xe5"; put(h,8,1,"<I"); put(h,28,2)
    r=bytearray(60); r[:4]=b"N\xf5F\xd8"; put(r,6,60); put(r,8,version); put(r,10,1,"<I"); put(r,58,5)
    t=struct.pack("<HHHHII",2,method,0,crc16(packed if version==2 else payload,65535),len(payload),len(packed))
    put(r,4,crc16(r[6:]+b"HELLO"+t)); out=h+r+b"HELLO"+t+packed
    put(out,38,len(out),"<I"); put(out,6,crc16(out[8:48])); return bytes(out)


def lzw_codes(raw, start=257):
    """Independent literal-only LZW stream with explicit table resets."""
    out=bytearray(); acc=bits=0; entry=start
    def emit(code,width):
        nonlocal acc,bits
        acc|=code<<bits; bits+=width
        while bits>=8: out.append(acc&255); acc>>=8; bits-=8
    have_previous=False
    for i,x in enumerate(raw):
        width=max(9,(entry+1).bit_length())
        if entry>=4095: emit(256,width); entry=257; width=9; have_previous=False
        emit(x,width)
        if have_previous:entry+=1
        have_previous=True
    if bits: out.append(acc&255)
    return bytes(out)


def nulzw(payload,method):
    padded=payload.ljust(4096,b"\0"); codes=lzw_codes(padded)
    if method==2:
        return struct.pack("<HBBHB",crc16(padded),254,0xdb,4096,1)+codes
    return bytes((254,0xdb))+struct.pack("<HH",0x9000,len(codes)+4)+codes


def gutenberg(po=False):
    b=bytearray(143360)
    def sector(t,s):
        idx=[0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15][s] if po else s
        return (t*16+idx)*256
    a=sector(17,7); b[a+2:a+6]=bytes((17,0x87,0x91,7)); b[a+6:a+15]=high(b"TEST",9); b[a+15]=0x8d
    e=a+16; b[e:e+12]=high(b"DIR",12); b[e+12:e+16]=bytes((17,7,ord("M")|128,0x8d))
    e+=16; b[e:e+12]=high(b"HELLO",12); b[e+12:e+16]=bytes((18,1,ord(" ")|128,0x8d))
    a2=sector(18,1); b[a2+2:a2+6]=bytes((18,0x81,0x92,1)); b[a2+6:a2+11]=HELLO
    return bytes(b),{"DIR":bytes(b[a+6:a+256]),"HELLO":HELLO}


def rdos(variant):
    physical=13 if variant==1 else 16; logical=16 if variant==2 else 13
    b=bytearray(35*physical*256); a=physical*256
    b[a:a+24]=high(b"RDOS 3.3 COPYRIGHT 1986" if variant==2 else b"RDOS 2.1 COPYRIGHT 1981",24); b[a+24]=0xa0
    a+=32; b[a:a+24]=high(b"HELLO",24); b[a+24]=ord("T")|128; b[a+25]=1; put(b,a+28,5); put(b,a+30,40)
    a=(40//logical*physical+40%logical)*256; b[a:a+5]=HELLO; return bytes(b)


GCR=(0x96,0x97,0x9a,0x9b,0x9d,0x9e,0x9f,0xa6,0xa7,0xab,0xac,0xad,0xae,0xaf,0xb2,0xb3,0xb4,0xb5,0xb6,0xb7,0xb9,0xba,0xbb,0xbc,0xbd,0xbe,0xbf,0xcb,0xcd,0xce,0xcf,0xd3,0xd6,0xd7,0xd9,0xda,0xdb,0xdc,0xdd,0xde,0xdf,0xe5,0xe6,0xe7,0xe9,0xea,0xeb,0xec,0xed,0xee,0xef,0xf2,0xf3,0xf4,0xf5,0xf6,0xf7,0xf9,0xfa,0xfb,0xfc,0xfd,0xfe,0xff)
DOS_ORDER=(0,7,14,6,13,5,12,4,11,3,10,2,9,1,8,15)
def gcr(data):
    aux=[0]*86
    for i,x in enumerate(data): aux[i%86]|=((x&1)<<1 | (x&2)>>1)<<(2*(i//86))
    vals=aux+[x>>2 for x in data]; prev=0; out=bytearray()
    for x in vals: out.append(GCR[x^prev]); prev=x
    out+=bytes((GCR[prev],0xde,0xaa,0xeb)); return out
def nibble_tracks(image, tracks=35, stride=6384):
    out=[]
    for t in range(tracks):
        raw=bytearray()
        for p in range(16):
            addr=bytes((254,t,p,254^t^p)); encoded=b"".join(bytes(((x>>1)|0xaa,x|0xaa)) for x in addr)
            raw+=b"\xff"*6+b"\xd5\xaa\x96"+encoded+b"\xde\xaa\xeb"+b"\xff"*8+b"\xd5\xaa\xad"
            s=DOS_ORDER[p]; raw+=gcr(image[(t*16+s)*256:(t*16+s+1)*256]); raw+=b"\xff"*2
        assert len(raw)<=stride
        out.append(bytes(raw).ljust(stride,b"\xff"))
    return out
def trackstar(tracks):
    out=bytearray(40*6656)
    for i,raw in enumerate(tracks):
        a=i*6656; out[a:a+6]=b"TEST  "; put(out,a+6654,len(raw)); out[a+129:a+129+len(raw)]=raw[::-1]
    return bytes(out)
def woz(tracks):
    info=bytearray(60); info[:2]=b"\x01\x01"
    table=bytearray(b"\xff"*160)
    for i in range(len(tracks)): table[4*i]=i
    trks=bytearray()
    for raw in tracks:
        r=bytearray(6656); r[:len(raw)]=raw; put(r,6646,len(raw)); put(r,6648,len(raw)*8); put(r,6650,65535); trks+=r
    body=b"INFO"+struct.pack("<I",60)+info+b"TMAP"+struct.pack("<I",160)+table+b"TRKS"+struct.pack("<I",len(trks))+trks
    return b"WOZ1\xff\x0a\x0d\x0a"+struct.pack("<I",zlib.crc32(body))+body


def bsd(big=False):
    b=bytearray(16*512); endian=">" if big else "<"; a=512
    for o in (0,132): put(b,a+o,0x82564557,endian+"I")
    put(b,a+40,512,endian+"I"); put(b,a+60,16,endian+"I"); put(b,a+138,2,endian+"H")
    put(b,a+148,2,endian+"I"); put(b,a+152,8,endian+"I"); b[a+160]=7
    checksum=0
    for i in range(0,180,2): checksum ^= struct.unpack_from(endian+"H",b,a+i)[0]
    put(b,a+136,checksum,endian+"H"); data=bytes(range(256))*4; b[4096:5120]=data
    return bytes(b),data


def opera(payload=HELLO, burst=0):
    b=bytearray(8*2048); b[:8]=b"\x01ZZZZZ\x01\0"
    for o,v in ((76,2048),(80,8),(88,1),(92,2048),(96,0),(100,1)): put(b,o,v,">I")
    a=2048; put(b,a,65535 if False else 0xffffffff,">I"); put(b,a+4,0xffffffff,">I")
    put(b,a+12,92,">I"); put(b,a+16,20,">I"); e=a+20
    for o,v in ((0,0xc0000000),(4,16),(12,2048),(16,len(payload)),(20,1),(24,burst),(28,0),(64,0),(68,2)): put(b,e+o,v,">I")
    b[e+32:e+37]=b"HELLO"; b[4096:4096+len(payload)]=payload; return bytes(b)


def cdi(form2=False,raw=False,subdir=False):
    b=bytearray(32*2048); a=16*2048; b[a:a+15]=b"\x01CD-I \x01\0CD-RTOS"
    for o,v,fmt in ((84,32,">I"),(130,2048,">H"),(136,10,">I"),(148,18,">I")): put(b,a+o,v,fmt)
    b[a+881]=1; a=17*2048; b[a:a+7]=b"\xffCD-I \x01"
    a=18*2048; b[a]=1; put(b,a+2,19,">I"); put(b,a+6,1,">H")
    def entry(name,extent,size,directory=False):
        tail=33+len(name)+(not len(name)&1); e=bytearray(tail+10); e[0]=len(e); e[32]=len(name); e[33:33+len(name)]=name
        put(e,6,extent,">I"); put(e,14,size,">I"); put(e,tail+4,0x8000 if directory else 0x0555,">H"); return e
    entries=entry(b"\0",19,2048,True)+entry(b"\1",19,2048,True)+entry(b"HELLO",20,2048 if form2 else 5)
    if subdir:
        entries+=entry(b"SUB",21,2048,True)
        child=entry(b"\0",21,2048,True)+entry(b"\1",19,2048,True)+entry(b"HELLO",22,5)
        b[21*2048:21*2048+len(child)]=child; b[22*2048:22*2048+5]=HELLO
        put(b,16*2048+136,22,">I"); a=18*2048+10; b[a]=3
        put(b,a+2,21,">I"); put(b,a+6,1,">H"); b[a+8:a+11]=b"SUB"
    b[19*2048:19*2048+len(entries)]=entries; b[20*2048:20*2048+5]=HELLO
    if not raw:return bytes(b),HELLO
    def edc(p):
        c=0
        for x in p:
            c^=x
            for _ in range(8):c=(c>>1)^(0xd8018001 if c&1 else 0)
        return c
    result=bytearray(); media=None
    for i in range(32):
        sector=bytearray(2352); sector[:12]=b"\0"+b"\xff"*10+b"\0"; sector[15]=2
        sub=bytes((0,0,0x28 if form2 and i==20 else 8,0)); sector[16:24]=sub*2; sector[24:2072]=b[i*2048:(i+1)*2048]
        if not form2 or i!=20:put(sector,2072,edc(sector[16:2072]),"<I")
        else:media=bytes(sector[16:])
        result+=sector
    return bytes(result),media if form2 else HELLO


def dc42_checksum(b):
    c=0
    for i in range(0,len(b),2):
        c=(c+int.from_bytes(b[i:i+2],"big"))&0xffffffff; c=((c>>1)|(c<<31))&0xffffffff
    return c
def lisa(version=15):
    data=bytearray(80*512); tags=bytearray(80*12); base=1
    put(data,4,0xaaaa,">H"); put(data,6,0x850,">H"); put(data,14,base,">H")
    a=512; put(data,a,version,">H"); data[a+12:a+17]=b"\x04TEST"
    for o,v,fmt in ((108,1,">I"),(120,80,">I"),(126,512,">H"),(148,2,">I"),(152,36,">H"),(154,1,">H"),(160,36,">H")):put(data,a+o,v,fmt)
    def tag(page,id,rel=0,next=0x7ff,prev=0x7ff):
        at=(base+page)*12; put(tags,at+4,id&65535,">H"); put(tags,at+6,rel,">H"); put(tags,at+8,next,">H"); put(tags,at+10,prev,">H")
    def srecord(id,page,size):
        at=(base+2)*512+id*14; put(data,at,page,">I"); put(data,at+8,size,">I")
    def leader(id,page,extent,count):
        tag(page,-id,next=page+1 if version==14 else 0x7ff)
        if version==14:tag(page+1,-id,1,prev=page)
        at=(base+page)*512+(0x208 if version==14 else 0x88); put(data,at,extent,">I"); put(data,at+4,count,">H")
    tag(2,3); srecord(5,6,5); leader(5,6,16,1); tag(16,5); data[(base+16)*512:(base+16)*512+5]=HELLO
    if version==17:
        put(data,512+302,20,">I"); node=bytearray(2048); node[0]=36; node[3:8]=b"HELLO"; node[36]=3
        put(node,38,5,">H"); put(node,48,5,">I"); put(node,2034,0,">H"); put(node,2036,1,">H"); put(node,2042,0xffffffff,">I")
        for i in range(4):tag(20+i,4,i,next=21+i if i<3 else 0x7ff,prev=19+i if i else 0x7ff)
        data[(base+20)*512:(base+24)*512]=node
    else:
        catalog=bytearray(54); catalog[:6]=b"\x05HELLO"; catalog[34]=3; put(catalog,36,5,">H")
        srecord(4,4,54); leader(4,4,10,1); tag(10,4); data[(base+10)*512:(base+10)*512+54]=catalog
    h=bytearray(84); h[:5]=b"\x04TEST"; put(h,64,len(data),">I"); put(h,68,len(tags),">I"); put(h,72,dc42_checksum(data),">I"); put(h,76,dc42_checksum(tags[12:]),">I"); put(h,82,0x100,">H")
    return bytes(h+data+tags)


def cassette(payload=HELLO,stereo=False,bad=False):
    checksum=255
    for x in payload:checksum^=x
    tape=payload+bytes((checksum^(1 if bad else 0),)); halves=[650]*1540+[200,250]
    for x in tape:
        for bit in range(7,-1,-1): halves.extend([500 if x>>bit&1 else 250]*2)
    rate=44100; samples=bytearray(); total=0; count=0; sign=1
    for usec in halves:
        total+=usec; end=round(total*rate/1_000_000); n=end-count; count=end
        frame=struct.pack("<h",sign*20000)
        if stereo:frame=struct.pack("<hh",0,sign*20000)
        samples+=frame*n; sign=-sign
    samples+=(b"\0\0\0\0" if stereo else b"\0\0")*100
    channels=2 if stereo else 1
    fmt=struct.pack("<HHIIHH",1,channels,rate,rate*channels*2,channels*2,16)
    body=b"WAVEfmt "+struct.pack("<I",16)+fmt+b"data"+struct.pack("<I",len(samples))+samples
    return b"RIFF"+struct.pack("<I",len(body))+body


def cases():
    # tuple(label, reader, bytes, expected exact members or None, profile, candidate)
    yield "acu-stored","applelink_pe",acu(),{"HELLO":HELLO},0,True
    yield "acu-squeeze","applelink_pe",acu(b"AAAAA",True),{"HELLO":b"AAAAA"},0,True
    yield "acu-squeeze-ff-flush","applelink_pe",acu(b"AAAAA",True,flush=b"\xff"),{"HELLO":b"AAAAA"},0,True
    yield "acu-squeeze-extra-two","applelink_pe",acu(b"AAAAA",True,flush=b"\xff\xff"),None,0,True
    yield "acu-header-crc","applelink_pe",mutation(acu(),25,b"\1"),None,0,True
    yield "acu-data-crc","applelink_pe",mutation(acu(),79,b"X"),None,0,True
    yield "acu-traversal","applelink_pe",acu(name=b"../evil"),None,0,True
    for method in (0,1,2,3):
        payload=b"AAAAA" if method==1 else HELLO
        packed=struct.pack("<HhhB",1,-66,-257,32) if method==1 else nulzw(payload,method) if method>=2 else payload
        for version in (2,3):
            yield f"nufx-{method}-v{version}","nufx",nufx(payload,method,packed,version),{"0000-record-0-data.bin":payload},0,False
    yield "nufx-payload-crc","nufx",mutation(nufx(),129,b"X"),None,0,False
    yield "nufx-truncated","nufx",nufx()[:-1],None,0,False
    yield "dos80-high-track","apple_dos33",dos(80),{"HELLO":HELLO},0,False
    yield "prodos-seedling","prodos",prodos(),{"HELLO":HELLO},0,False
    for po in (False,True):
        data,expected=gutenberg(po)
        yield f"gutenberg-{po}","gutenberg",data,expected,2 if po else 1,True
    data,_=gutenberg(); yield "gutenberg-loop","gutenberg",mutation(data,(18*16+1)*256+4,b"\x12\x01"),None,1,True
    data,expected=gutenberg(); zero=bytearray(data); zero[(18*16)*256:(18*16+1)*256]=data[(18*16+1)*256:(18*16+2)*256]
    zero[(18*16+1)*256:(18*16+2)*256]=b"\0"*256
    a=(18*16)*256; zero[a+3]=0xc0; zero[a+5]=0x40; zero[(17*16+7)*256+16+16+13]=0x40
    expected={"DIR":bytes(zero[(17*16+7)*256+6:(17*16+8)*256]),"HELLO":HELLO}
    yield "gutenberg-sector-zero","gutenberg",bytes(zero),expected,1,True
    data,expected=gutenberg(); a=(17*16+7)*256; slash=mutation(data,a+6,high(b"/TEST/",9))
    yield "gutenberg-volume-slash","gutenberg",slash,{"DIR":slash[a+6:a+256],"HELLO":HELLO},1,True
    for v in (1,2,3):yield f"rdos-{v}","apple_rdos",rdos(v),{"HELLO":HELLO},0,True
    yield "rdos-oob","apple_rdos",mutation(rdos(1),13*256+32+30,b"\xff\xff"),None,0,True
    d=dos(50,32); volumes=d+d; expected={"VOLUME01/HELLO":HELLO,"VOLUME02/HELLO":HELLO}
    for name in ("amdos","unidos"):yield name,name,volumes,expected,0,False
    oz=b"".join(d[i:i+256]+d[i:i+256] for i in range(0,len(d),256))
    yield "ozdos","ozdos",oz,expected,0,False
    f=bytearray(3*512); f[:14]=b"Parsons Engin."; f[15]=1; put(f,32,3,"<I"); put(f,36,8,"<I")
    yield "focus","focusdrive",bytes(f)+pascal(),{"VOLUME01/HELLO":HELLO},0,True
    yield "focus-map-oob","focusdrive",mutation(bytes(f)+pascal(),36,b"\xff\xff\xff\xff"),None,0,True
    m=bytearray(256*512); put(m,0,0xccca); m[12]=1; put(m,32,256,"<I"); put(m,64,8|0xab000000,"<I")
    yield "micro","microdrive",bytes(m)+pascal(),{"VOLUME01/HELLO":HELLO},0,True
    t=bytearray(1024); put(t,0,0x4552,">H"); put(t,2,512,">H"); put(t,4,22,">I"); put(t,512,0x5453,">H")
    for o,v in ((514,2),(518,20),(522,0x54465331)):put(t,o,v,">I")
    yield "mac-ts","mac_ts",bytes(t)+hfs(),{"VOLUME01/HELLO":HELLO},0,True
    yield "ppm","pascal_profile_manager",prodos(18,True),{"PRODOS/HELLO":HELLO,"VOLUME01/HELLO":HELLO},0,True
    master=bytearray(prodos(16+280)); master[8192:]=dos()
    yield "dos-master","dos_master",bytes(master),{"PRODOS/HELLO":HELLO,"DOS01/HELLO":HELLO},143360,False
    yield "dos-master-profile-required","dos_master",bytes(master),None,0,False
    free=bytearray(master); free[1538]=0x80
    yield "dos-master-unallocated","dos_master",bytes(free),None,143360,False
    for tracks,sectors in ((40,16),(50,16),(50,32)):
        child=dos(tracks,sectors); master=bytearray(prodos(16+len(child)//512)); master[8192:]=child
        yield f"dos-master-{tracks}-{sectors}","dos_master",bytes(master),{"PRODOS/HELLO":HELLO,"DOS01/HELLO":HELLO},len(child),False
    hybrid=bytearray(dos()); p=pascal(280); blockmap=(0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15)
    # ProDOS/Pascal block sector order mapped into the DOS carrier.
    for block in (2,3,4,5,6):
        for half in (0,1):
            sec=block*2+half; at=(sec//16*16+blockmap[sec%16])*256
            hybrid[at:at+256]=p[sec*256:(sec+1)*256]
    yield "hybrid","apple_dos_hybrid",bytes(hybrid),{"DOS/HELLO":HELLO,"BLOCK/HELLO":HELLO},0,False
    yield "hybrid-cpm","apple_dos_hybrid",cpm_hybrid(),{"DOS/HELLO":HELLO,"CPM/USER00/HELLO.TXT":HELLO.ljust(128,b"\0")},0,False
    yield "hybrid-cpm-empty-ambiguous","apple_dos_hybrid",cpm_hybrid(empty=True),None,0,False
    yield "hybrid-cpm-reserved-allocation","apple_dos_hybrid",cpm_hybrid(reserved=True),None,0,False
    cp=bytearray(cpm_hybrid()); cp[1028]=0xf4; cp[1059]=39; cp[1060]=13
    yield "hybrid-cpm-damaged-identified-block-root","apple_dos_hybrid",bytes(cp),None,0,False
    for big in (False,True):
        data,expected=bsd(big); yield f"bsd-{big}","bsd_disklabel",data,{"partition-00-type-7.img":expected},0,True
    data,payload=bsd(); shifted=bytearray(data); label=data[512:692]; shifted[512:692]=b"\0"*180; shifted[400:580]=label
    yield "bsd-cross-sector-label","bsd_disklabel",bytes(shifted),{"partition-00-type-7.img":payload},0,True
    yield "bsd-checksum","bsd_disklabel",mutation(bsd()[0],512+40,b"\1"),None,0,True
    yield "opera","opera_fs",opera(),{"HELLO":HELLO},0,True
    yield "opera-avatar-oob","opera_fs",mutation(opera(),2048+20+68,b"\xff\xff\xff\xff"),None,0,True
    for raw,form2 in ((False,False),(True,False),(True,True)):
        data,expected=cdi(form2,raw); yield f"cdi-{raw}-{form2}","cdi_fs",data,{"HELLO.cdi-sectors" if form2 else "HELLO":expected},0,True
    yield "cdi-edc","cdi_fs",mutation(cdi(False,True)[0],20*2352+24,b"X"),None,0,True
    yield "cdi-pathtable-oob","cdi_fs",mutation(cdi()[0],16*2048+148,b"\xff\xff\xff\xff"),None,0,True
    data,_=cdi(subdir=True)
    yield "cdi-subdirectory","cdi_fs",data,{"HELLO":HELLO,"SUB/HELLO":HELLO},0,True
    yield "cdi-duplicated-path-extent","cdi_fs",mutation(data,18*2048+12,struct.pack(">I",19)),None,0,True
    for version in (14,15,17):yield f"lisa-{version}","lisa_fs",lisa(version),{"HELLO":HELLO},0,True
    for pad in (0x01,0x5a,0xff):
        padded=bytearray(lisa(17)); padded[84+21*512+37]=pad
        put(padded,72,dc42_checksum(padded[84:84+80*512]),">I")
        yield f"lisa-nonzero-type-padding-{pad}","lisa_fs",bytes(padded),{"HELLO":HELLO},0,True
    badkey=bytearray(lisa(17)); badkey[84+21*512]=35
    put(badkey,72,dc42_checksum(badkey[84:84+80*512]),">I")
    yield "lisa-wrong-key-length-authenticated","lisa_fs",bytes(badkey),None,0,True
    yield "lisa-global-checksum","lisa_fs",mutation(lisa(),84+17*512,b"X"),None,0,True
    sibling=bytearray(lisa(17)); put(sibling,84+21*512+2042,30,">I"); put(sibling,72,dc42_checksum(sibling[84:84+80*512]),">I")
    yield "lisa-unreferenced-root-sibling","lisa_fs",bytes(sibling),None,0,True
    for stereo in (False,True):yield f"cassette-{stereo}","apple_cassette",cassette(stereo=stereo),{"cassette-001.bin":HELLO},2 if stereo else 0,True
    yield "cassette-xor","apple_cassette",cassette(bad=True),None,0,True
    d=dos(); tracks=nibble_tracks(d)
    for stride in (6384,6656):
        tr=[r.ljust(stride,b"\xff") for r in tracks]
        expected={f"{i:04}-track-{i:03}.nib":r for i,r in enumerate(tr)}; expected.update({"FILES/HELLO":HELLO,"decoded-sectors.do":d})
        yield f"nib-{stride}","apple_nib",b"".join(tr),expected,0,False
    trdata=trackstar(tracks)
    expected={f"track-{i:02}.nib":r for i,r in enumerate(tracks)}; expected.update({"FILES/HELLO":HELLO,"decoded-sectors.do":d})
    yield "trackstar","trackstar",trdata,expected,0,True
    for length in (1,128,511):
        short=list(tracks);short[0]=b"\xff"*length
        yield f"trackstar-short-capture-{length}","trackstar",trackstar(short),{f"track-{i:02}.nib":raw for i,raw in enumerate(short)},0,True
    yield "trackstar-length-oob","trackstar",mutation(trdata,6654,b"\xff\xff"),None,0,True
    w=woz(tracks)
    # WOZ preserves descriptive chunks and bitcells; selected expectations
    # below require the native filesystem output and complete sector image.
    yield "woz-full","apple_woz",w,{"FILES/HELLO":HELLO,"decoded-sectors.do":d},0,False
    yield "woz-crc","apple_woz",mutation(w,300,b"X"),None,0,False


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--probe",required=True,type=Path); ap.add_argument("--report",type=Path); ap.add_argument("--reference-dir",type=Path)
    args=ap.parse_args(); report={"fixtures":[],"references":[]}; failures=[]
    def run(label,reader,path,expected,profile=0,candidate=None,memory=None,member=None,cancel=False,subset=False,mode=None):
        command=[str(args.probe),str(path),reader,str(profile)]
        if memory is not None or member is not None or cancel or mode:command.extend([str(memory if memory is not None else 64*1024*1024),str(member if member is not None else 64*1024*1024)])
        if cancel:command.append("cancel")
        elif mode:command.append(mode)
        r=subprocess.run(command,capture_output=True,timeout=30)
        row={"case":label,"reader":reader,"exit_code":r.returncode,"expected_valid":expected is not None}
        try:
            assert r.returncode != 3,("RAM guard/cursor failure",r.stdout,r.stderr)
            if expected is None:assert r.returncode==1,("invalid source passed",r.stdout,r.stderr)
            else:
                assert r.returncode==0,(r.stdout,r.stderr)
                result=json.loads(r.stdout); row["result"]=result
                if candidate is not None:assert result["candidate"]==candidate,("candidate",result)
                if label.startswith("trackstar-short-capture-"):assert result["incomplete"] is True,("short capture claims full sectors",result)
                actual={e["name"]:(e["size"],e["sha256"]) for e in result["members"] if not e["folder"]}
                wanted={name:(len(data),hashlib.sha256(data).hexdigest()) for name,data in expected.items()}
                assert all(actual.get(k)==v for k,v in wanted.items()),(actual,wanted)
                if not subset:assert actual==wanted,(actual,wanted)
            row["passed"]=True
        except Exception as e:
            row["passed"]=False; row["failure"]=str(e); failures.append(row); print(label,"FAILED",str(e)[:1200],flush=True)
        report["fixtures"].append(row)
    with tempfile.TemporaryDirectory(prefix="xfu-apple-native-") as td:
        folder=Path(td); positives=[]
        for i,(label,reader,data,expected,profile,candidate) in enumerate(cases()):
            path=folder/f"{i}-{label}.img"; path.write_bytes(data)
            run(label,reader,path,expected,profile,candidate,subset=reader=="apple_woz")
            if expected is not None and reader not in ("nufx","apple_woz","apple_nib","apple_dos33","prodos"):positives.append((label,reader,path,profile,expected))
        # CFFA is streamed. Sparse fixture setup avoids a 128 MiB Python array;
        # the native reader still checks every byte in all nominally empty slots.
        path=folder/"cffa.img"
        with path.open("wb") as f:f.write(prodos()); f.truncate(128*1024*1024)
        run("cffa-four-slots","cffa",path,{"VOLUME01/HELLO":HELLO},4,False)
        positives.append(("cffa","cffa",path,4,{"VOLUME01/HELLO":HELLO}))
        path6=folder/"cffa6.img"
        with path6.open("wb") as f:
            f.write(prodos()); f.seek(128*1024*1024); f.write(prodos())
        expected6={"VOLUME01/HELLO":HELLO,"VOLUME05/HELLO":HELLO}
        run("cffa-six-partial-final-slot","cffa",path6,expected6,6,False)
        positives.append(("cffa6","cffa",path6,6,expected6))
        path8=folder/"cffa8.img"
        with path8.open("wb") as f:f.write(prodos()); f.truncate(256*1024*1024-512)
        run("cffa-eight-short-final-slot","cffa",path8,{"VOLUME01/HELLO":HELLO},8,False)
        positives.append(("cffa8","cffa",path8,8,{"VOLUME01/HELLO":HELLO}))
        for label,reader,path,profile,expected in positives:
            run(label+"-cancel",reader,path,None,profile,cancel=True)
            run(label+"-memory1",reader,path,None,profile,memory=1)
            run(label+"-member1",reader,path,None,profile,member=1)
            run(label+"-operation-memory1",reader,path,None,profile,memory=1,mode="operation")
            run(label+"-operation-member1",reader,path,None,profile,member=1,mode="operation")
            run(label+"-operation-overrides-default",reader,path,expected,profile,mode="override")
        if args.reference_dir:
            for name,reader in (("IconEd.ACU","applelink_pe"),("DOS33MAS.APP","trackstar"),("PatchHFS.shk","nufx"),("gjr-data.do","gutenberg"),("688-0036_Pascal_Workshop_3.0_1.dc42","lisa_fs")):
                source=args.reference_dir/name
                before=hashlib.sha256(source.read_bytes()).hexdigest()
                r=subprocess.run([str(args.probe),str(source),reader],capture_output=True,timeout=30)
                row={"file":name,"reader":reader,"source_sha256":before,"exit_code":r.returncode,"stdout":r.stdout.decode("utf8","replace"),"stderr":r.stderr.decode("utf8","replace")}
                assert hashlib.sha256(source.read_bytes()).hexdigest()==before
                assert r.returncode==0,(name,r.stdout,r.stderr)
                report["references"].append(row)
    report["passed"]=len(report["fixtures"])-len(failures); report["total"]=len(report["fixtures"])
    if args.report:args.report.write_text(json.dumps(report,indent=2),encoding="utf8")
    print(f"{report['passed']}/{report['total']} independent cases passed")
    return 1 if failures else 0
if __name__=="__main__":raise SystemExit(main())
