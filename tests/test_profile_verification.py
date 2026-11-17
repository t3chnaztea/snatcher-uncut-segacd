"""Independent oracles for optional restoration selection, not builder echoes."""
from pathlib import Path
import copy
import sys
import itertools

import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_build as disc
import verify_profile_matrix as matrix
from verify_player_browser import expected_cue_bytes


def record():
    return dict(path='file.bin',bytes=1,sha1='0'*40,sha256='0'*64)


def manifest(ident):
    keys={'bin','cue','track01','source_track01'}
    if ident!='d0-c0-a0-l0':keys.add('xdelta')
    return dict(version=2,profile=ident,no_patch=ident=='d0-c0-a0-l0',settings=disc.profile_settings(ident),source_cue='source.cue',
                source_manifest='source.json',canonical_tree='assets',source=record(),
                artifacts={key:record() for key in keys})


def test_profile_id_is_exact_and_settings_are_typed():
    for ident in matrix.PROFILE_IDS:
        m=manifest(ident);disc.validate_manifest(m)
        bad=copy.deepcopy(m);bad['settings']['cameos']=int(bad['settings']['cameos'])
        with pytest.raises(ValueError,match='boolean'):disc.validate_manifest(bad)
        bad=copy.deepcopy(m);bad['settings']['dates']='other'
        with pytest.raises(ValueError,match='settings mismatch'):disc.validate_manifest(bad)
    for ident in ('d2-c1-a1-l1','d1-c1-a1','D1-c1-a1-l1','d1-c1-a1-l1-extra',None):
        with pytest.raises(ValueError,match='Unknown profile'):disc.profile_settings(ident)


def test_v2_does_not_weaken_v1_chd_everdrive_requirements():
    m=manifest('d1-c1-a1-l1')
    bad=copy.deepcopy(m);bad['version']=1
    with pytest.raises(ValueError,match='six mandatory'):disc.validate_manifest(bad)
    bad['artifacts']['chd']=record()
    with pytest.raises(ValueError,match='EverDrive'):disc.validate_manifest(bad)
    bad['everdrive']={key:record() for key in ('bin','cue')};disc.validate_manifest(bad)
    for field in ('chd','everdrive'):
        bad=copy.deepcopy(m);bad[field]={}
        with pytest.raises(ValueError,match='unbuilt'):disc.validate_manifest(bad)
    bad=copy.deepcopy(m);bad['artifacts']['chd']=record()
    with pytest.raises(ValueError,match='inventory'):disc.validate_manifest(bad)


def test_no_patch_manifest_rejects_xdelta_and_missing_source():
    m=manifest('d0-c0-a0-l0');disc.validate_manifest(m)
    m['artifacts']['xdelta']=record()
    with pytest.raises(ValueError,match='inventory'):disc.validate_manifest(m)
    m=manifest('d0-c0-a0-l0');del m['source']
    with pytest.raises(ValueError,match='source BIN'):disc.validate_manifest(m)
    for key in ('bin','cue','track01','source_track01'):
        m=manifest('d0-c0-a0-l0');del m['artifacts'][key]
        with pytest.raises(ValueError,match='inventory'):disc.validate_manifest(m)


@pytest.fixture
def trees(tmp_path):
    source,accepted,canonical=[tmp_path/n for n in ('source','accepted','canonical')]
    for p in (source,accepted,canonical):p.mkdir()
    changed=set().union(*matrix.GROUP_FILES.values())
    names=changed|{'_boot.bin'}|{f'UNCHANGED{i:02}.BIN' for i in range(87)}
    assert len(names)==98
    for n in names:
        original=('source '+n).encode();restored=('accepted '+n).encode() if n in changed else original
        (source/n).write_bytes(original);(accepted/n).write_bytes(restored)
    return source,accepted,canonical


def populate(ident,source,accepted,canonical):
    s=disc.profile_settings(ident)
    enabled=set().union(*(files for group,files in matrix.GROUP_FILES.items()
       if (s['dates']=='japanese' if group=='dates' else s[group])))
    for p in source.iterdir():
        (canonical/p.name).write_bytes(((accepted if p.name in enabled else source)/p.name).read_bytes())


def test_all_16_profile_oracles_and_unchanged_files(trees):
    source,accepted,canonical=trees
    for ident in matrix.PROFILE_IDS:
        populate(ident,*trees)
        r=matrix.verify_asset_profile(ident,*trees)
        assert r['canonical_assets_verified']==98
        # Mutation outside any group must fail even if enabled assets are right.
        p=canonical/'UNCHANGED00.BIN';p.write_bytes(b'rogue edit')
        with pytest.raises(ValueError,match='enabled/disabled'):matrix.verify_asset_profile(ident,*trees)
    populate('d0-c1-a1-l1',*trees)
    for n in matrix.GROUP_FILES['dates']:assert (canonical/n).read_bytes()==(source/n).read_bytes()
    for n in set(p.name for p in canonical.iterdir())-matrix.GROUP_FILES['dates']:
        assert (canonical/n).read_bytes()==(accepted/n).read_bytes()


def test_each_disabled_group_must_be_retail_and_each_enabled_group_accepted(trees):
    source,accepted,canonical=trees
    for ident in matrix.PROFILE_IDS:
        populate(ident,*trees)
        settings=disc.profile_settings(ident)
        for group,files in matrix.GROUP_FILES.items():
            enabled=settings['dates']=='japanese' if group=='dates' else settings[group]
            n=next(iter(files));p=canonical/n;before=p.read_bytes()
            p.write_bytes(((source if enabled else accepted)/n).read_bytes())
            with pytest.raises(ValueError,match='enabled/disabled'):matrix.verify_asset_profile(ident,*trees)
            p.write_bytes(before)


def test_canonical_inventory_cannot_hide_extra_or_missing_files(trees):
    source,accepted,canonical=trees;populate('d1-c1-a1-l1',*trees)
    (canonical/'unexpected.json').write_text('{}')
    with pytest.raises(ValueError,match='inventory'):matrix.verify_asset_profile('d1-c1-a1-l1',*trees)


def test_browser_cue_expectation_changes_only_operand_and_preserves_bom_case_spacing():
    for bom,ending in itertools.product((b'',b'\xef\xbb\xbf'),(b'\n',b'\r\n')):
        original=bom+ending.join([b'REM fixture',b'  file  "Original.bin" binary',b'  TRACK 01 MODE1/2352',b'    INDEX 01 00:00:00',b''])
        actual=expected_cue_bytes(original,'Snatcher Uncut d0-c1-a1-l1.bin')
        assert actual==original.replace(b'Original.bin',b'Snatcher Uncut d0-c1-a1-l1.bin')
    with pytest.raises(ValueError,match='one original CUE'):expected_cue_bytes(b'no FILE','out.bin')


def test_version_and_no_patch_flags_are_strict_booleans():
    for ident in ('d0-c0-a0-l0','d1-c1-a1-l1'):
        for value in (None,0,1,'false',not (ident=='d0-c0-a0-l0')):
            m=manifest(ident);m['no_patch']=value
            with pytest.raises(ValueError,match='no_patch'):disc.validate_manifest(m)
        m=manifest(ident);del m['no_patch']
        with pytest.raises(ValueError,match='no_patch'):disc.validate_manifest(m)
    for value in (True,False,1.0,2.0,'2'):
        m=manifest('d1-c1-a1-l1');m['version']=value
        with pytest.raises(ValueError,match='version'):disc.validate_manifest(m)
