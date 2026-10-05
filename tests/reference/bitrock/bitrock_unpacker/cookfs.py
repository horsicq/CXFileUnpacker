from __future__ import annotations

import bz2
import lzma
import re
import struct
import zlib
from dataclasses import dataclass

from bitrock_unpacker.tcllist import tokenize_tcl_list

LAYOUT_UNAVAILABLE_MESSAGE = "cookfs layout unavailable"
OLD_SUFFIX_SIZE = 16
OLD_SUFFIX_MAGIC = b"CFS0002"
BZ2_HEADER_SIZE = 4
COMPRESS_ZLIB = 1
COMPRESS_BZ2 = 2
COMPRESS_LZMA = 255
ZLIB_HEADER = 0x78
ZLIB_WINDOW = 4096


@dataclass(frozen=True)
class CookFSInfo:
    dist_endoffset: int | None
    page_cache_size: int | None
    decompress_command: str | None
    suffix_offset: int | None
    index_size: int | None
    num_pages: int | None
    compression_id: int | None
    page_sizes_offset: int | None
    md5_table_offset: int | None
    index_blob_offset: int | None
    page_data_offset: int | None


@dataclass(frozen=True)
class FsEntry:
    path: str
    kind: str
    mtime: int
    blocks: list[tuple[int, int, int]]


class PageReader:
    def __init__(self, data: bytes, info: CookFSInfo) -> None:
        if (
            info.num_pages is None
            or info.page_sizes_offset is None
            or info.page_data_offset is None
        ):
            raise ValueError(LAYOUT_UNAVAILABLE_MESSAGE)
        self.data = data
        self.sizes = [
            struct.unpack_from(">I", data, info.page_sizes_offset + i * 4)[0]
            for i in range(info.num_pages)
        ]
        self.offsets: list[int] = []
        off = info.page_data_offset
        for size in self.sizes:
            self.offsets.append(off)
            off += size
        self.cache: dict[int, bytes] = {}

    def get(self, index: int) -> bytes:
        if index not in self.cache:
            off = self.offsets[index]
            self.cache[index] = decompress_page(
                self.data[off : off + self.sizes[index]]
            )
        return self.cache[index]

    def raw_page(self, index: int) -> bytes:
        off = self.offsets[index]
        return self.data[off : off + self.sizes[index]]

    def tag(self, index: int) -> int | None:
        raw = self.raw_page(index)
        return raw[0] if raw else None


def parse_old_suffix(data: bytes, endoffset: int) -> tuple[int, int, int] | None:
    if endoffset < OLD_SUFFIX_SIZE or endoffset > len(data):
        return None
    raw = data[endoffset - OLD_SUFFIX_SIZE : endoffset]
    index_size, num_pages = struct.unpack(">II", raw[:8])
    compression_id = raw[8]
    if raw[9:] != OLD_SUFFIX_MAGIC:
        return None
    return index_size, num_pages, compression_id


