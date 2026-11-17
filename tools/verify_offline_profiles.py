#!/usr/bin/env python3
"""Verify every released profile through four real offline disc layouts.

This developer verifier retains receipts and hashes, not installed disc images.
Derived fixtures are temporary. Virtual-pregap fixtures intentionally omit each
stored pregap's samples and express its duration through CUE PREGAP instead.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import patch_profiles
import player_install

SECTOR = 2352
BLOCK = 4 * 1024 * 1024
FREE_FLOOR = 100 * 1024**3


def require(value, message):
    if not value:
        raise ValueError(message)


def file_hash(path, start=0, length=None):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        stream.seek(start)
        while length is None or length:
            chunk = stream.read(BLOCK if length is None else min(BLOCK, length))
            if not chunk:
                require(length is None, 'Unexpected EOF while hashing')
                break
            h.update(chunk)
            if length is not None:
                length -= len(chunk)
    return h.hexdigest()


def joined_hash(paths):
    h = hashlib.sha256()
    for path in paths:
        with Path(path).open('rb') as stream:
            while data := stream.read(BLOCK):
                h.update(data)
    return h.hexdigest()


def copy_range(source, destination, start, length):
    with Path(source).open('rb') as src, Path(destination).open('xb') as dst:
        src.seek(start)
        while length:
            data = src.read(min(BLOCK, length))
            require(data, 'Unexpected EOF deriving fixture')
            dst.write(data)
            length -= len(data)


def stamp(frames):
    return f'{frames // 4500:02}:{frames // 75 % 60:02}:{frames % 75:02}'


def source_tracks(binary, cue):
    """Independent narrow parser for the original one-file source CUE."""
    text = cue.read_text(encoding='utf-8-sig')
    names = re.findall(r'^\s*FILE\s+"([^"\r\n]+)"\s+BINARY\s*$', text, re.M | re.I)
    require(names == [binary.name], 'Source CUE must name the supplied single BIN')
    tracks = []
    for number, mode, body in re.findall(r'TRACK\s+(\d+)\s+(\S+)(.*?)(?=\s*TRACK|\Z)', text, re.S | re.I):
        indices = {}
        for index, mm, ss, ff in re.findall(r'INDEX\s+(00|01)\s+(\d+):(\d+):(\d+)', body):
            require(int(ss) < 60 and int(ff) < 75, 'Invalid source time')
            require(index not in indices, 'Duplicate source index')
            indices[index] = (int(mm) * 60 + int(ss)) * 75 + int(ff)
        require('01' in indices, 'Source track lacks INDEX 01')
        tracks.append(dict(number=int(number), mode=mode.upper(), indices=indices,
                           start=indices.get('00', indices['01'])))
    require([t['number'] for t in tracks] == list(range(1, 22)), 'Expected 21 ordered tracks')
    require(tracks[0]['mode'] == 'MODE1/2352' and all(t['mode'] == 'AUDIO' for t in tracks[1:]), 'Wrong source track modes')
    require(binary.stat().st_size % SECTOR == 0, 'Source has partial raw sector')
    for n, track in enumerate(tracks):
        track['end'] = tracks[n+1]['start'] if n+1 < len(tracks) else binary.stat().st_size // SECTOR
        require(0 <= track['start'] <= track['indices']['01'] < track['end'], 'Source index outside track')
    require(tracks[0]['start'] == 0 and tracks[0]['indices'] == {'01': 0}, 'Unsupported source Track 1')
    return tracks


@dataclass
class Fixture:
    name: str
    input: Path
    files: list[Path]
    cue: Path | None
    audio: list[dict]
    transformation: str


def fixture_audio(path, number, start, end, pregap_frames):
    return dict(track=number, file=path.name, offset=start, bytes=end-start,
                sha256=file_hash(path, start, end-start), pregap_frames=pregap_frames)


def prepare_fixtures(binary, cue, folder, track_bytes):
    tracks = source_tracks(binary, cue)
    require(tracks[0]['end'] * SECTOR == track_bytes, 'Source Track 1 length differs from registry')
    raw = folder/'Track 01.bin'
    copy_range(binary, raw, 0, track_bytes)
    source_audio = [fixture_audio(binary, t['number'], t['start']*SECTOR, t['end']*SECTOR,
                                  t['indices']['01']-t['start']) for t in tracks[1:]]
    fixtures = [Fixture('raw-track1', raw, [raw], None, [], 'Exact original Track 1 slice'),
                Fixture('single-bin-cue', cue, [binary], cue, source_audio,
                        'Untouched supplied original BIN/CUE')]
    transformations = []
    for virtual in (False, True):
        sub = folder/('virtual' if virtual else 'stored')
        sub.mkdir()
        files, audio = [], []
        lines = ['REM Real source-derived fixture; original source is not changed']
        for t in tracks:
            name = f'Track {t["number"]:02}.bin'
            target = sub/name
            skip = virtual and t['number'] > 1
            start = t['indices']['01'] if skip else t['start']
            copy_range(binary, target, start*SECTOR, (t['end']-start)*SECTOR)
            files.append(target)
            lines += [f'FILE "{name}" BINARY', f'  TRACK {t["number"]:02} {t["mode"]}']
            gap = t['indices']['01']-t['start']
            if skip:
                if gap:
                    lines.append(f'    PREGAP {stamp(gap)}')
                lines.append('    INDEX 01 00:00:00')
                transformations.append(dict(track=t['number'], virtual_pregap_frames=gap,
                                            omitted_original_pregap_bytes=gap*SECTOR,
                                            omitted_original_pregap_sha256=file_hash(binary,t['start']*SECTOR,gap*SECTOR),
                                            retained_audio_bytes=target.stat().st_size))
            else:
                if '00' in t['indices']:
                    lines.append('    INDEX 00 00:00:00')
                lines.append('    INDEX 01 '+stamp(gap))
            if t['number'] > 1:
                audio.append(fixture_audio(target,t['number'],0,target.stat().st_size,gap))
        derived_cue = sub/('Virtual pregap.cue' if virtual else 'Stored pregap.cue')
        derived_cue.write_bytes(('\r\n'.join(lines)+'\r\n').encode())
        fixtures.append(Fixture('split-virtual-pregap' if virtual else 'split-stored-index00',
                                derived_cue, files, derived_cue, audio,
                                'Stored pregap samples omitted; same duration represented as virtual CUE PREGAP; post-INDEX01 samples retained exactly'
                                if virtual else 'Exact original track slices including all stored INDEX00 pregap samples'))
    return fixtures, transformations


def verify_case(fixture, entry, registry_path, output, expected_whole):
    result = player_install.install(fixture.input, None, output, registry=registry_path,
                                    profile_id=entry['id'])
    require(result.get('profile_id') == entry['id'] and result.get('settings') == entry['settings'], 'Receipt profile mismatch')
    require(result.get('status') == 'verified' and result.get('no_patch') is False, 'Installer did not verify active profile')
    receipt = json.loads((output/'install-receipt.json').read_text())
    require(receipt == result, 'Saved installer receipt differs from return value')
    expected_names = {f.name for f in fixture.files} | {'install-receipt.json'}
    if fixture.cue:
        expected_names.add(fixture.cue.name)
        require((output/fixture.cue.name).read_bytes() == fixture.cue.read_bytes(), 'Offline CUE bytes changed')
    require({f.name for f in output.iterdir()} == expected_names, 'Unexpected installed file inventory')
    data_file = output/fixture.files[0].name
    track_hash = file_hash(data_file, 0, patch_profiles.SOURCE_TRACK_BYTES)
    require(track_hash == entry['target_track1_sha256'], 'Independent target Track 1 check failed')
    require(data_file.stat().st_size == fixture.files[0].stat().st_size, 'Installed BIN size changed')
    audio_results=[]
    for a in fixture.audio:
        path=output/a['file']
        require(path.stat().st_size == next(f.stat().st_size for f in fixture.files if f.name==a['file']), 'Audio BIN size changed')
        actual=file_hash(path,a['offset'],a['bytes'])
        require(actual == a['sha256'], 'Supplied audio bytes changed')
        audio_results.append(dict(track=a['track'],sha256=actual,bytes=a['bytes'],pregap_frames=a['pregap_frames']))
    whole = None
    if fixture.name == 'single-bin-cue':
        whole = file_hash(data_file)
        require(whole == expected_whole, 'Full-disc output differs from verified profile build')
    elif fixture.name == 'split-stored-index00':
        whole = joined_hash([output/f.name for f in fixture.files])
        require(whole == expected_whole, 'Stored split tracks do not rejoin to verified whole BIN')
    require(len(audio_results)==(0 if fixture.name=='raw-track1' else 20), 'Audio coverage incomplete')
    return dict(profile=entry['id'], layout=fixture.name, status='pass',
                target_track1_sha256=track_hash, whole_bin_sha256=whole,
                whole_bin_comparison='not applicable to virtual-pregap transformation' if fixture.name=='split-virtual-pregap' else 'verified' if whole else 'raw Track 1 only',
                cue_exact=fixture.cue is not None, audio_tracks_verified=len(audio_results),
                audio=audio_results, provided_input_scope=fixture.transformation,
                installer_receipt=result)


def verify(registry_path, binary, cue, profiles_root, output):
    registry_path,binary,cue,profiles_root,output=map(lambda p:Path(p).resolve(),
                                                 (registry_path,binary,cue,profiles_root,output))
    require(not output.exists(), 'Evidence directory must be new')
    require(shutil.disk_usage(output.parent).free > FREE_FLOOR+4*1024**3, 'Need temporary reserve above 100 GiB free-space floor')
    output.mkdir(parents=True)
    registry=patch_profiles.load_registry(registry_path)
    entries=[e for e in registry['profiles'] if not e['no_patch']]
    require(len(entries)==15, 'Expected all 15 active profiles')
    result=dict(format=1,status='running',registry_sha256=file_hash(registry_path),
                active_profiles=15, expected_cases=60, cases=[],wrong_profile_patch_checks=[],
                source_bin_sha256=file_hash(binary),source_cue_sha256=file_hash(cue),
                virtual_fixture_limit='Virtual fixtures replace stored pregap samples with timing only. Only the audio bytes supplied to each fixture are promised unchanged; no claim that virtual-gap samples equal original stored pregap payloads.',
                temporary_game_outputs_retained=False)
    def save():
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='offline-profile-fixtures-',dir=output) as tmp:
            folder=Path(tmp)
            fixtures, transformations=prepare_fixtures(binary,cue,folder,registry['source']['track1_bytes'])
            result['virtual_fixture_transformations']=transformations
            all_inputs={str(f):file_hash(f) for fixture in fixtures for f in fixture.files+([fixture.cue] if fixture.cue else [])}
            result['fixture_inputs']=[dict(file=Path(f).name,sha256=h,bytes=Path(f).stat().st_size) for f,h in all_inputs.items()]
            save()
            for entry in entries:
                manifest=json.loads((profiles_root/entry['id']/'build-manifest.json').read_text())
                require(manifest['profile']==entry['id'] and manifest['settings']==entry['settings'], 'Build manifest profile differs')
                expected_whole=manifest['artifacts']['bin']['sha256']
                for fixture in fixtures:
                    require(shutil.disk_usage(output).free>FREE_FLOOR+2*1024**3,'Free-space floor reached')
                    with tempfile.TemporaryDirectory(prefix='installed-case-',dir=folder) as stage:
                        case=verify_case(fixture,entry,registry_path,Path(stage)/'result',expected_whole)
                    result['cases'].append(case)
                    save()
                    print(f'{len(result["cases"]):02}/60 {entry["id"]} {fixture.name}: pass',flush=True)
            # A different legitimate profile's delta must never pass this selection.
            for i,entry in enumerate(entries):
                other=entries[(i+1)%len(entries)]
                wrong_patch=registry_path.parent/other['patch']['file']
                destination=folder/('wrong-'+entry['id'])
                try:
                    player_install.install(fixtures[0].input,wrong_patch,destination,
                                           registry=registry_path,profile_id=entry['id'])
                except player_install.InstallError as exc:
                    require('Patch SHA256' in str(exc),'Wrong patch rejected for an unrelated reason')
                else:
                    raise ValueError('Cross-profile patch was accepted')
                require(not destination.exists(),'Cross-profile failure left an output directory')
                result['wrong_profile_patch_checks'].append(dict(profile=entry['id'],wrong_patch_profile=other['id'],status='rejected-before-output'))
                save()
            class NoRead:
                def __fspath__(self):
                    raise AssertionError('No-patch selection attempted to read or coerce the input path')
            noop_dest=folder/'noop-output'
            noop=player_install.install(NoRead(),None,noop_dest,registry=registry_path,profile_id='d0-c0-a0-l0')
            require(noop['no_patch'] and noop['input_verified'] is False and not noop_dest.exists(),'No-patch contract failed')
            result['no_patch']=dict(input_path_not_accessed=True,output_directory_created=False,receipt=noop)
            for path,expected in all_inputs.items():
                require(file_hash(path)==expected,'Source or derived fixture changed during verification')
            result['all_fixture_inputs_unchanged']=True
        require(file_hash(binary)==result['source_bin_sha256'] and file_hash(cue)==result['source_cue_sha256'],'Original supplied inputs changed')
        require(len(result['cases'])==60 and len(result['wrong_profile_patch_checks'])==15,'Incomplete offline matrix')
        result.update(status='pass',original_inputs_unchanged=True,temporary_fixtures_removed=True,
                      free_bytes_after=shutil.disk_usage(output).free)
        save()
        return result
    except Exception as exc:
        result.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        save()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--bin',type=Path,required=True)
    parser.add_argument('--cue',type=Path,required=True)
    parser.add_argument('--profiles-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=verify(args.registry,args.bin,args.cue,args.profiles_root,args.output)
    print(json.dumps(dict(status=report['status'],cases=len(report['cases']),wrong_patch_checks=len(report['wrong_profile_patch_checks']))))


if __name__=='__main__':
    main()
