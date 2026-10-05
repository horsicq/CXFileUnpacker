#!/usr/bin/env python3
"""Independent archive wire fixtures and exact decoded-byte regression.

The writers implement documented fields and independent encoders. They do
not import library code, run an installer, or modify any original sample.
The native helper additionally checks RAM-only, short I/O and lifecycle.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import lzma
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

BE16 = lambda n: struct.pack('>H', n)
BE32 = lambda n: struct.pack('>I', n)
LE16 = lambda n: struct.pack('<H', n)
LE32 = lambda n: struct.pack('<I', n)

def crc16(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xA001 if value & 1 else 0)
    return value

def raw_crc32(data):
    return zlib.crc32(data, 0xffffffff) ^ 0xffffffff

def olaf(data):
    value = 0
    for byte in data:
        high = value & 0xff00
        for _ in range(8):
            high = ((high << 1) ^ (0x1021 if high & 0x8000 else 0)) & 0xffff
        value = high ^ ((value << 8) & 0xffff) ^ byte
    return value

class Bits:
    def __init__(self, lsb=False): self.bits, self.lsb = [], lsb
    def put(self, value, width):
        self.bits.extend((value >> i) & 1 for i in (range(width) if self.lsb else range(width-1, -1, -1)))
    def finish(self):
        bits = self.bits + [0] * (-len(self.bits) % 8)
        return bytes(sum(bits[i+j] << (j if self.lsb else 7-j) for j in range(8)) for i in range(0,len(bits),8))

def adaptive_literals(data, alphabet, terminal=None):
    """Encode literals in the adaptive sibling tree; no decoder is reused."""
    total = alphabet * 2 - 1
    freq, child, parent = [0]*(total+1), [0]*total, [0]*(total+alphabet)
    for i in range(alphabet): freq[i], child[i], parent[total+i] = 1, total+i, i
    for i in range(alphabet, total):
        j = (i-alphabet)*2
        freq[i], child[i], parent[j], parent[j+1] = freq[j]+freq[j+1], j, i, i
    freq[total] = 65535
    bits = Bits()
    for value in list(data) + ([] if terminal is None else [terminal]):
        node, path = parent[total+value], []
        while node != total-1:
            p = parent[node]
            path.append(node - child[p]); node = p
        for bit in reversed(path): bits.put(bit,1)
        node = parent[total+value]
        while True:
            freq[node] += 1
            if freq[node] > freq[node+1]:
                other = node+1
                while freq[node] > freq[other+1]: other += 1
                freq[node], freq[other] = freq[other], freq[node]
                a, c = child[node], child[other]
                child[node], child[other] = c, a
                parent[a] = other
                if a < total: parent[a+1] = other
                parent[c] = node
                if c < total: parent[c+1] = node
                node = other
            node = parent[node]
            if node==0: break
    return bits.finish()

def shrink_literals(data):
    """Interval-constraint encoder for literal-only Shrink streams.

    Each token constrains a big-endian integer's prefix to its arithmetic
    interval. This is deliberately different from the production decoder.
    """
    weights = [0]*1008
    for i in range(261): weights[504+i] = 1 if i<32 or i>126 else 3
    weights[897] = 1
    for i in range(503,0,-1): weights[i] = weights[i*2]+weights[i*2+1]
    def add(symbol, amount=1):
        node = symbol+504
        while node: weights[node] += amount; node //= 2
        if weights[1] >= 8192:
            for i in range(504,1008):
                if weights[i]: weights[i] = weights[i]//2+1
            for i in range(503,0,-1): weights[i] = weights[i*2]+weights[i*2+1]
    count = 4 + 3*len(data) + 32
    low, high, consumed, offset, interval, next_event = 0, (1 << (count*8))-1, 4, 0, 0x80000000, 0
    def fraction(weight):
        q, rem = divmod(weight << 16, weights[1])
        r = (rem << 16)//weights[1]
        return (((interval & 65535)*q) >> 16) + (((interval >> 16)*(r & 65535)) >> 16) + (q & 65535)*(interval >> 16)
    for pos, symbol in enumerate(data):
        while next_event <= pos:
            if next_event < 48: add(next_event+261)
            k, power = 0, 4
            while power < next_event+4: k, power = k+1, power*2
            if power == next_event+4 and k<14:
                if k<13: add(394+2*k); add(395+2*k)
                for group in range(3): add(420+28*group+2*k); add(421+28*group+2*k)
                if k<7:
                    for j in range(4): add(309+4*k+j)
                for j in range(4): add(337+14*j+k)
            next_event += 1
            if next_event >= 48: next_event = 60 if next_event==48 else (next_event+3)*2-4
        node, cumulative = symbol+504, 0
        while node > 1:
            if node & 1: cumulative += weights[node-1]
            node //= 2
        lower, width = fraction(cumulative), fraction(weights[symbol+504])
        scale = 1 << (8*(count-consumed))
        low = max(low,(offset+lower)*scale)
        high = min(high,(offset+lower+width)*scale-1)
        assert low<=high, 'empty arithmetic interval'
        offset += lower; interval = width
        add(symbol,3+(weights[1]>>10))
        while interval<0x01000000:
            offset *= 256; interval *= 256; consumed += 1
    return ((low+high)//2).to_bytes(count,'big')[:consumed]

def amplus(data, compressed=False, mode=0):
    name = b'plus.bin\0'
    payload = b''.join(bytes([(1<<len(data[i:i+8]))-1])+data[i:i+8] for i in range(0,len(data),8)) if compressed else data
    file_header = b'FILE'+BE32(20)+BE32(len(data))+bytes(16)
    body = file_header+b'NAME'+BE32(len(name))+name+b'BODY'+BE32(len(payload))+payload+bytes(len(payload)&1)
    checksum = sum(byte << (8*(3-(i&3))) for i,byte in enumerate(data)) & 0xffffffff
    body = BE16(mode)+BE32(len(body))+BE32(checksum)+body
    chunk = (b'PACK' if compressed else b'DATA')+BE32(len(body))+body+bytes(len(body)&1)
    return b'FORM'+BE32(len(chunk)+4)+b'APUP'+chunk

def warp(data, method=0, side=b'TOP\0', cylinder=0):
    if method==0: packed=data
    elif method==3:
        packed=bytearray()
        for value in data: packed.extend(b'\x90\0' if value==0x90 else bytes([value]))
        packed=bytes(packed)
    elif method==2:
        # Root left='A', right=EOF; LSB bit stream.
        assert data == b'A'*len(data)
        bits=Bits(True)
        for _ in data: bits.put(0,1)
        bits.put(1,1)
        packed=LE16(1)+struct.pack('<hh',-66,-257)+bits.finish()
    else: raise ValueError(method)
    return b'Warp v1.1\0'+BE16(cylinder)+side+BE16(1)+BE16(method)+BE16(crc16(data))+BE32(len(packed))+packed

def lhwarp(data, method=1, bitmap=0x3fffff):
    packed=data if method else adaptive_literals(data,314)
    header = bytes([1,3,1,0])+BE16(0)+BE16(0)+BE32(0)+BE32(0)+BE32(0)
    record=bytes([method,0,0,0])+bitmap.to_bytes(3,'little')+b'\0'+BE32(len(data))+BE32(len(packed))+BE32(raw_crc32(data))
    return header+record+packed

def compdisk():
    chunks, image = [], bytearray()
    for cylinder in range(80):
        data=bytes([cylinder])*11264
        chunks.append(BE32(0)+BE16(olaf(data))+data); image.extend(data)
    return b'COMP'+BE32(5)+BE32(0)+BE32(0)+b''.join(chunks), bytes(image)

def cbm(data, method=0, version=2):
    name=b'CBMFILE'
    if method==0: packed=data
    elif method==1:
        packed=b'\xfe'+b''.join(b'\xfe\x01\xfe' if byte==0xfe else bytes([byte]) for byte in data)
    elif method in (2,4):
        bits=Bits(True)
        for value in range(256): bits.put(8,5); bits.put(value,8)
        for value in data: bits.put(value,8)
        packed=bits.finish()
    elif method==3:
        bits=Bits(True)
        for value in list(data)+[256]: bits.put(int(f'{value:09b}'[::-1],2),9)
        packed=bits.finish()
    else: packed=data
    header_size=11+len(name)+(3 if version==2 else 0)
    blocks=(header_size+len(packed)+253)//254
    checksum=sum((byte^(i+1)&255) if version==2 else byte for i,byte in enumerate(data))&65535
    header=bytes([version,method])+LE16(checksum)+len(data).to_bytes(3,'little')+LE16(blocks)+b'P'+bytes([len(name)])+name+(bytes(3) if version==2 else b'')
    return (header+packed).ljust(blocks*254,b'\0')

def powerpacker_literals(data):
    bits=Bits()
    bits.put(0,1)
    remaining=len(data)-1
    while remaining>=3: bits.put(3,2); remaining-=3
    bits.put(remaining,2)
    for value in reversed(data): bits.put(value,8)
    # Backwards reader takes LSB first while its returned words are MSB.
    stream=bytearray()
    for i in range(0,len(bits.bits),8): stream.append(sum(bit << j for j,bit in enumerate(bits.bits[i:i+8])))
    stream.reverse()
    stream=bytes(-len(stream)%4)+bytes(stream)
    return stream+len(data).to_bytes(3,'big')+b'\0'

def crunchdisk(data, method=0, transposed=False):
    assert len(data)==512
    source=b''.join(data[p::4] for p in range(4)) if transposed else data
    header=b'CDF0'+BE32(512)+BE32(1)+BE32(1)+BE32(0)+BE32(0)+bytes(4)+BE16(0)+BE16(method)
    packed=powerpacker_literals(source) if method==1 else source
    return header+(b'CYL1' if transposed else b'CYL0')+BE32(len(packed))+packed

def lhf(data, compressed=False):
    if compressed:
        assert len(set(data))==1
        bits=Bits(); bits.put(len(data),16); bits.put(0,9); bits.put(data[0],9); bits.put(0,1)
        payload=bits.finish(); original=len(data)
    else: payload=data; original=0
    name=b'lhf.bin\0'
    body=BE16(0)+BE16(len(name))+BE32(len(payload))+BE32(original)+BE32(0)+name+payload
    return b'LhF\0'+BE32(len(body)+8)+body

def cdaf(data, method=0):
    name=b'shrink.bin\0'
    header=bytearray(28); header[:4]=b'FILE'; header[4:8]=BE32(20+len(name)); header[9]=method; header[14:18]=BE32(len(data)); header[24:26]=BE16(crc16(data))
    payload=bytes(4)+shrink_literals(data) if method else data
    body=b'NAME'+BE32(6)+b'shrink'+bytes(header)+name+bytes(len(name)&1)+b'BODY'+BE32(len(payload))+payload+bytes(len(payload)&1)
    return b'FORM'+BE32(len(body)+4)+b'CDAF'+body

def spack(data, compressed=True):
    name=b'spack.bin\0'; number=1
    packed=shrink_literals(data)
    member=b'FI'+BE16(number if compressed else number|0x8000)+BE32(len(data))
    member+=(BE32(len(packed))+BE16(crc16(data))+packed) if compressed else data
    directory=bytes(12)+BE16(1)+b'FI'+BE16(number)+BE16(len(name))+name+BE32(len(data))+b'\0'
    index=shrink_literals(directory)
    body=b'FI'+BE16(0)+BE32(len(directory))+BE32(len(index))+BE16(crc16(directory))+index
    return b'PACK'+member+body+b'INDX'+BE32(len(body))+BE32(0)

def pcompress(data, compressed=True):
    packed=adaptive_literals(data,317,316)
    payload=b'LH'+BE32(len(data))+BE32(len(packed))+BE32(raw_crc32(packed))+packed if compressed else data
    return b'PACKpcompress.bin\n'+BE32(len(payload))+payload

def cpm(data, adaptive=True, old=False):
    if adaptive: packed=adaptive_literals(data,315,256)
    elif not old:
        bits=Bits()
        for value in list(data)+[256]: bits.put(value,9)
        packed=bits.finish()
    else:
        # Original fixed-12 Crunch atom allocation: mid-square + collision chain.
        slots, links, mapping = {0:(0,0)}, {}, {}
        for byte in range(256):
            a=((0x3fff+byte)|0x800)&0x1fff
            slot=0x800 if byte==0 else ((a>>1)*((a>>1)+(a&1))>>4)&4095
            while slot in links: slot=links[slot]
            if slot in slots:
                base=slot; slot=(slot+101)&4095
                while slot in slots: slot=(slot+1)&4095
                links[base]=slot
            slots[slot]=(0x3fff,byte); mapping[byte]=slot
        bits=Bits()
        for value in data: bits.put(mapping[value],12)
        bits.put(0,12); packed=bits.finish()
    return bytes([0x76,0xfd if adaptive else 0xfe])+b'CRUNCH.BIN\0'+bytes([0x20,0x10 if old else 0x20,0,0])+packed+LE16(sum(data)&65535)

def now(data, method=0, resource=b''):
    plain=resource+data
    if method==0: payload=plain; flags=0
    elif method==1: payload=b'\0\0'+b''.join(bytes([0xff])+plain[i:i+8] for i in range(0,len(plain),8)); flags=1
    elif method==2: payload=b'\0'+b'\x88'*128+b'\0'+plain; flags=0x20
    else: raise ValueError(method)
    start, first = 134,154
    end=first+len(payload)+4
    table=BE32(first)+BE16(flags)+BE16(0)+BE32(end)+bytes(4)
    stream=table+BE32(sum(table))+payload+bytes(4)
    entry=bytearray(110); name=b'now.bin'; entry[0]=len(name); entry[1:1+len(name)]=name
    entry[86:90]=BE32(len(data)); entry[90:94]=BE32(len(resource)); entry[98:102]=BE32(start); entry[102:106]=BE32(end); entry[106:110]=BE32(sum(entry[:106]))
    global_header=bytearray(24); global_header[:2]=b'\0\2'; global_header[8:12]=BE32(1)
    return bytes(global_header)+bytes(entry)+stream

def nsis(files, codec='stored', solid=False, pe=False, dictionary=1<<20):
    count=len(files); header_size=68+28*count
    strings=b'\0'+b''.join(name.encode('ascii')+b'\0' for name,_ in files)
    header=bytearray(header_size+len(strings)); header[4+2*8:8+2*8]=LE32(68); header[3*8:4+3*8]=LE32(count)
    header[4+3*8:8+3*8]=LE32(header_size); header[4+4*8:8+4*8]=LE32(len(header)); header[header_size:]=strings
    def encode(data):
        if codec=='stored': return data
        if codec=='deflate': return zlib.compress(data,wbits=-15)
        if codec=='lzma':
            return b'\x5d'+LE32(dictionary)+lzma.compress(data,format=lzma.FORMAT_RAW,filters=[{'id':lzma.FILTER_LZMA1,'dict_size':dictionary,'lc':3,'lp':0,'pb':2}])
        raise ValueError(codec)
    payload, name_offset = bytearray(),1
    for i,(name,data) in enumerate(files):
        command=68+i*28; header[command:command+4]=LE32(20); header[command+8:command+12]=LE32(name_offset); header[command+12:command+16]=LE32(len(payload)); name_offset+=len(name)+1
        block=data if solid else encode(data)
        payload+=LE32(len(block)|(0x80000000 if not solid and codec!='stored' else 0))+block
    framed=encode(LE32(len(header))+bytes(header)+payload) if solid else LE32(len(encode(header))|(0x80000000 if codec!='stored' else 0))+encode(header)+payload
    first=LE32(0)+LE32(0xdeadbeef)+b'NullsoftInst'+LE32(len(header))+LE32(28+len(framed)+4)
    prefix=b'MZ'+bytes(1022) if pe else b''
    body=prefix+first+framed
    return body+LE32(zlib.crc32(body[512:] if pe else body))

def lha_carrier(data,kind):
    name=b'carrier.bin'; header=bytearray(24+len(name)); header[0]=len(header)-2
    header[2:7]=b'-lh0-'; header[7:11]=LE32(len(data)); header[11:15]=LE32(len(data)); header[19]=0x20
    header[21]=len(name); header[22:22+len(name)]=name; header[-2:]=LE16(crc16(data)); header[1]=sum(header[2:])&255
    if kind in ('amiga','boa'):
        offset=0x1914 if kind=='boa' else 0x100
        prefix=bytearray(offset); prefix[:4]=BE32(0x3f3); prefix[44:48]=b'SFX!'; prefix[52:56]=BE32(offset)
        if kind=='boa': data=bytes(value^b'BOA\x0f'[i%4] for i,value in enumerate(data))
    elif kind=='c64':
        prefix=bytearray(0xe89); prefix[0]=1; prefix[2:4]=b'\x28\x1c'; prefix[0xd30]=ord('1'); prefix[0xd44:0xd47]=b'LHA'
    else:
        prefix=bytearray(128)
        if kind=='lh': prefix[36:44]=b'LHx\'s SF'
        elif kind=='lzss': prefix[32:40]=b'LZSS sel'
        elif kind=='lharch': prefix[6:18]=b'SFX of LHarc'
        elif kind=='names': prefix[37:39]=b'LH'; prefix[76:84]=b'name to '
    return bytes(prefix)+header+data+b'\0'

def dms_carrier(data,kind):
    header=bytearray(56); header[:4]=b'DMS!'; header[16:18]=BE16(0); header[18:20]=BE16(0); header[20:24]=BE32(len(data)); header[24:28]=BE32(len(data)); header[54:56]=BE16(crc16(header[4:54]))
    track=bytearray(20); track[:2]=b'TR'; track[6:8]=BE16(len(data)); track[8:10]=BE16(len(data)); track[10:12]=BE16(len(data)); track[14:16]=BE16(sum(data)&65535); track[16:18]=BE16(crc16(data)); track[18:20]=BE16(crc16(track[:18]))
    locations={0x1605:0x58c4,0x2462:0x45d0,0x2466:0x45e0,0x3269:0x537c}
    prefix=bytearray(locations[kind]); prefix[:4]=BE32(0x3f3); prefix[20:24]=BE32(kind)
    words={24:0x1c24,64:0x303c05cd,68:0x421b51c8,72:0xfffc47f9} if kind==0x1605 else {44:0xabcd,76:0x48e7fff6,80:0x61000030,84:0x4cdf6fff} if kind in (0x2462,0x2466) else {36:0x60000006,40:0x24e2,44:0x48e77efe,48:0x24482400,64:0x3b61425b}
    for at,value in words.items(): prefix[at:at+4]=BE32(value)
    return bytes(prefix)+header+track+data

def fixtures():
    cases=[]
    def add(reader,name,archive,outputs,valid=True): cases.append((reader,name,archive,outputs,valid))
    data=b'Independent archive fixture payload!\n'
    for compressed in (False,True): add('amplus',f'plus-{compressed}',amplus(data,compressed),[data])
    track=bytes((i*17)&255 for i in range(5808))
    for method in (0,3): add('warp',f'warp-{method}',warp(track,method),[track[:5632],track[5632:]])
    add('warp','squeeze',warp(b'A'*5808,2),[b'A'*5632,b'A'*176])
    cylinder=b''.join(bytes([i])*512+bytes([i+40])*16 for i in range(22))
    expected=b''.join(cylinder[i*528:i*528+512] for i in range(22))
    labels=b''.join(cylinder[i*528+512:(i+1)*528] for i in range(22))
    for method in (0,1): add('lhwarp',f'lhwarp-{method}',lhwarp(cylinder,method),[expected,labels])
    image,plain=compdisk(); add('compdisk','stored80',image,[plain])
    for version in (1,2):
        for method in (0,1,2,3,4):
            if version==1 and method>2: continue
            add('arc_cbm',f'cbm-{version}-{method}',cbm(data,method,version),[data])
    sector=bytes(range(256))*2
    add('crunchdisk','stored',crunchdisk(sector),[sector])
    add('crunchdisk','transpose',crunchdisk(sector,transposed=True),[sector])
    add('crunchdisk','powerpacker',crunchdisk(sector,method=1,transposed=True),[sector])
    for compressed in (False,True): add('lhf',f'lhf-{compressed}',lhf(b'Q'*57 if compressed else data,compressed),[b'Q'*57 if compressed else data])
    for method in (0,1,7): add('shrink_cdaf',f'shrink-{method}',cdaf(data,method),[data])
    for compressed in (False,True): add('spack',f'spack-{compressed}',spack(data,compressed),[data])
    for compressed in (False,True): add('pcompress_pack',f'pcompress-{compressed}',pcompress(data,compressed),[data])
    for old in (False,True):
        for adaptive in (False,True): add('cpm_crunch',f'cpm-{old}-{adaptive}',cpm(data,adaptive,old),[data])
    for method in (0,1,2): add('nowcompress',f'now-{method}',now(data,method),[data])
    add('nowcompress','forks',now(data,resource=b'RESOURCE'),[b'RESOURCE',data])
    files=[('one.bin',data),('two.bin',b'other payload'*100)]
    for codec in ('stored','deflate','lzma'):
        for solid in (False,True):
            if solid and codec=='stored': continue
            add('nsis',f'nsis-{codec}-{solid}',nsis(files,codec,solid),[p for _,p in files])
    add('nsis','pe',nsis(files,'deflate',pe=True),[p for _,p in files])
    add('nsis','solid-lzma8m',nsis(files,'lzma',True,dictionary=1<<23),[p for _,p in files])
    for kind in ('amiga','boa','c64','lh','lzss','lharch','names'): add('lha','carrier-'+kind,lha_carrier(data,kind),[data])
    dms_data=sector*22
    for kind in (0x1605,0x2462,0x2466,0x3269): add('dms',f'carrier-{kind:x}',dms_carrier(dms_data,kind),[dms_data,dms_data])
    positives=list(cases)
    for reader,name,archive,outputs,_ in positives:
        if reader not in ('lha','dms'): add(reader,name+'-truncated',archive[:-3],[],False)
    # Checksum corruption keeps framing unchanged, so it must never TEST OK.
    for reader,name,archive,outputs,_ in positives:
        if reader not in ('lhf','crunchdisk','lha','dms'):  # existing readers validate payload CRC at unpack
            changed=bytearray(archive)
            if reader=='amplus': changed[28]^=1
            elif reader=='warp': changed[20]^=1
            elif reader=='lhwarp': changed[39]^=1
            elif reader=='compdisk': changed[20]^=1
            elif reader=='arc_cbm': changed[2]^=1
            elif reader=='cpm_crunch': changed[-1]^=1
            elif reader=='pcompress_pack' and '-True' in name: changed[-1]^=1
            elif reader=='pcompress_pack': continue  # stored does not claim a CRC
            elif reader=='nowcompress': changed[130]^=1
            elif reader=='shrink_cdaf': changed[50]^=1
            elif reader=='spack':
                footer=len(changed)-12
                index=footer-int.from_bytes(changed[footer+4:footer+8],'big')
                changed[index+12]^=1
            elif reader=='nsis': changed[-1]^=1
            add(reader,name+'-bad-checksum',bytes(changed),[],False)
    add('amplus','unknown-codec',amplus(data,True,2),[],False)
    protected=bytearray(crunchdisk(sector)); protected[24]=1
    add('crunchdisk','password-unsupported',bytes(protected),[],False)
    for kind in ('amiga','boa','c64','lh','lzss','lharch','names'):
        changed=bytearray(lha_carrier(data,kind)); changed[-2]^=1
        add('lha','carrier-'+kind+'-bad-payload',bytes(changed),[],'unpack_fail')
    changed=bytearray(lha_carrier(data,'amiga')); changed[52:56]=BE32(len(changed)+1)
    add('lha','bad-carrier-offset',bytes(changed),[],False)
    return cases

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--probe'); parser.add_argument('--work-dir'); parser.add_argument('--generate-only',action='store_true')
    args=parser.parse_args(); cases=fixtures()
    with tempfile.TemporaryDirectory(prefix='archive-additions-') if not args.work_dir else _fixed(args.work_dir) as folder:
        root=Path(folder); root.mkdir(parents=True,exist_ok=True); report=[]
        for reader,name,data,outputs,valid in cases:
            source=root/(reader+'-'+name+'.bin'); source.write_bytes(data); out=root/(reader+'-'+name+'-out')
            row={'reader':reader,'name':name,'valid':valid,'input_sha256':hashlib.sha256(data).hexdigest(),'expected':[{ 'size':len(p),'sha256':hashlib.sha256(p).hexdigest()} for p in outputs]}
            if not args.generate_only:
                if not args.probe: parser.error('--probe is required unless --generate-only')
                run=subprocess.run([args.probe,reader,str(source),str(out) if valid is True else '-'],capture_output=True,text=True,timeout=120)
                row.update(exit_code=run.returncode,stdout=run.stdout,stderr=run.stderr)
                wanted=0 if valid is True else 1 if valid=='unpack_fail' else 2
                if run.returncode!=wanted: raise AssertionError(json.dumps(row,indent=2))
                if valid is True:
                    actual=[p.read_bytes() for p in out.rglob('*') if p.is_file()]
                    assert collections.Counter(actual)==collections.Counter(outputs),(reader,name,'output byte mismatch')
            report.append(row)
        (root/'report.json').write_text(json.dumps({'cases':len(report),'passed':not args.generate_only,'results':report},indent=2),encoding='utf-8')
        print(f'{len(report)} archive fixture checks '+('generated' if args.generate_only else 'passed'))

class _fixed:
    def __init__(self,path): self.path=path
    def __enter__(self): return self.path
    def __exit__(self,*unused): return False

if __name__=='__main__': main()
