#!/usr/bin/env python3
"""CookFS grammar fixtures checked with the independent upstream MIT parser."""
import argparse
import bz2
import hashlib
import importlib
import json
import lzma
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib

U32=lambda n:struct.pack('>I',n)
U64=lambda n:struct.pack('>Q',n)

def encode(data,tag):
    if tag==0:return b'\0'+data
    if tag==1:
        c=zlib.compressobj(wbits=-15)
        return b'\1'+c.compress(data)+c.flush()
    if tag==2:return b'\2'+U32(len(data))+bz2.compress(data)
    if tag==255:return b'\xff'+lzma.compress(data,format=lzma.FORMAT_ALONE,filters=[{'id':lzma.FILTER_LZMA1,'dict_size':1<<20}])
    raise ValueError(tag)

def index(entries,metadata=True):
    def directory(children):
        data=U32(len(children))
        for name,value in children:
            raw=name.encode('utf8')
            data+=bytes([len(raw)])+raw+b'\0'+U64(1700000000)
            if isinstance(value,list):data+=U32(0xffffffff)+directory(value)
            else:data+=U32(len(value))+b''.join(struct.pack('>III',*b) for b in value)
        return data
    return b'CFS2.200'+directory(entries)+(U32(1)+U32(15)+b'creator\0fixture' if metadata else b'')

def build(pages,entries,tags=0,index_tag=0,prefix=b'',tail=b'',crc=False,raw_index=None,digests=None):
    if isinstance(tags,int):tags=[tags]*len(pages)
    encoded=[encode(p,t) for p,t in zip(pages,tags)]
    ix=encode(index(entries) if raw_index is None else raw_index,index_tag)
    hashes=digests or b''.join(U32(0)+U32(0)+U32(len(p))+U32(zlib.crc32(p)) if crc else hashlib.md5(p).digest() for p in pages)
    data=prefix+b''.join(encoded)+hashes+b''.join(U32(len(p)) for p in encoded)+ix+U32(len(ix))+U32(len(pages))+bytes([index_tag])+b'CFS0002'
    return data+tail,len(data)

