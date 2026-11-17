#!/usr/bin/env python3
"""Audit compact choices using independent payload placement and exhaustive hashes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import patch_choices as choices
import patch_profiles
from scd_disc import mode1_sector
from verify_build import verify_sector

ROOT = Path(__file__).resolve().parents[1]
SECTOR = 2352


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def range_lbas(ranges):
    return tuple(n for row in ranges for n in range(row['lba'], row['lba'] + row['count']))


def expected_sectors(source_raw, source, manifest, assets, files):
    """Place ISO file payloads directly; do not call the builder overlay primitive."""
    rows = {row['name']:row for row in manifest['files']}
    payloads = {}

    def user_sector(lba):
        if lba not in payloads:
            payloads[lba] = bytearray(source_raw[lba*SECTOR+16:lba*SECTOR+2064])
        return payloads[lba]

    for name in files:
        row = rows[name]; old = (source/name).read_bytes(); new = (assets/name).read_bytes()
        require(len(old) == row['size'], 'Source extent size mismatch')
        growing = name == 'DATA_G0.BIN' and len(old) == 121076 and len(new) == 123728
        require(len(old) == len(new) or growing, f'Unapproved size change: {name}')
        count = (len(new)+2047)//2048
        for other in rows.values():
            if other['name'] != name and other['size']:
                require(max(row['lba'], other['lba']) >= min(row['lba']+count, other['lba']+(other['size']+2047)//2048), 'Asset extents overlap')
        if growing:
            tail = b''.join(source_raw[lba*SECTOR+16:lba*SECTOR+2064] for lba in range(row['lba'], row['lba']+count))
            require(not any(tail[len(old):len(new)]), 'Alice growth is not source zero gap')
        for index in range(count):
            chunk = new[index*2048:(index+1)*2048]
            user_sector(row['lba']+index)[:len(chunk)] = chunk
        if growing:
            # Independently enumerate ISO9660 directory records from the PVD.
            root = source_raw[16*SECTOR+16+156:16*SECTOR+16+190]
            matches = []

            def walk(record, parent=''):
                lba = int.from_bytes(record[2:6], 'little'); length = int.from_bytes(record[10:14], 'little')
                data = b''.join(source_raw[n*SECTOR+16:n*SECTOR+2064] for n in range(lba, lba+(length+2047)//2048))[:length]
                pos = 0
                while pos < len(data):
                    size = data[pos]
                    if not size:
                        pos = (pos//2048+1)*2048
                        continue
                    rec = data[pos:pos+size]
                    require(size >= 34 and len(rec) == size and pos%2048+size <= 2048, 'Invalid ISO record')
                    ident = rec[33:33+rec[32]]
                    if ident not in (b'\0', b'\1'):
                        path = (parent+'/' if parent else '') + ident.decode('ascii').split(';')[0]
                        if rec[25] & 2:
                            walk(rec, path)
                        elif path == name:
                            require(int.from_bytes(rec[2:6],'little') == row['lba'] == int.from_bytes(rec[6:10],'big'), 'ISO directory LBA changed')
                            require(int.from_bytes(rec[10:14],'little') == len(old) == int.from_bytes(rec[14:18],'big'), 'ISO directory size changed')
                            matches.append((lba+pos//2048, pos%2048))
                    pos += size
            walk(root)
            require(len(matches) == 1, 'Expected exactly one Alice directory record')
            for lba, offset in matches:
                sector = user_sector(lba)
                sector[offset+10:offset+14] = len(new).to_bytes(4,'little')
                sector[offset+14:offset+18] = len(new).to_bytes(4,'big')
    result = {}
    for lba, payload in payloads.items():
        raw = mode1_sector(payload, lba)
        if raw != source_raw[lba*SECTOR:(lba+1)*SECTOR]:
            result[lba] = raw
    return result


def target_hash(source_raw, replacements):
    digest = hashlib.sha256(); previous = 0; view = memoryview(source_raw)
    for lba in sorted(replacements):
        offset = lba*SECTOR
        digest.update(view[previous:offset]); digest.update(replacements[lba]); previous = offset+SECTOR
    digest.update(view[previous:])
    return digest.hexdigest()


def legacy_id(settings):
    """Independent immutable old-control mapping to the twelve source choices."""
    mask = 15 if settings['dates'] == 'japanese' else 0
    if settings['cameos']:
        mask |= sum(1 << bit for bit in (4,5,6,7,8,11))
    if settings['alice']:
        mask |= 1 << 9
    if settings['lisa']:
        mask |= 1 << 10
    return f'x{mask:03x}'


def verify(source, registry_path, build_manifest, accepted, legacy, evidence):
    original_evidence=Path(evidence).absolute()
    require(not original_evidence.is_symlink() and not any(p.is_symlink() for p in original_evidence.parents), 'Evidence must not traverse symlinks')
    source, registry_path, build_manifest, accepted, legacy, evidence = map(lambda p:Path(p).resolve(),
        (source, registry_path, build_manifest, accepted, legacy, evidence))
    require(evidence.is_relative_to(ROOT/'build'), 'Evidence must stay under checkout build')
    require(not evidence.exists(), 'Choose a fresh verification evidence folder')
    evidence.mkdir(parents=True)
    receipt_path = evidence/'verification.json'
    receipt = dict(status='running', registry_sha256=sha(registry_path.read_bytes()))
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    try:
        registry = choices.load_registry(registry_path)
        source_raw = (source/'_track01.raw').read_bytes()
        require(len(source_raw) == choices.SOURCE_TRACK_BYTES and sha(source_raw) == choices.SOURCE_TRACK_SHA256, 'Source raw Track 1 changed')
        manifest = json.loads((source/'manifest.json').read_text())
        names = {row['name'] for row in manifest['files'] if row['name'].endswith('.BIN')} | {'_boot.bin'}
        require(len(names) == 98, 'Expected 98 canonical assets')
        for row in manifest['files']:
            data = (source/row['name']).read_bytes()
            require(len(data) == row['size'] and hashlib.sha1(data).hexdigest() == row['sha1'], 'Source extracted asset changed')
        boot = b''.join(source_raw[n*SECTOR+16:n*SECTOR+2064] for n in range(16))
        require((source/'_boot.bin').read_bytes() == boot, 'Source boot area changed')
        for lba in range(len(source_raw)//SECTOR):
            verify_sector(source_raw[lba*SECTOR:(lba+1)*SECTOR], lba)
            if (lba+1) % 4096 == 0:
                print(json.dumps(dict(source_sectors_verified=lba+1,total=len(source_raw)//SECTOR)),flush=True)
        built = json.loads(build_manifest.read_text())
        require(built.get('status') == 'pass' and built.get('source_sha256') == choices.SOURCE_TRACK_SHA256, 'Unfinished or wrong-source component build')
        records = {(row['family'], row['value']):row for row in built['assets']}
        require(len(records) == len(built['assets']) == sum((1 << len(keys))-1 for _,keys,_ in choices.FAMILIES), 'Unexpected family asset state count')
        cache = {}; variant_receipts = []; sector_proofs = set(); changed_union = set()
        for family in registry['families']:
            name = family['id']; family_files = set(family['files']); lbas = range_lbas(family['ranges']); actual_union = set()
            for variant in family['variants']:
                value = variant['value']; files = family_files if name != 'cameos' or value & 31 else {'DATA_O0.BIN'}
                record = records[name,value]; assets = Path(record['assets'])
                require(record['selection'] == choices.family_selection(name,value).id, 'Asset selection mismatch')
                if record.get('cache_verification'):
                    binding=record['cache_verification']; proof_path=Path(binding['path'])
                    require(sha(proof_path.read_bytes()) == binding['sha256'], 'Independent content receipt changed')
                    proof=json.loads(proof_path.read_text())
                    require(proof.get('status') == 'pass' and proof.get('selection') == record['selection']
                            and proof.get('variant') == value and proof.get('asset_sha256') == record['files'], 'Independent content receipt does not bind these assets')
                    require(proof.get('all_five_front_and_rear_poses_match_source_or_accepted') is True
                            and proof.get('catalogue_and_provenance_checked') is True, 'Independent cameo content checks missing')
                actual_names = {p.name for p in assets.iterdir() if p.is_file() and (p.suffix == '.BIN' or p.name == '_boot.bin')}
                require(actual_names == names and set(record['files']) == names, 'Canonical asset inventory mismatch')
                changed = set()
                for file in sorted(names):
                    data = (assets/file).read_bytes()
                    require(sha(data) == record['files'][file], 'Family asset hash changed')
                    if data != (source/file).read_bytes():
                        changed.add(file)
                    if file not in files:
                        require(data == (source/file).read_bytes(), 'Family changed an unowned asset')
                    # Every whole-family endpoint has an immutable accepted oracle.
                    if value == (1 << len(family['setting_keys']))-1 and file in files:
                        require(data == (accepted/file).read_bytes(), f'Accepted endpoint mismatch: {name}/{file}')
                require(changed == files, f'Family changed-file mismatch: {name}')
                expected = expected_sectors(source_raw,source,manifest,assets,files)
                actual_union.update(expected)
                patch = registry_path.parent/variant['patch']['file']
                require(sha(patch.read_bytes()) == variant['patch']['sha256'], 'Component patch hash changed')
                decoded_path = evidence/'decoded-component.bin'
                subprocess.run(['xdelta3','-f','-d','-s',str(source/'_track01.raw'),str(patch),str(decoded_path)],check=True)
                data = decoded_path.read_bytes()
                require(len(data) == variant['decoded_bytes'] and sha(data) == variant['decoded_sha256'], 'Decoded component checksum or size differs')
                rawmap = {}
                for index,lba in enumerate(lbas):
                    sector = data[index*SECTOR:(index+1)*SECTOR]
                    require(sector == expected.get(lba,source_raw[lba*SECTOR:(lba+1)*SECTOR]), f'Component differs from independent ISO payload oracle: {variant["id"]}/{lba}')
                    proof = (lba,sector)
                    if proof not in sector_proofs:
                        verify_sector(sector,lba); sector_proofs.add(proof)
                    rawmap[lba] = sector
                require(set(expected) <= set(lbas), 'Registry omits required family sector')
                cache[name,value] = rawmap
                variant_receipts.append(dict(id=variant['id'],decoded_sha256=sha(data),sectors=len(lbas),canonical_assets_verified=98))
            require(actual_union == set(lbas), 'Family ownership is not exact union of changed sectors')
            require(not changed_union & actual_union, 'Family ownership overlaps')
            changed_union.update(actual_union)
        targets = {}
        for mask in range(len(choices.CHOICE_IDS)):
            ident = f'x{mask:03x}'; merged = {}
            # Decode the public bit positions directly rather than use builder composition.
            for family in registry['families']:
                value = sum(bool(mask & (1 << choices.SETTING_KEYS.index(key))) << index for index,key in enumerate(family['setting_keys']))
                merged.update(cache.get((family['id'],value),{}))
            targets[ident] = target_hash(source_raw,merged)
            require(targets[ident] == registry['targets'][ident], f'Target differs: {ident}')
            if (mask+1) % 128 == 0:
                receipt.update(targets_verified=mask+1)
                receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
                print(json.dumps(dict(targets_verified=mask+1,total=len(choices.CHOICE_IDS))),flush=True)
        old = patch_profiles.load_registry(legacy)
        for row in old['profiles']:
            require(targets[legacy_id(row['settings'])] == row['target_track1_sha256'], 'Legacy target oracle differs')
        require(targets['x000'] == choices.SOURCE_TRACK_SHA256 and targets[choices.DEFAULT_CHOICE_ID] == choices.ACCEPTED_TRACK_SHA256, 'Source/default oracle differs')
        (evidence/'decoded-component.bin').write_bytes(b'')
        receipt.update(status='pass', source_sha256=sha(source_raw), components_verified=len(records),
                       family_asset_states=len(records)+len(choices.FAMILIES), canonical_asset_comparisons=len(records)*98, targets_verified=len(choices.CHOICE_IDS),
                       legacy_targets_verified=16, source_sectors_verified=len(source_raw)//SECTOR,
                       unique_component_sector_proofs=len(sector_proofs), owned_sectors=len(changed_union),
                       variants=variant_receipts, targets=targets,
                       limitation='Mixed cameo semantic/pixel oracles are supplied by the independent content lane; this audit proves exact asset-to-sector composition and accepted family endpoints.')
    except Exception as error:
        receipt.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'private/extracted/segacd-usa')
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--build-manifest',type=Path,required=True)
    parser.add_argument('--accepted',type=Path,default=ROOT/'build/m5/assets')
    parser.add_argument('--legacy',type=Path,default=ROOT/'build/m8/release/profiles.json')
    parser.add_argument('--evidence',type=Path,required=True)
    args = parser.parse_args()
    result = verify(args.source,args.registry,args.build_manifest,args.accepted,args.legacy,args.evidence)
    print(json.dumps({k:v for k,v in result.items() if k not in ('targets','variants')}))


if __name__ == '__main__':
    main()
