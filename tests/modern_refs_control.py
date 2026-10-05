"""Read-only GFS1 driver for authentic ReFS controls, optionally retain reads.

The helper receives no host path and cannot mount or create image files.
The source may be a Windows-produced corpus image with a partition base.
"""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--helper',required=True);p.add_argument('--source',required=True);p.add_argument('--base',type=int,default=0);p.add_argument('--length',type=int);p.add_argument('--path',default='');p.add_argument('--capture');p.add_argument('--quiet',action='store_true');a=p.parse_args()
    size=a.length or Path(a.source).stat().st_size-a.base
    proc=subprocess.Popen([a.helper],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None)
    op=2 if a.path else 1;name=b'refs';path=a.path.encode();proc.stdin.write(struct.pack('<4sIQQQII',b'GFS1',op,size,128*1024*1024,(1<<63)-1,len(name),len(path))+name+path);proc.stdin.flush();read_bytes=0;reads={};listing=[];digest=hashlib.sha256();content=0
    def exact(n):
        data=proc.stdout.read(n)
        if len(data)!=n:raise RuntimeError(('short frame',n,len(data),proc.poll()))
        return data
    with open(a.source,'rb') as src:
        while True:
            frame=struct.unpack('<I',exact(4))[0]
            if frame==1:
                off,n=struct.unpack('<QI',exact(12));assert off<=size and n<=size-off and n<=65536
                src.seek(a.base+off);data=src.read(n);assert len(data)==n
                
                try:proc.stdin.write(struct.pack('<I',n)+data);proc.stdin.flush();read_bytes+=n
                except BrokenPipeError:raise RuntimeError(('helper exited',off,n,proc.wait(),proc.poll()))
                if a.capture:reads[(off,n)]=data
            elif frame==2:
                flags,sz,mt,n=struct.unpack('<IQQI',exact(24));name=exact(n).decode();listing.append({'path':name,'directory':bool(flags&1),'size':sz})
                if not a.quiet:print(name,sz,flush=True)
            elif frame==3:
                n=struct.unpack('<I',exact(4))[0];data=exact(n);digest.update(data);content+=n
            elif frame==4:
                err,total=struct.unpack('<IQ',exact(12));print('result',err,total,'source reads',read_bytes,'content',content,'sha256',digest.hexdigest(),flush=True);assert err==0;break
            else:raise RuntimeError(('invalid frame',frame))
    proc.stdin.close();assert proc.wait(timeout=5)==0
    if a.capture:
        target=Path(a.capture);target.mkdir(parents=True,exist_ok=True);index=[]
        for i,((off,n),data) in enumerate(sorted(reads.items())):
            f=str(i)+'.bin';(target/f).write_bytes(data);index.append({'offset':off,'size':n,'file':f,'sha256':hashlib.sha256(data).hexdigest()})
        (target/'manifest.json').write_text(json.dumps({'source':a.source,'base':a.base,'size':size,'path':a.path,'listing':listing,'content_size':content,'content_sha256':digest.hexdigest(),'reads':index},indent=2))

if __name__=='__main__':main()

