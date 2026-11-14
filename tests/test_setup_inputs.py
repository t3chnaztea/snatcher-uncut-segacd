"""Staging rejects corrupt or unsafe inputs before creating a manifest."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import setup_inputs


@pytest.fixture
def staged(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    (tmp_path/'private').mkdir()
    rows = []
    for index in range(32):
        data = f'synthetic input {index}'.encode()
        name = f'fixture-{index}.dat'
        (tmp_path/'private'/name).write_bytes(data)
        rows.append(dict(path=name, bytes=len(data), sha1=hashlib.sha1(data).hexdigest()))
    specification = dict(version=1, inputs=rows,
                         reference=dict(path='.deps/reference', revision='a'*40))
    (tmp_path/'config/input-manifest.json').write_text(json.dumps(specification))
    tools = tmp_path/'.deps/reference/pce/tools'
    tools.mkdir(parents=True)
    (tools/'pcescript.py').write_text('# synthetic reference\n')
    monkeypatch.setattr(setup_inputs.subprocess, 'run',
                        lambda *args, **kwargs: SimpleNamespace(stdout='a'*40+'\n', returncode=0))
    return tmp_path


def test_manifest_created_after_verified_inputs_only(staged):
    assert setup_inputs.setup(staged)['manifest_created'] is True
    original = (staged/'private/MANIFEST.md').read_bytes()
    assert setup_inputs.setup(staged)['manifest_created'] is False
    assert (staged/'private/MANIFEST.md').read_bytes() == original


@pytest.mark.parametrize('corruption', ['missing', 'same_size', 'wrong_size'])
def test_bad_input_never_creates_manifest(staged, corruption):
    path = staged/'private/fixture-0.dat'
    if corruption == 'missing':
        path.rename(path.with_suffix('.missing'))
    elif corruption == 'same_size':
        path.write_bytes(b'X'*path.stat().st_size)
    else:
        path.write_bytes(b'changed size')
    with pytest.raises(ValueError):
        setup_inputs.setup(staged)
    assert not (staged/'private/MANIFEST.md').exists()


def test_unsafe_manifest_path_rejected(staged):
    path = staged/'config/input-manifest.json'
    record = json.loads(path.read_text())
    record['inputs'][0]['path'] = '../outside.dat'
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='Unsafe'):
        setup_inputs.setup(staged)


def test_existing_foreign_manifest_not_overwritten(staged):
    manifest = staged/'private/MANIFEST.md'
    manifest.write_text('Existing user notes\n')
    with pytest.raises(ValueError, match='not overwritten'):
        setup_inputs.setup(staged)
    assert manifest.read_text() == 'Existing user notes\n'


def test_dirty_reference_never_creates_manifest(staged, monkeypatch):
    monkeypatch.setattr(setup_inputs.subprocess, 'run',
                        lambda args, **kwargs: SimpleNamespace(
                            stdout='a'*40+'\n', returncode=1 if 'diff' in args else 0))
    with pytest.raises(ValueError, match='modified'):
        setup_inputs.setup(staged)
    assert not (staged/'private/MANIFEST.md').exists()
