"""WIM create options and preservation before unavailable/invalid compression."""
import argparse,json,os,pathlib,shutil,struct,subprocess,tempfile
def run(args,ok=True,env=None):
    p=subprocess.run(list(map(str,args)),capture_output=True,timeout=90,env=env)
    if (p.returncode==0)!=ok:raise AssertionError((args,p.returncode,p.stdout,p.stderr))
    return p
def main():
    p=argparse.ArgumentParser();p.add_argument('--cli',type=pathlib.Path,required=True);p.add_argument('--sevenzip',type=pathlib.Path,required=True);p.add_argument('--root',type=pathlib.Path,required=True);a=p.parse_args();a.root.mkdir(parents=True,exist_ok=True)
    folder=pathlib.Path(tempfile.mkdtemp(prefix='run-',dir=a.root));source=folder/'source.bin';source.write_bytes(b'WIM compression payload\n'*12000);checks=0
    for method,flag in [('stored',0),('xpress',0x20000),('lzx',0x40000),('lzms',0x80000),(None,0x20000)]:
        image=folder/f'{method or "default"}.wim';args=[a.cli,'a',image,source]
        if method:args+=['--compression='+method]
        run(args);checks+=1;header=image.read_bytes();assert struct.unpack_from('<I',header,16)[0]&0xe0000==flag;checks+=1
        run([a.sevenzip,'t',image]);checks+=1
        original=run([a.sevenzip,'x','-so',image,'source.bin']).stdout;assert original==source.read_bytes();checks+=1
        run([a.cli,'t',image]);checks+=1
        if method!='stored':assert image.stat().st_size<source.stat().st_size//2;checks+=1
    for method,levels in [('stored',[0]),('xpress',[0,100]),('lzx',[0,100]),('lzms',[0,100])]:
        for level in levels:
            image=folder/f'{method}-level-{level}.wim'
            run([a.cli,'a',image,source,'--compression',method,'--compression-level',level]);checks+=1
            run([a.sevenzip,'t',image]);checks+=1
            assert run([a.sevenzip,'x','-so',image,'source.bin']).stdout==source.read_bytes();checks+=1
            run([a.cli,'t',image]);checks+=1
    target=folder/'preserve.wim';sentinel=b'existing archive must survive invalid preflight'
    bad=[['--compression=unknown'],['--compression=lzx','--compression-level=101'],['--compression=stored','--compression-level=1'],['--compression-level=-1'],['--compression-level='],['--compression=xpress','--compression=lzx'],['--compression-level=10','--compression-level=20'],['--compression-level=9junk'],['--compression'],['--compression-level'],['--compression='],['--compression','--compression-level','10'],['--compression-level','--compression','lzx'],['-p']]
    for extra in bad:
        target.write_bytes(sentinel);run([a.cli,'a',target,source]+extra,False);assert target.read_bytes()==sentinel;checks+=2
    for extension in ['zip','tar','7z']:
        target=folder/f'preserve.{extension}';target.write_bytes(sentinel);run([a.cli,'a',target,source,'--compression=xpress'],False);assert target.read_bytes()==sentinel;checks+=2
    image=folder/'space-options.wim';run([a.cli,'a',image,source,'--compression','lzx','--compression-level','10']);checks+=1
    run([a.sevenzip,'t',image]);checks+=1
    # Fresh isolated CLI lacks the compressor; output must not be truncated.
    runtime=folder/'missing-runtime';runtime.mkdir();isolated=runtime/a.cli.name;shutil.copy2(a.cli,isolated)
    target=folder/'missing.wim';target.write_bytes(sentinel);env=os.environ.copy();env.pop('XFU_WIM_CODEC_HELPER',None)
    run([isolated,'a',target,source],False,env);assert target.read_bytes()==sentinel;checks+=2
    run([isolated,'a',folder/'stored-without-helper.wim',source,'--compression=stored'],True,env);checks+=1
    report={'checks':checks,'methods':['stored','xpress','lzx','lzms'],'default':'xpress','target_preservation':'passed'};(folder/'wim-cli-compression-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
