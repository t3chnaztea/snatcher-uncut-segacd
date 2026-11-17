"""Bounds, ownership and independent byte-placement checks for compact choices."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_choices as builder
import patch_choices as choices
import verify_choices as audit
from scd_disc import mode1_sector


def registry_fixture():
    families=[]
    lba=100
    for name,keys,files in choices.FAMILIES:
        variants=[]
        for number in range(1,1 << len(keys)):
            ident=choices.variant_id(name,number)
            variants.append(dict(value=number,id=ident,patch=dict(file=f'patches/components/{ident}.xdelta',
                sha256=hashlib.sha256(('patch-'+ident).encode()).hexdigest()),decoded_bytes=2352,
                decoded_sha256=hashlib.sha256(('decoded-'+ident).encode()).hexdigest()))
        families.append(dict(id=name,setting_keys=list(keys),files=list(files),ranges=[dict(lba=lba,count=1)],variants=variants))
        lba+=1
    targets={ident:hashlib.sha256(ident.encode()).hexdigest() for ident in choices.CHOICE_IDS}
    targets['x000']=choices.SOURCE_TRACK_SHA256
    targets[choices.DEFAULT_CHOICE_ID]=choices.ACCEPTED_TRACK_SHA256
    return dict(format=2,version=choices.VERSION,default_profile=choices.DEFAULT_CHOICE_ID,source=choices.SOURCE,
                families=families,targets=targets)


def test_every_setting_maps_to_exactly_one_variant_per_family():
    seen=set()
    for mask in range(len(choices.CHOICE_IDS)):
        selection=choices.Selection(mask)
        assert choices.get_selection(selection.settings)==selection
        values=choices.family_values(selection)
        reconstructed=0
        for name,keys,_ in choices.FAMILIES:
            component=choices.family_selection(name,values[name])
            reconstructed |= component.mask
            seen.add((name,values[name]))
        assert reconstructed==mask
    assert len(seen)==sum(1 << len(keys) for _,keys,_ in choices.FAMILIES)


def test_registry_fixture_is_complete():
    value=registry_fixture()
    assert choices.validate_registry(value)==value
    assert sum(len(f['variants']) for f in value['families'])==sum((1 << len(keys))-1 for _,keys,_ in choices.FAMILIES)


def test_independent_legacy_adapter_keeps_background_paired_with_old_cameos():
    import patch_profiles
    ids=set()
    for profile in patch_profiles.PROFILES.values():
        ident=audit.legacy_id(profile.settings)
        assert ident==choices.legacy_selection(profile.settings).id
        assert choices.get_selection(ident).settings['bar_background']==profile.cameos
        ids.add(ident)
    assert len(ids)==16


@pytest.mark.parametrize('mutation',[
    lambda r:r['families'][1]['ranges'][0].update(lba=100),
    lambda r:r['families'][0]['ranges'][0].update(lba=-1),
    lambda r:r['families'][0]['ranges'][0].update(lba=choices.SOURCE_TRACK_BYTES//2352),
    lambda r:r['families'][0]['ranges'][0].update(count=True),
    lambda r:r['families'][0]['variants'][0].update(decoded_bytes=2351),
    lambda r:r['families'][0]['variants'][0]['patch'].update(file='../outside.xdelta'),
    lambda r:r['families'][0]['variants'].clear(),
    lambda r:r['families'][0]['variants'][0].update(value=0),
    lambda r:r['targets'].pop('x345'),
    lambda r:r['targets'].update({choices.DEFAULT_CHOICE_ID:'0'*64}),
    lambda r:r.update(format=True),
])
def test_registry_rejects_incomplete_or_unsafe_components(mutation):
    value=registry_fixture(); mutation(value)
    with pytest.raises(ValueError): choices.validate_registry(value)


def test_duplicate_json_keys_rejected(tmp_path):
    file=tmp_path/'registry.json'
    file.write_text('{"format":2,"format":2}')
    with pytest.raises(ValueError,match='Duplicate'):choices.load_registry(file)


def test_streaming_hash_matches_real_target_without_disc_copies():
    source=b''.join(bytes([n])*2352 for n in range(10))
    changes={1:b'X'*2352,7:b'Y'*2352}
    expected=bytearray(source)
    for lba,data in changes.items():expected[lba*2352:(lba+1)*2352]=data
    assert builder.streamed_hash(source,changes)==hashlib.sha256(expected).hexdigest()
    assert audit.target_hash(source,changes)==hashlib.sha256(expected).hexdigest()
    assert builder.sector_ranges({1,2,3,9,10,12})==[
        dict(lba=1,count=3),dict(lba=9,count=2),dict(lba=12,count=1)]


def test_independent_payload_placement_preserves_tail_and_other_sectors(tmp_path):
    source=tmp_path/'source';assets=tmp_path/'assets';source.mkdir();assets.mkdir()
    (source/'TEST.BIN').write_bytes(b'old!')
    (assets/'TEST.BIN').write_bytes(b'new!')
    raw=b''.join(mode1_sector(bytes([n])*2048,n) for n in range(4))
    manifest=dict(files=[dict(name='TEST.BIN',lba=2,size=4)])
    replacements=audit.expected_sectors(raw,source,manifest,assets,{'TEST.BIN'})
    assert set(replacements)=={2}
    expected=mode1_sector(b'new!'+bytes([2])*2044,2)
    assert replacements[2]==expected
    audit.verify_sector(expected,2)
    assert raw[2*2352:3*2352]!=expected


def test_independent_placement_rejects_growth_and_overlap(tmp_path):
    source=tmp_path/'source';assets=tmp_path/'assets';source.mkdir();assets.mkdir()
    (source/'TEST.BIN').write_bytes(b'old!');(assets/'TEST.BIN').write_bytes(b'longer')
    raw=b''.join(mode1_sector(b'\0'*2048,n) for n in range(4))
    manifest=dict(files=[dict(name='TEST.BIN',lba=2,size=4)])
    with pytest.raises(ValueError,match='Unapproved'):audit.expected_sectors(raw,source,manifest,assets,{'TEST.BIN'})
    (assets/'TEST.BIN').write_bytes(b'new!')
    manifest['files'].append(dict(name='OTHER.BIN',lba=2,size=4))
    with pytest.raises(ValueError,match='overlap'):audit.expected_sectors(raw,source,manifest,assets,{'TEST.BIN'})


def test_alice_growth_updates_both_directory_sizes_and_zero_gap(tmp_path):
    source=tmp_path/'source';assets=tmp_path/'assets';source.mkdir();assets.mkdir()
    old=b'A'*121076;new=old+b'B'*(123728-len(old))
    (source/'DATA_G0.BIN').write_bytes(old);(assets/'DATA_G0.BIN').write_bytes(new)
    payloads=[bytearray(2048) for _ in range(100)]
    def record(lba,size,ident,directory=False):
        rec=bytearray(33+len(ident)+(len(ident)%2==0));rec[0]=len(rec)
        rec[2:6]=lba.to_bytes(4,'little');rec[6:10]=lba.to_bytes(4,'big')
        rec[10:14]=size.to_bytes(4,'little');rec[14:18]=size.to_bytes(4,'big')
        rec[25]=2 if directory else 0;rec[32]=len(ident);rec[33:33+len(ident)]=ident
        return rec
    root=record(20,2048,b'\0',True)
    payloads[16][156:190]=root
    file_record=record(30,len(old),b'DATA_G0.BIN;1')
    payloads[20][:len(file_record)]=file_record
    for i in range((len(old)+2047)//2048):
        chunk=old[i*2048:(i+1)*2048];payloads[30+i][:len(chunk)]=chunk
    raw=b''.join(mode1_sector(data,lba) for lba,data in enumerate(payloads))
    manifest=dict(files=[dict(name='DATA_G0.BIN',lba=30,size=len(old))])
    changed=audit.expected_sectors(raw,source,manifest,assets,{'DATA_G0.BIN'})
    assert 20 in changed and 90 in changed
    directory=changed[20][16:2064]
    assert int.from_bytes(directory[10:14],'little')==123728
    assert int.from_bytes(directory[14:18],'big')==123728
    assert changed[90][16:2064].startswith(b'B')
    dirty=bytearray(raw);dirty[90*2352+16]=1
    with pytest.raises(ValueError,match='zero gap'):
        audit.expected_sectors(dirty,source,manifest,assets,{'DATA_G0.BIN'})


def test_browser_schedule_covers_components_and_every_family_pair():
    from verify_choice_browser import pairwise_ids,full_disc_ids
    assert len(pairwise_ids())==4*(1 << len(choices.FAMILY_MAP['cameos'][0]))
    ids=full_disc_ids()
    assert len(ids)==1 << len(choices.FAMILY_MAP['cameos'][0]) and choices.DEFAULT_CHOICE_ID in ids
    covered=set().union(*(set(choices.family_values(ident).items()) for ident in ids))
    required={(name,value) for name,keys,_ in choices.FAMILIES for value in range(1,1<<len(keys))}
    assert required <= covered


def test_partial_family_cache_falls_back_only_for_absent_families(tmp_path):
    cache=tmp_path/'cache';assets=cache/'cameos-01'/'assets';assets.mkdir(parents=True)
    assert builder.find_assets(cache,'cameos',1)==assets.resolve()
    assert builder.find_assets(cache,'database',1) is None
    with pytest.raises(ValueError,match='Missing supplied'):
        builder.find_assets(cache,'cameos',2)
    with pytest.raises(ValueError,match='does not exist'):
        builder.find_assets(tmp_path/'typo','cameos',1)


def test_vcdiff_full_source_to_noncontiguous_sector_target(tmp_path):
    if shutil.which('xdelta3') is None:pytest.skip('xdelta3 unavailable')
    source=tmp_path/'source.bin';target=tmp_path/'compact.bin';patch=tmp_path/'compact.xdelta';output=tmp_path/'decoded.bin'
    data=b''.join(mode1_sector(bytes([n])*2048,n) for n in range(30))
    source.write_bytes(data)
    target.write_bytes(data[24*2352:25*2352]+mode1_sector(b'changed'+b'\0'*2041,3))
    subprocess.run(['xdelta3','-e','-s',str(source),str(target),str(patch)],check=True)
    subprocess.run(['xdelta3','-d','-s',str(source),str(patch),str(output)],check=True)
    assert output.read_bytes()==target.read_bytes()
    assert len(output.read_bytes())==4704
    patch.write_bytes(patch.read_bytes()[:-1])
    result=subprocess.run(['xdelta3','-f','-d','-s',str(source),str(patch),str(output)],capture_output=True)
    assert result.returncode!=0
