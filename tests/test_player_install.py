"""Installer invariants using generated disc layouts and real xdelta decoding."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import player_install as p


def sha(data, name='sha256'):
    return hashlib.new(name, data).hexdigest()


def stamp(frames):
    return f'{frames // 4500:02}:{frames // 75 % 60:02}:{frames % 75:02}'


@pytest.fixture
def fixture(tmp_path):
    source = bytes(range(256)) * (p.SECTOR * 4 // 256) + b'S' * (p.SECTOR * 4 % 256)
    target = source[:100] + b'PATCHED' + source[107:]
    base, changed, patch = (tmp_path / n for n in ['base.bin', 'target.bin', 'release.xdelta'])
    base.write_bytes(source)
    changed.write_bytes(target)
    if not shutil.which('xdelta3'):
        pytest.skip('xdelta3 is required for generated-patch integration tests')
    subprocess.run(['xdelta3', '-e', '-s', str(base), str(changed), str(patch)], check=True)
    release = p.Release(len(source), sha(source, 'sha1'), sha(target), p.digest(patch))
    return tmp_path, source, target, patch, release


def cue_layout(fixture, split=False, virtual_pregap=False):
    root, source, _, _, _ = fixture
    lines = ['REM test fixture', 'TITLE "Preserve this metadata"']
    audio = [bytes([n]) * (p.SECTOR * 3) for n in range(2, 22)]
    if split:
        for n, data in enumerate([source] + audio, 1):
            name = f'Track {n:02}.bin'
            (root / name).write_bytes(data)
            lines.extend([f'FILE "{name}" BINARY', f'  TRACK {n:02} {"MODE1/2352" if n == 1 else "AUDIO"}'])
            if n != 1 and virtual_pregap:
                lines.append('    PREGAP 00:02:00')
            elif n != 1:
                lines.append('    INDEX 00 00:00:00')
            lines.append(f'    INDEX 01 {"00:00:00" if n == 1 or virtual_pregap else "00:00:01"}')
    else:
        (root / 'Disc.bin').write_bytes(source + b''.join(audio))
        lines.extend(['FILE "Disc.bin" BINARY', '  TRACK 01 MODE1/2352', '    INDEX 01 00:00:00'])
        for n in range(2, 22):
            start = len(source) // p.SECTOR + (n - 2) * 3
            lines.extend([f'  TRACK {n:02} AUDIO', f'    INDEX 00 {stamp(start)}', f'    INDEX 01 {stamp(start + 1)}'])
    cue = root / 'Disc.cue'
    cue.write_bytes(('\r\n'.join(lines) + '\r\n').encode())
    return cue, audio


@pytest.mark.parametrize('split,virtual', [(False, False), (True, False), (True, True)])
def test_install_preserves_cue_audio_pregaps_and_source(fixture, split, virtual):
    root, source, target, patch, release = fixture
    cue, audio = cue_layout(fixture, split, virtual)
    original = {f.name: f.read_bytes() for f in root.glob('*.bin')}
    cue_before = cue.read_bytes()
    out = root / 'installed'
    result = p.install(cue, patch, out, release=release)
    assert result['audio_tracks_unchanged'] == 20
    assert (out / cue.name).read_bytes() == cue_before
    assert cue.read_bytes() == cue_before
    assert all((root / name).read_bytes() == data for name, data in original.items())
    if split:
        assert (out / 'Track 01.bin').read_bytes() == target
        assert [(out / f'Track {n:02}.bin').read_bytes() for n in range(2, 22)] == audio
    else:
        assert (out / 'Disc.bin').read_bytes() == target + b''.join(audio)
    assert all(t['unchanged'] for t in result['tracks'][1:])
    assert json.loads((out / 'install-receipt.json').read_text()) == result


def test_raw_track_install_and_already_patched(fixture):
    root, source, target, patch, release = fixture
    result = p.install(root / 'base.bin', patch, root / 'output', release=release)
    assert result['layout'] == 'raw-track1'
    assert result['audio_tracks_unchanged'] == 0
    assert (root / 'output/base.bin').read_bytes() == target
    assert (root / 'base.bin').read_bytes() == source
    with pytest.raises(p.InstallError, match='already patched'):
        p.install(root / 'target.bin', patch, root / 'repatch', release=release)
    assert not (root / 'repatch').exists()


@pytest.mark.parametrize('old,new,message', [
    ('MODE1/2352', 'MODE1/2048', 'Unsupported'),
    ('TRACK 21 AUDIO', 'TRACK 22 AUDIO', 'numbered'),
    ('INDEX 01 00:00:00', 'INDEX 01 00:00:75', 'Invalid CUE time'),
    ('INDEX 01 00:00:00', 'INDEX 02 00:00:00', 'Unsupported'),
    ('INDEX 01 00:00:00', 'INDEX 01 00:00:01', 'Track 1'),
    ('INDEX 01 00:00:00', 'INDEX 01 00:00:00\n    INDEX 01 00:00:00', 'Duplicate'),
    ('FILE "Disc.bin"', 'FILE "../Disc.bin"', 'flat'),
    ('FILE "Disc.bin"', 'FILE "/Disc.bin"', 'flat'),
    ('TRACK 02 AUDIO', 'TRACK 02 MODE1/2352', 'AUDIO'),
    ('INDEX 00 00:00:04', 'INDEX 00 00:00:05', 'precede'),
    ('INDEX 00 00:00:04', 'INDEX 00 00:00:03', 'data-track size'),
    ('TRACK 02 AUDIO', 'TRACK 02 AUDIO\n    PREGAP 00:02:00', 'Single-BIN'),
    ('TITLE "Preserve this metadata"', 'POSTGAP 00:02:00', 'Unsupported'),
])
def test_reject_bad_cue_before_output(fixture, old, new, message):
    root, _, _, patch, release = fixture
    cue, _ = cue_layout(fixture)
    text = cue.read_text()
    assert old in text
    cue.write_text(text.replace(old, new, 1))
    with pytest.raises(p.InstallError, match=message):
        p.install(cue, patch, root / 'no-output', release=release)
    assert not (root / 'no-output').exists()
    assert not list(root.glob('.snatcher-install-*'))


def test_reject_wrong_data_truncated_audio_and_patch(fixture):
    root, source, _, patch, release = fixture
    cue, _ = cue_layout(fixture)
    image = root / 'Disc.bin'
    original = image.read_bytes()
    image.write_bytes(b'X' + original[1:])
    with pytest.raises(p.InstallError, match='SHA1'):
        p.install(cue, patch, root / 'wrong-data', release=release)
    image.write_bytes(original[:-1])
    with pytest.raises(p.InstallError, match='multiple of 2352'):
        p.install(cue, patch, root / 'truncated', release=release)
    image.write_bytes(original)
    patch.write_bytes(b'corrupted patch')
    with pytest.raises(p.InstallError, match='Patch SHA256'):
        p.install(cue, patch, root / 'wrong-patch', release=release)
    assert not any((root / name).exists() for name in ['wrong-data', 'truncated', 'wrong-patch'])


def test_no_overwrite_missing_tool_symlink_and_bad_target(fixture):
    root, source, _, patch, release = fixture
    existing = root / 'existing'
    existing.mkdir()
    (existing / 'keep').write_text('unchanged')
    with pytest.raises(p.InstallError, match='must not exist'):
        p.install(root / 'base.bin', patch, existing, release=release)
    assert (existing / 'keep').read_text() == 'unchanged'
    with pytest.raises(p.InstallError, match='not found'):
        p.install(root / 'base.bin', patch, root / 'no-tool', xdelta='missing-snatcher-xdelta', release=release)
    alias = root / 'link.bin'
    alias.symlink_to(root / 'base.bin')
    with pytest.raises(p.InstallError, match='symlink'):
        p.inspect_input(alias, release)
    wrong = p.Release(release.size, release.source_sha1, '0' * 64, release.patch_sha256)
    with pytest.raises(p.InstallError, match='release target'):
        p.install(root / 'base.bin', patch, root / 'wrong-target', release=wrong)
    assert not (root / 'wrong-target').exists()


def test_unsupported_raw_size_format_and_split_offsets(fixture):
    root, source, _, patch, release = fixture
    (root / 'short.bin').write_bytes(source[:-p.SECTOR])
    with pytest.raises(p.InstallError, match='only the supported Track 1'):
        p.inspect_input(root / 'short.bin', release)
    (root / 'disc.iso').write_bytes(source)
    with pytest.raises(p.InstallError, match='ISO/2048'):
        p.inspect_input(root / 'disc.iso', release)
    cue, _ = cue_layout(fixture, split=True)
    cue.write_text(cue.read_text().replace('INDEX 00 00:00:00', 'INDEX 00 00:00:01', 1)
                   .replace('INDEX 01 00:00:01', 'INDEX 01 00:00:02', 1))
    with pytest.raises(p.InstallError, match='first stored index'):
        p.inspect_input(cue, release)


def test_decode_failure_and_low_space_leave_no_output(fixture, monkeypatch):
    root, _, _, patch, release = fixture
    original_usage = p.shutil.disk_usage(root)
    monkeypatch.setattr(p.shutil, 'disk_usage', lambda _: original_usage._replace(free=0))
    with pytest.raises(p.InstallError, match='Not enough free space'):
        p.install(root / 'base.bin', patch, root / 'space', release=release)
    monkeypatch.setattr(p.shutil, 'disk_usage', lambda _: original_usage)
    monkeypatch.setattr(p.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 1, '', 'decode error'))
    with pytest.raises(p.InstallError, match='decode failed'):
        p.install(root / 'base.bin', patch, root / 'decode', release=release)
    assert not (root / 'space').exists()
    assert not (root / 'decode').exists()
    assert not list(root.glob('.snatcher-install-*'))


@pytest.mark.parametrize('mutate_patch', [False, True])
def test_changed_inputs_abort_before_output(fixture, monkeypatch, mutate_patch):
    root, _, _, patch, release = fixture
    original_run = p.subprocess.run
    def decode_then_mutate(*args, **kwargs):
        result = original_run(*args, **kwargs)
        changed = patch if mutate_patch else root / 'base.bin'
        data = changed.read_bytes()
        changed.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        return result
    monkeypatch.setattr(p.subprocess, 'run', decode_then_mutate)
    with pytest.raises(p.InstallError, match='changed during installation'):
        p.install(root / 'base.bin', patch, root / 'changed', release=release)
    assert not (root / 'changed').exists()
    assert not list(root.glob('.snatcher-install-*'))
