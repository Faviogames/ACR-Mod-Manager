"""Lossless Zlib compression for unsigned, single-partition UE IoStore output.

Only container storage changes. Package bytes, chunk IDs/hashes, virtual offsets,
directory index and container ID are preserved. No asset parsing is involved.
Format reference: trumank/retoc, retoc/src/lib.rs (MIT).
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import struct
import time
import zlib


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Toc:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        data = self.data
        if len(data) < 144 or data[:16] != b'-==--==--==--==-':
            raise ValueError('Invalid IoStore header')
        self.version = data[16]
        (header, self.count, self.block_count, entry_size, method_count,
         method_length, self.block_size, directory_size, partitions) = struct.unpack_from('<9I', data, 20)
        if header != 144 or entry_size != 12 or self.version != 8:
            raise ValueError('Unsupported IoStore layout (expected UE5.6 TOC version 8)')
        if partitions != 1 or data[80] & 6:
            raise ValueError('Signed, encrypted or multi-partition containers are unsupported')
        seeds = struct.unpack_from('<I', data, 84)[0]
        overflow = struct.unpack_from('<I', data, 96)[0]
        self.block_start = header + self.count * 22 + (seeds + overflow) * 4
        self.methods_start = self.block_start + self.block_count * 12
        self.methods_end = self.methods_start + method_count * method_length
        self.meta_start = self.methods_end + directory_size
        if len(data) != self.meta_start + self.count * 24:
            raise ValueError('Unexpected TOC trailing data')
        self.methods = [data[self.methods_start + i * method_length:
                             self.methods_start + (i + 1) * method_length].split(b'\0', 1)[0]
                        for i in range(method_count)]
        if any(method != b'Zlib' for method in self.methods):
            raise ValueError('Only uncompressed or Zlib input is supported')
        self.blocks = []
        for index in range(self.block_count):
            entry = data[self.block_start + index * 12:self.block_start + (index + 1) * 12]
            offset = int.from_bytes(entry[:5], 'little')
            size = int.from_bytes(entry[5:8], 'little')
            raw_size = int.from_bytes(entry[8:11], 'little')
            method = entry[11]
            if raw_size > self.block_size or method > len(self.methods) or (not method and size != raw_size):
                raise ValueError('Invalid compression block')
            self.blocks.append((offset, size, raw_size, method))
        self.chunks = []
        self.memory_blocks = set()
        self.bootstrap_blocks = set()
        offsets_start = header + self.count * 12
        for index in range(self.count):
            entry = data[offsets_start + index * 10:offsets_start + (index + 1) * 10]
            offset = int.from_bytes(entry[:5], 'big')
            length = int.from_bytes(entry[5:], 'big')
            first = offset // self.block_size
            end = (offset + length + self.block_size - 1) // self.block_size
            if first >= end or end > self.block_count:
                raise ValueError('Invalid chunk range')
            self.chunks.append((first, end))
            # The package-store bootstrap reads these before normal chunk IO.
            # Match shipping containers: never compress their initial metadata.
            chunk_type = data[header + index * 12 + 11]
            if chunk_type in (5, 6):  # ScriptObjects, ContainerHeader
                self.bootstrap_blocks.update(range(first, end))
            if data[self.meta_start + index * 24 + 20] & 2:
                self.memory_blocks.update(range(first, end))

    def block(self, stream, index):
        offset, size, raw_size, method = self.blocks[index]
        stream.seek(offset)
        data = stream.read(size)
        if len(data) != size:
            raise ValueError('Truncated UCAS')
        raw = zlib.decompress(data) if method else data
        if len(raw) != raw_size:
            raise ValueError('Incorrect decompressed block length')
        return raw


def compare(source, destination):
    """Read files from disk again and compare every decompressed block."""
    old, new = Toc(source), Toc(destination)
    if old.data[:old.block_start] != new.data[:new.block_start]:
        # Header compression fields are allowed to change; all others are exact.
        before, after = bytearray(old.data[:old.block_start]), bytearray(new.data[:new.block_start])
        for a, b in ((36, 44), (80, 81)):
            before[a:b] = after[a:b]
        if before != after:
            raise ValueError('Changed chunk identity, virtual offset or container header')
    if old.data[old.methods_end:old.meta_start] != new.data[new.methods_end:new.meta_start]:
        raise ValueError('Changed directory index')
    for index in range(old.count):
        a = old.data[old.meta_start + index * 24:old.meta_start + (index + 1) * 24]
        b = new.data[new.meta_start + index * 24:new.meta_start + (index + 1) * 24]
        if a[:20] != b[:20] or a[21:] != b[21:] or (a[20] & ~1) != (b[20] & ~1):
            raise ValueError('Changed chunk hash or memory mapping flags')
    digest = hashlib.sha256()
    with Path(source).with_suffix('.ucas').open('rb') as a, Path(destination).with_suffix('.ucas').open('rb') as b:
        for index in range(old.block_count):
            raw = old.block(a, index)
            if raw != new.block(b, index):
                raise ValueError(f'Changed chunk payload in block {index}')
            digest.update(raw)
    return digest.hexdigest()


def compress(source, destination, *, workers=8, level=6, log=print):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Use a separate destination; never overwrite a mounted container')
    if any(destination.with_suffix(ext).exists() for ext in ('.utoc', '.ucas', '.pak')):
        raise FileExistsError(destination)
    toc = Toc(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    entries, compressed = bytearray(), []
    uncompressed_blocks = toc.memory_blocks | toc.bootstrap_blocks

    def encode(item):
        index, raw = item
        data = zlib.compress(raw, level) if index not in uncompressed_blocks else raw
        method = 1 if len(data) < len(raw) else 0
        return (data if method else raw), len(raw), method

    try:
        with source.with_suffix('.ucas').open('rb') as reader, destination.with_suffix('.ucas').open('xb') as writer, ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for start in range(0, toc.block_count, 128):
                batch = [(index, toc.block(reader, index)) for index in range(start, min(start + 128, toc.block_count))]
                for index, (data, raw_size, method) in enumerate(pool.map(encode, batch), start):
                    # Memory-mapped chunks must stay uncompressed and page-aligned.
                    alignment = 65536 if index in toc.memory_blocks else 16
                    writer.write(b'\0' * ((-writer.tell()) % alignment))
                    offset = writer.tell()
                    writer.write(data)
                    entries.extend(offset.to_bytes(5, 'little') + len(data).to_bytes(3, 'little') + raw_size.to_bytes(3, 'little') + bytes([method]))
                    compressed.append(bool(method))
            writer.flush()
            os.fsync(writer.fileno())
        header = bytearray(toc.data[:toc.block_start])
        struct.pack_into('<II', header, 36, 1, 32)
        header[80] |= 1
        tail = bytearray(toc.data[toc.methods_end:])
        for index, (start, end) in enumerate(toc.chunks):
            flag = toc.meta_start - toc.methods_end + index * 24 + 20
            tail[flag] = (tail[flag] & ~1) | int(any(compressed[start:end]))
        destination.write_bytes(header + entries + b'Zlib'.ljust(32, b'\0') + tail)
        shutil.copyfile(source.with_suffix('.pak'), destination.with_suffix('.pak'))
        content_hash = compare(source, destination)
        report = dict(source=str(source), destination=str(destination), blocks=toc.block_count,
                      chunks=toc.count, memory_mapped_blocks=len(toc.memory_blocks),
                      uncompressed_bootstrap_blocks=len(toc.bootstrap_blocks),
                      source_bytes=source.with_suffix('.ucas').stat().st_size,
                      output_bytes=destination.with_suffix('.ucas').stat().st_size,
                      payload_sha256=content_hash, verified_all_blocks=True,
                      seconds=round(time.monotonic() - started, 2),
                      files={destination.with_suffix(ext).name: sha(destination.with_suffix(ext))
                             for ext in ('.pak', '.ucas', '.utoc')})
        log(f"IoStore compression: {report['source_bytes'] / 2**30:.3f} -> {report['output_bytes'] / 2**30:.3f} GiB; all {toc.block_count} blocks identical")
        return report
    except BaseException:
        for ext in ('.utoc', '.ucas', '.pak'):
            destination.with_suffix(ext).unlink(missing_ok=True)
        raise


def repair_bootstrap(source, destination):
    """Fix bootstrap storage in an existing compressed package; keep payloads."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or any(destination.with_suffix(ext).exists() for ext in ('.pak', '.ucas', '.utoc')):
        raise FileExistsError('Use a new unpublished destination')
    toc = Toc(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(toc.data)
    shutil.copyfile(source.with_suffix('.ucas'), destination.with_suffix('.ucas'))
    with source.with_suffix('.ucas').open('rb') as reader, destination.with_suffix('.ucas').open('ab') as writer:
        for index in sorted(toc.bootstrap_blocks):
            raw = toc.block(reader, index)
            writer.write(b'\0' * ((-writer.tell()) % 16))
            entry = writer.tell().to_bytes(5, 'little') + len(raw).to_bytes(3, 'little') * 2 + b'\0'
            data[toc.block_start + index * 12:toc.block_start + (index + 1) * 12] = entry
            writer.write(raw)
    for index, (first, end) in enumerate(toc.chunks):
        if all(block in toc.bootstrap_blocks for block in range(first, end)):
            data[toc.meta_start + index * 24 + 20] &= ~1
    destination.write_bytes(data)
    shutil.copyfile(source.with_suffix('.pak'), destination.with_suffix('.pak'))
    digest = compare(source, destination)
    fixed = Toc(destination)
    assert all(fixed.blocks[index][3] == 0 for index in fixed.bootstrap_blocks)
    report = dict(source=str(source), destination=str(destination), chunks=toc.count,
                  bootstrap_blocks=len(toc.bootstrap_blocks), verified_all_blocks=True,
                  payload_sha256=digest, output_bytes=destination.with_suffix('.ucas').stat().st_size,
                  files={destination.with_suffix(ext).name: sha(destination.with_suffix(ext))
                         for ext in ('.pak', '.ucas', '.utoc')})
    destination.with_suffix('.compression.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def needs_repack(path):
    toc = Toc(path)
    return not toc.data[80] & 1 or any(toc.blocks[index][3] for index in toc.bootstrap_blocks)


def compress_build(toc, *, log=print):
    """Compress an unpublished build atomically; caller verifies before deploy."""
    toc = Path(toc)
    temporary = toc.parent / ('compress-' + os.urandom(16).hex())
    try:
        output = temporary / toc.name
        current = Toc(toc)
        if current.methods and any(current.blocks[index][3] for index in current.bootstrap_blocks):
            report = repair_bootstrap(toc, output)
        else:
            report = compress(toc, output, log=log)
        for ext in ('.ucas', '.pak', '.utoc'):
            os.replace(output.with_suffix(ext), toc.with_suffix(ext))
        report['destination'] = str(toc)
        report['source'] = str(toc)
        toc.with_suffix('.compression.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--level', type=int, choices=range(1, 10), default=6)
    args = parser.parse_args()
    report = compress(args.source, args.destination, workers=args.workers, level=args.level)
    args.destination.with_suffix('.compression.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
