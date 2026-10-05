"""Native WIM RAM compression, independent decoders, ratio and corruption proof."""
import argparse, hashlib, json, pathlib, shutil, struct, subprocess, time, uuid

def run(args, timeout=120):
    p = subprocess.run(list(map(str,args)),capture_output=True,timeout=timeout)
    if p.returncode: raise RuntimeError(f'{args}: {p.returncode}\n{p.stdout.decode("utf-8","replace")}\n{p.stderr.decode("utf-8","replace")}')
    return p.stdout

def payload(pattern,size):
    x=0x12345678; out=bytearray()
    for i in range(size):
        x ^= (x<<13)&0xffffffff; x ^= x>>17; x ^= (x<<5)&0xffffffff
        out.append(x&255 if pattern=='random' or pattern=='mixed' and i//32768%2 else i%23)
    return bytes(out)

def resource(image,expected):
    data=image.read_bytes(); at=struct.unpack_from('<Q',data,0x38)[0]; length=int.from_bytes(data[0x30:0x37],'little'); key=hashlib.sha1(expected).digest()
    for pos in range(at,at+length,50):
        if data[pos+30:pos+50]!=key:continue
        packed=int.from_bytes(data[pos:pos+7],'little'); flags=data[pos+7]; offset,size=struct.unpack_from('<QQ',data,pos+8)
        assert size==len(expected)
        item={'lookup_offset':pos,'packed':packed,'size':size,'offset':offset,'flags':flags,'chunks':[]}
        if flags&4:
            chunks=(size+32767)//32768; width=8 if size>0xffffffff else 4; table=(chunks-1)*width; starts=[0]
            starts += [int.from_bytes(data[offset+i*width:offset+(i+1)*width],'little') for i in range(chunks-1)]
            starts.append(packed-table)
            for i in range(chunks):
                k=starts[i+1]-starts[i]; n=min(32768,size-i*32768);assert 0<k<=n
                item['chunks'].append({'packed':k,'size':n,'raw':k==n})
        return item
    raise AssertionError('expected resource not found')

def snapshot(folder):return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}

