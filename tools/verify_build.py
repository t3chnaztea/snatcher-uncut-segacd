#!/usr/bin/env python3
"""Independently audit the fixed-layout M5 BIN/CUE, xdelta and CHD artifacts.

No builder implementation is imported. ISO directory traversal, authorized
payload reconstruction and raw-sector checks are implemented here. Approved
asset authenticity is checked separately by fresh guarded M3/M4 regeneration.
"""
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

SOURCE_SHA1 = '9ff422fcbdb3cbd5a585d1c822f28930713ba4a8'
SYNC = b'\0' + b'\xff' * 10 + b'\0'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha1(data).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha1').hexdigest()


def check_artifact(path, record):
    """Bind builder receipts to actual files; receipts alone do not prove content."""
    require(path.is_file(), f'Missing artifact: {path}')
    if not isinstance(record, dict):
        return
    require(path.stat().st_size == record['bytes'], f'Artifact size mismatch: {path}')
    for algorithm in ('sha1','sha256'):
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, algorithm).hexdigest()
        require(actual == record[algorithm], f'Artifact {algorithm} mismatch: {path}')


def validate_manifest(config):
    require(config.get('version') == 1, 'Build manifest version must be 1')
    for field in ('source_cue','source_manifest','canonical_tree'):
        require(isinstance(config.get(field),str) and bool(config[field]), f'Missing manifest field: {field}')
    required = {'bin','cue','chd','xdelta','track01','source_track01'}
    require(set(config.get('artifacts',{})) == required, 'Manifest must name all six mandatory artifacts')
    require(set(config.get('everdrive',{})) == {'bin','cue'}, 'Manifest must name both EverDrive artifacts')
    for record in list(config['artifacts'].values())+list(config['everdrive'].values()):
        require(isinstance(record,dict) and {'path','bytes','sha1','sha256'} <= set(record),
                'Incomplete artifact record')
        require(isinstance(record['path'],str) and bool(record['path']) and
                type(record['bytes']) is int and record['bytes'] > 0, 'Invalid artifact path/length')
        for field,length in [('sha1',40),('sha256',64)]:
            require(isinstance(record[field],str) and bool(re.fullmatch('[0-9a-f]{'+str(length)+'}',record[field])),
                    f'Invalid artifact {field}')


def cue_layout(path):
    """Read one-file raw cues without losing INDEX00 pregap ownership."""
    text = Path(path).read_text()
    files = re.findall(r'^\s*FILE\s+"([^"]+)"\s+BINARY\s*$', text, re.M)
    require(len(files) == 1, 'Expected exactly one BINARY file in cue')
    binary = Path(path).resolve().parent / files[0]
    require(binary.stat().st_size % 2352 == 0, 'BIN contains a partial raw sector')
    tracks = []
    for number, mode, body in re.findall(r'TRACK\s+(\d+)\s+(\S+)(.*?)(?=\s*TRACK|\Z)', text, re.S):
        indices = {}
        for index, minute, second, frame in re.findall(r'INDEX\s+(\d+)\s+(\d+):(\d+):(\d+)', body):
            require(int(second) < 60 and int(frame) < 75, 'Invalid cue timestamp')
            require(index not in indices, 'Duplicate cue index')
            indices[index] = (int(minute)*60 + int(second))*75 + int(frame)
        require('01' in indices, 'Missing INDEX01')
        require(not re.search(r'\b(?:PREGAP|POSTGAP)\b', body), 'Synthetic cue gaps require explicit policy')
        tracks.append(dict(number=int(number), mode=mode, indices=indices,
                           start=indices.get('00', indices['01'])))
    require(tracks and tracks[0]['mode'] == 'MODE1/2352' and tracks[0]['start'] == 0,
            'Expected raw Mode1 data at sector zero')
    for i, row in enumerate(tracks):
        require(row['number'] == i+1, 'Nonconsecutive track numbers')
        row['end'] = tracks[i+1]['start'] if i+1 < len(tracks) else binary.stat().st_size//2352
        require(row['start'] <= row['indices']['01'] < row['end'], 'Invalid cue track extent')
    return binary, tracks