def main():
    p=argparse.ArgumentParser();p.add_argument('--probe',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--reference',type=Path,default=Path(__file__).parent/'reference'/'bitrock');a=p.parse_args()
    sys.path.insert(0,str(a.reference));ref=importlib.import_module('bitrock_unpacker.cookfs')
    work=a.work/('run-'+str(time.time_ns()));work.mkdir(parents=True)
    blocker=work/'not-a-temp-directory';blocker.write_bytes(b'TEMP blocked')
    env=dict(os.environ,TEMP=str(blocker),TMP=str(blocker));cases=[];checks=0

    def independent(data,end):
        info=ref.CookFSInfo(end,None,None,None,None,None,None,None,None,None,None)
        info=ref.build_cookfs_layout(data,0,info)
        decoded=ref.decompress_page(data[info.index_blob_offset:info.index_blob_offset+info.index_size])
        entries=ref.parse_fsindex(decoded)
        if not any(e.kind=='file' and e.blocks for e in entries):return {e.path:b'' for e in entries if e.kind=='file'}
        reader=ref.PageReader(data,info)
        files={e.path:b''.join(reader.get(n)[offset:offset+size] for n,offset,size in e.blocks) for e in entries if e.kind=='file'}
        return files

    def run(name,data,valid,expected=None,end=None,limit=None,member=None,cancel=False,base=0,candidate=None,reject_writes=False):
        nonlocal checks
        path=work/(name+'.bin');path.write_bytes(data);before=hashlib.sha256(data).hexdigest()
        command=[str(a.probe),str(path),'-',str(limit if limit is not None else 256<<20),str(member if member is not None else (1<<63)-1),str(int(cancel)),str(base)]
        r=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
        assert (r.returncode==0)==valid,(name,r.returncode,r.stdout,r.stderr)
        checks+=1
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before;checks+=1
        if candidate is not None:assert ('candidate='+str(int(candidate))) in r.stdout;checks+=1
        if reject_writes:
            out=work/(name+'-rejected');command[2]=str(out)
            rejected=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
            assert rejected.returncode!=0;checks+=1
            assert not any(p.is_file() for p in out.rglob('*'));checks+=1
        if expected is not None:
            out=work/(name+'-extracted');command[2]=str(out)
            r2=subprocess.run(command,env=env,capture_output=True,text=True,timeout=30)
            assert r2.returncode==0,(name,r2.stdout,r2.stderr);checks+=1
            actual={p.relative_to(out).as_posix():p.read_bytes() for p in out.rglob('*') if p.is_file()}
            assert actual==expected,(name,{n:len(v) for n,v in actual.items()},{n:len(v) for n,v in expected.items()});checks+=1
            if end is not None:
                raw=independent(data[base:],end-base)
                if any('___bitrockBigFile' in n for n in raw):
                    for n in list(raw):
                        if '___bitrockBigFile' in n:continue
                        parts=sorted((int(k.rsplit('___bitrockBigFile',1)[1]),k) for k in raw if k.startswith(n+'___bitrockBigFile'))
                        for _,k in parts:raw[n]+=raw.pop(k)
                assert raw==expected,(name,'upstream mismatch');checks+=1
        cases.append({'name':name,'valid':valid,'returncode':r.returncode,'source_sha256':before,'error':r.stderr.strip()})

    payload=(b'CookFS memory payload\x00\xff'*10000)+bytes(range(256));pages=[payload,b'prefix:second page:suffix']
    entries=[('folder',[('file.bin',((0,7,100003),(1,7,11))),('empty',())]),('unicode-\u03b2.txt',((0,0,23),))]
    expected={'folder/file.bin':pages[0][7:100010]+pages[1][7:18],'folder/empty':b'','unicode-\u03b2.txt':pages[0][:23]}
    baseline=None
    for tag in (0,1,2,255):
        for index_tag in (0,1,2,255):
            data,end=build(pages,entries,tag,index_tag)
            run(f'page-{tag}-index-{index_tag}',data,True,expected,end,candidate=True)
            if tag==index_tag==0:baseline=data
        data,end=build(pages,entries,tag,1,crc=True)
        run(f'crc-page-{tag}',data,True,expected,end)
        run(f'budget-page-{tag}',data,False,limit=32768)
    chunks=[('large.bin',((0,0,3),)),('large.bin___bitrockBigFile2',((0,6,3),)),('large.bin___bitrockBigFile1',((0,3,3),)),('orphan___bitrockBigFile1',((0,9,3),))]
    data,end=build([b'AAABBBCCCDDD'],chunks,1,1)
    run('stitched-chunks',data,True,{'large.bin':b'AAABBBCCC','orphan___bitrockBigFile1':b'DDD'},end)
    prefix=b'MZ'+b'\0'*4092+b'dist-endoffset '+b'0'*20+b'\n'
    data,end=build(pages,entries,1,1,prefix=prefix,tail=b'installer-signature-tail')
    at=data.index(b'dist-endoffset ')+len(b'dist-endoffset ');data=data[:at]+str(end).zfill(20).encode()+data[at+20:]
    run('pe-prefix-offset-tail',data,True,expected,end,candidate=True)
    data,end=build(pages,entries,2,2,prefix=b'#!/bin/sh\n# static launcher\n',tail=b'unknown trailer')
    run('shell-prefix-tail',data,True,expected,end,candidate=True)
    inner,inner_end=build(pages,entries,1,1,prefix=b'MZ'+b'\0'*62)
    config=f'dist-endoffset {inner_end} -pagecachesize 8 -decompresscommand none'.encode()
    data,_=build([config],[('cookfsinfo.txt',((0,0,len(config)),))],1,1,prefix=inner)
    run('launcher-cookfsinfo-redirect',data,True,expected,inner_end,candidate=True)
    data,end=build(pages,entries,0,0);data=b'notarchiveprefix'+data
    run('nonzero-base',data,True,expected,end+16,base=16,candidate=True)
    data,end=build([],[],0,0)
    run('empty-archive',data,True,{},end,candidate=True)
    data,end=build([b''],[('empty',((0,0,0),))],0,1,crc=True)
    run('empty-crc-page',data,True,{'empty':b''},end)
    run('member-limit',baseline,False,member=1024)
    run('cancelled',baseline,False,cancel=True)
    for n in (0,7,15,16,23,len(baseline)-1):run('truncated-'+str(n),baseline[:n],False)
    for name,entries_bad in [('traversal',[('..',())]),('absolute',[('/root',())]),('reserved',[('NUL.txt',())]),('duplicate',[('File',()),('file',())]),('out-of-page',[('file',((0,BR_MAX:=64<<20,1),))]),('invalid-page',[('file',((5,0,1),))]),('actual-range',[('file',((0,9999,2),))])]:
        data,_=build([b'abc'],entries_bad,1,1);run(name,data,False)
    for name,pos in [('bad-suffix',-1),('page-checksum',10),('bad-index-magic',len(payload)+len(pages[1])+2+40+1)]:
        bad=bytearray(baseline);bad[pos]^=0x44;run(name,bytes(bad),False,reject_writes=name=='page-checksum')
    for field,value in [(-16,0xffffffff),(-12,0xffffffff)]:
        bad=bytearray(baseline);struct.pack_into('>I',bad,len(bad)+field,value);run('huge-footer-'+str(-field),bytes(bad),False)
    for tag in (1,2,255):
        data,_=build(pages,entries,tag,0);bad=bytearray(data);bad[10]^=0x81;run('corrupt-codec-'+str(tag),bytes(bad),False)
    data,_=build([b'abc'],[('file',((0,0,3),))],255,0);bad=bytearray(data);bad[2:6]=b'\xff'*4
    run('huge-lzma-dictionary',bytes(bad),False,reject_writes=True)
    data,_=build([b'abc'],[('file',((0,0,3),))],0,0);bad=bytearray(data);bad[0]=3;run('unknown-compression',bytes(bad),False)
    bad=bytearray(data);bad[0]=255;run('encrypted-custom-page',bytes(bad),False)
    for name,raw in [('truncated-directory',b'CFS2.200'+U32(1)),('huge-directory',b'CFS2.200'+U32(0xffffffff)),('trailing-index',index([])+b'garbage'),('bad-metadata',b'CFS2.200'+U32(0)+U32(1)+U32(20)+b'no-null-value'),('huge-blocks',b'CFS2.200'+U32(1)+b'\1a\0'+U64(0)+U32(1000001)),('invalid-utf8',index([('name',())]).replace(b'name',b'\xffame'))]:
        data,_=build([],[],raw_index=raw);run(name,data,False)
    nested=[('leaf',())]
    for i in range(66):nested=[('dir',nested)]
    data,_=build([],nested);run('directory-depth-limit',data,False)
    data,_=build([b'abcdefgh'],[('large',((0,0,1),)),('large___bitrockBigFile1',((0,1,1),)),('large___bitrockBigFile01',((0,2,1),))])
    run('duplicate-chunk-number',data,False)
    data,_=build([b'abc'],[('file',((0,0,3),))],0,0,crc=True);bad=bytearray(data);bad[15]^=0x20
    run('bad-page-crc',bytes(bad),False)
    data,_=build([],[],raw_index=index([],metadata=False));run('metadata-absent',data,True,{})
    run('plain-unknown',b'ordinary input without container footer'*200,False,candidate=False)
    run('false-suffix-candidate',b'not a container'+b'\0'*9+b'CFS0002',False,candidate=True)
    assert blocker.read_bytes()==b'TEMP blocked';checks+=1
    report={'checks':checks,'fixtures':len(cases),'failed':0,'reference':'MIT vpetrigo/bitrock-unpacker cookfs.py independent parser; Python zlib/bz2/lzma producers','memory_only_test':True,'temporary_paths_blocked':True,'cases':cases}
    target=work/'uniextract-bitrock-report.json';target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'checks':checks,'fixtures':len(cases),'failed':0,'report':str(target)}))

if __name__=='__main__':main()
