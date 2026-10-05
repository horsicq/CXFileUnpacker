"""Independent PDP-11 V7 oracle for the untouched TUHS Torsten Hippe image."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, struct, subprocess
URL='https://www.tuhs.org/Archive/Distributions/Research/Torsten_Hippe_v7/v7.gz'
def main():
    p=argparse.ArgumentParser();p.add_argument('--probe',required=True);p.add_argument('--image',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    source=pathlib.Path(a.image);b=source.read_bytes();before=hashlib.sha256(b).hexdigest();expected={};totals={'files':0,'directories':0,'bytes':0}
    def pdp(at):hi,lo=struct.unpack_from('<HH',b,at);return (hi<<16)|lo
    def address(p):return (p[0]<<16)|(p[2]<<8)|p[1]
    def data(ino):
        at=1024+(ino-1)*64;size=pdp(at+8);pointers=[address(b[at+12+3*n:at+15+3*n]) for n in range(13)]
        result=bytearray()
        def branch(block,level):
            if len(result)>=size:return
            if not block:result.extend(bytes(min(size-len(result),512*128**level)))
            elif not level:result.extend(b[block*512:block*512+min(512,size-len(result))])
            else:
                for n in range(128):branch(pdp(block*512+n*4),level-1)
        for n,block in enumerate(pointers):branch(block,0 if n<10 else n-9)
        assert len(result)==size
        return struct.unpack_from('<H',b,at)[0]&0xf000,bytes(result)
    def walk(ino,path,parents=()):
        assert ino not in parents;mode,content=data(ino)
        if mode==0x4000:
            if path:expected[path]=(1,hashlib.sha256(b'').hexdigest());totals['directories']+=1
            for offset in range(0,len(content),16):
                child=struct.unpack_from('<H',content,offset)[0];name=content[offset+2:offset+16].split(b'\0',1)[0].decode('ascii')
                if child and name not in ('.','..'):walk(child,path+'/'+name if path else name,parents+(ino,))
        elif mode in (0x8000,0xa000):
            expected[path]=(0,hashlib.sha256(content).hexdigest());totals['files']+=1;totals['bytes']+=len(content)
    walk(2,'');r=subprocess.run([a.probe,'2545',str(source)],capture_output=True,text=True,check=True);actual={}
    for line in r.stdout.splitlines():
        name,folder,digest=line.split('\t')
        if 'volume-info.txt' not in name:actual[name]=(int(folder),digest)
    assert actual==expected,(len(actual),len(expected),set(actual)^set(expected))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    report={'source_url':URL,'source_image_sha256':before,'source_bytes':len(b),'native_members':len(actual),'independent_sha256_matches':len(expected),'totals':totals,'ram_only_test':True,'source_unchanged':True,'native_output':r.stdout}
    pathlib.Path(a.report).write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='native_output'}))
if __name__=='__main__':main()
