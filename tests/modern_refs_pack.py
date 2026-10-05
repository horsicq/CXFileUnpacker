"""Pack exact producer read ranges for an offline borrowed-RAM control.

Usage: modern_refs_pack.py --output control.mfr capture-list capture-read [...]
Input directories come from modern_refs_control.py. No unobserved image byte
is invented. Overlapping reads must agree exactly and every fragment hash is
validated before inclusion. The C lifecycle source rejects uncaptured ranges.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('captures',nargs='+');a=p.parse_args();parts={};length=None;controls=[]
    for name in a.captures:
        directory=Path(name);manifest=json.loads((directory/'manifest.json').read_text())
        assert length is None or length==manifest['size'];length=manifest['size'];controls.append({k:manifest[k] for k in ['base','path','content_size','content_sha256']})
        for fragment in manifest['reads']:
            data=(directory/fragment['file']).read_bytes();assert len(data)==fragment['size'];assert hashlib.sha256(data).hexdigest()==fragment['sha256']
            key=fragment['offset'],fragment['size'];assert key not in parts or parts[key]==data;parts[key]=data
    segments=[]
    for (off,n),data in sorted(parts.items()):
        assert off<=length and n<=length-off
        if segments and off<=segments[-1][0]+len(segments[-1][1]):
            start,previous=segments[-1];shared=min(len(previous)-(off-start),n);assert previous[off-start:off-start+shared]==data[:shared];segments[-1]=start,previous+data[shared:]
        else:segments.append((off,data))
    target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('wb') as f:
        f.write(struct.pack('<4sQI',b'MFR1',length,len(segments)))
        for off,data in segments:f.write(struct.pack('<QI',off,len(data))+data)
    report={'logical_size':length,'segments':len(segments),'captured_bytes':sum(len(data) for _,data in segments),'packed_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'controls':controls,'range_policy':'Uncaptured source reads fail; all included ranges are exact producer bytes.'}
    target.with_suffix('.provenance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