def main():
    p=argparse.ArgumentParser();p.add_argument('--probe',type=pathlib.Path,required=True);p.add_argument('--writer-probe',type=pathlib.Path,required=True);p.add_argument('--helper',type=pathlib.Path,required=True);p.add_argument('--sevenzip',type=pathlib.Path,required=True);p.add_argument('--wimlib',type=pathlib.Path);p.add_argument('--pipe-probe',type=pathlib.Path);p.add_argument('--stalled-helper',type=pathlib.Path);p.add_argument('--root',type=pathlib.Path,required=True);a=p.parse_args()
    folder=a.root/('run-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);folder.mkdir(parents=True);runtime=folder/'runtime';runtime.mkdir();cases=[];checks=0;proofs=0
    for exe in (a.probe,a.writer_probe,a.helper):shutil.copy2(exe,runtime/exe.name)
    shutil.copy2(a.helper.parent/'libwim-15.dll',runtime/'libwim-15.dll');probe=runtime/a.probe.name;writer=runtime/a.writer_probe.name
    pipe=None
    if a.pipe_probe or a.stalled_helper:
        assert a.pipe_probe and a.stalled_helper
        shutil.copy2(a.pipe_probe,runtime/a.pipe_probe.name);shutil.copy2(a.stalled_helper,runtime/a.stalled_helper.name)
        before=snapshot(runtime);pipe=json.loads(run([runtime/a.pipe_probe.name,runtime/a.stalled_helper.name]));checks+=pipe['checks'];assert snapshot(runtime)==before
    before=snapshot(runtime)
    for method in range(4):
        native=json.loads(run([probe,'controls',method]));checks+=native['checks'];cases.append({'method':method,'control':native});assert snapshot(runtime)==before
    for method in range(1,4):
        for mode in ('full','short','base','empty','invalid'):
            image=folder/f'{method}-{mode}.wim';native=json.loads(run([writer,image,mode,method]));checks+=native['checks']
            if mode!='invalid':
                independent=image
                if mode=='base':independent=folder/f'{method}-base-plain.wim';independent.write_bytes(image.read_bytes()[17:]);assert image.read_bytes()[:17]==b'XFU-prefix-17BYTE'
                run([a.sevenzip,'t',independent]);proofs+=1
                if a.wimlib:run([a.wimlib,'verify',independent]);proofs+=1
            cases.append({'method':method,'mode':mode,'native':native})
        for pattern,size,level in [('repeat',0,0),('repeat',1,0),('repeat',32767,0),('repeat',32768,0),('repeat',32769,0),('repeat',131073,10),('repeat',131073,100),('mixed',131073,0),('random',131073,0),('repeat',1048577,0)]:
            image=folder/f'{method}-{pattern}-{size}-{level}.wim';native=json.loads(run([probe,'create',image,method,pattern,size,level]));checks+=native['checks'];raw=payload(pattern,size)
            run([a.sevenzip,'t',image]);proofs+=1
            extracted=run([a.sevenzip,'x','-so',image,'nested/payload-*.bin']);assert extracted==raw;proofs+=1
            if a.wimlib:run([a.wimlib,'verify',image]);proofs+=1
            data=image.read_bytes();assert struct.unpack_from('<I',data,12)[0]==(0xe00 if method==3 else 0x10d00);assert struct.unpack_from('<I',data,20)[0]==32768
            info=resource(image,raw) if size else None
            if pattern=='repeat' and size>=32767:assert info['flags']&4 and info['packed']<size//2
            if pattern=='mixed':assert any(c['raw'] for c in info['chunks']) and any(not c['raw'] for c in info['chunks'])
            if pattern=='random':assert not info['flags']&4 and info['packed']==size
            cases.append({'method':method,'pattern':pattern,'size':size,'level':level,'native':native,'resource':info,'sha256':hashlib.sha256(raw).hexdigest(),'file_size':len(data)})
            snap=snapshot(folder);native=json.loads(run([probe,'test',image,1]));checks+=native['checks'];assert snapshot(folder)==snap
            if pattern=='mixed':
                mutations={};start=info['offset'];tablebytes=4*((size+32767)//32768-1)
                bad=bytearray(data);bad[start+tablebytes]^=0xff;mutations['payload']=bad
                bad=bytearray(data);bad[info['lookup_offset']+30]^=0xff;mutations['sha1']=bad
                bad=bytearray(data);struct.pack_into('<I',bad,start,0xffffffff);mutations['chunk-table']=bad
                mutations['truncated']=data[:-128]
                for name,bad in mutations.items():
                    path=folder/f'{method}-bad-{name}.wim';path.write_bytes(bad);snap=snapshot(folder);native=json.loads(run([probe,'test',path,0]));checks+=native['checks'];assert snapshot(folder)==snap;cases.append({'method':method,'rejected':name,'native':native})
    # Missing runtime is an explicit pre-write rejection; stored controls still run.
    isolated=folder/'absent';isolated.mkdir();shutil.copy2(probe,isolated/probe.name)
    native=json.loads(run([isolated/probe.name,'controls',0]));checks+=native['checks']
    for method in range(1,4):
        output=isolated/f'no-runtime-{method}.wim';result=subprocess.run([str(isolated/probe.name),'create',str(output),str(method),'repeat','32768','0'],capture_output=True,timeout=10);assert result.returncode and output.stat().st_size==0;checks+=1
    report={'pipe_controls':pipe,'cases':cases,'native_checks':checks,'independent_proofs':proofs,'sevenzip_sha256':hashlib.sha256(a.sevenzip.read_bytes()).hexdigest(),'wimlib_reference_ran':bool(a.wimlib),'wimlib_sha256':hashlib.sha256(a.wimlib.read_bytes()).hexdigest() if a.wimlib else None,'ram_test_snapshots_unchanged':True,'helper_sha256':hashlib.sha256(a.helper.read_bytes()).hexdigest()}
    path=folder/'wim-compression-report.json';path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(f'{checks} native controls; {proofs} independent proofs passed. {path}')
if __name__=='__main__':main()
