#!/usr/bin/env python3
"""Independent AES/PBKDF2/AF disk fixtures; optional QEMU byte cross-check.

PyCryptodome is a fixture encoder only, never a production dependency. Source
images are generated here and every native extraction must exactly match the
independently constructed plaintext. No input program is executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from Crypto.Cipher import AES

P = struct.pack
PASSWORD = 'disk-password!'


def pattern(n, seed=7):
    return bytes((i * 37 + seed) & 255 for i in range(n))


def encrypt(data, key, mode, first=0):
    result = bytearray()
    for off in range(0, len(data), 512):
        sector = first + off // 512
        iv = P('<Q', sector) + bytes(8)
        if mode == 'cbc-plain':
            iv = P('<I', sector & 0xffffffff) + bytes(12)
        if mode == 'cbc-essiv:sha256':
            iv = AES.new(hashlib.sha256(key).digest(), AES.MODE_ECB).encrypt(iv)
        if mode.startswith('cbc-'):
            result += AES.new(key, AES.MODE_CBC, iv).encrypt(data[off:off + 512])
        else:
            a, b = key[:len(key)//2], key[len(key)//2:]
            tweak = int.from_bytes(AES.new(b, AES.MODE_ECB).encrypt(iv), 'little')
            cipher = AES.new(a, AES.MODE_ECB)
            for k in range(0, 512, 16):
                x = int.from_bytes(data[off+k:off+k+16], 'little') ^ tweak
                y = int.from_bytes(cipher.encrypt(x.to_bytes(16, 'little')), 'little') ^ tweak
                result += y.to_bytes(16, 'little')
                carry = tweak >> 127
                tweak = ((tweak << 1) & ((1 << 128)-1)) ^ (0x87 if carry else 0)
    return bytes(result)


def diffuse(block, name):
    hlen = hashlib.new(name).digest_size
    return b''.join(hashlib.new(name, P('>I', k//hlen) + block[k:k+hlen]).digest()[:min(hlen,len(block)-k)]
                    for k in range(0, len(block), hlen))


def split(key, stripes, name):
    state = bytes(len(key))
    output = bytearray()
    for k in range(stripes-1):
        part = pattern(len(key), 19+k)
        output += part
        state = diffuse(bytes(a ^ b for a,b in zip(state, part)), name)
    output += bytes(a ^ b for a,b in zip(state, key))
    return bytes(output)


def luks(plain, mode='xts-plain64', n=64, name='sha256', password=PASSWORD,
         stripes=7, detached=False, second=False, qemu_compatible=False):
    key = pattern(n, 13)
    stripe_n = n * stripes
    slot_size = (stripe_n + 4095) // 4096 * 4096
    payload = 4096 + 8 * slot_size
    h = bytearray(payload)
    h[:8] = b'LUKS\xba\xbe\0\1'
    for at,text in ((8,'aes'),(40,mode),(72,name),(168,'12345678-1234-1234-1234-123456789abc')):
        h[at:at+len(text)] = text.encode()
    h[104:112] = P('>II', 0 if detached else payload//512, n)
    salt = pattern(32, 41)
    h[132:164] = salt
    h[164:168] = P('>I', 19)
    h[112:132] = hashlib.pbkdf2_hmac(name, key, salt, 19, 20)
    for slot in range(8):
        at=208+48*slot
        h[at:at+4] = P('>I', 0xdead)
        h[at+40:at+48] = P('>II', (4096+slot*slot_size)//512, stripes)
    enabled=[(0, 'not-the-password' if second else password)]
    if second:
        enabled.append((1,password))
    for slot,pw in enabled:
        at=208+48*slot
        slot_salt=pattern(32, 83+slot)
        h[at:at+8] = P('>II', 0xac71f3, 23)
        h[at+8:at+40] = slot_salt
        derived=hashlib.pbkdf2_hmac(name,pw.encode(),slot_salt,23,n)
        raw=split(key,stripes,name)
        raw += bytes((-len(raw)) % 512)
        where=4096+slot*slot_size
        h[where:where+len(raw)] = encrypt(raw,derived,mode)
    return bytes(h) if detached else bytes(h)+encrypt(plain,key,mode), key


def qcow1(plain, password=PASSWORD):
    cluster=512
    h=bytearray(1024+len(plain))
    h[:48]=P('>IIQIIQBBHIQ',0x514649fb,1,0,0,0,len(plain),9,6,0,1,48)
    h[48:56]=P('>Q',512)
    for k in range(len(plain)//cluster):
        h[512+k*8:520+k*8]=P('>Q',1024+k*cluster)
    key=password.encode()[:16].ljust(16,b'\0')
    h[1024:]=encrypt(plain,key,'cbc-plain64')
    return bytes(h)


def qcow2(plain, version=3, password=PASSWORD, embedded=False):
    c=4096
    # One L1 and L2, two refcount clusters, then all allocated data clusters.
    n=(len(plain)+c-1)//c
    header_size=104 if version==3 else 72
    h=bytearray((5+n)*c)
    h[:72]=P('>IIQIIQIIQQIIQ',0x514649fb,version,0,0,12,len(plain),2 if embedded else 1,1,c,3*c,1,0,0)
    if version==3:
        h[72:104]=P('>QQQII',0,0,0,4,104)
    h[c:c+8]=P('>Q',(1<<63)|2*c)
    h[3*c:3*c+8]=P('>Q',4*c)
    for k in range(5+n):
        h[4*c+k*2:4*c+k*2+2]=P('>H',1)
    if embedded:
        detached,key=luks(b'',n=32,detached=True)
        where=len(h)
        h[header_size:header_size+24]=P('>IIQQ',0x0537be77,16,where,len(detached))
        h += detached
    else:
        key=password.encode()[:16].ljust(16,b'\0')
    for k in range(n):
        body=plain[k*c:(k+1)*c].ljust(c,b'\0')
        if body==bytes(c):
            continue
        host=(5+k)*c
        h[2*c+k*8:2*c+k*8+8]=P('>Q',(1<<63)|host)
        h[host:host+c]=encrypt(body,key,'xts-plain64' if embedded else 'cbc-plain64',host//512 if embedded else k*c//512)
    return bytes(h)


def run(command, expect=0):
    r=subprocess.run([str(x) for x in command],capture_output=True,timeout=25)
    if r.returncode not in (expect if isinstance(expect, tuple) else (expect,)):
        raise AssertionError(f'{command[0]} exit {r.returncode}, expected {expect}\n{r.stdout.decode(errors="replace")}\n{r.stderr.decode(errors="replace")}')
    return r


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--unpacker')
    ap.add_argument('--crypto-probe',required=True)
    ap.add_argument('--qemu')
    ap.add_argument('--root')
    args=ap.parse_args()
    context=tempfile.TemporaryDirectory(prefix='xfu-disk-crypto-') if not args.root else None
    root=Path(args.root or context.name);root.mkdir(parents=True,exist_ok=True)
    plain=pattern(1536)
    cases=[]
    for mode in ('cbc-plain','cbc-plain64','cbc-essiv:sha256'):
        for name,n in (('sha1',16),('sha256',24),('sha256',32)):
            data,_=luks(plain,mode,n,name)
            cases.append((3,f'{mode.replace(":", "-")}-{name}-{n}',data,plain,PASSWORD))
    for n in (32,64):
        for name in ('sha1','sha256'):
            data,_=luks(plain,n=n,name=name)
            cases.append((3,f'xts-{name}-{n}',data,plain,PASSWORD))
    for label,password,second in (('empty','',False),('later-slot',PASSWORD,True)):
        data,_=luks(plain,password=password,second=second)
        cases.append((3,label,data,plain,password))
    cases.append((1,'qcow1-aes',qcow1(plain),plain,PASSWORD))
    guest=pattern(4096)+bytes(4096)+pattern(4096,91)
    for version in (2,3):
        cases.append((2,f'qcow{version}-aes',qcow2(guest,version),guest,PASSWORD))
    cases.append((2,'qcow3-luks1',qcow2(guest,embedded=True),guest,PASSWORD))
    longpw='0123456789abcdefextra-ignored-by-legacy'
    cases.append((1,'qcow1-long-key',qcow1(plain,longpw),plain,longpw))
    proof=[]
    for kind,label,data,expected,pw in cases:
        folder=root/label;folder.mkdir(exist_ok=True);src=folder/'source.img';body=folder/'expected.bin';src.write_bytes(data);body.write_bytes(expected)
        before=(hashlib.sha256(src.read_bytes()).hexdigest(),src.stat().st_mtime_ns)
        run([args.crypto_probe,kind,src,pw,body])
        if args.unpacker:
            reader={1:'qcow1',2:'qcow',3:'luks'}[kind]
            out=folder/'out';run([args.unpacker,'t',src,'--reader',reader,'-p'+pw]);run([args.unpacker,'x',src,'--reader',reader,'-p'+pw,'-o'+str(out)])
            outputs=[p for p in out.rglob('*') if p.is_file()]
            assert len(outputs)==1 and outputs[0].read_bytes()==expected,(label,outputs)
            none=run([args.unpacker,'t',src,'--reader',reader],1)
            if kind==3 or 'luks' in label:
                run([args.unpacker,'t',src,'--reader',reader,'-pwrong'],1)
        assert before==(hashlib.sha256(src.read_bytes()).hexdigest(),src.stat().st_mtime_ns)
        proof.append(dict(case=label,kind=kind,source_sha256=before[0],plaintext_sha256=hashlib.sha256(expected).hexdigest(),source_unchanged=True))
    negatives=[]
    original,_=luks(plain)
    for label,at,body in [('slot-body-digest-mismatch',4096,b'\xff'),('master-digest-mismatch',112,b'\xff'),
                          ('slot-outside-source',248,P('>I',0xffffffff)),('slot-zero-iterations',212,bytes(4)),
                          ('slot-zero-stripes',252,bytes(4)),('slot-overlaps-payload',248,P('>I',(len(original)-len(plain))//512)),
                          ('unsupported-cipher',8,b'twofish\0'),('unsupported-mode',40,b'xts-benbi\0'),
                          ('unsupported-hash',72,b'sha512\0'),('bounded-KDF',212,P('>I',0xffffffff))]:
        data=bytearray(original);data[at:at+len(body)]=body;negatives.append((3,label,bytes(data)))
    overlap=bytearray(original);overlap[256:304]=overlap[208:256]
    negatives.append((3,'overlapping-active-slots',bytes(overlap)))
    negatives.append((3,'partial-payload-sector',original[:-1]))
    l2=bytearray(32768+len(plain));l2[:8]=b'LUKS\xba\xbe\0\2';l2[8:16]=P('>Q',16384);l2[16:24]=P('>Q',1);l2[72:79]=b'sha256\0';l2[4096:4144]=b'{"segments":{"0":{"offset":"32768"}}}'.ljust(48,b' ')
    negatives.append((3,'unsupported-LUKS2',bytes(l2)))
    embedded=bytearray(qcow2(guest,embedded=True))
    for label,at,body in [('crypto-extension-length',108,P('>I',8)),('crypto-header-outside-source',112,P('>Q',1<<62)),
                          ('crypto-header-too-small',120,P('>Q',591)),('missing-crypto-extension',104,bytes(8))]:
        data=bytearray(embedded);data[at:at+len(body)]=body;negatives.append((2,label,bytes(data)))
    late=bytearray(qcow2(pattern(71*4096)))
    late[8192+70*8:8192+71*8]=P('>Q',(1<<63)|(len(late)+4096))
    negatives.append((2,'invalid-cluster-after-old-64-cluster-cutoff',bytes(late)))
    compressed=bytearray(qcow2(guest));compressed[8192:8200]=P('>Q',(1<<62)|5*4096)
    negatives.append((2,'encrypted-compressed-cluster',bytes(compressed)))
    q1=bytearray(qcow1(plain));q1[512:520]=P('>Q',(1<<63)|1024|(20<<(63-9)))
    negatives.append((1,'qcow1-encrypted-compressed-cluster',bytes(q1)))
    negatives.append((1,'qcow1-truncated-cipher-sector',qcow1(plain)[:-1]))
    for kind,label,data in negatives:
        folder=root/label;folder.mkdir(exist_ok=True);src=folder/'source.img';src.write_bytes(data);body=folder/'expected.bin';body.write_bytes(plain)
        before=hashlib.sha256(data).hexdigest();run([args.crypto_probe,kind,src,PASSWORD,body,'reject'])
        if args.unpacker:
            reader={1:'qcow1',2:'qcow',3:'luks'}[kind]
            out=folder/'out';run([args.unpacker,'t',src,'--reader',reader,'-p'+PASSWORD],(1,2));run([args.unpacker,'x',src,'--reader',reader,'-p'+PASSWORD,'-o'+str(out)],(1,2))
            assert not out.exists() or not any(p.is_file() for p in out.rglob('*')),label
        assert hashlib.sha256(src.read_bytes()).hexdigest()==before
        proof.append(dict(case=label,kind=kind,rejected=True,source_unchanged=True,source_sha256=before))
    if args.qemu:
        # A trusted independent implementation creates its own LUKS1 and
        # QCOW AES images from known plaintext, then the native RAM probe
        # compares their complete logical bytes. No filesystem is mounted.
        raw=root/'qemu-plain.raw';raw.write_bytes(guest)
        for fmt,kind,opts in [('luks',3,'key-secret=secret,cipher-alg=aes-256,cipher-mode=xts,ivgen-alg=plain64,hash-alg=sha256,iter-time=1'),
                              ('qcow2',2,'encrypt.format=aes,encrypt.key-secret=secret'),
                              ('qcow2',2,'encrypt.format=luks,encrypt.key-secret=secret,encrypt.iter-time=1'),
                              ('qcow',1,'encrypt.format=aes,encrypt.key-secret=secret')]:
            name=f'qemu-{fmt}-{len(proof)}';src=root/(name+'.img')
            run([args.qemu,'convert','--object','secret,id=secret,data='+PASSWORD,'-f','raw','-O',fmt,'-o',opts,raw,src])
            run([args.crypto_probe,kind,src,PASSWORD,raw])
            proof.append(dict(case=name,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),plaintext_sha256=hashlib.sha256(guest).hexdigest(),independent_producer='QEMU qemu-img'))
    (root/'report.json').write_text(json.dumps(dict(passed=len(proof),cases=proof),indent=2)+'\n')
    print(f'{len(proof)} encrypted disk cases passed exact plaintext and RAM lifecycle checks')
    if context:context.cleanup()


if __name__=='__main__':
    main()
