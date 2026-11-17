"""Packaging binds the exact runtime, components and verified manifest before writing."""
from pathlib import Path
import sys
import json
import hashlib
import zipfile
import copy

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from package_player_release import package_choices, PLAYER_DOCUMENTS, PROFILE_MEDIA
from test_patch_choices import registry_fixture


def sha(data): return hashlib.sha256(data).hexdigest()


@pytest.fixture
def candidate(tmp_path):
    root=tmp_path/'root';browser=tmp_path/'browser';media=tmp_path/'media';release=tmp_path/'release'
    for folder in (root,browser,media/'assets',release):folder.mkdir(parents=True)
    for name in PLAYER_DOCUMENTS:(root/name).write_text('[Rebuild from source](docs/setup.md)\n' if name=='README.md' else name+'\n')
    (root/'OFFLINE-INSTALL.md').write_text('Local installer instructions\n')
    (root/'tools').mkdir()
    for name in ('player_install.py','patch_profiles.py','patch_choices.py','choice_install.py'):(root/'tools'/name).write_text('# runtime fixture\n')
    for name in PROFILE_MEDIA:(media/'assets'/name).write_bytes(('reviewed-'+name).encode())
    registry=registry_fixture()
    for family in registry['families']:
        for variant in family['variants']:
            data=('component-'+variant['id']).encode();path=release/variant['patch']['file'];path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(data);variant['patch']['sha256']=sha(data)
    specification=release/'profiles.json';specification.write_text(json.dumps(registry))
    files={}
    for name in ('index.html','style.css','app.js','choices.js','patch-data.js','vendor/LICENSE','vendor/RomPatcher.js','vendor/modules/BinFile.js','vendor/modules/HashCalculator.js','vendor/modules/RomPatcher.format.vcdiff.js'):
        file=browser/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(('reviewed-'+name).encode());files[name]=sha(file.read_bytes())
    receipt=dict(registry_format=2,profile_registry_sha256=sha(specification.read_bytes()),profiles=registry,engine_commit='4f17297cd1dc0835a0b0747497fa15f5f63f1623',component_patch_sha256={v['id']:v['patch']['sha256'] for f in registry['families'] for v in f['variants']},files=files)
    (browser/'browser-build.json').write_text(json.dumps(receipt))
    return root,browser,specification,media,tmp_path/'package'


def test_flat_source_package_is_reproducible_and_has_complete_internal_checksums(candidate):
    result=package_choices(*candidate);root,browser,specification,media,destination=candidate
    again=package_choices(root,browser,specification,media,destination.parent/'second-package')
    assert result['choices']==4096 and result['component_patches']==70
    assert result['archive']==again['archive']
    with zipfile.ZipFile(destination/result['archive']['file']) as archive:
        assert archive.testzip() is None
        assert len([x for x in archive.namelist() if x.startswith('patches/components/')])==70
        assert b'https://github.com/' in archive.read('README.md')
        for line in archive.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1);assert sha(archive.read(name))==digest


@pytest.mark.parametrize('damage',['runtime','component','registry','missing_runtime','wrong_engine'])
def test_changed_or_incomplete_inputs_fail_without_creating_output(candidate,damage):
    root,browser,registry,media,output=candidate
    if damage=='runtime':(browser/'app.js').write_text('altered after review')
    elif damage=='component':
        next((registry.parent/'patches/components').glob('*.xdelta')).write_bytes(b'bad')
    elif damage=='registry':
        data=json.loads(registry.read_text());data['targets']['x001']='0'*64;registry.write_text(json.dumps(data))
    else:
        p=browser/'browser-build.json';data=json.loads(p.read_text())
        if damage=='missing_runtime':data['files'].pop('choices.js')
        else:data['engine_commit']='0'*40
        p.write_text(json.dumps(data))
    with pytest.raises(ValueError):package_choices(root,browser,registry,media,output)
    assert not output.exists()
