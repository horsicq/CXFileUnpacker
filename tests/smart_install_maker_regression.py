"""Independent SIM/CAB fixtures, Binary Refinery comparison, public RAM controls."""
import argparse,hashlib,json,os,struct,subprocess,sys,time,uuid,zlib
from pathlib import Path

def checksum(p):
 n=0
 while len(p)>=4:n^=int.from_bytes(p[:4],'little');p=p[4:]
 return n^(int.from_bytes(p,'big') if p else 0)
def lzx(p):
 bits='0'+'011'+f'{len(p):024b}';bits+='0'*(-len(bits)%16)
 return b''.join(struct.pack('<H',int(bits[i:i+16],2)) for i in range(0,len(bits),16))+struct.pack('<III',1,1,1)+p+(b'\0' if len(p)&1 else b'')
def cabinet(values,method=0,reserved=False):
 table=b'';offset=0
 for i,(_,p) in enumerate(values):table+=struct.pack('<IIHHHH',len(p),offset,0,0,0,32)+str(i).encode()+b'\0';offset+=len(p)
 data=b''.join(p for _,p in values);hr,fr,dr=(b'head',b'folder',b'data') if reserved else (b'',b'',b'')
 extra=struct.pack('<HBB',len(hr),len(fr),len(dr))+hr if reserved else b'';files=36+len(extra)+8+len(fr);at=files+len(table);blocks=b'';previous=b'';count=0
 for start in range(0,len(data),32768):
  p=data[start:start+32768]
  if method==0:z=p
  elif method==1:
   kwargs={'zdict':previous} if previous else {};encoder=zlib.compressobj(9,zlib.DEFLATED,-15,**kwargs);z=b'CK'+encoder.compress(p)+encoder.flush();previous=(previous+p)[-32768:]
  else:z=lzx(p)
  lengths=struct.pack('<HH',len(z),len(p));blocks+=struct.pack('<I',checksum(z)^int.from_bytes(lengths,'little'))+lengths+dr+z;count+=1
 folder=struct.pack('<IHH',at,count,0x1503 if method==3 else method)+fr
 header=b'MSCF'+struct.pack('<IIIII',0,at+len(blocks),0,files,0)+struct.pack('<BBHHHHH',3,1,1,len(values),4 if reserved else 0,0,0)
 return (header+extra+folder+table+blocks)[4:]
