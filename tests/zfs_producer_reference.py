"""Independent ZEVO reference file mapping, with native helper byte compare.

Metadata candidates come from raw source sectors requested by the helper. The
Python decoder independently expands LZJB, resolves the directory object ID,
reads its dnode and follows native block pointers, sizes and Fletcher checks.
"""
from __future__ import annotations
import argparse,hashlib,json,pathlib,struct,subprocess
MASK=(1<<64)-1
def lzjb(raw,size):
    out=bytearray();at=0;mask=0;bits=0
    while len(out)<size:
        if not mask:
            if at>=len(raw):raise ValueError('lzjb map')
            bits=raw[at];at+=1;mask=1
        if bits&mask:
            if at+2>len(raw):raise ValueError('lzjb pair')
            length=(raw[at]>>2)+3;back=((raw[at]&3)<<8)|raw[at+1];at+=2
            if not back or back>len(out) or length>size-len(out):raise ValueError('lzjb reference')
            for _ in range(length):out.append(out[-back])
        else:
            if at>=len(raw):raise ValueError('lzjb literal')
            out.append(raw[at]);at+=1
        mask=(mask<<1)&255
    return bytes(out)
def helper_read(exe,source,path):
    process=subprocess.Popen([exe],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);name=b'zfs';path=path.encode();reads=[];out=bytearray()
    process.stdin.write(struct.pack('<4sIQQQII',b'GFS1',2,len(source),128*1024*1024,(1<<63)-1,len(name),len(path))+name+path);process.stdin.flush()
    while True:
        raw=process.stdout.read(4)
        if len(raw)!=4:raise ValueError('helper stopped')
        code=struct.unpack('<I',raw)[0]
        if code==1:
            at,n=struct.unpack('<QI',process.stdout.read(12));data=source[at:at+n];assert len(data)==n;reads.append((at,n));process.stdin.write(struct.pack('<I',n)+data);process.stdin.flush()
        elif code==3:n=struct.unpack('<I',process.stdout.read(4))[0];out.extend(process.stdout.read(n))
        elif code==4:status,count=struct.unpack('<IQ',process.stdout.read(12));assert not status and count==len(out);break
        else:raise ValueError(code)
    process.stdin.close();assert process.wait()==0,process.stderr.read();return bytes(out),reads
def main():
    p=argparse.ArgumentParser();p.add_argument('--helper',required=True);p.add_argument('--image',required=True);p.add_argument('--report',required=True);a=p.parse_args();path=pathlib.Path(a.image);source=path.read_bytes();before=hashlib.sha256(source).hexdigest();native,reads=helper_read(a.helper,source,'/fs/@/f_with_data');assert len(native)==512000
    candidates=[];object_ids=set();name=b'f_with_data\0'
    for at,n in dict.fromkeys(reads):
        raw=source[at:at+n];variants=[('stored',raw)]
        for size in (512,1024,4096,8192,16384,32768,65536,131072):
            try:variants.append(('lzjb',lzjb(raw,size)))
            except ValueError:pass
        for codec,data in variants:
            if len(data)>=64 and struct.unpack_from('<Q',data)[0]==(1<<63)+3:
                for offset in range(64,len(data)-63,64):
                    if data[offset+14:offset+14+len(name)]==name:object_ids.add(struct.unpack_from('<Q',data,offset)[0]&((1<<48)-1))
            for offset in range(0,len(data)-511,512):
                node=data[offset:offset+512];nptr=node[3];bonus=64+nptr*128
                if node[0]!=19 or node[4]!=44 or nptr>3 or bonus+24>512:continue
                if struct.unpack_from('<I',node,bonus)[0]!=0x2f505a:continue
                header=(struct.unpack_from('<H',node,bonus+4)[0]>>10)*8
                if bonus+header+16>512 or struct.unpack_from('<Q',node,bonus+header+8)[0]!=512000:continue
                candidates.append({'at':at,'codec':codec,'node_index':offset//512,'node':node})
    unique={row['node']:(row) for row in candidates};assert object_ids,('directory lookup missing',reads)
    candidates=[r for r in unique.values() if r['node_index'] in {obj%32 for obj in object_ids}];assert len(candidates)==1,(len(candidates),object_ids,[(r['at'],r['codec'],r['node_index']) for r in unique.values()]);candidate=candidates[0];node=candidate['node'];blocks=[]
    def bp_read(bp,endian='<'):
        words=struct.unpack(endian+'16Q',bp);prop=words[6];logical=((prop&65535)+1)*512;physical=(((prop>>16)&65535)+1)*512;codec=(prop>>32)&127;level=(prop>>56)&31;check=(prop>>40)&255
        if not any(words[:6]):return bytes(logical),prop
        assert not (prop>>39)&1,'embedded BP is not this producer fixture'
        assert not (words[1]>>63),'gang block is not this producer fixture'
        assert not (words[0]>>32)&((1<<24)-1),'single vdev required'
        address=(words[1]&((1<<63)-1))*512+4*1024*1024;raw=source[address:address+physical];assert len(raw)==physical
        if check==7:
            sums=[0,0,0,0]
            for word in struct.unpack(('<' if prop>>63 else '>')+str(len(raw)//4)+'I',raw):
                sums[0]=(sums[0]+word)&MASK
                for index in range(1,4):sums[index]=(sums[index]+sums[index-1])&MASK
            assert tuple(sums)==words[12:16],(check,address,tuple(sums),words[12:16])
        elif check!=2:raise ValueError('unexpected producer checksum '+str(check))
        data=raw if codec==2 else lzjb(raw,logical) if codec==3 else None;assert data is not None and len(data)==logical
        blocks.append({'source_offset':address,'physical_bytes':physical,'logical_bytes':logical,'compression':codec,'level':level,'checksum':check,'raw_sha256':hashlib.sha256(raw).hexdigest()});return data,prop
    nlevels=node[2];shift=node[1]-7;assert 0<=shift<=16 and 1<=nlevels<=4;record=struct.unpack_from('<H',node,8)[0]*512;decoded=bytearray()
    for index in range((512000+record-1)//record):
        blockptrs=node[64:64+node[3]*128];endian='<'
        for level in range(nlevels-1,-1,-1):
            position=(index>>(shift*level))&((1<<shift)-1);assert position*128+128<=len(blockptrs);blockptrs,prop=bp_read(blockptrs[position*128:position*128+128],endian);endian='<' if prop>>63 else '>'
        decoded.extend(blockptrs)
    decoded=bytes(decoded[:512000]);assert decoded==native;assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    report={'source_image_sha256':before,'source_bytes':len(source),'object_ids':sorted(object_ids),'dnode_source_offset':candidate['at'],'dnode_codec':candidate['codec'],'dnode_index':candidate['node_index'],'file_bytes':len(decoded),'file_sha256':hashlib.sha256(decoded).hexdigest(),'native_matches_independent_decoder':True,'source_unchanged':True,'blocks':blocks,'helper_reads':reads}
    pathlib.Path(a.report).write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('blocks','helper_reads')}))
if __name__=='__main__':main()