def parse_cookfsinfo(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    toks = list(tokenize_tcl_list(text))
    for i in range(0, len(toks) - 1, 2):
        out[toks[i]] = toks[i + 1]
    return out


def find_cookfsinfo(data: bytes, overlay_start: int) -> CookFSInfo:
    hay = data[overlay_start:]
    m = re.search(
        rb"dist-endoffset\s+(\d+).*?-pagecachesize\s+(\d+).*?-decompresscommand\s+(\S+)",
        hay,
        re.DOTALL,
    )
    if m:
        return CookFSInfo(
            int(m.group(1)),
            int(m.group(2)),
            m.group(3).decode("ascii", "replace"),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    dist = page_cache = None
    cmd = None
    for key in (b"cookfsinfo.txt", b"dist-endoffset"):
        pos = hay.find(key)
        if pos < 0:
            continue
        dec = find_zlib_stream(data, overlay_start + pos, window=65536)
        if dec:
            try:
                opts = parse_cookfsinfo(dec.decode("utf-8", "replace"))
                if "dist-endoffset" in opts:
                    dist = int(opts["dist-endoffset"])
                if "-pagecachesize" in opts:
                    page_cache = int(opts["-pagecachesize"])
                cmd = opts.get("-decompresscommand") or cmd
                break
            except ValueError:
                pass
    return CookFSInfo(
        dist, page_cache, cmd, None, None, None, None, None, None, None, None
    )


def build_cookfs_layout(
    data: bytes, overlay_start: int, info: CookFSInfo
) -> CookFSInfo:
    endoffset = info.dist_endoffset
    if endoffset is None:
        m = re.search(
            rb"dist-endoffset\s+(\d+)", data[overlay_start : overlay_start + 131072]
        )
        if m:
            endoffset = int(m.group(1))
    if endoffset is None:
        return info
    suf = parse_old_suffix(data, endoffset)
    if not suf:
        return info
    index_size, num_pages, compression_id = suf
    md5_table_offset = endoffset - 16 - index_size - (num_pages * 4) - (num_pages * 16)
    page_sizes_offset = md5_table_offset + (num_pages * 16)
    index_blob_offset = endoffset - 16 - index_size
    page_sizes = (
        [
            struct.unpack_from(">I", data, page_sizes_offset + i * 4)[0]
            for i in range(num_pages)
        ]
        if page_sizes_offset >= 0
        else []
    )
    page_data_offset = md5_table_offset - sum(page_sizes) if page_sizes else None
    return CookFSInfo(
        endoffset,
        info.page_cache_size,
        info.decompress_command,
        endoffset - 16,
        index_size,
        num_pages,
        compression_id,
        page_sizes_offset,
        md5_table_offset,
        index_blob_offset,
        page_data_offset,
    )


def decompress_index_blob(data: bytes, info: CookFSInfo) -> bytes | None:
    if info.index_blob_offset is None or info.index_size is None:
        return None
    blob = data[info.index_blob_offset : info.index_blob_offset + info.index_size + 1]
    if not blob:
        return None
    comp_id, payload = blob[0], blob[1:]
    if comp_id == 0:
        return payload
    if comp_id == 1:
        return zlib.decompress(payload, wbits=-15)
    return None


def parse_fsindex(decoded: bytes) -> list[FsEntry]:
    if not decoded.startswith(b"CFS2.200"):
        return []
    pos = 8

    def read_u32() -> int:
        nonlocal pos
        v = struct.unpack_from(">I", decoded, pos)[0]
        pos += 4
        return v

    def read_i32() -> int:
        nonlocal pos
        v = struct.unpack_from(">i", decoded, pos)[0]
        pos += 4
        return v

    def read_u64() -> int:
        nonlocal pos
        v = struct.unpack_from(">Q", decoded, pos)[0]
        pos += 8
        return v

    entries: list[FsEntry] = []

    def read_dir(prefix: str) -> None:
        nonlocal pos
        if pos + 4 > len(decoded):
            return
        child_count = read_u32()
        for _ in range(child_count):
            name_len = decoded[pos]
            pos += 1
            name = decoded[pos : pos + name_len].decode("utf-8", "replace")
            pos += name_len + 1
            mtime = read_u64()
            block_count = read_i32()
            full = f"{prefix}/{name}" if prefix else name
            if block_count == -1:
                entries.append(FsEntry(full, "directory", mtime, []))
                read_dir(full)
            else:
                blocks = [
                    (read_u32(), read_u32(), read_u32()) for _ in range(block_count)
                ]
                entries.append(FsEntry(full, "file", mtime, blocks))

    read_dir("")

    return entries


def decompress_page(raw: bytes) -> bytes:
    if not raw:
        return b""

    tag, payload = raw[0], raw[1:]

    if tag == 0:
        return payload
    if tag == COMPRESS_ZLIB:
        return zlib.decompress(payload, wbits=-15)
    if tag == COMPRESS_BZ2:
        return (
            bz2.decompress(payload[BZ2_HEADER_SIZE:])
            if len(payload) >= BZ2_HEADER_SIZE
            else b""
        )
    if tag == COMPRESS_LZMA:
        return lzma.decompress(payload, format=lzma.FORMAT_ALONE)

    return b""


def find_zlib_stream(data: bytes, near: int, window: int = 4096) -> bytes | None:
    start = max(0, near - window)
    end = min(len(data), near + window)
    chunk = data[start:end]

    for i in range(len(chunk) - 2):
        if chunk[i] != ZLIB_HEADER:
            continue

        if ((chunk[i] << 8) + chunk[i + 1]) % 31 != 0:
            continue

        try:
            obj = zlib.decompressobj()
            dec = obj.decompress(data[start + i :])
            if obj.eof and (
                b" {file " in dec or b" {directory " in dec or b" {link " in dec
            ):
                return dec
        except zlib.error:
            continue

    return None
