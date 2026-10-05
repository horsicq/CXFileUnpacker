"""Full authentic ReFS helper READ control using a successful LIST capture.

Reads all regular members into a streaming SHA256 sink in RAM. Reports actual
lengths and hashes; it asserts every returned length matches canonical LIST.
This is a control of the helper. The application CLI is tested separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

def main():
    p=argparse.ArgumentParser();p.add_argument('--helper',required=True);p.add_argument('--source',required=True);p.add_argument('--listing',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    manifest=json.loads(Path(a.listing).read_text());entries=manifest['listing'];base=manifest['base'];size=manifest['size'];results=[]
    with open(a.source,'rb') as source:
        for item in entries:
            if item['directory']:continue
            path=item['path'].encode();proc=subprocess.Popen([a.helper],stdin=subprocess.PIPE,stdout=subprocess.PIPE);proc.stdin.write(struct.pack('<4sIQQQII',b'GFS1',2,size,128*1024*1024,(1<<63)-1,4,len(path))+b'refs'+path);proc.stdin.flush();count=0;digest=hashlib.sha256()
            def exact(n):
                data=proc.stdout.read(n);assert len(data)==n,('short frame',item['path'],n,len(data));return data
            while True:
                frame=struct.unpack('<I',exact(4))[0]
                if frame==1:
                    off,n=struct.unpack('<QI',exact(12));assert off<=size and n<=size-off and n<=65536;source.seek(base+off);data=source.read(n);assert len(data)==n;proc.stdin.write(struct.pack('<I',n)+data);proc.stdin.flush()
                elif frame==3:
                    n=struct.unpack('<I',exact(4))[0];assert n<=65536;data=exact(n);digest.update(data);count+=n
                elif frame==4:
                    error,actual=struct.unpack('<IQ',exact(12));assert error==0 and actual==count==item['size'],(item['path'],error,actual,count,item['size']);break
                else:raise AssertionError(frame)
            proc.stdin.close();assert proc.wait(timeout=5)==0
            results.append({'path':item['path'],'bytes':count,'sha256':digest.hexdigest()})
            if len(results)%100==0:print('checked',len(results),'regular members',flush=True)
    report={'source':a.source,'base':base,'length':size,'members':len(entries),'directories':sum(e['directory'] for e in entries),'files':len(results),'total_bytes':sum(r['bytes'] for r in results),'failures':[],'helper_sha256':hashlib.sha256(Path(a.helper).read_bytes()).hexdigest(),'results':results}
    Path(a.report).write_text(json.dumps(report,indent=2)+'\n');print('passed',report['files'],'regular members,',report['total_bytes'],'decoded bytes')

if __name__=='__main__':main()
