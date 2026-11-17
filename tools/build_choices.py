#!/usr/bin/env python3
"""Build bounded source-relative sector components, never thousands of disc copies."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import patch_choices as choices
import patch_profiles
import scd_art
import scd_disc

ROOT = Path(__file__).resolve().parents[1]
SECTOR = 2352
TOOLS = ('tools/build_choices.py','tools/patch_choices.py','tools/patch_profiles.py',
         'tools/scd_art.py','tools/scd_text.py','tools/m4_animation.py','tools/m4_captions.py',
         'tools/source_text_recipe.py','tools/scd_disc.py','patches/text/m3.json',
         'patches/gfx/animation.json','patches/gfx/captions.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def destination(path):
    path = Path(path).absolute()
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Output must not traverse symlinks')
    if not any(path.is_relative_to(ROOT / name) for name in ('build', 'dist')):
        raise ValueError('Outputs must stay under this checkout build or dist')
    if shutil.disk_usage(ROOT).free < 101 * 1024**3:
        raise ValueError('Need 100 GiB free plus one GiB build reserve')
    return path


def sector_ranges(sectors):
    result = []
    for lba in sorted(sectors):
        if result and result[-1]['lba'] + result[-1]['count'] == lba:
            result[-1]['count'] += 1
        else:
            result.append(dict(lba=lba, count=1))
    return result


def sector_ids(ranges):
    return [n for r in ranges for n in range(r['lba'], r['lba'] + r['count'])]


def streamed_hash(source, substitutions):
    """Hash the complete target, copying only small replaced spans in memory."""
    h = hashlib.sha256(); previous = 0
    view = memoryview(source)
    for lba, raw in sorted(substitutions.items()):
        start = lba * SECTOR
        h.update(view[previous:start]); h.update(raw)
        previous = start + SECTOR
    h.update(view[previous:])
    return h.hexdigest()


def check_assets(source, assets, names, files):
    actual = {p.name for p in assets.iterdir() if p.is_file() and (p.suffix == '.BIN' or p.name == '_boot.bin')}
    if actual != set(names):
        raise ValueError(f'Canonical asset inventory mismatch: {assets}')
    changed = {name for name in names if (assets/name).read_bytes() != (source/name).read_bytes()}
    if changed != set(files):
        raise ValueError(f'Family changed-file boundary mismatch: {assets}: {sorted(changed)}')
    for name in files:
        old = (source/name).read_bytes(); new = (assets/name).read_bytes()
        if len(new) != len(old) and not (name == 'DATA_G0.BIN' and len(old) == 121076 and len(new) == 123728):
            raise ValueError(f'Unapproved file size: {name}')


def find_assets(cache, name, number):
    if cache is None:
        return None
    cache = Path(cache)
    if not cache.is_dir():
        raise ValueError('Supplied family cache directory does not exist')
    candidates = (cache/choices.variant_id(name, number)/'assets', cache/name/f'{number:02x}'/'assets')
    for path in candidates:
        if path.is_dir():
            return path.resolve()
    if not (cache/name).is_dir() and not any(cache.glob(name+'-*')):
        return None  # A cache may supply only the expensive cameo family.
    raise ValueError(f'Missing supplied family cache: {name}-{number:02x}')


def build(source, output, legacy, asset_cache=None):
    source = Path(source).resolve(); output = destination(output)
    if output.exists():
        raise ValueError('Choose a fresh output folder')
    names = scd_art.source_inventory(source)  # Verify every source before filtering.
    tool_hashes = {name:digest((ROOT/name).read_bytes()) for name in TOOLS}
    source_assets = {name:digest((source/name).read_bytes()) for name in names}
    raw = (source/'_track01.raw').read_bytes()
    if len(raw) != choices.SOURCE_TRACK_BYTES or digest(raw) != choices.SOURCE_TRACK_SHA256:
        raise ValueError('Source Track 1 changed')
    manifest = json.loads((source/'manifest.json').read_text())
    output.mkdir(parents=True)
    write_json(output/'build-status.json',dict(status='running',source_sha256=digest(raw),tools=tool_hashes))
    release = output/'release'; (release/'patches/components').mkdir(parents=True)
    scratch = output/'work-track01.bin'
    compact = output/'work-component.bin'
    decoded = output/'work-decoded.bin'
    source_track = source/'_track01.raw'
    families = []; components = {}; asset_records = []; occupied = set()
    for name, keys, files in choices.FAMILIES:
        states = {}; union = set()
        for number in range(1, 1 << len(keys)):
            selected = choices.family_selection(name, number)
            assets = find_assets(asset_cache, name, number)
            cache_verification = None
            if assets is not None and name == 'cameos':
                proof_path=assets.parent/'verification.json'
                proof=json.loads(proof_path.read_text())
                actual_hashes={file:digest((assets/file).read_bytes()) for file in names}
                if (proof.get('status') != 'pass' or proof.get('selection') != selected.id or proof.get('variant') != number
                    or proof.get('asset_sha256') != actual_hashes
                    or proof.get('all_five_front_and_rear_poses_match_source_or_accepted') is not True
                    or proof.get('catalogue_and_provenance_checked') is not True):
                    raise ValueError('Supplied cameo cache lacks matching independent content proof')
                cache_verification=dict(path=str(proof_path),sha256=digest(proof_path.read_bytes()))
            if assets is None:
                assets = output/'assets'/choices.variant_id(name, number)
                scd_art.apply(source=source, output=assets, evidence=output/'conversion'/selected.id, profile=selected)
            check_assets(source, assets, names, selected.changed_files)
            scratch.write_bytes(raw)
            overlays = []
            for file in sorted(selected.changed_files):
                overlays.append(scd_disc.patch_file_extent(scratch, manifest, file, (assets/file).read_bytes(), allow_zero_gap=file == 'DATA_G0.BIN'))
            target = scratch.read_bytes()
            changes = {lba:target[lba*SECTOR:(lba+1)*SECTOR] for lba in range(len(raw)//SECTOR)
                       if target[lba*SECTOR:(lba+1)*SECTOR] != raw[lba*SECTOR:(lba+1)*SECTOR]}
            if not changes:
                raise ValueError(f'Empty active component: {selected.id}')
            union.update(changes); states[number] = changes
            asset_records.append(dict(family=name, value=number, selection=selected.id, assets=str(assets),
                                      files={file:digest((assets/file).read_bytes()) for file in names}, overlays=overlays,
                                      cache_verification=cache_verification))
        if occupied & union:
            raise ValueError('Component sector ownership overlaps')
        occupied.update(union); ranges = sector_ranges(union); variants = []
        for number, changes in states.items():
            ident = choices.variant_id(name, number)
            payload = b''.join(changes.get(lba, raw[lba*SECTOR:(lba+1)*SECTOR]) for lba in sorted(union))
            compact.write_bytes(payload)
            patch = release/'patches/components'/f'{ident}.xdelta'
            subprocess.run(['xdelta3', '-e', '-s', str(source_track), str(compact), str(patch)], check=True)
            subprocess.run(['xdelta3', '-f', '-d', '-s', str(source_track), str(patch), str(decoded)], check=True)
            if decoded.read_bytes() != payload:
                raise ValueError(f'Component round trip failed: {ident}')
            variants.append(dict(value=number, id=ident, patch=dict(file=f'patches/components/{ident}.xdelta', sha256=digest(patch.read_bytes())),
                                 decoded_bytes=len(payload), decoded_sha256=digest(payload)))
            components[name, number] = {lba:payload[i*SECTOR:(i+1)*SECTOR] for i,lba in enumerate(sorted(union))}
        families.append(dict(id=name, setting_keys=list(keys), files=list(files), ranges=ranges, variants=variants))
        write_json(output/'build-status.json',dict(status='running',families_complete=len(families),source_sha256=digest(raw),tools=tool_hashes))
        print(json.dumps(dict(family=name, variants=len(variants), sectors=len(union))), flush=True)
    targets = {}
    for index,ident in enumerate(choices.CHOICE_IDS,1):
        substitutions = {}
        for name, value in choices.family_values(ident).items():
            substitutions.update(components.get((name, value), {}))
        targets[ident] = streamed_hash(raw, substitutions)
        if index % 128 == 0:
            print(json.dumps(dict(targets_hashed=index,total=len(choices.CHOICE_IDS))),flush=True)
            write_json(output/'build-status.json',dict(status='running',families_complete=len(families),targets_hashed=index,tools=tool_hashes))
    legacy_registry = patch_profiles.load_registry(legacy)
    for entry in legacy_registry['profiles']:
        ident = choices.legacy_selection(entry['settings']).id
        if targets[ident] != entry['target_track1_sha256']:
            raise ValueError(f'Legacy target differs: {entry["id"]}')
    registry = dict(format=2, version=choices.VERSION, default_profile=choices.DEFAULT_CHOICE_ID,
                    source=choices.SOURCE, families=families, targets=targets)
    choices.validate_registry(registry)
    if digest(source_track.read_bytes()) != choices.SOURCE_TRACK_SHA256 or any(digest((source/name).read_bytes()) != expected for name,expected in source_assets.items()):
        raise ValueError('Source inputs changed during build')
    if any(digest((ROOT/name).read_bytes()) != expected for name,expected in tool_hashes.items()):
        raise ValueError('Source tools changed during build')
    write_json(release/'profiles.json', registry)
    receipt = dict(status='pass', source_tree=str(source), source_sha256=digest(raw), registry=str(release/'profiles.json'),
                   family_asset_states=sum(1 << len(keys) for _,keys,_ in choices.FAMILIES),
                   active_components=sum((1 << len(keys))-1 for _,keys,_ in choices.FAMILIES),
                   targets=len(choices.CHOICE_IDS), legacy_targets=16,
                   assets=asset_records, tools=tool_hashes, source_assets=source_assets,
                   stock_family_states=len(choices.FAMILIES), source_unchanged=True)
    write_json(output/'build-manifest.json', receipt)
    write_json(output/'build-status.json',dict(status='pass',registry_sha256=digest((release/'profiles.json').read_bytes()),tools=tool_hashes))
    # Keep the scratch paths, but not duplicate game outputs.
    for path in (scratch, compact, decoded):
        path.write_bytes(b'')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'private/extracted/segacd-usa')
    parser.add_argument('--output', type=Path, default=ROOT/'build/m9/choices')
    parser.add_argument('--legacy', type=Path, default=ROOT/'build/m8/release/profiles.json')
    parser.add_argument('--asset-cache', type=Path)
    args = parser.parse_args()
    output_was_absent=not args.output.exists()
    try:
        result=build(args.source,args.output,args.legacy,args.asset_cache)
    except Exception as error:
        if output_was_absent and (args.output/'build-status.json').is_file():
            write_json(args.output/'build-status.json',dict(status='failed',error=f'{type(error).__name__}: {error}'))
        raise
    print(json.dumps({k:v for k,v in result.items() if k not in ('assets','source_assets','tools')}))


if __name__ == '__main__':
    main()
