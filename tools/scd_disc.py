#!/usr/bin/env python3
"""Lossless ISO9660 extraction and fixed-layout Mode 1 disc rebuilding.

The original raw track is a layout template, including filesystem metadata,
padding and boot code. File extents are replaced from the extracted files.
Every data sector's sync, address, EDC and ECC is regenerated on rebuild.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CUE = ROOT / 'private/discs/segacd-usa/Snatcher.cue'
DEFAULT_EXTRACT = ROOT / 'private/extracted/segacd-usa'


def sha1(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha1').hexdigest()


def tracks(cue):
    text = Path(cue).read_text()
    names = re.findall(r'FILE "([^"]+)" BINARY', text)
    if len(names) != 1:
        raise ValueError('Expected a single BIN cue')
    rows = []
    for number, mode, body in re.findall(r'TRACK (\d+) (\S+)(.*?)(?=\s*TRACK|\Z)', text, re.S):
        indices = {}
        for index, m, s, f in re.findall(r'INDEX (\d+) (\d+):(\d+):(\d+)', body):
            indices[index] = (int(m) * 60 + int(s)) * 75 + int(f)
        rows.append(dict(number=int(number), mode=mode, indices=indices,
                         start=indices.get('00', indices['01'])))
    source = Path(cue).resolve().parent / names[0]
    for i, row in enumerate(rows):
        row['end'] = rows[i+1]['start'] if i+1 < len(rows) else source.stat().st_size // 2352
    if rows[0]['mode'] != 'MODE1/2352' or rows[0]['start'] != 0:
        raise ValueError('Expected track 1 MODE1/2352 at sector 0')
    return source, rows


def track_hashes(cue):
    source, rows = tracks(cue)
    with source.open('rb') as f:
        for row in rows:
            f.seek(row['start'] * 2352)
            data = f.read((row['end'] - row['start']) * 2352)
            row.update(bytes=len(data), sha1=hashlib.sha1(data).hexdigest(),
                       md5=hashlib.md5(data).hexdigest(), crc32=f'{zlib.crc32(data):08x}')
    return rows


# CD-ROM EDC polynomial and GF(256) parity arithmetic.
EDC_TABLE = []
GF_DOUBLE = []
GF_UNMIX = [0] * 256
for value in range(256):
    crc = value
    for _ in range(8):
        crc = (crc >> 1) ^ (0xd8018001 if crc & 1 else 0)
    EDC_TABLE.append(crc)
    doubled = (value << 1) ^ (0x11d if value & 128 else 0)
    GF_DOUBLE.append(doubled)
    GF_UNMIX[value ^ doubled] = value


def parity(data, count, depth, stride_start, stride):
    result = bytearray(count * 2)
    for major in range(count):
        position = (major >> 1) * stride_start + (major & 1)
        a = b = 0
        for _ in range(depth):
            byte = data[position]
            a = GF_DOUBLE[a ^ byte]
            b ^= byte
            position = (position + stride) % (count * depth)
        a = GF_UNMIX[GF_DOUBLE[a] ^ b]
        result[major] = a
        result[major + count] = a ^ b
    return result


def mode1_sector(payload, lba):
    if len(payload) != 2048:
        raise ValueError('Sector payload must be 2048 bytes')
    def bcd(n):
        return (n // 10) * 16 + n % 10
    address = lba + 150
    sector = bytearray(b'\0' + b'\xff' * 10 + b'\0')
    sector.extend((bcd(address // 4500), bcd(address // 75 % 60), bcd(address % 75), 1))
    sector.extend(payload)
    crc = 0
    for byte in sector:
        crc = (crc >> 8) ^ EDC_TABLE[(crc ^ byte) & 255]
    sector.extend(struct.pack('<I', crc))
    sector.extend(b'\0' * 8)
    sector.extend(parity(sector[12:], 86, 24, 2, 86))
    sector.extend(parity(sector[12:], 52, 43, 86, 88))
    return sector


def extract(cue=DEFAULT_CUE, output=DEFAULT_EXTRACT):
    cue, output = Path(cue), Path(output)
    source, rows = tracks(cue)
    output.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as stream:
        raw = stream.read(rows[0]['end'] * 2352)
    if len(raw) != rows[0]['end'] * 2352:
        raise ValueError('Truncated data track')
    iso = b''.join(raw[i+16:i+2064] for i in range(0, len(raw), 2352))
    if iso[16*2048+1:16*2048+6] != b'CD001':
        raise ValueError('Missing ISO9660 PVD')
    (output / '_track01.raw').write_bytes(raw)
    (output / '_boot.bin').write_bytes(iso[:16*2048])
    entries = []
    def walk(record, parent):
        lba = int.from_bytes(record[2:6], 'little')
        size = int.from_bytes(record[10:14], 'little')
        data = iso[lba*2048:lba*2048+size]
        pos = 0
        while pos < len(data):
            length = data[pos]
            if not length:
                pos = (pos // 2048 + 1) * 2048
                continue
            rec = data[pos:pos+length]
            name = rec[33:33+rec[32]]
            pos += length
            if name in (b'\0', b'\1'):
                continue
            name = name.decode('ascii').split(';')[0]
            path = parent / name
            if name in ('.', '..') or '/' in name or '\\' in name:
                raise ValueError('Unsafe ISO name')
            if rec[25] & 2:
                walk(rec, path)
            else:
                file_lba = int.from_bytes(rec[2:6], 'little')
                file_size = int.from_bytes(rec[10:14], 'little')
                payload = iso[file_lba*2048:file_lba*2048+file_size]
                if len(payload) != file_size:
                    raise ValueError(f'Truncated {path}')
                dest = output / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(payload)
                entries.append(dict(name=str(path), lba=file_lba, size=file_size,
                                    sha1=hashlib.sha1(payload).hexdigest()))
    walk(iso[16*2048+156:16*2048+190], Path())
    manifest = dict(version=1, source=str(source.resolve()), cue=str(cue.resolve()),
                    source_sha1=sha1(source), track_sectors=rows[0]['end'],
                    boot_sectors=16, files=entries, tracks=rows)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Extracted {len(entries)} files; {rows[0]["end"]} data sectors')
    return manifest


def patch_file_extent(bin_path, manifest, name, payload, allow_sector_slack=False, allow_zero_gap=False):
    """Patch a QA copy at its original LBA, optionally using its last-sector slack.

    Growth normally stays in the original rounded extent. Approved dog data
    may opt into one further zero-filled, nonoverlapping sector. Both ISO size
    fields are updated. Touched Mode 1 sectors are checked and regenerated.
    This is an overlay primitive, not a release build.
    """
    bin_path=Path(bin_path)
    if bin_path.resolve()==Path(manifest['source']).resolve():
        raise ValueError('Cannot patch the staged source BIN')
    matches=[r for r in manifest['files'] if r['name']==name]
    if len(matches)!=1:
        raise ValueError('Unknown or ambiguous ISO file')
    row=matches[0];original_capacity=((row['size']+2047)//2048)*2048
    capacity=original_capacity
    if allow_zero_gap:
        if name!='DATA_G0.BIN':
            raise ValueError('Only approved dog data may use an additional gap sector')
        capacity+=2048
    if len(payload)!=row['size'] and not ((allow_sector_slack or allow_zero_gap) and row['size']<len(payload)<=capacity):
        raise ValueError('Overlay must retain its allocated sector count')
    for other in manifest['files']:
        if other is row or not other['size']:
            continue
        if max(row['lba'],other['lba'])<min(row['lba']+capacity//2048,other['lba']+(other['size']+2047)//2048):
            raise ValueError('Source ISO extents overlap')
    sectors={};directory_locations=[]
    with bin_path.open('r+b') as stream:
        def get(lba):
            if lba not in sectors:
                stream.seek(lba*2352);raw=stream.read(2352)
                if len(raw)!=2352 or mode1_sector(raw[16:2064],lba)!=raw:
                    raise ValueError('Invalid source Mode 1 sector')
                sectors[lba]=bytearray(raw[16:2064])
            return sectors[lba]
        def read(lba,size):
            return b''.join(bytes(get(lba+i)) for i in range((size+2047)//2048))[:size]
        pvd=get(16)
        if pvd[1:6]!=b'CD001':
            raise ValueError('Missing ISO9660 primary descriptor')
        def walk(record,parent=''):
            lba=int.from_bytes(record[2:6],'little');size=int.from_bytes(record[10:14],'little')
            data=read(lba,size);pos=0
            while pos<len(data):
                length=data[pos]
                if not length:
                    pos=(pos//2048+1)*2048;continue
                rec=data[pos:pos+length]
                if len(rec)!=length or length<34 or pos%2048+length>2048:
                    raise ValueError('Invalid ISO directory record')
                ident=rec[33:33+rec[32]]
                if ident not in (b'\0',b'\1'):
                    component=ident.decode('ascii').split(';')[0]
                    path=parent+'/'+component if parent else component
                    if rec[25]&2:
                        walk(rec,path)
                    elif path==name:
                        if int.from_bytes(rec[2:6],'little')!=row['lba'] or int.from_bytes(rec[6:10],'big')!=row['lba']:
                            raise ValueError('ISO file LBA no longer matches source')
                        le=int.from_bytes(rec[10:14],'little');be=int.from_bytes(rec[14:18],'big')
                        if le!=be or le not in (row['size'],len(payload)):
                            raise ValueError('ISO file size no longer matches source or overlay')
                        directory_locations.append((lba+pos//2048,pos%2048))
                pos+=length
        walk(bytes(pvd[156:190]))
        if len(directory_locations)!=1:
            raise ValueError('Expected one guarded ISO file record')
        # Validate append space before making any on-disc write.
        if len(payload)>row['size']:
            old=read(row['lba'],capacity)
            if any(old[row['size']:len(payload)]):
                raise ValueError('Allocated tail slack is not zero-filled')
        for i in range((len(payload)+2047)//2048):
            chunk=payload[i*2048:(i+1)*2048];get(row['lba']+i)[:len(chunk)]=chunk
        for lba,offset in directory_locations:
            sector=get(lba);sector[offset+10:offset+14]=len(payload).to_bytes(4,'little');sector[offset+14:offset+18]=len(payload).to_bytes(4,'big')
        changed=0
        for lba,data in sorted(sectors.items()):
            stream.seek(lba*2352);before=stream.read(2352);after=mode1_sector(data,lba)
            if before!=after:
                stream.seek(lba*2352);stream.write(after);changed+=1
    return dict(file=name,lba=row['lba'],source_size=row['size'],size=len(payload),source_sector_capacity=original_capacity,sector_capacity=capacity,uses_zero_gap=len(payload)>original_capacity,changed_sectors=changed,directory_records=len(directory_locations))


def rebuild(extracted=DEFAULT_EXTRACT, output=ROOT/'build/roundtrip/Snatcher.cue'):
    extracted, output = Path(extracted), Path(output)
    manifest = json.loads((extracted/'manifest.json').read_text())
    source = Path(manifest['source'])
    if sha1(source) != manifest['source_sha1']:
        raise ValueError('Source BIN changed')
    raw = (extracted/'_track01.raw').read_bytes()
    sectors = manifest['track_sectors']
    if len(raw) != sectors*2352:
        raise ValueError('Template size changed')
    iso = bytearray(b''.join(raw[i+16:i+2064] for i in range(0,len(raw),2352)))
    boot = (extracted/'_boot.bin').read_bytes()
    if len(boot) != 16*2048:
        raise ValueError('Boot area size changed')
    iso[:16*2048] = boot
    for row in manifest['files']:
        payload = (extracted/row['name']).read_bytes()
        if len(payload) != row['size']:
            raise ValueError(f'{row["name"]}: fixed-layout rebuild requires {row["size"]} bytes')
        offset = row['lba']*2048
        iso[offset:offset+row['size']] = payload
    output.parent.mkdir(parents=True,exist_ok=True)
    dest = output.with_suffix('.bin')
    if dest.resolve() == source.resolve():
        raise ValueError('Cannot overwrite source')
    differences = 0
    with dest.open('wb') as stream:
        for lba in range(sectors):
            sector = mode1_sector(iso[lba*2048:(lba+1)*2048],lba)
            differences += sector != raw[lba*2352:(lba+1)*2352]
            stream.write(sector)
        with source.open('rb') as src:
            src.seek(sectors*2352)
            while chunk := src.read(1024*1024):
                stream.write(chunk)
    text = Path(manifest['cue']).read_text()
    output.write_text(re.sub(r'FILE "[^"]+" BINARY', f'FILE "{dest.name}" BINARY', text))
    report = dict(bin=str(dest),sha1=sha1(dest),source_sha1=manifest['source_sha1'],
                  identical=sha1(dest)==manifest['source_sha1'],changed_data_sectors=differences)
    print(json.dumps(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    p = sub.add_parser('extract'); p.add_argument('--cue',type=Path,default=DEFAULT_CUE); p.add_argument('--output',type=Path,default=DEFAULT_EXTRACT)
    p = sub.add_parser('rebuild'); p.add_argument('--extracted',type=Path,default=DEFAULT_EXTRACT); p.add_argument('--output',type=Path,default=ROOT/'build/roundtrip/Snatcher.cue')
    p = sub.add_parser('hashes'); p.add_argument('--cue',type=Path,default=DEFAULT_CUE)
    args = parser.parse_args()
    if args.command == 'extract': extract(args.cue,args.output)
    elif args.command == 'rebuild': rebuild(args.extracted,args.output)
    else: print(json.dumps(track_hashes(args.cue),indent=2))

if __name__ == '__main__':
    main()
