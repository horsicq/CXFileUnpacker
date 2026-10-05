"""RAM-only stalled archive-codec writer deadline/cancellation controls."""
import argparse,hashlib,json,os,subprocess,time,uuid
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--probe',required=True,type=Path);p.add_argument('--stalled-helper',required=True,type=Path);p.add_argument('--echo-helper',required=True,type=Path);p.add_argument('--root',required=True,type=Path);a=p.parse_args()
 work=a.root/('run-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);work.mkdir(parents=True);block=work/'blocked-temp';block.write_bytes(b'TEMP/TMP not directories');env=dict(os.environ,TEMP=str(block),TMP=str(block));before={str(q.relative_to(work)) for q in work.rglob('*')}
 result=subprocess.run([str(a.probe),str(a.stalled_helper),str(a.echo_helper)],capture_output=True,text=True,env=env,timeout=10)
 assert result.returncode==0,(result.stdout,result.stderr);detail=json.loads(result.stdout);assert before=={str(q.relative_to(work)) for q in work.rglob('*')};assert block.read_bytes()==b'TEMP/TMP not directories'
 report=dict(all_passed=True,checks=detail['checks']+2,controls=detail,test_created_no_files=True,binaries={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in [a.probe,a.stalled_helper,a.echo_helper]});target=work/'archive-codec-pipe-report.json';target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(report=str(target),**report['controls'],all_passed=True)))
if __name__=='__main__':main()
