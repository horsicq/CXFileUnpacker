"""Independent ZipCrypto fixtures for CLI passwords, CRCs, and SFX delegation."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import zipfile
import zlib


def encrypt(data,password):
    table=[]
    for value in range(256):
        for _ in range(8): value=(value>>1)^ (0xedb88320 if value&1 else 0)
        table.append(value)
    keys=[0x12345678,0x23456789,0x34567890]
    def update(value):
        keys[0]=(keys[0]>>8)^table[(keys[0]^value)&255]
        keys[1]=((keys[1]+(keys[0]&255))*134775813+1)&0xffffffff
        keys[2]=(keys[2]>>8)^table[(keys[2]^(keys[1]>>24))&255]
    for value in password: update(value)
    out=bytearray()
    for value in data:
        temp=keys[2]|2
        out.append(value^(((temp*(temp^1))>>8)&255));update(value)
    return bytes(out)


def archive(password,prefix=b'',descriptor=False,encrypted=True):
    parts,central=[],[]
    expected={'stored.txt':b'Password regression stored bytes\n'*3,
              'nested/deflated.txt':b'Independent DEFLATE and CRC fixture.\n'*400}
    position=len(prefix)
    for index,(filename,plain) in enumerate(expected.items()):
        name=filename.encode();method=0 if index==0 else 8
        compressor=zlib.compressobj(wbits=-15)
        packed=plain if method==0 else compressor.compress(plain)+compressor.flush()
        crc=zlib.crc32(plain);flags=(1 if encrypted else 0)|(8 if descriptor else 0)
        mtime=0x5c20
        if encrypted:
            header=bytes(range(11))+bytes([mtime>>8 if descriptor else crc>>24])
            packed=encrypt(header+packed,password)
        local=struct.pack('<I5H3I2H',0x04034b50,20,flags,method,mtime,0,
                          0 if descriptor else crc,0 if descriptor else len(packed),
                          0 if descriptor else len(plain),len(name),0)+name+packed
        if descriptor:local+=struct.pack('<4I',0x08074b50,crc,len(packed),len(plain))
        central.append(struct.pack('<I6H3I5H2I',0x02014b50,20,20,flags,method,mtime,0,
            crc,len(packed),len(plain),len(name),0,0,0,0,0,position)+name)
        parts.append(local);position+=len(local)
    directory=b''.join(central)
    return prefix+b''.join(parts)+directory+struct.pack('<I4H2IH',0x06054b50,0,0,
        len(parts),len(parts),len(directory),position,0),expected


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('unpacker',type=Path)
    args=parser.parse_args();exe=args.unpacker.resolve()
    with tempfile.TemporaryDirectory(prefix='xfu_password_') as folder:
        root=Path(folder)
        def run(source,*options,env=None,command='x'):
            return subprocess.run([str(exe),command,str(source),*options],cwd=root,
                env=env,capture_output=True,timeout=30)
        for label,password,descriptor in [('stored-deflate',b'test',False),
            ('descriptor',b'test',True),('unicode','p\u00e4ss\u03bb'.encode(),False),('empty',b'',False)]:
            source=root/(label+'.zip');data,expected=archive(password,descriptor=descriptor)
            source.write_bytes(data)
            # Independent Python decryption establishes fixture validity.
            if password:
                with zipfile.ZipFile(source) as z:
                    assert {name:z.read(name,pwd=password) for name in z.namelist()}==expected
            out=root/(label+'-out')
            process=run(source,'-o'+str(out),'-p'+password.decode())
            assert process.returncode==0,(label,process.stdout,process.stderr)
            assert {str(p.relative_to(out)).replace('\\','/'):p.read_bytes() for p in out.rglob('*') if p.is_file()}==expected
            process=run(source,'-p'+password.decode(),command='t')
            assert process.returncode==0,(label,'test',process.stdout,process.stderr)
        source=root/'stored-deflate.zip'
        for options in ([],['-pwrong']):
            output=root/('bad'+str(len(options)));output.mkdir()
            (output/'stored.txt').write_bytes(b'existing bytes')
            process=run(source,'-o'+str(output),*options)
            assert process.returncode!=0
            assert (output/'stored.txt').read_bytes()==b'existing bytes'
            assert [p for p in output.rglob('*') if p.is_file()]==[output/'stored.txt']
            assert run(source,*options,command='t').returncode!=0
        process=run(source,'-ptest','--advanced',command='l')
        assert process.returncode==0 and b'stored.txt' in process.stdout and b'deflated.txt' in process.stdout
        env=dict(os.environ,XFU_TEST_PASSWORD='p\u00e4ss\u03bb')
        process=run(root/'unicode.zip','-o'+str(root/'env-out'),'--password-env=XFU_TEST_PASSWORD',env=env)
        assert process.returncode==0,(process.stdout,process.stderr)
        assert b'p\xc3\xa4ss' not in process.stdout+process.stderr
        env.pop('XFU_TEST_PASSWORD')
        process=run(source,'--password-env=XFU_TEST_PASSWORD',env=env)
        assert process.returncode==2 and b'not set' in process.stderr
        process=run(source,'-ptest','-pwrong')
        assert process.returncode==2 and b'wrong' not in process.stderr
        # A valid DOS image and ZIP directory exercise password forwarding from
        # the self-extracting wrapper to its internal ZIP reader.
        stub=bytearray(128);stub[:2]=b'MZ';struct.pack_into('<HH',stub,2,128,1)
        struct.pack_into('<H',stub,8,4);stub[64:70]=b'PKSFX '
        data,expected=archive(b'test',bytes(stub))
        source=root/'carrier.exe';source.write_bytes(data)
        process=run(source,'-o'+str(root/'sfx-out'),'-ptest')
        assert process.returncode==0,('SFX',process.stdout,process.stderr)
        assert {str(p.relative_to(root/'sfx-out')).replace('\\','/'):p.read_bytes()
                for p in (root/'sfx-out').rglob('*') if p.is_file()}==expected
        assert run(source,'-ptest',command='t').returncode==0
        assert run(source,'-pwrong',command='t').returncode!=0
    print('Password options: independent ZIPCrypto, descriptors, Unicode/env, empty/wrong password, and SFX passed')


if __name__=='__main__':main()
