"""Advanced settings preserve reviewed group dependencies and reject bad manifests."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import patch_choices as choices
import patch_profiles as legacy


def h(value): return hashlib.sha256(value.encode()).hexdigest()


def registry_fixture():
    targets={f'x{i:03x}':h(f'target-{i}') for i in range(4096)}
    targets['x000']=legacy.SOURCE_TRACK_SHA256
    targets['xfff']=legacy.ACCEPTED_TRACK_SHA256
    families=[]
    for i,(name,keys,files) in enumerate(choices.FAMILIES):
        variants=[]
        for value in range(1,1 << len(keys)):
            ident=f'{name}-{value:02x}'
            variants.append(dict(value=value,id=ident,patch=dict(file=f'patches/components/{ident}.xdelta',sha256=h('patch-'+ident)),decoded_bytes=2352,decoded_sha256=h('decoded-'+ident)))
        families.append(dict(id=name,setting_keys=list(keys),files=list(files),ranges=[dict(lba=100+i*10,count=1)],variants=variants))
    return dict(format=2,version=choices.VERSION,default_profile='xfff',source=dict(choices.SOURCE),families=families,targets=targets)


def test_every_selection_keeps_logical_dependencies():
    ids=set()
    for mask in range(4096):
        selected=choices.get_selection(f'x{mask:03x}');ids.add(selected.id)
        assert choices.get_selection(selected.settings)==selected
        # Database records always travel as one coherent chronology.
        assert (set(legacy.DATE_TEXT_ROWS) <= selected.text_rows)==selected.dates
        assert not selected.text_rows & {'TEXT-027','TEXT-028','TEXT-029','TEXT-030','TEXT-031','TEXT-032','TEXT-037','TEXT-038','TEXT-039'}
        for key,row in [('mask_rider','TERM-002'),('cornelius','TERM-003'),('alyen','TERM-004'),('miss_money','TERM-005'),('h2o_gulliver','TERM-006')]:
            assert (row in selected.text_rows)==selected.settings[key]
            assert (key in selected.cameo_groups)==selected.settings[key]
        for key,row,file in [('moscow_date','TEXT-034','DATA_D1.BIN'),('newspaper_date','TEXT-035','DATA_D1.BIN'),('neokobe_date','TEXT-036','DATA_D0.BIN')]:
            assert (row in selected.art_rows)==selected.settings[key]
            if selected.settings[key]:assert file in selected.changed_files
        assert ('SP25.BIN' in selected.changed_files)==selected.alice
        assert ('DATA_G0.BIN' in selected.changed_files)==selected.alice
        assert ('DATA_F0.BIN' in selected.changed_files)==selected.lisa
        assert selected.no_patch==(mask==0)
    assert len(ids)==4096


def test_all_legacy_states_have_exact_row_and_file_mapping():
    for ident,old in legacy.PROFILES.items():
        new=choices.legacy_selection(ident)
        assert new==choices.legacy_selection(old.settings)
        assert new.text_rows==old.text_rows and new.art_rows==old.art_rows
        assert new.changed_files==old.changed_files and new.no_patch==old.no_patch
    assert choices.legacy_selection(legacy.DEFAULT_PROFILE_ID).id=='xfff'
    assert choices.legacy_selection('d0-c0-a0-l0').id=='x000'
    assert legacy.get_profile('xfff')==choices.get_selection()


def test_family_partition_covers_all_11_choices_without_overlap():
    keys=[key for _,group,_ in choices.FAMILIES for key in group]
    assert len(keys)==len(set(keys))==12
    assert set(keys)==set(choices.SETTING_KEYS)
    assert sum((1 << len(group))-1 for _,group,_ in choices.FAMILIES)==70
    for name,group,_ in choices.FAMILIES:
        for value in range(1 << len(group)):
            selected=choices.family_selection(name,value)
            values=choices.family_values(selected)
            assert values[name]==value
            assert all(number==0 for family,number in values.items() if family!=name)


@pytest.mark.parametrize('value',[True,False,-1,4096,'x1000','xFFF','x00','x0000','d9-c0-a0-l0',[],{},dict.fromkeys(choices.SETTING_KEYS,1)])
def test_unknown_choices_rejected(value):
    with pytest.raises(ValueError):choices.get_selection(value)


def test_registry_roundtrip_is_defensive_and_complete(tmp_path):
    original=registry_fixture();validated=choices.validate_registry(original)
    assert validated==original and validated is not original
    validated['families'][0]['ranges'][0]['lba']=1000
    assert original['families'][0]['ranges'][0]['lba']==100
    path=tmp_path/'profiles.json';path.write_text(json.dumps(original))
    assert choices.load_registry(path)==original
    path.write_text('{"format":2,"format":2}')
    with pytest.raises(ValueError,match='Duplicate'):choices.load_registry(path)


@pytest.mark.parametrize('damage',[
    lambda d:d.update(format=True),
    lambda d:d.update(source=[]),
    lambda d:d.update(default_profile='x000'),
    lambda d:d['source'].update(track1_bytes=True),
    lambda d:d['targets'].pop('x001'),
    lambda d:d['targets'].update(xfff='0'*64),
    lambda d:d['targets'].update(x001=d['targets']['x002']),
    lambda d:d['families'][1]['ranges'][0].update(lba=100),
    lambda d:d['families'][0]['ranges'][0].update(lba=-1),
    lambda d:d['families'][0]['ranges'][0].update(lba=56014),
    lambda d:d['families'][0]['ranges'][0].update(count=True),
    lambda d:d['families'][0]['ranges'].append(dict(lba=100,count=1)),
    lambda d:d['families'][0]['variants'][0].update(decoded_bytes=2353),
    lambda d:d['families'][0]['variants'][0].update(value=False),
    lambda d:d['families'][0]['variants'][0]['patch'].update(file='../private.bin'),
    lambda d:d['families'][3]['variants'].pop(),
    lambda d:d['families'][0].update(files=['SUBCODE.BIN']),
    lambda d:d['families'][0].update(id=[]),
])
def test_bad_registry_rejected_before_input(damage):
    data=registry_fixture();damage(data)
    with pytest.raises(ValueError):choices.validate_registry(data)


def test_wide_crowd_is_not_misrepresented_as_an_interactive_guest():
    background=choices.get_selection('x800')
    assert background.bar_background and background.cameos
    assert not background.cameo_groups and not background.text_rows
    assert background.art_rows=={'GFX-002'}
    assert background.changed_files=={'DATA_O0.BIN'}
    guest=choices.get_selection('x010')
    assert not guest.bar_background and guest.cameo_groups=={'mask_rider'}
    assert guest.text_rows=={'TERM-002'}
    assert guest.changed_files=={'DATA_O0.BIN','SP13.BIN','SUBCODE.BIN'}
