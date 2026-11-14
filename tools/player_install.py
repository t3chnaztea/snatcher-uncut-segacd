#!/usr/bin/env python3
"""Apply the release Track 1 patch without rebuilding or changing audio.

Python 3.10+ and xdelta3 are required. All work is local. Inputs are read only.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

SECTOR = 2352
CHUNK = 1024 * 1024


class InstallError(ValueError):
    """An unsupported or invalid release input."""


@dataclass(frozen=True)
class Release:
    size: int = 131744928
    source_sha1: str = '1f4164205ed736a0d9a03eb7972868e9aa737d35'
    target_sha256: str = 'f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba'
    patch_sha256: str = '1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4'


RELEASE = Release()


@dataclass
class Track:
    number: int
    mode: str
    file: Path
    indices: dict[int, int] = field(default_factory=dict)
    pregap: int | None = None
    start: int = 0
    end: int = 0


@dataclass
class Layout:
    kind: str
    files: list[Path]
    tracks: list[Track]
    cue: Path | None = None
    cue_bytes: bytes | None = None


def digest(path: Path, algorithm: str = 'sha256', start: int = 0,
           length: int | None = None) -> str:
    result = hashlib.new(algorithm)
    with path.open('rb') as stream:
        stream.seek(start)
        remaining = length
        while remaining is None or remaining:
            data = stream.read(CHUNK if remaining is None else min(CHUNK, remaining))
            if not data:
                if remaining:
                    raise InstallError(f'Truncated file: {path.name}')
                break
            result.update(data)
            if remaining is not None:
                remaining -= len(data)
    return result.hexdigest()


def regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise InstallError(f'Expected a regular file, not a symlink: {path.name}')


def timecode(value: str) -> int:
    match = re.fullmatch(r'(\d{2,}):(\d{2}):(\d{2})', value)
    if not match:
        raise InstallError(f'Invalid CUE time: {value}')
    minute, second, frame = map(int, match.groups())
    if second >= 60 or frame >= 75:
        raise InstallError(f'Invalid CUE time: {value}')
    return (minute * 60 + second) * 75 + frame


def parse_cue(path: Path) -> Layout:
    """Accept two explicit layouts; retain original CUE bytes unchanged."""
    regular_file(path)
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise InstallError('CUE must use UTF-8 or ASCII encoding.') from exc
    files: list[Path] = []
    tracks: list[Track] = []
    current_file = None
    current_track = None
    file_has_track = False
    metadata = {'REM', 'TITLE', 'PERFORMER', 'SONGWRITER', 'CATALOG', 'ISRC', 'FLAGS'}
    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        command = line.split()[0].upper()
        if command in metadata:
            continue
        match = re.fullmatch(r'FILE\s+"([^"\x00-\x1f]+)"\s+BINARY', line, re.I)
        if match:
            if current_file is not None and not file_has_track:
                raise InstallError('CUE contains a FILE without a TRACK.')
            name = match[1]
            if name in {'.', '..'} or '/' in name or '\\' in name or ':' in name:
                raise InstallError('CUE BIN files must have flat relative filenames.')
            current_file = path.parent / name
            if name.casefold() in {f.name.casefold() for f in files}:
                raise InstallError('Duplicate or case-colliding CUE FILE names.')
            if name.casefold() in {path.name.casefold(), 'install-receipt.json'}:
                raise InstallError('CUE FILE name conflicts with an output file.')
            regular_file(current_file)
            if current_file.stat().st_size == 0 or current_file.stat().st_size % SECTOR:
                raise InstallError(f'BIN length is not a positive multiple of 2352: {name}')
            files.append(current_file)
            current_track = None
            file_has_track = False
            continue
        match = re.fullmatch(r'TRACK\s+(\d{2})\s+(MODE1/2352|AUDIO)', line, re.I)
        if match and current_file is not None:
            current_track = Track(int(match[1]), match[2].upper(), current_file)
            tracks.append(current_track)
            file_has_track = True
            continue
        match = re.fullmatch(r'INDEX\s+(00|01)\s+(\S+)', line, re.I)
        if match and current_track is not None:
            index = int(match[1])
            if index in current_track.indices:
                raise InstallError('Duplicate CUE INDEX.')
            if index == 0 and 1 in current_track.indices:
                raise InstallError('CUE INDEX 00 must precede INDEX 01.')
            current_track.indices[index] = timecode(match[2])
            continue
        match = re.fullmatch(r'PREGAP\s+(\S+)', line, re.I)
        if match and current_track is not None:
            if current_track.pregap is not None or current_track.indices:
                raise InstallError('PREGAP must occur once, before INDEX.')
            current_track.pregap = timecode(match[1])
            continue
        raise InstallError(f'Unsupported or malformed CUE directive at line {line_number}: {command}')
    if not file_has_track or len(tracks) != 21:
        raise InstallError('Expected exactly 21 tracks: one data track and 20 audio tracks.')
    if [t.number for t in tracks] != list(range(1, 22)):
        raise InstallError('CUE tracks must be numbered 01 through 21 in order.')
    if tracks[0].mode != 'MODE1/2352' or any(t.mode != 'AUDIO' for t in tracks[1:]):
        raise InstallError('Expected MODE1/2352 Track 1 followed by AUDIO tracks.')
    if len(files) == 1:
        kind = 'single-bin-cue'
        if any(t.pregap is not None for t in tracks):
            raise InstallError('Single-BIN layout must store pregaps as INDEX 00, not PREGAP.')
    elif len(files) == 21 and all(t.file == f for t, f in zip(tracks, files)):
        kind = 'split-bin-cue'
    else:
        raise InstallError('Supported CUE layouts use one BIN or one BIN per track.')
    for i, track in enumerate(tracks):
        if 1 not in track.indices:
            raise InstallError(f'Track {track.number:02} has no INDEX 01.')
        if 0 in track.indices and (track.indices[0] >= track.indices[1] or track.pregap is not None):
            raise InstallError('INDEX 00 must precede INDEX 01 and cannot accompany PREGAP.')
        track.start = track.indices.get(0, track.indices[1])
        if kind == 'split-bin-cue' and track.start != 0:
            raise InstallError('Each split BIN must start at its first stored index (00:00:00).')
        track.end = (tracks[i + 1].indices.get(0, tracks[i + 1].indices.get(1, -1))
                     if i + 1 < len(tracks) and tracks[i + 1].file == track.file
                     else track.file.stat().st_size // SECTOR)
        if not 0 <= track.start <= track.indices[1] < track.end:
            raise InstallError(f'Track {track.number:02} indices overlap or exceed its BIN.')
    first = tracks[0]
    if first.start != 0 or first.indices != {1: 0} or first.pregap is not None:
        raise InstallError('Track 1 must begin with INDEX 01 00:00:00 and no pregap.')
    return Layout(kind, files, tracks, path, raw)


def inspect_input(path: Path, release: Release = RELEASE) -> Layout:
    regular_file(path)
    if path.name.casefold() == 'install-receipt.json':
        raise InstallError('Input filename conflicts with the install receipt.')
    if path.suffix.lower() == '.cue':
        layout = parse_cue(path)
    elif path.suffix.lower() == '.bin':
        size = path.stat().st_size
        if size != release.size:
            raise InstallError('Raw BIN must contain only the supported Track 1. Supply its CUE for a full disc.')
        layout = Layout('raw-track1', [path], [Track(1, 'MODE1/2352', path, {1: 0}, end=size // SECTOR)])
    else:
        raise InstallError('Supply a raw Track 1 .bin or a .cue. ISO/2048 and CHD are not direct inputs.')
    first = layout.tracks[0]
    length = (first.end - first.start) * SECTOR
    if length != release.size:
        raise InstallError(f'Unsupported data-track size: {length}; expected {release.size} bytes.')
    if digest(first.file, 'sha256', 0, length) == release.target_sha256:
        raise InstallError('Track 1 is already patched.')
    actual = digest(first.file, 'sha1', 0, length)
    if actual != release.source_sha1:
        raise InstallError(f'Unsupported Track 1 SHA1: {actual}. Check region, revision and dump integrity.')
    return layout


def copy_bytes(source, target, length: int | None = None) -> None:
    remaining = length
    while remaining is None or remaining:
        data = source.read(CHUNK if remaining is None else min(CHUNK, remaining))
        if not data:
            if remaining:
                raise InstallError('Input changed or became truncated during installation.')
            break
        target.write(data)
        if remaining is not None:
            remaining -= len(data)


def install(source: Path, patch: Path, output: Path, xdelta: str = 'xdelta3',
            release: Release = RELEASE) -> dict:
    source, patch, output = Path(source), Path(patch), Path(output)
    if output.exists() or output.is_symlink():
        raise InstallError('Output directory must not exist. Inputs are never overwritten.')
    if not output.parent.is_dir():
        raise InstallError('Output parent directory must already exist.')
    layout = inspect_input(source, release)
    regular_file(patch)
    if digest(patch) != release.patch_sha256:
        raise InstallError('Patch SHA256 does not match this release.')
    executable = shutil.which(xdelta)
    if not executable:
        raise InstallError('xdelta3 was not found. Install it or supply --xdelta PATH.')
    before = {f.name: digest(f) for f in layout.files}
    track_before = [digest(t.file, start=t.start * SECTOR, length=(t.end - t.start) * SECTOR)
                    for t in layout.tracks]
    needed = 2 * sum(f.stat().st_size for f in layout.files) + 2 * release.size + CHUNK
    if shutil.disk_usage(output.parent).free < needed:
        raise InstallError(f'Not enough free space. Need at least {needed} bytes.')
    with tempfile.TemporaryDirectory(prefix='.snatcher-install-', dir=output.parent) as temporary:
        stage = Path(temporary)
        data_track, patched = stage / 'source-track1', stage / 'patched-track1'
        with layout.files[0].open('rb') as src, data_track.open('xb') as dst:
            copy_bytes(src, dst, release.size)
        if digest(data_track, 'sha1') != release.source_sha1:
            raise InstallError('Input changed after validation.')
        result = subprocess.run([executable, '-d', '-s', str(data_track), str(patch.resolve()), str(patched)],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            raise InstallError(f'xdelta3 decode failed (exit {result.returncode}): {result.stderr.strip()}')
        if digest(patch) != release.patch_sha256:
            raise InstallError('Patch changed during installation.')
        if patched.stat().st_size != release.size or digest(patched) != release.target_sha256:
            raise InstallError('Decoded Track 1 does not match the release target.')
        package = stage / 'package'
        package.mkdir()
        for file in layout.files:
            with file.open('rb') as src, (package / file.name).open('xb') as dst:
                if file == layout.files[0]:
                    with patched.open('rb') as replacement:
                        copy_bytes(replacement, dst)
                    src.seek(release.size)
                copy_bytes(src, dst)
        if layout.cue:
            if layout.cue.read_bytes() != layout.cue_bytes:
                raise InstallError('CUE changed during installation.')
            (package / layout.cue.name).write_bytes(layout.cue_bytes)
        tracks = []
        for track, original_hash in zip(layout.tracks, track_before):
            target = package / track.file.name
            installed_hash = digest(target, start=track.start * SECTOR,
                                    length=(track.end - track.start) * SECTOR)
            expected = release.target_sha256 if track.number == 1 else original_hash
            if installed_hash != expected:
                raise InstallError(f'Output verification failed for Track {track.number:02}.')
            tracks.append(dict(track=track.number, file=track.file.name, indices={str(k): v for k, v in track.indices.items()},
                               pregap_frames=track.pregap, bytes=(track.end - track.start) * SECTOR,
                               source_sha256=original_hash, output_sha256=installed_hash,
                               unchanged=installed_hash == original_hash))
        if any(digest(f) != before[f.name] for f in layout.files):
            raise InstallError('An input BIN changed during installation. No package was published.')
        receipt = dict(format_version=1, status='verified', layout=layout.kind,
                       patch_sha256=release.patch_sha256,
                       source_track1_sha1=release.source_sha1, target_track1_sha256=release.target_sha256,
                       cue_unchanged=layout.cue is not None,
                       audio_tracks_unchanged=len(tracks) - 1,
                       files=[dict(name=f.name, source_sha256=before[f.name],
                                   output_sha256=digest(package / f.name)) for f in layout.files],
                       tracks=tracks)
        # Exclusive creation is the commit point. Never replace an existing directory.
        output.mkdir()
        try:
            for artifact in package.iterdir():
                with artifact.open('rb') as src, (output / artifact.name).open('xb') as dst:
                    copy_bytes(src, dst)
            for item in receipt['files']:
                if digest(output / item['name']) != item['output_sha256']:
                    raise InstallError('Final output verification failed; inputs are unchanged.')
            if layout.cue and (output / layout.cue.name).read_bytes() != layout.cue_bytes:
                raise InstallError('Final CUE verification failed; inputs are unchanged.')
            with (output / 'install-receipt.json').open('x') as stream:
                stream.write(json.dumps(receipt, indent=2) + '\n')
        except OSError as exc:
            raise InstallError(f'Output write failed. Incomplete files remain in {output}; inputs are unchanged.') from exc
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Source CUE or raw Track 1 BIN')
    parser.add_argument('--patch', type=Path, required=True, help='Release snatcher-uncut-track01.xdelta')
    parser.add_argument('--output', type=Path, required=True, help='New output directory; must not exist')
    parser.add_argument('--xdelta', default='xdelta3', help='xdelta3 executable or path')
    args = parser.parse_args()
    try:
        receipt = install(args.input, args.patch, args.output, args.xdelta)
    except (InstallError, OSError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(f'Verified {receipt["layout"]}; {receipt["audio_tracks_unchanged"]} audio tracks unchanged.')
    print(f'Output: {args.output}')
    print('Raw Track 1 output is not a complete playable disc.' if receipt['layout'] == 'raw-track1'
          else 'CUE bytes, BIN filenames, audio and pregap bytes were preserved.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
