"""Profile routing and fail-closed installer selection checks."""
from pathlib import Path
import hashlib
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import patch_profiles as profiles
import player_install


def registry_fixture():
    rows = []
    for ident, profile in profiles.PROFILES.items():
        target = hashlib.sha256(('target-' + ident).encode()).hexdigest()
        patch_hash = hashlib.sha256(('patch-' + ident).encode()).hexdigest()
        patch = {'file': f'patches/profiles/{ident}.xdelta', 'sha256': patch_hash}
        if profile.no_patch:
            target, patch = profiles.SOURCE_TRACK_SHA256, None
        elif ident == profiles.DEFAULT_PROFILE_ID:
            target, patch['sha256'] = profiles.ACCEPTED_TRACK_SHA256, profiles.ACCEPTED_PATCH_SHA256
        rows.append(dict(id=ident, settings=profile.settings, no_patch=profile.no_patch,
                         target_track1_sha256=target, patch=patch))
    return dict(format=1, version='v0.10.0-rc1', default_profile=profiles.DEFAULT_PROFILE_ID,
                source=dict(track1_bytes=profiles.SOURCE_TRACK_BYTES,
                            track1_sha1=profiles.SOURCE_TRACK_SHA1,
                            track1_sha256=profiles.SOURCE_TRACK_SHA256), profiles=rows)


def test_no_patch_does_not_read_inputs_or_create_destination(tmp_path):
    registry = registry_fixture()
    out = tmp_path / 'do-not-create'
    result = player_install.install(tmp_path/'not-a-file.cue', None, out,
                                    registry=registry, profile_id='d0-c0-a0-l0')
    assert result['no_patch'] and not result['input_verified']
    assert result['profile_id'] == 'd0-c0-a0-l0'
    assert result['files'] == [] and result['tracks'] == []
    assert not out.exists()


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'settings', 'source', 'default-target', 'traversal'])
def test_invalid_registry_fails_before_input_or_output(tmp_path, change):
    registry = registry_fixture()
    if change == 'missing': registry['profiles'].pop()
    elif change == 'duplicate': registry['profiles'][1] = registry['profiles'][0]
    elif change == 'settings': registry['profiles'][1]['settings']['dates'] = 'japanese'
    elif change == 'source': registry['source']['track1_sha1'] = '0'*40
    elif change == 'default-target': registry['profiles'][-1]['target_track1_sha256'] = '1'*64
    elif change == 'traversal': registry['profiles'][-1]['patch']['file'] = '../secret'
    out = tmp_path/'no-output'
    with pytest.raises(player_install.InstallError):
        player_install.install(tmp_path/'missing.cue', None, out, registry=registry)
    assert not out.exists()


def test_unknown_profile_and_unregistered_selection_fail(tmp_path):
    with pytest.raises(player_install.InstallError, match='Unknown'):
        player_install.install(tmp_path/'missing.cue', None, tmp_path/'out',
                               registry=registry_fixture(), profile_id='unknown')
    with pytest.raises(player_install.InstallError, match='registry'):
        player_install.install(tmp_path/'missing.cue', None, tmp_path/'out', profile_id='d1-c1-a1-l1')


def test_registry_path_rejects_duplicate_json_field(tmp_path):
    p = tmp_path/'profiles.json'
    s = json.dumps(registry_fixture()).replace('"format": 1', '"format": 1, "format": 1')
    p.write_text(s)
    with pytest.raises(player_install.InstallError, match='Duplicate'):
        player_install.install(tmp_path/'missing.cue', None, tmp_path/'out', registry=p)
