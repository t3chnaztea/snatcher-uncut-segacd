"""Contracts for supported selections and packaged profile metadata."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import patch_profiles as p


def registry():
    entries=[]
    for profile in p.PROFILES.values():
        target=hashlib.sha256(('target '+profile.id).encode()).hexdigest()
        patch={'file':'patches/profiles/'+profile.id+'.xdelta','sha256':hashlib.sha256(('patch '+profile.id).encode()).hexdigest()}
        if profile.no_patch:target=p.SOURCE_TRACK_SHA256;patch=None
        elif profile.id==p.DEFAULT_PROFILE_ID:target=p.ACCEPTED_TRACK_SHA256;patch['sha256']=p.ACCEPTED_PATCH_SHA256
        entries.append(dict(id=profile.id,settings=profile.settings,no_patch=profile.no_patch,target_track1_sha256=target,patch=patch))
    return dict(format=1,version='v0.10.0-rc1',default_profile=p.DEFAULT_PROFILE_ID,source=dict(track1_bytes=p.SOURCE_TRACK_BYTES,track1_sha1=p.SOURCE_TRACK_SHA1,track1_sha256=p.SOURCE_TRACK_SHA256),profiles=entries)


def test_all_states_cover_exact_reviewed_groups():
    assert len(p.PROFILES)==16
    assert sum(x.no_patch for x in p.PROFILES.values())==1
    assert p.get_profile().text_rows==p.DATE_TEXT_ROWS|p.CAMEO_TEXT_ROWS
    assert len(p.DATE_TEXT_ROWS)==26 and len(p.CAMEO_TEXT_ROWS)==5
    assert len(p.get_profile().art_rows)==6
    assert p.get_profile('d0-c1-a1-l1').changed_files==p.get_profile().changed_files-p.GROUP_FILES['dates']
    assert p.get_profile('d0-c0-a0-l0').changed_files==frozenset()
    for profile in p.PROFILES.values():
        assert p.profile_id(**profile.settings)==profile.id
        assert ('GFX-005' in profile.art_rows)==profile.lisa
        assert ('GFX-001' in profile.art_rows)==profile.alice
        assert ('GFX-002' in profile.art_rows)==profile.cameos
        assert bool(p.DATE_TEXT_ROWS&profile.text_rows)==profile.dates


@pytest.mark.parametrize('value',['unknown','d2-c1-a1-l1',{},1,False])
def test_unknown_profiles_fail(value):
    with pytest.raises(ValueError):p.get_profile(value)


def test_registry_roundtrip_and_no_mutable_alias(tmp_path):
    data=registry();result=p.validate_registry(data)
    result['profiles'][0]['settings']['lisa']=True
    assert data['profiles'][0]['settings']['lisa'] is False
    path=tmp_path/'profiles.json';path.write_text(json.dumps(data))
    assert p.load_registry(path)==data


@pytest.mark.parametrize('kind',['missing','duplicate','settings','no_patch','source','default_target','default_patch','path','extra','duplicate_target','bool_size'])
def test_registry_rejects_mismatches(kind):
    data=registry();entry=data['profiles'][1]
    if kind=='missing':data['profiles'].pop()
    elif kind=='duplicate':data['profiles'][-1]=copy.deepcopy(entry)
    elif kind=='settings':entry['settings']['lisa']=False
    elif kind=='no_patch':entry['no_patch']=True
    elif kind=='source':data['source']['track1_sha1']='0'*40
    elif kind=='default_target':data['profiles'][-1]['target_track1_sha256']='0'*64
    elif kind=='default_patch':data['profiles'][-1]['patch']['sha256']='0'*64
    elif kind=='path':entry['patch']['file']='../outside.xdelta'
    elif kind=='extra':entry['extra']=True
    elif kind=='duplicate_target':entry['target_track1_sha256']=data['profiles'][0]['target_track1_sha256']
    elif kind=='bool_size':data['source']['track1_bytes']=True
    with pytest.raises(ValueError):p.validate_registry(data)


def test_duplicate_json_fields_rejected(tmp_path):
    path=tmp_path/'profiles.json';path.write_text('{"format":1,"format":1}')
    with pytest.raises(ValueError,match='Duplicate'):p.load_registry(path)