def dual(record, offset):
    little = int.from_bytes(record[offset:offset+4], 'little')
    big = int.from_bytes(record[offset+4:offset+8], 'big')
    require(little == big, 'ISO dual-endian field mismatch')
    return little


def iso_inventory(iso):
    """Return every file and exact directory field offsets; reject aliases."""
    pvd = iso[16*2048:17*2048]
    require(pvd[:7] == b'\x01CD001\x01', 'Invalid primary volume descriptor')
    require(dual(pvd, 80)*2048 <= len(iso), 'ISO volume exceeds data track')
    require(int.from_bytes(pvd[128:130], 'little') == 2048 and
            int.from_bytes(pvd[130:132], 'big') == 2048, 'Unexpected ISO block size')
    files = {}
    visited = set()

    def walk(record, parent):
        lba, size = dual(record, 2), dual(record, 10)
        require((lba, size) not in visited, 'Directory cycle or alias')
        visited.add((lba, size))
        require(lba*2048+size <= len(iso), 'Directory exceeds data track')
        pos = 0
        while pos < size:
            absolute = lba*2048+pos
            length = iso[absolute]
            if length == 0:
                pos = (pos//2048+1)*2048
                continue
            require(length >= 34 and pos%2048+length <= 2048 and pos+length <= size,
                    'Invalid ISO directory record bounds')
            rec = iso[absolute:absolute+length]
            require(33+rec[32] <= length, 'Truncated ISO identifier')
            child_lba, child_size = dual(rec, 2), dual(rec, 10)
            require(rec[26:28] == b'\0\0' and not rec[25]&128, 'Interleaved/multiextent file unsupported')
            require(rec[28:32] == b'\x01\0\0\x01', 'Invalid ISO volume sequence')
            ident = rec[33:33+rec[32]]
            if ident not in (b'\0', b'\1'):
                name = ident.decode('ascii').split(';')[0]
                require(name not in ('', '.', '..') and '/' not in name and '\\' not in name,
                        'Unsafe ISO identifier')
                name = parent+'/'+name if parent else name
                if rec[25]&2:
                    walk(rec, name)
                else:
                    require(name not in files, 'Duplicate ISO filename')
                    require(child_lba*2048+child_size <= len(iso), 'File exceeds data track')
                    files[name] = dict(name=name, lba=child_lba, size=child_size,
                                       record_offset=absolute, record_length=length)
            pos += length
    walk(pvd[156:156+pvd[156]], '')
    extents = sorted((r['lba']*2048, r['lba']*2048+r['size'], n) for n,r in files.items() if r['size'])
    require(all(a[1] <= b[0] for a,b in zip(extents,extents[1:])), 'Overlapping ISO files')
    return files


def payload_image(raw, sectors):
    require(len(raw) >= sectors*2352, 'Truncated raw data track')
    return bytearray(b''.join(raw[i*2352+16:i*2352+2064] for i in range(sectors)))


# Independent Mode1 EDC and Reed-Solomon P/Q syndrome checks.
CRC = []
FORWARD = []
BACKWARD = [0]*256
for value in range(256):
    crc = value
    for _ in range(8):
        crc = (crc >> 1) ^ (0xd8018001 if crc&1 else 0)
    CRC.append(crc)
    doubled = ((value << 1) ^ (0x11d if value&128 else 0)) & 255
    FORWARD.append(doubled)
    BACKWARD[value ^ doubled] = value


def ecc_check(data, parity, major_count, minor_count, major_mult, minor_inc):
    size = major_count*minor_count
    for major in range(major_count):
        index = (major//2)*major_mult+(major&1)
        a = b = 0
        for _ in range(minor_count):
            value = data[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= value
            b ^= value
            a = FORWARD[a]
        a = BACKWARD[FORWARD[a] ^ b]
        if parity[major] != a or parity[major+major_count] != a^b:
            return False
    return True


def verify_sector(sector, lba):
    require(len(sector) == 2352 and sector[:12] == SYNC, f'Invalid sync at LBA {lba}')
    address = lba+150
    bcd = lambda n: (n//10)*16+n%10
    require(sector[12:16] == bytes([bcd(address//4500), bcd(address//75%60), bcd(address%75), 1]),
            f'Invalid Mode1 address at LBA {lba}')
    crc = 0
    for byte in sector[:2064]:
        crc = (crc>>8) ^ CRC[(crc^byte)&255]
    require(struct.unpack('<I', sector[2064:2068])[0] == crc, f'EDC mismatch at LBA {lba}')
    require(sector[2068:2076] == bytes(8), f'Nonzero reserved bytes at LBA {lba}')
    require(ecc_check(sector[12:2076], sector[2076:2248], 86,24,2,86), f'ECC P mismatch at LBA {lba}')
    require(ecc_check(sector[12:2248], sector[2248:2352], 52,43,86,88), f'ECC Q mismatch at LBA {lba}')


def authorized_iso(original, canonical, source_dir, manifest):
    """Reconstruct exactly authorized bytes, including only G0's size fields."""
    inventory = iso_inventory(original)
    require(len(inventory) == 100, 'Expected 100 original ISO files')
    require(set(inventory) == {r['name'] for r in manifest['files']}, 'Source manifest inventory mismatch')
    expected = bytearray(original)
    canonical_names = {p.name for p in canonical.iterdir() if p.is_file()}
    require(canonical_names == {n for n in inventory if n.endswith('.BIN')} | {'_boot.bin'},
            'Canonical tree must contain exactly 98 game assets')
    records = {r['name']:r for r in manifest['files']}
    changed = []
    for name,row in inventory.items():
        guard = records[name]
        start = row['lba']*2048
        old = bytes(original[start:start+row['size']])
        require(row['size'] == guard['size'] and row['lba'] == guard['lba'] and digest(old) == guard['sha1'],
                f'Source ISO/manifest guard mismatch: {name}')
        require((source_dir/name).read_bytes() == old, f'Extracted source changed: {name}')
        new = (canonical/name).read_bytes() if name in canonical_names else old
        if len(new) != len(old):
            require(name == 'DATA_G0.BIN' and len(old) == 121076 and len(new) == 123728 and row['lba'] == 53425,
                    'Unapproved logical file growth')
            require((len(new)+2047)//2048 == 61 and len(new) <= 124928, 'G0 budget exceeded')
            capacity = ((len(old)+2047)//2048+1)*2048
            require(not any(original[start+len(old):start+capacity]), 'G0 append space is not zero')
            require(all(other['lba']*2048 >= start+capacity or other['lba'] <= row['lba']
                        for other in inventory.values()), 'G0 growth overlaps another file')
            at = row['record_offset']+10
            expected[at:at+8] = len(new).to_bytes(4,'little')+len(new).to_bytes(4,'big')
        expected[start:start+len(new)] = new
        if old != new:
            changed.append(dict(file=name,source_sha1=digest(old),sha1=digest(new),size=len(new)))
    boot = bytes(original[:32768])
    require((source_dir/'_boot.bin').read_bytes() == boot, 'Source boot guard mismatch')
    expected[:32768] = (canonical/'_boot.bin').read_bytes()
    require(len(expected) == len(original), 'Canonical boot or payload changed ISO length')
    return expected, inventory, changed


def run(command, log):
    result = subprocess.run([str(x) for x in command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write_text(result.stdout)
    require(result.returncode == 0, f'Command failed ({result.returncode}); see {log}: {command[0]}')
    return result.stdout


def verify(root, manifest_path=None, evidence=None):
    root = Path(root).resolve()
    def resolve(value):
        p = Path(value)
        return p if p.is_absolute() else root/p
    if manifest_path is None:
        manifest_path = root/'build/m5/build-manifest.json'
    require(resolve(manifest_path).is_file(), 'Missing required build manifest')
    manifest_bytes = resolve(manifest_path).read_bytes()
    config = json.loads(manifest_bytes)
    validate_manifest(config)
    evidence = resolve(evidence or 'build/evidence/m5/verification-lane')
    evidence.mkdir(parents=True, exist_ok=True)
    artifacts = config['artifacts']
    paths = {}
    for key,record in artifacts.items():
        paths[key] = resolve(record['path'])
        check_artifact(paths[key],record)
    everdrive = {}
    for key, record in config.get('everdrive',{}).items():
        path = resolve(record['path'])
        check_artifact(path,record)
        require(file_hash(path) == file_hash(paths[key]), f'EverDrive {key} copy differs')
        everdrive[key] = dict(path=str(path),sha1=file_hash(path))
    if everdrive:
        require(set(everdrive)=={'bin','cue'}, 'Incomplete EverDrive copy')
        mirror_binary,mirror_tracks = cue_layout(Path(everdrive['cue']['path']))
        require(mirror_binary.resolve()==Path(everdrive['bin']['path']).resolve(), 'EverDrive cue references wrong BIN')
    source_cue = resolve(config['source_cue'])
    source_manifest = resolve(config['source_manifest'])
    source_dir = resolve(config.get('source_tree',str(source_manifest.parent)))
    manifest = json.loads(source_manifest.read_text())
    canonical = resolve(config['canonical_tree'])
    source, source_tracks = cue_layout(source_cue)
    target, target_tracks = cue_layout(paths['cue'])
    require(target.resolve() == paths['bin'].resolve(), 'Built cue references an unexpected BIN')
    normalize_cue = lambda text: re.sub(r'FILE\s+"[^"]+"\s+BINARY', 'FILE "BIN" BINARY', text)
    require(normalize_cue(source_cue.read_text()) == normalize_cue(paths['cue'].read_text()),
            'Built cue changed beyond its BIN filename')
    require(file_hash(source) == SOURCE_SHA1 == manifest['source_sha1'], 'Original full BIN guard failed')
    require(source_tracks == target_tracks and len(source_tracks) == 21, 'TOC changed')
    require(all(t['mode']=='AUDIO' for t in source_tracks[1:]), 'Expected 20 audio tracks')
    require(source.stat().st_size == target.stat().st_size, 'Built BIN length changed')
    # Regenerate approved recipes in the lead-owned implementation; its output
    # authenticity check is independent of the packaging builder audited below.
    run([sys.executable,root/'tools/scd_art.py','verify','--source',source_dir,'--output',canonical,
         '--evidence',evidence/'canonical-regeneration'], evidence/'canonical-regeneration.txt')
    sectors = source_tracks[0]['end']
    require(sectors == manifest['track_sectors'] == 56014, 'Data track length changed')
    print('Checking ISO authorization and all 56,014 raw sectors', flush=True)
    audio = []
    with source.open('rb') as sf, target.open('rb') as tf:
        with mmap.mmap(sf.fileno(),0,access=mmap.ACCESS_READ) as old, mmap.mmap(tf.fileno(),0,access=mmap.ACCESS_READ) as new:
            original = payload_image(old,sectors)
            expected, inventory, changed = authorized_iso(original,canonical,source_dir,manifest)
            actual = payload_image(new,sectors)
            require(actual == expected, 'Unapproved Mode1 payload or ISO metadata change')
            restored_inventory = iso_inventory(actual)
            require(set(restored_inventory)==set(inventory), 'Built ISO inventory changed')
            file_receipts = []
            for name,row in restored_inventory.items():
                oldrow = inventory[name]
                require(row['lba']==oldrow['lba'], f'File LBA moved: {name}')
                payload = actual[row['lba']*2048:row['lba']*2048+row['size']]
                want = (canonical/name).read_bytes() if (canonical/name).is_file() else (source_dir/name).read_bytes()
                require(payload == want, f'Built ISO file differs: {name}')
                file_receipts.append(dict(file=name,lba=row['lba'],source_size=oldrow['size'],size=row['size'],
                                          source_sha1=digest(original[oldrow['lba']*2048:oldrow['lba']*2048+oldrow['size']]),
                                          sha1=digest(payload)))
            changed_sectors = 0
            for lba in range(sectors):
                sector = new[lba*2352:(lba+1)*2352]
                verify_sector(sector,lba)
                changed_sectors += sector != old[lba*2352:(lba+1)*2352]
            for track in source_tracks[1:]:
                a,b = track['start']*2352,track['end']*2352
                require(old[a:b] == new[a:b], f'Audio or pregap changed: track {track["number"]}')
                audio.append(dict(track=track['number'],start_including_index00=track['start'],end=track['end'],
                                  sha1=digest(new[a:b]),bytes=b-a))
    scratch = evidence/'scratch'
    scratch.mkdir(parents=True,exist_ok=True)
    print('Checking xdelta decode and CHD verify/extractcd parity', flush=True)
    with tempfile.TemporaryDirectory(prefix='audit-',dir=scratch) as folder:
        temp = Path(folder)
        base_track,temp_track = temp/'source-track01.bin',temp/'decoded-track01.bin'
        with source.open('rb') as stream:
            base_track.write_bytes(stream.read(sectors*2352))
        if 'source_track01' in paths:
            require(file_hash(paths['source_track01']) == file_hash(base_track) and
                    paths['source_track01'].stat().st_size == sectors*2352, 'Source track01 artifact differs')
        run(['xdelta3','-d','-s',base_track,paths['xdelta'],temp_track],evidence/'xdelta-decode.txt')
        with target.open('rb') as stream:
            built_track_hash = digest(stream.read(sectors*2352))
        require(file_hash(temp_track)==built_track_hash and temp_track.stat().st_size==sectors*2352,
                'xdelta decoded track differs from built track01')
        if 'track01' in paths:
            require(file_hash(paths['track01']) == built_track_hash and
                    paths['track01'].stat().st_size == sectors*2352, 'Built track01 artifact differs')
        run(['chdman','verify','-i',paths['chd']],evidence/'chd-verify.txt')
        info = run(['chdman','info','-i',paths['chd']],evidence/'chd-info.txt')
        run(['chdman','extractcd','-i',paths['chd'],'-o',temp/'extracted.cue','-ob',temp/'extracted.bin'],evidence/'chd-extract.txt')
        extracted, extracted_tracks = cue_layout(temp/'extracted.cue')
        require(extracted_tracks == target_tracks, 'CHD extraction changed TOC/pregap timing')
        require(extracted.stat().st_size == target.stat().st_size and file_hash(extracted)==file_hash(target),
                'CHD extraction differs in raw data/audio/pregap bytes; normalization is not allowed')
        (evidence/'chd-extracted.cue').write_text((temp/'extracted.cue').read_text())
    versions = {}
    for name,command in [('chdman',['chdman','help']),('xdelta3',['xdelta3','-V'])]:
        result = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        versions[name] = result.stdout.splitlines()[0]
    for key,record in artifacts.items():
        check_artifact(paths[key],record)
    if manifest_bytes is not None:
        require(resolve(manifest_path).read_bytes() == manifest_bytes, 'Build manifest changed during verification')
        (evidence/'build-manifest-input.json').write_bytes(manifest_bytes)
    report = dict(status='pass',source_sha1=SOURCE_SHA1,artifacts={k:dict(path=str(p),sha1=file_hash(p),bytes=p.stat().st_size) for k,p in paths.items()},
                  build_manifest=dict(path=str(manifest_path),sha1=file_hash(resolve(manifest_path))) if manifest_path else None,
                  source_manifest=dict(path=str(source_manifest),sha1=file_hash(source_manifest)),
                  files=file_receipts,everdrive=everdrive,
                  boot=dict(source_sha1=digest(original[:32768]),sha1=digest(actual[:32768])),
                  source_files_verified=100,boot_verified=True,canonical_assets=98,iso_files_verified=100,
                  changed_files=changed,changed_data_sectors=changed_sectors,edc_ecc_sectors_verified=sectors,
                  data_track_sha1=built_track_hash,toc_unchanged=True,audio_tracks=audio,
                  xdelta_decode_exact=True,chd_verify=True,chd_extracted_raw_bin_exact=True,
                  chd_policy='Exact raw BIN and INDEX00/INDEX01 timing parity required. CHD internal track padding is container-only; no extracted payload, audio, pregap, duration or byte-order normalization accepted.',
                  tool_versions=versions,scope='Local packaging integrity and approved asset composition. No console acceptance claim.')
    (evidence/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--evidence',type=Path)
    args = parser.parse_args()
    report = verify(args.root,args.manifest,args.evidence)
    print(json.dumps({k:report[k] for k in ['status','iso_files_verified','edc_ecc_sectors_verified','chd_extracted_raw_bin_exact']}))


if __name__=='__main__':
    main()
