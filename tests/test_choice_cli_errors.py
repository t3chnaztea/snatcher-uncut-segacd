"""Invalid imports fail as CLI errors without reading game inputs or writing outputs."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('kind',['malformed','array','missing-settings','null-settings','wrong-settings','mismatch','oversized','missing-file','bad-code'])
def test_cli_bad_settings_are_readable_and_create_no_output(tmp_path,kind):
    settings=tmp_path/'settings.json';output=tmp_path/'must-not-exist'
    documents={'malformed':'{bad','array':'[]','missing-settings':json.dumps(dict(format=3,installer='Snatcher Patcher',profile_id='xfff')),'null-settings':json.dumps(dict(format=3,installer='Snatcher Patcher',profile_id='xfff',settings=None)),'wrong-settings':json.dumps(dict(format=3,installer='Snatcher Patcher',profile_id='xfff',settings=['invalid'])),'mismatch':json.dumps(dict(format=1,kind='snatcher-patcher-settings',choice_id='xfff',settings={})), 'oversized':'x'*65537}
    if kind in documents:settings.write_text(documents[kind])
    option=['--code','SP2:not-a-choice'] if kind=='bad-code' else ['--settings',str(settings)]
    result=subprocess.run([sys.executable,str(ROOT/'tools/player_install.py'),str(tmp_path/'never-read.bin'),*option,'--output',str(output)],capture_output=True,text=True)
    assert result.returncode!=0
    assert 'Traceback' not in result.stderr
    assert 'error:' in result.stderr.lower()
    assert not output.exists()


@pytest.mark.parametrize('document',['[]','null'])
def test_identify_rejects_nonobject_registry_without_traceback(tmp_path,document):
    registry=tmp_path/'profiles.json';registry.write_text(document)
    result=subprocess.run([sys.executable,str(ROOT/'tools/player_install.py'),str(tmp_path/'unread.bin'),'--registry',str(registry),'--identify'],capture_output=True,text=True)
    assert result.returncode!=0 and 'Invalid release registry document' in result.stderr
    assert 'Traceback' not in result.stderr
    assert {p.name for p in tmp_path.iterdir()}=={'profiles.json'}


def test_identify_unknown_track_creates_no_output(tmp_path):
    from test_choice_installer import registry_fixture
    registry=tmp_path/'profiles.json';registry.write_text(json.dumps(registry_fixture()))
    source=tmp_path/'unknown.bin'
    with source.open('wb') as stream:stream.truncate(131744928)
    result=subprocess.run([sys.executable,str(ROOT/'tools/player_install.py'),str(source),'--registry',str(registry),'--identify'],capture_output=True,text=True)
    assert result.returncode!=0 and 'Unrecognized Track 1' in result.stderr
    assert 'Traceback' not in result.stderr
    assert {p.name for p in tmp_path.iterdir()}=={'profiles.json','unknown.bin'}
