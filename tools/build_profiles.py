#!/usr/bin/env python3
"""Build isolated, checked restoration selections from user-supplied inputs.

No existing release file is overwritten. Disc images stay in ignored build paths.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import patch_profiles as profiles
import scd_art
import scd_disc
import verify_inputs

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v0.10.0-rc1'
TOOLS = ('tools/build_profiles.py','tools/patch_profiles.py','tools/scd_art.py',
         'tools/scd_text.py','tools/m4_animation.py','tools/m4_captions.py',
         'tools/scd_disc.py','tools/source_text_recipe.py','patches/text/m3.json',
         'patches/gfx/animation.json','patches/gfx/captions.json')


def sha(path, algorithm='sha256'):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,algorithm).hexdigest()


def record(path):
    path=Path(path)
    return dict(path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                bytes=path.stat().st_size,sha1=sha(path,'sha1'),sha256=sha(path))


def destination(path):
    path=Path(path).absolute()
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Build destination must not traverse a symlink')
    path=path.resolve()
    if not (path.is_relative_to(ROOT/'build') or path.is_relative_to(ROOT/'dist')):
        raise ValueError('Profile outputs must stay under this repository build or dist directory')
    return path


def run(command, log):
    with Path(log).open('w') as stream:
        subprocess.run([str(x) for x in command],stdout=stream,stderr=subprocess.STDOUT,check=True)


def build_profile(profile, folder, source, source_cue, source_track, accepted_delta):
    profile=profiles.get_profile(profile);folder=destination(folder)
    tool_hashes={name:sha(ROOT/name) for name in TOOLS}
    manifest_path=folder/'build-manifest.json'
    if manifest_path.exists():
        prior=json.loads(manifest_path.read_text())
        if prior.get('profile')!=profile.id or prior.get('tool_hashes')!=tool_hashes:
            raise ValueError('Existing candidate belongs to different tools or profile; choose a fresh output root')
        for item in prior['artifacts'].values():
            path=ROOT/item['path']
            if not path.is_file() or path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
                raise ValueError('Existing profile artifact changed; do not resume it')
        return prior
    if folder.exists():
        raise ValueError('Incomplete profile folder exists; choose a fresh output root')
    if shutil.disk_usage(ROOT).free < 108*1024**3:
        raise ValueError('Need 8 GiB reserve above the 100 GiB free-space floor')
    folder.mkdir(parents=True)
    evidence=folder/'evidence';evidence.mkdir()
    assets=folder/'assets'
    composition=scd_art.apply(source=source,output=assets,evidence=evidence/'composition',profile=profile)
    actual={r['file'] for r in composition['files'] if r['sha1']!=r['source_sha1']}
    if actual!=profile.changed_files:
        raise ValueError('Profile changed-file inventory differs from reviewed groups')
    original,tracks=scd_disc.tracks(source_cue)
    if tracks[0]['end']*2352!=profiles.SOURCE_TRACK_BYTES:
        raise ValueError('Source track length changed')
    binary=folder/('Snatcher Uncut '+profile.id+'.bin');cue=binary.with_suffix('.cue')
    if binary.exists() and binary.samefile(original):
        raise ValueError('Build output aliases original input')
    subprocess.run(['cp','-c',str(original),str(binary)],check=True)
    source_manifest=json.loads((source/'manifest.json').read_text());overlays=[]
    for name in sorted(actual):
        overlays.append(scd_disc.patch_file_extent(binary,source_manifest,name,(assets/name).read_bytes(),allow_zero_gap=name=='DATA_G0.BIN'))
    cue.write_text(re.sub(r'FILE "[^\"]+" BINARY',f'FILE "{binary.name}" BINARY',Path(source_cue).read_text()))
    target=folder/'track01.bin'
    with binary.open('rb') as stream,target.open('xb') as output:
        remaining=profiles.SOURCE_TRACK_BYTES
        while remaining:
            data=stream.read(min(2**20,remaining))
            if not data:raise ValueError('Truncated profile BIN')
            output.write(data);remaining-=len(data)
    target_hash=sha(target)
    if profile.no_patch and (target_hash!=profiles.SOURCE_TRACK_SHA256 or sha(binary)!=sha(original)):
        raise ValueError('No-patch profile differs from original source')
    if profile.id==profiles.DEFAULT_PROFILE_ID:
        if target_hash!=profiles.ACCEPTED_TRACK_SHA256 or sha(binary)!='5b502e0a5b52175ebc16d66b88078ce22d652e9fb38e1250bde9b2774561e7bd':
            raise ValueError('Default profile differs from accepted release')
    artifacts=dict(bin=record(binary),cue=record(cue),track01=record(target),source_track01=record(source_track))
    if not profile.no_patch:
        patch=folder/'patch.xdelta'
        if profile.id==profiles.DEFAULT_PROFILE_ID:
            if sha(accepted_delta)!=profiles.ACCEPTED_PATCH_SHA256:
                raise ValueError('Accepted default patch changed')
            shutil.copyfile(accepted_delta,patch)
        else:
            run(['xdelta3','-e','-s',source_track,target,patch],evidence/'xdelta-create.log')
        decoded=folder/'decoded-track01.bin'
        run(['xdelta3','-d','-s',source_track,patch,decoded],evidence/'xdelta-decode.log')
        if sha(decoded)!=target_hash or decoded.stat().st_size!=profiles.SOURCE_TRACK_BYTES:
            raise ValueError('Profile patch round-trip failed')
        # Only the digest is evidence; release packaging does not need this duplicate.
        decoded.write_bytes(b'')
        artifacts['xdelta']=record(patch)
    report=dict(version=2,profile=profile.id,settings=profile.settings,
                source_cue=str(Path(source_cue).relative_to(ROOT)),source_manifest=str((source/'manifest.json').relative_to(ROOT)),
                canonical_tree=str(assets.relative_to(ROOT)),source=record(original),overlays=overlays,
                artifacts=artifacts,tool_hashes=tool_hashes,no_patch=profile.no_patch)
    manifest_path.write_text(json.dumps(report,indent=2)+'\n')
    return report


def build_all(output=ROOT/'build/m8/profiles', release=ROOT/'build/m8/release', selected=None):
    output=destination(output);release=destination(release)
    verify_inputs.intake()
    source=scd_disc.DEFAULT_EXTRACT;source_cue=scd_disc.DEFAULT_CUE
    source_track=source/'_track01.raw'
    if source_track.stat().st_size!=profiles.SOURCE_TRACK_BYTES or sha(source_track)!=profiles.SOURCE_TRACK_SHA256:
        raise ValueError('Staged original raw data track differs')
    # Validate full source layout before making any profile folder.
    scd_art.source_inventory(source)
    # Curated source carries the accepted patch at its root; private builds
    # retain the original dist location. Both are checked against the same hash.
    packaged_delta=ROOT/'snatcher-uncut-track01.xdelta'
    accepted_delta=packaged_delta if packaged_delta.is_file() else ROOT/'dist/snatcher-uncut-track01.xdelta'
    chosen=list(selected) if selected else list(profiles.PROFILE_IDS)
    if len(chosen)!=len(set(chosen)):
        raise ValueError('Duplicate requested profile')
    results=[]
    # Default first: a parity failure stops the remaining matrix immediately.
    order=sorted(chosen,key=lambda ident:(ident!=profiles.DEFAULT_PROFILE_ID,ident))
    for ident in order:
        profile=profiles.get_profile(ident)
        report=build_profile(profile,output/profile.id,source,source_cue,source_track,accepted_delta)
        results.append(report)
        print(json.dumps(dict(status='built',profile=ident,target_sha256=report['artifacts']['track01']['sha256'])),flush=True)
    output.mkdir(parents=True,exist_ok=True)
    (output/'matrix-build.json').write_text(json.dumps(dict(version=1,profiles=[dict(id=r['profile'],manifest=str((output/r['profile']/'build-manifest.json').relative_to(ROOT))) for r in results]),indent=2)+'\n')
    if set(chosen)==set(profiles.PROFILE_IDS):
        entries=[];release.mkdir(parents=True,exist_ok=True)
        patches=release/'patches/profiles';patches.mkdir(parents=True,exist_ok=True)
        for report in sorted(results,key=lambda item:item['profile']):
            profile=profiles.get_profile(report['profile']);patch=None
            if not profile.no_patch:
                target=patches/(profile.id+'.xdelta');shutil.copyfile(ROOT/report['artifacts']['xdelta']['path'],target)
                patch=dict(file=str(target.relative_to(release)),sha256=sha(target))
            entries.append(dict(id=profile.id,settings=profile.settings,no_patch=profile.no_patch,
                target_track1_sha256=report['artifacts']['track01']['sha256'],patch=patch))
        registry=dict(format=1,version=VERSION,default_profile=profiles.DEFAULT_PROFILE_ID,
            source=dict(track1_bytes=profiles.SOURCE_TRACK_BYTES,track1_sha1=profiles.SOURCE_TRACK_SHA1,track1_sha256=profiles.SOURCE_TRACK_SHA256),profiles=entries)
        profiles.validate_registry(registry)
        (release/'profiles.json').write_text(json.dumps(registry,indent=2)+'\n')
        print(json.dumps(dict(status='registry-ready',profiles=16,patches=15,registry=str(release/'profiles.json'))),flush=True)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/m8/profiles')
    parser.add_argument('--release',type=Path,default=ROOT/'build/m8/release')
    parser.add_argument('--profiles',nargs='+',choices=profiles.PROFILE_IDS)
    args=parser.parse_args();build_all(args.output,args.release,args.profiles)

if __name__=='__main__':main()