def fixture(values,mode='stored',method=0,reserved=False,codec='cp1252',lcid=1033,prefix=0):
 h=[b'0']*119;h[0]=b'Smart Install Maker v.5.02';h[26]=b'1';h[67]=str(len(values)).encode();h[95]=h[117]=h[118]=b'0'
 filetable=b''.join(b'0\0'+name.encode(codec)+b'\0' +b'0\0' for name,p in values);language=b'0\0English\0'+str(lcid).encode()+b'\0' +b'0\0'
 runtime=[('$inst\\4.tmp',b'PNG-runtime\0\xff')];runtime_is_cab=mode=='runtime-cab'
 r=cabinet(runtime,method,reserved) if runtime_is_cab else b''.join(name.encode(codec)+b'\0'+str(len(p)).encode()+b'\0'+p for name,p in runtime)
 if mode=='stored':content=b''.join(struct.pack('<IIIIII',0,len(p),0,0,0,0)+p for _,p in values)
 else:content=cabinet(values,method,reserved);h[118]=str(len(content)).encode()
 strings=b'\0'.join(h)+b'\0'+filetable+language+b'\0';so=4096;ro=so+len(strings);co=ro+len(r)
 trailer=struct.pack('<QQQQ?BBB',so,len(r),ro,co,runtime_is_cab,1,119,0xf1);image=b'MZ'+b'\0'*4094+strings+r+content+trailer
 expected={'setup/strings.bin':strings,'runtime/0' if runtime_is_cab else 'runtime/header.png':runtime[0][1]}
 for name,p in values:
  name=name.replace('\\','/').replace('@$&%04','$InstallPath').replace('@$&%17','$SystemDrive')
  if len(name)>2 and name[1:3]==':/':name='$Drive'+name[0].upper()+'/'+name[3:]
  expected[('data/' if mode=='stored' else 'content/')+name]=p
 return b'R'*prefix+image,expected

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--probe',required=True,type=Path);ap.add_argument('--root',required=True,type=Path);ap.add_argument('--reference',type=Path);a=ap.parse_args()
 xtsim=None;oracle_checks=0;reference_version=None
 if a.reference:
  sys.path.insert(0,str(a.reference))
  from refinery.units.formats.archive.xtsim import xtsim
  from refinery.lib.structures import StructReader
  import importlib.metadata
  reference_version=importlib.metadata.version('binary-refinery')
  # Upstream pure-Python 0.11.2 returns memoryview where xtsim expects bytes;
  # its Cythonized tests return bytes. Normalize representation only.
  original=StructReader.read_c_string
  def compatible(self,*args,**kwargs):
   result=original(self,*args,**kwargs);return bytes(result) if isinstance(result,memoryview) else result
  StructReader.read_c_string=compatible
 root=a.root/('run-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);root.mkdir(parents=True);blocked=root/'blocked-temp';blocked.write_bytes(b'not a directory');env=dict(os.environ,TEMP=str(blocked),TMP=str(blocked));checks=0;cases=[]
 def run(name,data,expected=None,valid=True,memory=None,base=0):
  nonlocal checks,oracle_checks
  source=root/(name+'.exe');source.write_bytes(data);before={str(p.relative_to(root)) for p in root.rglob('*')};cmd=[str(a.probe),str(source),'','1' if valid else '0']
  if memory is not None or base:cmd.append(str(memory if memory is not None else 256*1024*1024))
  if base:cmd.append(str(base))
  tested=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=90);assert tested.returncode==0,(name,tested.stdout,tested.stderr);detail=json.loads(tested.stdout);checks+=detail['checks']
  assert before=={str(p.relative_to(root)) for p in root.rglob('*')};assert source.read_bytes()==data;checks+=2
  if valid:
   out=root/(name+'-output');cmd[2]=str(out);decoded=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=90);assert decoded.returncode==0,(name,decoded.stderr);checks+=json.loads(decoded.stdout)['checks']
   actual={str(p.relative_to(out)).replace('\\','/'):p.read_bytes() for p in out.rglob('*') if p.is_file()};assert actual==expected,(name,actual.keys(),expected.keys());checks+=len(actual)
   if xtsim:
    oracle={str(item.path).replace('\\','/'):bytes(item.get_data()) for item in xtsim().unpack(data[base:])}
    for path,payload in expected.items():
     if path=='setup/strings.bin':continue
     assert oracle[path]==payload,(name,path);checks+=1;oracle_checks+=1
  cases.append(dict(name=name,accepted=valid,source_sha256=hashlib.sha256(data).hexdigest(),controls=detail['checks'],test_created_no_files=True,cursor_restored=True,short_reads=True,reference_compared=bool(valid and xtsim)))
 values=[('@$&%04\\payload.bin',bytes(range(256))*5),('C:\\nest\\empty.bin',b''),('@$&%17\\notes.txt',b'notes\n')]
 for mode in ('stored','cab','runtime-cab'):
  for method in ((0,) if mode=='stored' else (0,1,3)):
   for reserved in ((False,) if mode=='stored' else (False,True)):
    data,expected=fixture(values,mode,method,reserved);run(f'{mode}-{method}-{int(reserved)}',data,expected)
 data,expected=fixture(values,prefix=777);run('rebased',data,expected)
 data,expected=fixture(values);run('borrowed-base',b'P'*313+data,expected,base=313)
 for codec,lcid,name in [('cp1251',1049,'@$&%17\\\u041f\u043b\u0430\u0442\u0435\u0436 \u2116131.pdf'),('cp932',1041,'@$&%04\\\u65e5\u672c\u8a9e.txt')]:
  # Unicode escapes make the fixture source portable between Windows locales.
  name=name.encode().decode('unicode_escape') if '\\u' in name else name
  data,expected=fixture([(name,b'Unicode payload')],codec=codec,lcid=lcid);run('unicode-'+codec,data,expected)
 data,expected=fixture([('@$&%04\\large.bin',bytes(range(251))*530)],'cab',1);run('dictionary-multi-block',data,expected)
 data,_=fixture(values);run('low-memory',data,valid=False,memory=1024)
 for cut in (1,8,35,36,100,len(data)-100):run('truncated-'+str(cut),data[:-cut],valid=False)
 for offset in (0,16,24,32,34,35):
  bad=bytearray(data);bad[-36+offset]=255;run('trailer-'+str(offset),bad,valid=False)
 for path in ('COM\u00b9.foo','LPT\u00b2.txt','../escape','dir/../../escape','/absolute','CON.foo','dir/NUL.txt','file.','file ','dir//file'):
  bad,_=fixture([(path,b'bad')]);run('unsafe-'+str(len(cases)),bad,valid=False)
 bad,_=fixture([('same',b'one'),('SAME',b'two')]);run('duplicate',bad,valid=False)
 bad,_=fixture([('\u0444\u0430\u0439\u043b',b'one'),('\u0424\u0410\u0419\u041b',b'two')],codec='cp1251',lcid=1049);run('duplicate-unicode',bad,valid=False)
 compressed,_=fixture(values,'cab',1)
 bad=bytearray(compressed);co=struct.unpack_from('<Q',bad,len(bad)-36+24)[0];bad[co+26]=3;run('multivolume',bad,valid=False)
 bad=bytearray(compressed);bad[-37]^=1;run('cab-checksum',bad,valid=False)
 for offset in (36,4,len(compressed)):
  bad=bytearray(compressed);co=struct.unpack_from('<Q',bad,len(bad)-36+24)[0];struct.pack_into('<I',bad,co+32,offset);run('cab-data-offset-'+str(offset),bad,valid=False)
 run('not-installer',b'MZ'+bytes(4998),valid=False)
 bad=bytearray(compressed);ro=struct.unpack_from('<Q',bad,len(bad)-36+16)[0];bad[ro-1]=65;run('bad-string-terminator',bad,valid=False)
 report=dict(all_passed=True,checks=checks,fixtures=len(cases),reference_comparison_ran=bool(xtsim),reference=('Binary Refinery xtsim '+reference_version+'; bytes/memoryview representation normalization only') if xtsim else None,reference_checks=oracle_checks,fixture_verification='Independently authored stored/MSZIP/LZX CAB and SIM fixtures compared with known exact payload bytes',cases=cases,test_payload_disk_writes=0,limitations=['EOF footer grammar only','Single-volume CAB only','Quantum decoder wired but no independent SIM Quantum fixture','Unsupported password/encryption variants not claimed'])
 target=root/'smart-install-maker-report.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(report=str(target),checks=checks,fixtures=len(cases),all_passed=True)))
if __name__=='__main__':main()
