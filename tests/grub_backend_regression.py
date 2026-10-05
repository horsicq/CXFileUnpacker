#!/usr/bin/env python3
"""Independent filesystem fields + real duplex protocol, no mounted image."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import zlib
P = struct.pack

def xfs():
    # XFS v4,512-byte blocks,256-byte inodes, a short-form root directory,
    # and one extent-backed regular file. Field positions follow XFS docs.
    image = bytearray(8192)
    image[:4] = b'XFSB'
    image[4:8] = P('>I', 512)
    image[8:16] = P('>Q', 16)
    image[56:64] = P('>Q', 4) # sb_rootino
    image[84:88] = P('>I', 16) # sb_agblocks
    image[100:102] = P('>H', 0x2004) # v4 with directoryv2
    image[120:125] = bytes([9, 9, 8, 1, 4])
    root = 4 * 256
    image[root:root+6] = b'IN' + P('>H', 0x41ED) + bytes([2, 1])
    directory = bytes([2, 0]) + P('>I', 4) + b'\x09\0\0hello.bin' + P('>I', 6) + b'\x05\0\0empty' + P('>I', 8)
    image[root+56:root+64] = P('>Q', len(directory))
    image[root+100:root+100+len(directory)] = directory
    body = b'GRUB hosted reader\n'
    inode = 6 * 256
    image[inode:inode+6] = b'IN' + P('>H', 0x81A4) + bytes([2, 2])
    image[inode+56:inode+64] = P('>Q', len(body))
    image[inode+76:inode+80] = P('>I', 1)
    image[inode+100:inode+116] = P('>IIII', 0, 0, 0, (8 << 21) | 1)
    image[4096:4096+len(body)] = body
    empty=8*256
    image[empty:empty+6] = b'IN' + P('>H', 0x41ED) + bytes([2,1])
    image[empty+56:empty+64] = P('>Q', 6)
    image[empty+100:empty+106] = bytes([0,0])+P('>I',4)
    return bytes(image), body

def reiserfs():
    # ReiserFS3.6: one leaf with a directory item, v1 stat item and packed
    # direct file item. Keys use explicit little-endian v1 field encodings.
    image = bytearray(131072)
    image[65536:65540] = P('<I', 32)
    image[65536+8:65536+12] = P('<I', 1)
    image[65536+44:65536+46] = P('<H', 4096)
    image[65536+52:65536+62] = b'ReIsEr2Fs\0'
    body = b'GRUB hosted reader\n'
    directory = P('<IIIHH', 1, 2, 3, 16, 4) + b'hello.bin'
    stat = P('<HHHHIIIIII', 0x81A4, 1, 0, 0, len(body), 0, 0, 0, 0, 1)
    image[4096:4100] = P('<HH', 1, 3)
    for index, (key, entries, offset, payload) in enumerate([
            ((1, 2, 1, 500), 1, 1000, directory),
            ((2, 3, 0, 0), 0, 1040, stat),
            ((2, 3, 1, 0xFFFFFFFF), 0, 1100, body)]):
        at = 4096 + 24 + index * 24
        image[at:at+24] = P('<IIIIHHHH', *key, entries, len(payload), offset, 0)
        image[4096+offset:4096+offset+len(payload)] = payload
    return bytes(image), body


def bee_fs(atheos=False):
    # AtheOS AFS and BeOS/Haiku BFS have different packed inode/B-tree
    # headers. This independent single-leaf directory uses one direct run
    # for each file, including their distinct range units and alignments.
    image=bytearray(8192)
    body=b'GRUB hosted reader\n'
    sb=1024 if atheos else 512
    image[sb:sb+13]=b'fixture-volume'
    for off,value in ((32,0x41465331 if atheos else 0x42465331),(40,512),(44,9),
                      (68,0xdd121031),(76,9 if atheos else 4),(112,0x15b6830e)):
        image[sb+off:sb+off+4]=P('<I',value)
    image[sb+116:sb+124]=P('<IHH',0,4,1)
    direct=76 if atheos else 72
    for block,mode,where,size in ((4,0x41ed,6,512),(5,0x81a4,8,len(body))):
        at=block*512
        image[at:at+4]=P('<I',0x3bbe0ad9)
        image[at+20:at+24]=P('<I',mode)
        image[at+direct:at+direct+8]=P('<IHH',0,where,1)
        image[at+direct+96:at+direct+104]=P('<Q',1 if atheos else 512)
        image[at+direct+136:at+direct+144]=P('<Q',size)
    tree=6*512
    image[tree:tree+4]=P('<I',0x69f6c2e8)
    if atheos:
        image[tree+4:tree+20]=P('<QII',128,1,512)
        image[tree+128:tree+160]=P('<QQQII',0,(1<<64)-1,(1<<64)-1,1,9)
        key=160;values=172
    else:
        image[tree+4:tree+24]=P('<IIIQ',512,1,0,128)
        image[tree+128:tree+156]=P('<QQQHH',0,(1<<64)-1,(1<<64)-1,1,9)
        key=156;values=168
    image[tree+key:tree+key+9]=b'hello.bin'
    image[tree+values:tree+values+10]=P('<HQ',9,5)
    image[4096:4096+len(body)]=body
    return bytes(image),body


def amiga_sfs():
    # SFS1 root, root-object container, one ordinary file object and one
    # single-leaf extent. Metadata block checksums are independently summed.
    image=bytearray(8192);body=b'GRUB hosted reader\n'
    image[:4]=b'SFS\0';image[12:16]=P('>I',1);image[52:56]=P('>I',512)
    image[104:112]=P('>II',1,3)
    for block,magic in ((1,b'OBJC'),(2,b'OBJC'),(3,b'BNDC')):
        image[block*512:block*512+4]=magic
        image[block*512+8:block*512+12]=P('>I',block)
    image[512+40:512+44]=P('>I',2)
    image[512+48]=128;image[512+49:512+57]=b'fixture\0'
    image[1024+36:1024+44]=P('>II',4,len(body))
    image[1024+49:1024+59]=b'hello.bin\0'
    image[1536+12:1536+16]=P('>HBB',1,1,14)
    image[1536+16:1536+30]=P('>IIIH',4,0,0,1)
    image[2048:2048+len(body)]=body
    for block in range(4):
        at=block*512;total=sum(struct.unpack('>128I',image[at:at+512]))&0xffffffff
        image[at+4:at+8]=P('>I',(-total)&0xffffffff)
    return bytes(image),body

def nilfs2():
    # NILFS2 rev2,1024-byte blocks; direct DAT/checkpoint/ifile maps. The
    # virtual-block translation is independent of the parent's RPC offsets.
    image = bytearray(65536)
    body = b'GRUB hosted reader\n'
    sb = 1024
    image[sb:sb+4] = P('<I', 2)
    image[sb+6:sb+8] = P('<H', 0x3434)
    image[sb+8:sb+10] = P('<H', 1024)
    image[sb+32:sb+40] = P('<Q', len(image))
    image[sb+56:sb+72] = P('<QQ', 1, 2)
    image[2048+40:2048+44] = P('<I', 2)
    # Super-root at last partial-segment block3.
    image[3072+16+80:3072+16+88] = P('<Q', 4) # DAT logical block2 -> block4
    image[3072+144+64:3072+144+72] = P('<Q', 1) # cpfile block0 -> virtual1
    for virtual, physical in [(1, 5), (2, 6), (3, 7), (4, 8)]:
        image[4096+virtual*32:4096+virtual*32+8] = P('<Q', physical)
    cp_ifile = 5120 + 192 + 64
    image[cp_ifile+80:cp_ifile+88] = P('<Q', 2) # ifile logical2 -> virtual2
    directory = P('<QHBB', 3, 24, 9, 1) + b'hello.bin' + bytes(3)
    for ino, mode, data, virtual in [(2, 0x41ED, directory, 3), (3, 0x81A4, body, 4)]:
        at = 6144 + ino*128
        image[at+8:at+16] = P('<Q', len(data))
        image[at+48:at+50] = P('<H', mode)
        image[at+64:at+72] = P('<Q', virtual)
        physical = 7 if ino == 2 else 8
        image[physical*1024:physical*1024+len(data)] = data
    return bytes(image), body

def f2fs():
    # F2FS4KiB blocks, a CRC-protected checkpoint pair, NAT-backed root/file
    # nodes, normal directory block and an inline regular file body.
    image = bytearray(64 * 4096)
    body = b'GRUB hosted reader\n'
    sb = 1024
    image[sb:sb+4] = P('<I', 0xF2F52010)
    image[sb+8:sb+24] = P('<IIII', 9, 3, 12, 4)
    image[sb+36:sb+44] = P('<Q', 64)
    image[sb+76:sb+100] = P('<IIIIII', 2, 0, 6, 0, 8, 3)
    cp = bytearray(4096)
    cp[:8] = P('<Q', 1)
    cp[132:144] = P('<III', 4, 4, 2) # compact summary, four-block pack
    cp[164:168] = P('<I', 4092)
    # Python zlib is an independent CRC oracle with a complemented seed/API.
    cp[4092:] = P('<I', zlib.crc32(cp[:4092], 0xF2F52010 ^ 0xFFFFFFFF) ^ 0xFFFFFFFF)
    image[2*4096:3*4096] = cp
    image[5*4096:6*4096] = cp
    for ino, block in [(3, 8), (4, 9)]:
        at = 6*4096 + ino*9
        image[at:at+9] = P('<BII', 0, ino, block)
    root = 8*4096
    image[root:root+2] = P('<H', 0x41ED)
    image[root+16:root+24] = P('<Q', 4096)
    image[root+360:root+364] = P('<I', 10)
    file = 9*4096
    image[file:file+4] = P('<HBB', 0x81A4, 0, 2)
    image[file+16:file+24] = P('<Q', len(body))
    image[file+364:file+364+len(body)] = body
    directory = 10*4096
    image[directory] = 3 # both slots occupied for the nine-byte name
    image[directory+30:directory+41] = P('<IIHB', 0, 4, 9, 1)
    image[directory+2384:directory+2393] = b'hello.bin'
    return bytes(image), body

def jfs():
    # JFS512-byte inodes,4096-byte blocks. The aggregate's fileset inode
    # maps its IAG, which maps the inode extent. Root dir is inline; file data
    # is a normal xad extent. UTF16 directory text is independent of UTF8 RPC.
    image = bytearray(131072)
    body = b'GRUB hosted reader\n'
    sb = 64*512
    image[sb:sb+4] = b'JFS1'
    image[sb+8:sb+16] = P('<Q', 32)
    image[sb+16:sb+22] = P('<IH', 4096, 12)
    image[sb+36:sb+40] = P('<I', 0x00200000)
    def tree(at, logical, physical):
        image[at+224+16] = 2
        image[at+224+18:at+224+20] = P('<H', 3)
        image[at+256:at+272] = P('<BHBIHBBI', 0, 0, 0, logical, 1, 0, 0, physical)
    tree(104*512, 1, 16)
    image[16*4096+3072:16*4096+3080] = P('<HBBI', 4, 0, 0, 17)
    root = 17*4096 + 2*512
    image[root+8:root+12] = P('<I', 2)
    image[root+52:root+56] = P('<I', 0x41ED)
    image[root+240:root+242] = bytes([2, 1])
    image[root+248] = 1
    image[root+256:root+262] = P('<IBB', 3, 255, 9)
    image[root+262:root+280] = 'hello.bin'.encode('utf-16le')
    file = 17*4096 + 3*512
    image[file+8:file+12] = P('<I', 3)
    image[file+24:file+32] = P('<Q', len(body))
    image[file+52:file+56] = P('<I', 0x81A4)
    tree(file, 0, 20)
    image[20*4096:20*4096+len(body)] = body
    return bytes(image), body

def invoke(helper, image, fs='xfs', path=None, memory=256*1024*1024, maximum=(1<<64)-1):
    proc = subprocess.Popen([str(helper)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    timer = threading.Timer(10, proc.kill)
    timer.start()
    rows, body, reads, status = [], bytearray(), [], None
    def read(n):
        p = proc.stdout.read(n)
        if len(p) != n:
            raise AssertionError(('short protocol', n, p, proc.poll()))
        return p
    try:
        name = fs.encode()
        filename = path.encode() if path else b''
        proc.stdin.write(b'GFS1' + P('<IQQQII', 2 if path else 1, len(image), memory,
                                    maximum, len(name), len(filename)) + name + filename)
        proc.stdin.flush()
        while True:
            kind, = struct.unpack('<I', read(4))
            if kind == 1:
                offset, n = struct.unpack('<QI', read(12))
                assert 0 < n <= 65536 and offset+n <= len(image)
                reads.append((offset, n))
                proc.stdin.write(P('<I', n) + image[offset:offset+n]); proc.stdin.flush()
            elif kind == 2:
                flags, size, mtime, n = struct.unpack('<IQQI', read(24))
                assert n <= 4096
                rows.append({'path': read(n).decode(), 'size': size, 'flags': flags})
            elif kind == 3:
                n, = struct.unpack('<I', read(4)); assert 0 < n <= 65536
                body += read(n)
            elif kind == 4:
                status, count = struct.unpack('<IQ', read(12)); break
            else:
                raise AssertionError(('unknown frame', kind))
        proc.stdin.close()
        exit_code = proc.wait(5)
        return status, count, rows, bytes(body), reads, exit_code
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill(); proc.wait()
        proc.stdout.close(); proc.stderr.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--backend-probe', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    image, body = xfs()
    results = []
    status, count, entries, data, reads, code = invoke(args.helper, image)
    assert status == 0 and code == 0 and count == 2 and not data
    assert entries == [{'path': '/hello.bin', 'size': len(body), 'flags': 2}, {'path': '/empty', 'size': 0, 'flags': 3}], entries
    results.append({'case': 'xfs-shortform-list-and-empty-directory', 'reads': len(reads)})
    status, count, entries, data, reads, code = invoke(args.helper, image, path='/hello.bin')
    assert status == 0 and code == 0 and count == len(body) and data == body and not entries
    results.append({'case': 'xfs-extent-read', 'reads': len(reads),
                    'plaintext_sha256': hashlib.sha256(data).hexdigest()})
    reiser_image, reiser_body = reiserfs()
    status, count, entries, data, reads, code = invoke(args.helper, reiser_image, 'reiserfs')
    assert status == 0 and code == 0 and count == 1 and entries[0]['path'] == '/hello.bin', (status, code, entries)
    results.append({'case': 'reiserfs-packed-leaf-list', 'reads': len(reads)})
    status, count, entries, data, reads, code = invoke(args.helper, reiser_image, 'reiserfs', '/hello.bin')
    assert status == 0 and code == 0 and count == len(reiser_body) and data == reiser_body, (status, code, data)
    results.append({'case': 'reiserfs-direct-file-read', 'reads': len(reads),
                    'plaintext_sha256': hashlib.sha256(data).hexdigest()})
    nilfs_image, nilfs_body = nilfs2()
    status, count, entries, data, reads, code = invoke(args.helper, nilfs_image, 'nilfs2')
    assert status == 0 and code == 0 and count == 1 and entries[0]['path'] == '/hello.bin', (status, code, entries)
    results.append({'case': 'nilfs2-dat-checkpoint-ifile-list', 'reads': len(reads)})
    status, count, entries, data, reads, code = invoke(args.helper, nilfs_image, 'nilfs2', '/hello.bin')
    assert status == 0 and code == 0 and count == len(nilfs_body) and data == nilfs_body, (status, code, data)
    results.append({'case': 'nilfs2-translated-file-read', 'reads': len(reads),
                    'plaintext_sha256': hashlib.sha256(data).hexdigest()})
    f2fs_image, f2fs_body = f2fs()
    status, count, entries, data, reads, code = invoke(args.helper, f2fs_image, 'f2fs')
    assert status == 0 and code == 0 and count == 1 and entries[0]['path'] == '/hello.bin', (status, code, entries)
    results.append({'case': 'f2fs-checkpoint-nat-dir-list', 'reads': len(reads)})
    status, count, entries, data, reads, code = invoke(args.helper, f2fs_image, 'f2fs', '/hello.bin')
    assert status == 0 and code == 0 and count == len(f2fs_body) and data == f2fs_body, (status, code, data)
    results.append({'case': 'f2fs-inline-file-read', 'reads': len(reads),
                    'plaintext_sha256': hashlib.sha256(data).hexdigest()})
    jfs_image, jfs_body = jfs()
    status, count, entries, data, reads, code = invoke(args.helper, jfs_image, 'jfs')
    assert status == 0 and code == 0 and count == 1 and entries[0]['path'] == '/hello.bin', (status, code, entries)
    results.append({'case': 'jfs-fileset-iag-inline-dir-list', 'reads': len(reads)})
    status, count, entries, data, reads, code = invoke(args.helper, jfs_image, 'jfs', '/hello.bin')
    assert status == 0 and code == 0 and count == len(jfs_body) and data == jfs_body, (status, code, data)
    results.append({'case': 'jfs-extent-file-read', 'reads': len(reads),
                    'plaintext_sha256': hashlib.sha256(data).hexdigest()})
    optional=[('afs',*bee_fs(True)),('bfs',*bee_fs(False)),('sfs',*amiga_sfs())]
    for fs,optional_image,optional_body in optional:
        status,count,entries,data,reads,code=invoke(args.helper,optional_image,fs)
        assert status==0 and code==0 and count==1 and entries==[{'path':'/hello.bin','size':len(optional_body),'flags':2}],(fs,status,code,entries)
        results.append({'case':fs+'-directory-list','reads':len(reads)})
        status,count,entries,data,reads,code=invoke(args.helper,optional_image,fs,'/hello.bin')
        assert status==0 and code==0 and count==len(optional_body) and data==optional_body,(fs,status,code,data)
        results.append({'case':fs+'-file-read','reads':len(reads),'plaintext_sha256':hashlib.sha256(data).hexdigest()})
        status,count,entries,data,reads,code=invoke(args.helper,optional_image[:2048 if fs=='sfs' else 4096],fs,'/hello.bin')
        assert status!=0 and code!=0 and not data,fs
        results.append({'case':fs+'-truncated-file-extent','rejected':True})
    for label, bad, fs, path, maximum in [
            ('bad-magic', b'NOPE' + image[4:], 'xfs', None, (1<<64)-1),
            ('source-range', image[:2048], 'xfs', '/hello.bin', (1<<64)-1),
            ('member-ceiling', image, 'xfs', '/hello.bin', len(body)-1),
            ('missing-file', image, 'xfs', '/missing', (1<<64)-1),
            ('unknown-fs', image, 'gfs2', None, (1<<64)-1)]:
        status, count, entries, data, reads, code = invoke(args.helper, bad, fs, path,
                                                         maximum=maximum)
        assert status != 0 and code != 0 and not data, label
        results.append({'case': label, 'rejected': True})
    for fs in ['f2fs', 'jfs', 'nilfs2', 'reiserfs', 'afs', 'bfs', 'sfs']:
        status, count, entries, data, reads, code = invoke(args.helper, bytes(131072), fs)
        assert status != 0 and code != 0 and not data and not entries, fs
        results.append({'case': fs + '-impostor', 'rejected': True})
    with tempfile.TemporaryDirectory(prefix='xfu-grub-backend-') as temporary:
        root = args.root or Path(temporary)
        root.mkdir(parents=True, exist_ok=True)
        source, expected = root/'xfs.img', root/'expected.bin'
        source.write_bytes(image); expected.write_bytes(body)
        for fs, data in [('reiserfs', reiser_image), ('nilfs2', nilfs_image),
                         ('f2fs', f2fs_image), ('jfs', jfs_image)]:
            (root/(fs+'.img')).write_bytes(data)
        for fs,data,_ in optional:
            (root/(fs+'.img')).write_bytes(data)
        if args.backend_probe:
            p = subprocess.run([str(args.backend_probe), str(source), 'xfs', str(args.helper),
                                '/hello.bin', str(expected)], capture_output=True, timeout=20)
            assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
            results.append({'case': 'native-backend-memory-scope', 'passed': True})
            source = root/'reiserfs.img'; source.write_bytes(reiser_image)
            p = subprocess.run([str(args.backend_probe), str(source), 'reiserfs', str(args.helper),
                                '/hello.bin', str(expected)], capture_output=True, timeout=20)
            assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
            results.append({'case': 'native-reiserfs-backend-memory-scope', 'passed': True})
            source = root/'nilfs2.img'; source.write_bytes(nilfs_image)
            p = subprocess.run([str(args.backend_probe), str(source), 'nilfs2', str(args.helper),
                                '/hello.bin', str(expected)], capture_output=True, timeout=20)
            assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
            results.append({'case': 'native-nilfs2-backend-memory-scope', 'passed': True})
            source = root/'f2fs.img'; source.write_bytes(f2fs_image)
            p = subprocess.run([str(args.backend_probe), str(source), 'f2fs', str(args.helper),
                                '/hello.bin', str(expected)], capture_output=True, timeout=20)
            assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
            results.append({'case': 'native-f2fs-backend-memory-scope', 'passed': True})
            source = root/'jfs.img'; source.write_bytes(jfs_image)
            p = subprocess.run([str(args.backend_probe), str(source), 'jfs', str(args.helper),
                                '/hello.bin', str(expected)], capture_output=True, timeout=20)
            assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
            results.append({'case': 'native-jfs-backend-memory-scope', 'passed': True})
            for fs,_,_ in optional:
                p=subprocess.run([str(args.backend_probe),str(root/(fs+'.img')),fs,str(args.helper),'/hello.bin',str(expected)],capture_output=True,timeout=20)
                assert p.returncode==0,(fs,p.returncode,p.stdout,p.stderr)
                results.append({'case':'native-'+fs+'-backend-memory-scope','passed':True})
        if args.root:
            (root/'report.json').write_text(json.dumps(results,indent=2)+'\n')
    print(f'{len(results)} GRUB helper/backend controls passed')

if __name__ == '__main__':
    main()
