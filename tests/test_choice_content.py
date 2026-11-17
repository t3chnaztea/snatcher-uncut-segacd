"""Advanced date/caption/text choices retain the complete guarded catalogue."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import m4_captions
import patch_choices
import scd_art
import scd_text


@pytest.fixture(scope='module')
def evidence():
    path = ROOT / 'build/m9-content/choice-tests'
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.parametrize('mask', range(64))
def test_database_and_each_identity_text(mask, evidence):
    # Five identity bits are independent of the chronology bit.
    selection = patch_choices.Selection((mask & 1) | ((mask >> 1) << 4))
    output = evidence / selection.id / 'text'
    scd_text.apply_patches(ROOT / 'patches/text', output=output, profile=selection)
    report = scd_text.verify(ROOT / 'patches/text', output=output, profile=selection)
    assert report['catalogue_rows'] == 31
    assert report['approved_rows'] == 26 * (mask & 1) + (mask >> 1).bit_count()
    assert {edit['row'] for edit in report['edits']} == selection.text_rows
    # Every unselected identity's fixed-width pool and speaker records are retail.
    records = scd_text.patch_records(ROOT / 'patches/text')
    for row in records:
        for edit in row['edits']:
            start, count = edit['_offset'], len(edit['_bytes'])
            actual = (output / edit['file']).read_bytes()[start:start+count]
            source = (scd_text.SOURCE / edit['file']).read_bytes()[start:start+count]
            assert actual == (edit['_bytes'] if row['id'] in selection.text_rows else source)
    (output.parent / 'text-verification.json').write_text(json.dumps(report, indent=2) + '\n')


@pytest.mark.parametrize('mask', range(16))
def test_each_caption_and_lisa_composes_only_its_approved_spans(mask, evidence):
    selection = patch_choices.Selection(((mask & 7) << 1) | ((mask >> 3) << 10))
    output = evidence / selection.id / 'captions'
    report = m4_captions.apply(scd_art.SOURCE, output, output.parent / 'caption-evidence', profile=selection)
    assert report['catalogue_rows'] == 4
    assert {row['id'] for row in report['rows']} == selection.art_rows
    rows = json.loads((ROOT / 'patches/gfx/captions.json').read_text())['rows']
    for name in {row['file'] for row in rows}:
        source = (scd_art.SOURCE / name).read_bytes()
        expected = bytearray(source)
        occupied = set()
        for row in rows:
            if row['file'] != name or row['id'] not in selection.art_rows:
                continue
            data, _, _, _ = m4_captions._row_patch(scd_art.SOURCE, row, scd_art.SOURCE.parents[2])
            changes = {i for i, (a, b) in enumerate(zip(source, data)) if a != b}
            assert not occupied & changes
            occupied |= changes
            for i in changes:
                expected[i] = data[i]
        actual = (output / name).read_bytes() if (output / name).exists() else source
        assert actual == expected
        assert len(actual) == len(source)


def test_advanced_noop_keeps_all_98_source_files(evidence):
    output = evidence / 'noop-assets'
    report = scd_art.apply(output=output, evidence=evidence / 'noop-evidence', profile='x000')
    assert report['source_files'] == 98
    assert not any(row['changed_bytes'] for row in report['files'])
    for name in scd_art.source_inventory(scd_art.SOURCE):
        assert (output / name).read_bytes() == (scd_art.SOURCE / name).read_bytes()


def _pose_pixels(data, group):
    """Read callback frames and VRAM independently of conversion allocations."""
    import struct
    import scd_gfx as gfx
    sequence = gfx.sequences(data)[2]
    vram = bytearray(65536)
    colors = gfx.palette(data, sequence['commands'])[0]
    for resource in gfx.resources(data, [sequence])[0]:
        raw = gfx.decode(data, resource['offset']+2, resource['decoded_size'])[0]
        start = resource['references'][0]['vram']
        vram[start:start+len(raw)] = raw
    for command in sequence['commands']:
        if command['op'] != 2:
            continue
        for offset in range(command['body'], command['body']+command['length'], 12):
            if data[offset] != group:
                continue
            ox, oy = struct.unpack_from('>hh', data, offset+2)
            table = gfx.u32(data, offset+6)-gfx.BASE
            script = offset+12+struct.unpack_from('>h', data, offset+10)[0]
            poses = []
            for step in range(5):
                token = data[script+step*4]
                if token == 0x81:
                    break
                if token >= 128:
                    continue
                frame = table+struct.unpack_from('>h', data, table+token*2)[0]
                pixels = {}
                entries = []
                for n in range(gfx.u16(data, frame)+1):
                    at = frame+2+n*8
                    dy, size, tile, dx = struct.unpack_from('>hHHh', data, at)
                    width, height = ((size>>10)&3)+1, ((size>>8)&3)+1
                    for y in range(height*8):
                        for x in range(width*8):
                            xx = width*8-1-x if tile&0x800 else x
                            yy = height*8-1-y if tile&0x1000 else y
                            index = ((tile&2047)+(xx//8)*height+yy//8)*32+(yy%8)*4+(xx%8)//2
                            value = (vram[index]>>(0 if xx&1 else 4))&15
                            if value:
                                pixels[(ox+dx+x,oy+dy+y)] = (colors[((tile>>13)&3)*16+value], bool(tile&0x8000))
                    # Sprite dimensions/order and screen coordinates are controls,
                    # separate from its allocated tile index.
                    entries.append((ox+dx,oy+dy,size,tile&0xf800))
                poses.append((entries,pixels))
            return poses
    raise AssertionError('Missing native guest group')


@pytest.mark.parametrize('value', range(64))
def test_cameo_family_preserves_each_selected_or_stock_pose(value, evidence):
    import shutil
    import m4_animation
    import scd_gfx
    selection = patch_choices.family_selection('cameos', value)
    folder = ROOT / 'build/m9-content/families' / f'cameos-{value:02x}'
    assets = folder / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    for name in scd_art.source_inventory(scd_art.SOURCE):
        shutil.copyfile(scd_art.SOURCE / name, assets / name)
    report = m4_animation.apply(scd_art.SOURCE, assets, folder / 'animation', profile=selection)
    scd_text.apply_patches(ROOT / 'patches/text', output=assets, profile=selection)
    scd_text.verify(ROOT / 'patches/text', output=assets, profile=selection)
    if value:
        assert report['rows'][0]['selected_groups'] == sorted(selection.cameo_groups)
    actual = (assets / 'DATA_O0.BIN').read_bytes()
    original = (scd_art.SOURCE / 'DATA_O0.BIN').read_bytes()
    accepted = (ROOT / 'build/m5/assets/DATA_O0.BIN').read_bytes()
    if value == 0:
        assert actual == original
    if value == 63:
        assert actual == accepted
    assert len(actual) == len(original)
    assert not scd_gfx.inventory(actual, 'DATA_O0.BIN')[2]
    assert not scd_gfx.frame_inventory(actual, scd_gfx.sequences(actual))['errors']
    for key, group in {'mask_rider':18,'cornelius':21,'alyen':19,'miss_money':20,'h2o_gulliver':17}.items():
        expected = accepted if key in selection.cameo_groups else original
        assert _pose_pixels(actual, group) == _pose_pixels(expected, group), (value,key)
    changed = {name for name in scd_art.source_inventory(scd_art.SOURCE)
               if (assets/name).read_bytes() != (scd_art.SOURCE/name).read_bytes()}
    assert changed == selection.changed_files
    proof = dict(status='pass', selection=selection.id, variant=value,
                 exact_default_or_source=value in (0,63),
                 all_five_front_and_rear_poses_match_source_or_accepted=True,
                 catalogue_and_provenance_checked=True,
                 changed_files=sorted(changed), animation=report,
                 asset_sha256={name:hashlib.sha256((assets/name).read_bytes()).hexdigest()
                               for name in scd_art.source_inventory(scd_art.SOURCE)})
    (folder/'verification.json').write_text(json.dumps(proof,indent=2)+'\n')
