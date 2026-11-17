"""Fail-closed advanced selection and portable settings contracts."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import patch_choices as choices
import player_install
from choice_install import parse_settings


def registry_fixture():
    h=lambda x:hashlib.sha256(x.encode()).hexdigest()
    targets={key:h('target-'+key) for key in choices.CHOICE_IDS}
    targets['x000']=choices.SOURCE['track1_sha256']
    from patch_profiles import ACCEPTED_TRACK_SHA256
    targets[choices.DEFAULT_CHOICE_ID]=ACCEPTED_TRACK_SHA256
    families=[]
    for lba,(name,keys,files) in enumerate(choices.FAMILIES):
        variants=[]
        for value in range(1,1<<len(keys)):
            ident=choices.variant_id(name,value)
            variants.append(dict(value=value,id=ident,patch=dict(file=f'patches/components/{ident}.xdelta',sha256=h('patch-'+ident)),decoded_bytes=2352,decoded_sha256=h('decoded-'+ident)))
        families.append(dict(id=name,setting_keys=list(keys),files=list(files),ranges=[dict(lba=lba,count=1)],variants=variants))
    return dict(format=2,version=choices.VERSION,default_profile=choices.DEFAULT_CHOICE_ID,source=choices.SOURCE,families=families,targets=targets)


def test_no_op_dispatch_reads_no_source_or_output(tmp_path):
    class Unreadable:
        def __fspath__(self): raise AssertionError('source/output touched')
    result=player_install.install(Unreadable(),None,Unreadable(),registry=registry_fixture(),profile_id='x000')
    assert result['format_version']==3 and result['no_patch'] and result['files']==[]


@pytest.mark.parametrize('damage',['target','overlap','patch','count','source'])
def test_registry_rejected_before_input(tmp_path,damage):
    r=registry_fixture()
    if damage=='target': del r['targets']['x001']
    elif damage=='overlap': r['families'][1]['ranges'][0]['lba']=0
    elif damage=='patch': r['families'][0]['variants'][0]['patch']['file']='../escape'
    elif damage=='count': r['families'][0]['ranges'][0]['count']=0
    else: r['source']=dict(r['source'],track1_sha256='0'*64)
    with pytest.raises(ValueError): player_install.install(tmp_path/'missing',None,tmp_path/'out',registry=r,profile_id='x000')
    assert not (tmp_path/'out').exists()


def test_settings_receipts_only_supply_choices():
    selected=choices.get_selection('x80a')
    doc=dict(format_version=3,installer='Snatcher Patcher',profile_id=selected.id,settings=selected.settings,files=[{'name':'../../secret'}],target_track1_sha256='untrusted')
    assert parse_settings(json.dumps(doc))==selected
    doc['profile_id']='xfff'
    with pytest.raises(ValueError):parse_settings(json.dumps(doc))


def test_legacy_receipt_maps_background_and_all_dates():
    doc=dict(format=2,installer='Snatcher Patcher',profile_id='d0-c1-a0-l0',settings=dict(dates='segacd',cameos=True,alice=False,lisa=False))
    result=parse_settings(json.dumps(doc)).settings
    assert result['bar_background'] and all(result[k] for k in choices.CAMEO_KEYS)
    assert not any(result[k] for k in choices.SETTING_KEYS[:4])


@pytest.mark.parametrize('text',['{"kind":"x","kind":"y"}','[]','x'*65537])
def test_malformed_settings_rejected(text):
    with pytest.raises(ValueError):parse_settings(text)


def test_receipt_requires_explicit_matching_profile_id():
    doc=dict(format_version=3,installer='Snatcher Patcher',settings=choices.get_selection().settings)
    with pytest.raises(ValueError):parse_settings(json.dumps(doc))
