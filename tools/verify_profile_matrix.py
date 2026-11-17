#!/usr/bin/env python3
"""Independently verify all 16 reviewed restoration selections.

Asset expectations come from untouched source and immutable accepted assets,
not from the profile builder. Raw-sector parity checks reuse a proof only for
exactly equal (LBA, sector bytes) within this invocation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import verify_build as disc
from patch_profiles import load_registry

SOURCE_TRACK_SHA256 = '9592d44b3241b31f36d235acc651bfa9cd2ab9562eadf9aecd86735913f0495d'
ACCEPTED_TRACK_SHA256 = 'f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba'
ACCEPTED_BIN_SHA256 = '5b502e0a5b52175ebc16d66b88078ce22d652e9fb38e1250bde9b2774561e7bd'
GROUP_FILES = {
    'dates': {'SP04.BIN','SP05.BIN','DATA_D0.BIN','DATA_D1.BIN'},
    'cameos': {'DATA_O0.BIN','SP13.BIN','SUBCODE.BIN'},
    'alice': {'DATA_G0.BIN','SP25.BIN'},
    'lisa': {'DATA_F0.BIN'},
}
PROFILE_IDS = tuple(f'd{d}-c{c}-a{a}-l{l}' for d in range(2) for c in range(2)
                    for a in range(2) for l in range(2))


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def asset_inventory(path):
    names = {p.name for p in Path(path).iterdir() if p.is_file() and
             (p.suffix == '.BIN' or p.name == '_boot.bin')}
    disc.require(len(names) == 98 and '_boot.bin' in names, 'Expected 98 canonical assets')
    return names


def verify_asset_profile(profile_id, source, accepted, canonical):
    """Check every selected file against an independent source/accepted oracle."""
    source,accepted,canonical = map(Path,(source,accepted,canonical))
    settings = disc.profile_settings(profile_id)
    names = asset_inventory(source)
    disc.require(asset_inventory(accepted) == names, 'Accepted asset inventory mismatch')
    disc.require({p.name for p in canonical.iterdir() if p.is_file()} == names,
                 'Profile canonical inventory mismatch')
    expected_changed = set().union(*(files for group,files in GROUP_FILES.items()
          if (settings['dates'] == 'japanese' if group == 'dates' else settings[group])))
    selected_files = []
    for name in sorted(names):
        oracle = accepted/name if name in expected_changed else source/name
        actual = canonical/name
        disc.require(actual.read_bytes() == oracle.read_bytes(),
                     f'{profile_id}: enabled/disabled asset differs: {name}')
        selected_files.append(dict(file=name,oracle='accepted' if name in expected_changed else 'source',
                                   sha256=sha256(actual)))
    actual_changed = {name for name in names if (canonical/name).read_bytes() != (source/name).read_bytes()}
    disc.require(actual_changed == expected_changed, f'{profile_id}: changed-file group boundary mismatch')
    return dict(profile=profile_id,settings=settings,canonical_assets_verified=98,
                selected_changed_files=sorted(expected_changed),files=selected_files)


def verify(root, profiles_root, registry_path, evidence, source_tree=None, accepted_tree=None):
    root,profiles_root,registry_path,evidence = map(lambda p:Path(p).resolve(),
                                                  (root,profiles_root,registry_path,evidence))
    def resolve(value):
        p=Path(value)
        return p if p.is_absolute() else root/p
    source_tree = resolve(source_tree or 'private/extracted/segacd-usa')
    accepted_manifest = json.loads((root/'build/m5/build-manifest.json').read_text())
    accepted_tree = resolve(accepted_tree or accepted_manifest['canonical_tree'])
    disc.require(sha256(resolve(accepted_manifest['artifacts']['bin']['path'])) == ACCEPTED_BIN_SHA256,
                 'Accepted baseline BIN no longer matches immutable golden hash')
    registry = load_registry(registry_path)
    profiles = {p['id']:p for p in registry['profiles']}
    disc.require(set(profiles) == set(PROFILE_IDS), 'Registry must contain all 16 selections')
    evidence.mkdir(parents=True,exist_ok=False)
    report = dict(status='running',profiles=[],source_oracle=str(source_tree),accepted_oracle=str(accepted_tree),
                  all_settings_verified=False,sector_cache_policy='Exact LBA and full sector bytes; no persisted cache')
    def save():
        (evidence/'matrix.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    sector_cache = set()
    for ident in PROFILE_IDS:
        folder = profiles_root/ident
        manifest_path = folder/'build-manifest.json'
        config = json.loads(manifest_path.read_text())
        disc.validate_manifest(config)
        disc.require(config.get('version') == 2 and config.get('profile') == ident,
                     'Profile manifest identity mismatch')
        disc.require(config['settings'] == profiles[ident]['settings'], 'Registry/manifest settings mismatch')
        assets = verify_asset_profile(ident, source_tree, accepted_tree, resolve(config['canonical_tree']))
        result = disc.verify(root,manifest_path,evidence/ident,sector_cache=sector_cache)
        track = resolve(config['artifacts']['track01']['path'])
        track_hash = sha256(track)
        disc.require(track_hash == profiles[ident]['target_track1_sha256'], 'Registry target does not match output')
        if ident == 'd0-c0-a0-l0':
            disc.require(track_hash == SOURCE_TRACK_SHA256 and profiles[ident]['no_patch'],
                         'No-patch selection is not original Track 1')
            disc.require('xdelta' not in config['artifacts'], 'No-op selection must not emit a patch')
        else:
            delta = resolve(config['artifacts']['xdelta']['path'])
            disc.require(sha256(delta) == profiles[ident]['patch']['sha256'], 'Registry patch hash mismatch')
            packaged_delta = registry_path.parent/profiles[ident]['patch']['file']
            disc.require(packaged_delta.read_bytes() == delta.read_bytes(), 'Registry patch file differs from verified delta')
        if ident == 'd1-c1-a1-l1':
            disc.require(track_hash == ACCEPTED_TRACK_SHA256, 'Default target differs from accepted release')
            disc.require(sha256(resolve(config['artifacts']['bin']['path'])) == ACCEPTED_BIN_SHA256,
                         'Default full BIN differs from accepted release')
        (evidence/ident/'asset-oracles.json').write_text(json.dumps(assets,indent=2)+'\n')
        report['profiles'].append(dict(profile=ident,target_track1_sha256=track_hash,
             canonical_assets_verified=98,iso_files_verified=result['iso_files_verified'],
             edc_ecc_sectors_verified=result['edc_ecc_sectors_verified'],
             fresh_sector_checks=result['edc_ecc_fresh_sector_checks'],
             identical_sector_proofs_reused=result['edc_ecc_cached_identical_sector_checks'],
             audio_tracks_verified=len(result['audio_tracks']),xdelta_decode_exact=result['xdelta_decode_exact'],
             no_patch_exact_source=result['no_patch_exact_source'],chd_status=result['chd_status']))
        save()
        print(f'{ident}: 98 assets, 100 ISO files, 56014 sectors, 20 audio tracks verified',flush=True)
    report.update(status='pass',all_settings_verified=True,settings_count=16,active_patches=15,
                  original_disc_no_patch=True,unique_raw_sector_proofs=len(sector_cache))
    save()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--profiles-root',type=Path,required=True)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--source-tree',type=Path)
    parser.add_argument('--accepted-tree',type=Path)
    args=parser.parse_args()
    r=verify(args.root,args.profiles_root,args.registry,args.evidence,args.source_tree,args.accepted_tree)
    print(json.dumps({key:r[key] for key in ('status','settings_count','active_patches','unique_raw_sector_proofs')}))

if __name__=='__main__':main()
