"""Profile selection must preserve exact accepted or retail group assets."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import m4_captions
import patch_profiles
import scd_art
import scd_text

# Independent file oracle, deliberately not imported from the implementation.
GROUPS={
    'dates': {'SP04.BIN','SP05.BIN','DATA_D0.BIN','DATA_D1.BIN'},
    'cameos': {'DATA_O0.BIN','SP13.BIN','SUBCODE.BIN'},
    'alice': {'DATA_G0.BIN','SP25.BIN'},
    'lisa': {'DATA_F0.BIN'},
}
ALL_IDS=tuple(f'd{d}-c{c}-a{a}-l{l}' for d in (0,1) for c in (0,1) for a in (0,1) for l in (0,1))


@pytest.fixture(scope='module')
def workspace():
    base=ROOT/'build/m8-content';base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='profiles-',dir=base) as tmp:
        yield Path(tmp)


@pytest.mark.parametrize('profile_id',ALL_IDS)
def test_selected_groups_match_independent_accepted_and_source_oracle(profile_id,workspace):
    profile=patch_profiles.get_profile(profile_id)
    output=workspace/profile_id
    report=scd_art.apply(output=output,evidence=workspace/(profile_id+'-evidence'),profile=profile_id)
    names=scd_art.source_inventory(scd_art.SOURCE)
    changed=set().union(*(files for flag,files in GROUPS.items() if getattr(profile,flag)))
    assert set(profile.changed_files)==changed
    assert {r['file'] for r in report['files'] if r['source_sha1']!=r['sha1']}==changed
    assert set(report['approved_rows'])==set(profile.art_rows)
    assert report['catalogue_rows']==6 and report['profile']==profile_id
    for name in names:
        expected=(ROOT/'build/m5/assets'/name) if name in changed else (scd_art.SOURCE/name)
        assert (output/name).read_bytes()==expected.read_bytes(),(profile_id,name)
    # Text verifier independently checks every SP and speaker byte, including disabled rows.
    text_output=workspace/(profile_id+'-text')
    scd_text.apply_patches(ROOT/'patches/text',output=text_output,profile=profile_id)
    checked=scd_text.verify(ROOT/'patches/text',output=text_output,profile=profile_id)
    assert checked['catalogue_rows']==31 and checked['approved_rows']==len(profile.text_rows)
    proof={'profile':profile_id,'canonical_assets':len(names),'changed_files':sorted(changed),
           'source_or_accepted_exact':True,'active_text_rows':checked['approved_rows'],
           'asset_sha256':{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in names}}
    evidence=ROOT/'build/m8-content/profile-oracles';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/(profile_id+'.json')).write_text(json.dumps(proof,indent=2)+'\n')


def test_unknown_profile_is_rejected_before_output(workspace):
    for module,call in [
        (scd_art,lambda out:scd_art.apply(output=out,evidence=out/'evidence',profile='unknown')),
        (scd_art,lambda out:scd_art.verify(output=out,evidence=out/'evidence',profile='unknown')),
        (scd_text,lambda out:scd_text.apply_patches(ROOT/'patches/text',output=out,profile='unknown')),
        (m4_captions,lambda out:m4_captions.apply(scd_art.SOURCE,out,out/'evidence',profile='unknown')),
    ]:
        output=workspace/('bad-'+module.__name__)
        with pytest.raises(ValueError,match='Unknown restoration profile'):call(output)
        assert not output.exists()


def test_inactive_text_rows_still_require_full_catalogue_validation(workspace):
    folder=workspace/'bad-text-catalogue';folder.mkdir()
    patch=json.loads((ROOT/'patches/text/m3.json').read_text())
    inactive=next(row for row in patch['rows'] if row['id']=='TEXT-001')
    inactive['edits'][0]['old_hash']='0'*40
    (folder/'m3.json').write_text(json.dumps(patch))
    output=workspace/'rejected-inactive-text'
    with pytest.raises(ValueError):
        scd_text.apply_patches(folder,output=output,profile='d0-c0-a0-l0')
    assert not output.exists()


def test_inactive_caption_rows_still_require_full_catalogue_validation(workspace,monkeypatch):
    fake=workspace/'bad-caption-catalogue';(fake/'patches/gfx').mkdir(parents=True)
    patch=json.loads((ROOT/'patches/gfx/captions.json').read_text())
    next(row for row in patch['rows'] if row['id']=='TEXT-034')['source_sha1']='0'*40
    (fake/'patches/gfx/captions.json').write_text(json.dumps(patch))
    monkeypatch.setattr(m4_captions,'ROOT',fake)
    output=workspace/'rejected-inactive-caption'
    with pytest.raises(ValueError,match='source hash mismatch'):
        m4_captions.apply(scd_art.SOURCE,output,output/'evidence',profile='d0-c0-a0-l0')
    assert not output.exists()


def test_caption_duplicates_rejected_even_with_all_groups_off(workspace,monkeypatch):
    fake=workspace/'duplicate-caption-catalogue';(fake/'patches/gfx').mkdir(parents=True)
    patch=json.loads((ROOT/'patches/gfx/captions.json').read_text())
    patch['rows'].append(copy.deepcopy(patch['rows'][0]))
    (fake/'patches/gfx/captions.json').write_text(json.dumps(patch))
    monkeypatch.setattr(m4_captions,'ROOT',fake)
    output=workspace/'rejected-duplicate-caption'
    with pytest.raises(ValueError,match='approval inventory mismatch'):
        m4_captions.apply(scd_art.SOURCE,output,output/'evidence',profile='d0-c0-a0-l0')
    assert not output.exists()


def test_profile_ids_select_the_expected_groups():
    for profile_id in ALL_IDS:
        profile=patch_profiles.get_profile(profile_id)
        flags={key:bool(int(token[1])) for key,token in zip(('dates','cameos','alice','lisa'),profile_id.split('-'))}
        assert all(getattr(profile,key)==flag for key,flag in flags.items())
        expected=set().union(*(files for key,files in GROUPS.items() if flags[key]))
        assert set(profile.changed_files)==expected
        assert profile.no_patch==(not any(flags.values()))
