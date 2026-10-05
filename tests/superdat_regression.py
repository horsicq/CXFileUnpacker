"""Independent small LH1 fixtures exercise SuperDAT layouts and failure paths."""
import argparse,json,pathlib,struct,subprocess,tempfile,zlib

def lh1_literals(data):
    n=314;t=627;r=626
    freq=[1]*n+[0]*(t+1-n);child=list(range(t,t+n))+[0]*(t-n);parent=[0]*(t+n)
    for i in range(n):parent[i+t]=i
    i=0
    for j in range(n,r+1):freq[j]=freq[i]+freq[i+1];child[j]=i;parent[i]=parent[i+1]=j;i+=2
    freq[t]=65535;bits=[]
    for symbol in data:
        node=parent[symbol+t];code=[]
        while node!=r:
            p=parent[node];code.append(node-child[p]);node=p
        bits.extend(reversed(code));node=parent[symbol+t]
        while True:
            freq[node]+=1;value=freq[node];other=node+1
            if value>freq[other]:
                while value>freq[other+1]:other+=1
                freq[node]=freq[other];freq[other]=value
                first=child[node];parent[first]=other
                if first<t:parent[first+1]=other
                second=child[other];child[other]=first;parent[second]=node
                if second<t:parent[second+1]=node
                child[node]=second;node=other
            node=parent[node]
            if not node:break
    out=bytearray((len(bits)+7)//8)
    for i,b in enumerate(bits):out[i//8]|=b<<(7-i%8)
    return bytes(out)

def member(name,data):
    packed=struct.pack('<I',len(data))+lh1_literals(data)
    name=name.encode('ascii');assert len(name)<260
    return b'__NAILZHUFLIB\0'+name.ljust(260,b'\0')+struct.pack('<II',len(data),len(packed))+bytes([12,34,56,126,10,4])+packed

def group(items):
    return b'\xef\xbe\xad\xde'+b''.join(member(n,d) for n,d in items)+b'NAISIGN\0\0\0\1'+struct.pack('<IH',0,17)

def manifest(items):
    out=bytearray()
    for name,data in items:
        out+=name.encode('ascii').ljust(144,b'\0')+struct.pack('<I',zlib.crc32(data,0xffffffff)^0xffffffff)
        out+=b'1.0'.ljust(12,b'\0')+struct.pack('<I',len(data))+bytes([12,34,56,126,10,4])+b'\0'*8
    return bytes(out)

def package(items,modern=False,signed=False):
    prefix=bytearray(512);prefix[:2]=b'MZ'
    support=[('NaiScrip.nsc',b'script\n'),('GSDSuper.dll',b'dll\n')];body=group(support+items)
    first=group([('0409SDStbRes.dll',b'resource')]) if modern else b''
    table=manifest(items)+(b'\1'+b'\0'*11 if modern else b'')
    footer=b'_SUPERDAT_HEADER\0'+struct.pack('<II',len(body)-4,len(prefix))
    footer+=struct.pack('<III',0,len(items),0) if modern else struct.pack('<II',len(items),0)
    result=bytes(prefix)+first+body+table+footer
    if signed:
        struct.pack_into('<I',prefix,60,64);prefix[64:68]=b'PE\0\0';struct.pack_into('<H',prefix,84,224)
        struct.pack_into('<H',prefix,88,0x10b);struct.pack_into('<I',prefix,180,16)
        struct.pack_into('<II',prefix,216,len(result),70000)
        result=bytes(prefix)+result[512:]+b'certificate-data'.ljust(70000,b'\0')
    return result

def run(args,success=True):
    p=subprocess.run(list(map(str,args)),capture_output=True,timeout=60)
    if (p.returncode==0)!=success:raise AssertionError((args,p.returncode,p.stdout,p.stderr))
    return p

def main():
    p=argparse.ArgumentParser();p.add_argument('--probe',required=True,type=pathlib.Path);p.add_argument('--cli',type=pathlib.Path);p.add_argument('--lifecycle-probe',type=pathlib.Path);p.add_argument('--root',type=pathlib.Path);a=p.parse_args()
    root=a.root or pathlib.Path(tempfile.mkdtemp(prefix='xfu-superdat-'));root.mkdir(parents=True,exist_ok=True);checks=0
    items=[('nested/payload.bin',bytes(range(256))*24),('empty.bin',b'')]
    images=[]
    for modern,signed in [(False,False),(True,False),(True,True)]:
        image=root/f'{modern}-{signed}.exe';image.write_bytes(package(items,modern,signed));images.append(image)
        run([a.probe,image]);checks+=1
        output=root/f'{image.stem}-out';run([a.probe,image,output]);checks+=1
        for name,data in items:assert (output/name).read_bytes()==data;checks+=1
        if a.cli:
            tested=run([a.cli,'t',image]);assert b'100%' in tested.stdout and b'payload.bin' not in tested.stdout;checks+=1
            tested=run([a.cli,'t',image,'--verbose']);assert b'payload.bin' in tested.stdout and b'OK' in tested.stdout;checks+=1
            listing=run([a.cli,'l',image,'--advanced']);assert b'SuperDAT' in listing.stdout and b'CRC32' in listing.stdout;checks+=1
    if a.lifecycle_probe:
        lifecycle=run([a.lifecycle_probe,images[0],images[1]]);print(lifecycle.stdout.decode('utf-8','replace'));checks+=1
    original=images[0].read_bytes();third=original.index(b'__NAILZHUFLIB\0nested/');footer=original.rfind(b'_SUPERDAT_HEADER\0');table=footer-len(items)*178
    negatives={}
    altered=bytearray(original);altered[table+144]^=1;negatives['crc']=altered
    altered=bytearray(original);altered[third+292]^=255;negatives['compressed']=altered
    altered=bytearray(original);struct.pack_into('<I',altered,third+278,0xffffffff);negatives['packed-bound']=altered
    altered=bytearray(original);altered[third+14:third+17]=b'../';negatives['path']=altered
    altered=bytearray(original);struct.pack_into('<I',altered,footer+17,1);negatives['group-bound']=altered
    altered=bytearray(original);struct.pack_into('<I',altered,footer+25,1);negatives['count']=altered
    negatives['truncated']=original[:-1]
    for name,data in negatives.items():
        image=root/f'bad-{name}.exe';image.write_bytes(data);run([a.probe,image],False);checks+=1
        if a.cli:run([a.cli,'t',image,'--reader','superdat'],False);checks+=1
    report={'checks':checks,'layouts':len(images),'negative_cases':list(negatives)};(root/'superdat-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
