#!/usr/bin/env python3
"""Build the private fixed-layout disc from guarded untouched inputs.

Run with .venv/bin/python tools/build.py. No remote access is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import scd_art
import scd_disc
import scd_text
import verify_inputs

ROOT = Path(__file__).resolve().parents[1]
CHANGED = {'DATA_D0.BIN', 'DATA_D1.BIN', 'DATA_F0.BIN', 'DATA_G0.BIN',
           'DATA_O0.BIN', 'SP04.BIN', 'SP05.BIN', 'SP13.BIN', 'SP25.BIN',
           'SUBCODE.BIN'}


def record(path):
    path = Path(path)
    # Staged inputs may be shared into an isolated checkout through a symlink.
    display = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    result = {'path': str(display), 'bytes': path.stat().st_size}
    for algorithm in ('sha1', 'sha256'):
        with path.open('rb') as stream:
            result[algorithm] = hashlib.file_digest(stream, algorithm).hexdigest()
    return result


def run(args, log):
    with log.open('w') as stream:
        subprocess.run(list(map(str, args)), check=True, stdout=stream, stderr=subprocess.STDOUT)


def build(work=ROOT/'build/m5', output=ROOT/'dist'):
    work, output = Path(work).resolve(), Path(output).resolve()
    # Converter reference roots require ROOT/build/<lane>/extracted.
    if work.parent != ROOT/'build' or output != ROOT/'dist':
        raise ValueError('Work must be directly under build; output must be dist')
    if shutil.disk_usage(ROOT).free < 108 * 1024**3:
        raise ValueError('Need 8 GiB build reserve above the 100 GiB free-space floor')
    for command in ('chdman', 'xdelta3'):
        if not shutil.which(command):
            raise ValueError(f'Required command missing: {command}')
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    receipt = work/'build-manifest.json'
    if receipt.exists():
        receipt.replace(work/'previous-build-manifest.json')
    evidence = work/'evidence'
    evidence.mkdir(exist_ok=True)
    inputs = verify_inputs.intake()
    (evidence/'inputs.json').write_text(json.dumps(inputs, indent=2)+'\n')
    source_cue = scd_disc.DEFAULT_CUE
    source_bin, tracks = scd_disc.tracks(source_cue)
    extracted, assets = work/'extracted', work/'assets'
    manifest = scd_disc.extract(source_cue, extracted)
    # Recreate donor references from staged bytes and the read-only codec.
    scd_text.reference_pce()
    composition = scd_art.apply(extracted, assets, evidence/'composition')
    actual = {r['file'] for r in composition['files'] if r['sha1'] != r['source_sha1']}
    if actual != CHANGED:
        raise ValueError(f'Unexpected changed file inventory: {actual}')
    cue = output/'Snatcher Uncut (USA).cue'
    binary = cue.with_suffix('.bin')
    # Clone when available; writes always target a separate file.
    if binary.exists() and binary.samefile(source_bin):
        raise ValueError('Output aliases the input')
    subprocess.run(['cp', '-c', str(source_bin), str(binary)], check=True)
    receipts = []
    for name in sorted(actual):
        receipts.append(scd_disc.patch_file_extent(binary, manifest, name,
                        (assets/name).read_bytes(), allow_zero_gap=name=='DATA_G0.BIN'))
    cue.write_text(re.sub(r'FILE "[^\"]+" BINARY', f'FILE "{binary.name}" BINARY', source_cue.read_text()))
    (evidence/'disc-ready.json').write_text(json.dumps({'bin':record(binary), 'cue':record(cue), 'overlays':receipts}, indent=2)+'\n')
    print(f'Disc ready: {cue}', flush=True)
    source_track, patched_track = work/'source-track01.bin', work/'patched-track01.bin'
    length = tracks[0]['end'] * 2352
    for src, dest in ((source_bin, source_track), (binary, patched_track)):
        with src.open('rb') as stream, dest.open('wb') as target:
            remaining = length
            while remaining:
                data = stream.read(min(1024*1024, remaining))
                if not data:
                    raise ValueError('Truncated data track')
                target.write(data)
                remaining -= len(data)
    delta = output/'snatcher-uncut-track01.xdelta'
    run(['xdelta3','-f','-e','-s',source_track,patched_track,delta], evidence/'xdelta-create.log')
    check = work/'xdelta-roundtrip.bin'
    run(['xdelta3','-f','-d','-s',source_track,delta,check], evidence/'xdelta-apply.log')
    if record(check)['sha256'] != record(patched_track)['sha256']:
        raise ValueError('Xdelta did not reproduce patched track')
    original_audio = scd_disc.track_hashes(source_cue)
    built_audio = scd_disc.track_hashes(cue)
    if original_audio[1:] != built_audio[1:]:
        raise ValueError('Audio tracks or timing changed')
    (evidence/'audio.json').write_text(json.dumps({'source':original_audio, 'built':built_audio},indent=2)+'\n')
    chd = cue.with_suffix('.chd')
    run(['chdman','createcd','-f','-np','4','-i',cue,'-o',chd], evidence/'chd-create.log')
    run(['chdman','verify','-i',chd], evidence/'chd-verify.log')
    everdrive = output/'everdrive/Sega CD/003 Snatcher Uncut'
    everdrive.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cp','-c',str(binary),str(everdrive/binary.name)],check=True)
    shutil.copyfile(cue,everdrive/cue.name)
    if record(everdrive/binary.name)['sha256'] != record(binary)['sha256']:
        raise ValueError('EverDrive BIN copy differs')
    if (everdrive/cue.name).read_bytes() != cue.read_bytes():
        raise ValueError('EverDrive CUE copy differs')
    report = {'version':1, 'source_cue':str(source_cue.relative_to(ROOT)),
              'source_manifest':str((extracted/'manifest.json').relative_to(ROOT)),
              'canonical_tree':str(assets.relative_to(ROOT)),
              'source':record(source_bin), 'overlays':receipts,
              'everdrive':{'bin':record(everdrive/binary.name),'cue':record(everdrive/cue.name)},
              'artifacts':{key:record(path) for key,path in
                  [('bin',binary),('cue',cue),('chd',chd),('xdelta',delta),
                   ('track01',patched_track),('source_track01',source_track)]}}
    temporary = work/'build-manifest.tmp'
    temporary.write_text(json.dumps(report,indent=2)+'\n')
    temporary.replace(receipt)
    print(json.dumps({'status':'built', 'manifest':str(work/'build-manifest.json')}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=ROOT/'build/m5')
    build(parser.parse_args().work)
