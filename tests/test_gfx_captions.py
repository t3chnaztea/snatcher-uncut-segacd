"""Approved still-art scope, source guards and exact compressed round trips."""
import copy
import importlib.util
import json
from pathlib import Path
import random
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('m4_captions',ROOT/'tools/m4_captions.py')
art=importlib.util.module_from_spec(spec);spec.loader.exec_module(art)
SOURCE=ROOT/'private/extracted/segacd-usa'

@pytest.fixture
def workspace():
    # Keep all generated assets on HomeLab, including temporary test files.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='m4-still-test-',dir=ROOT/'build') as name:yield Path(name)

def test_still_art_preserves_every_unapproved_resource_and_control(workspace):
    report=art.apply(SOURCE,workspace/'output',workspace/'evidence')
    assert report['status']=='pass'
    assert {r['id']for r in report['rows']}=={'GFX-005','TEXT-034','TEXT-035','TEXT-036'}
    assert set(report['changed_files'])=={'DATA_D0.BIN','DATA_D1.BIN','DATA_F0.BIN'}
    for name in report['changed_files']:
        old=(SOURCE/name).read_bytes();new=(workspace/'output'/name).read_bytes()
        assert len(old)==len(new)
        allowed=report['permitted_spans'][name]
        assert all(a==b or any(s['start']<=i<s['end']for s in allowed)for i,(a,b)in enumerate(zip(old,new)))
        seqs,streams,errors=art.scd_gfx.inventory(new,name)
        assert not errors
        assert seqs==art.scd_gfx.sequences(old)
        approved={s['offset']for r in report['rows']if r['file']==name for s in r['resources']}
        for stream in art.scd_gfx.inventory(old,name)[1]:
            if stream['offset']not in approved:assert art.scd_gfx.stream_bytes(old,stream)==art.scd_gfx.stream_bytes(new,stream)
    for row in report['rows']:
        assert row['palettes_unchanged']and row['animation_graph_unchanged']and row['frame_tables_unchanged']
        for stream in row['resources']:assert stream['encoded_size']<=stream['capacity']
    from PIL import Image
    recipes=json.loads((ROOT/'patches/gfx/captions.json').read_text())['rows']
    newspaper=Image.open(workspace/'evidence/TEXT-035-converted.png')
    pce=art._pce_image(ROOT,next(r for r in recipes if r['id']=='TEXT-035')['pce'])
    assert [sum(newspaper.getpixel((x,y)))<300 for y in range(26,31)for x in range(104,119)]==[sum(pce.getpixel((x,y+8)))<300 for y in range(26,31)for x in range(104,119)]
    assert [sum(newspaper.getpixel((x,y)))<300 for y in range(93,98)for x in range(169,176)]==[sum(pce.getpixel((112+x,34+y)))<300 for y in range(5)for x in range(7)]
    oldpaper=Image.open(workspace/'evidence/TEXT-035-source.png')
    assert newspaper.crop((161,93,168,98)).tobytes()==oldpaper.crop((161,93,168,98)).tobytes()
    # The two source4glyphs locate the changed field independently of the
    # reconstructed preview. A2pxsprite-origin error must not move this field.
    assert oldpaper.crop((169,93,172,98)).tobytes()==oldpaper.crop((173,93,176,98)).tobytes()
    front=next(r for r in report['rows']if r['id']=='TEXT-035')['visual']['foreground_date']
    assert front['local_bbox']==[119,29,126,34] and front['native_bbox']==[169,93,176,98] and front['other_sprite_pixels_unchanged']
    original=Image.open(workspace/'evidence/TEXT-034-source.png');patched=Image.open(workspace/'evidence/TEXT-034-converted.png')
    assert original.crop((144,112,153,132)).tobytes()==patched.crop((182,112,191,132)).tobytes()
    original=Image.open(workspace/'evidence/TEXT-036-source.png');patched=Image.open(workspace/'evidence/TEXT-036-converted.png')
    assert original.crop((128,318,137,332)).tobytes()==patched.crop((160,318,169,332)).tobytes()
    original=Image.open(workspace/'evidence/GFX-005-source.png');patched=Image.open(workspace/'evidence/GFX-005-converted.png')
    pce=art._pce_image(ROOT,next(r for r in recipes if r['id']=='GFX-005')['pce'])
    def error(image):return sum((a-b)**2 for y in range(60,97)for x in range(88,126)for a,b in zip(image.getpixel((x,y)),pce.getpixel((x,y))))
    # Existing Sega palettes and protected room pixels intentionally prevent
    # RGB identity. The restored pose must reduce this source error by75%.
    assert error(patched)<error(original)/4
    city=next(r for r in report['rows']if r['id']=='TEXT-036')
    assert len(city['visual']['allocations'])==1
    assert city['visual']['allocations'][0]['from_tile']==572
    # Shared blanks remain shared; only one approved cell gets the cloned tile.
    assert city['visual']['allocations'][0]['cell']==[21,41]
    assert next(r for r in report['rows']if r['id']=='TEXT-034')['visual']['changed_bbox']==[181,113,192,130]
    assert next(r for r in report['rows']if r['id']=='TEXT-035')['visual']['changed_bbox']==[112,26,119,31]

def test_hash_and_consumer_guards_reject_before_any_file_write(workspace,monkeypatch):
    original=json.loads((ROOT/'patches/gfx/captions.json').read_text());fake=workspace/'fake';(fake/'patches/gfx').mkdir(parents=True)
    cases=[]
    bad=copy.deepcopy(original);bad['rows'][0]['source_sha1']='0'*40;cases.append(bad)
    bad=copy.deepcopy(original);bad['rows'][0]['pce']['block_sha1']='0'*40;cases.append(bad)
    bad=copy.deepcopy(original);bad['rows'][0]['resources'][0]['decoded_sha1']='0'*40;cases.append(bad)
    bad=copy.deepcopy(original);bad['rows'][0]['resources'][0]['references']=[];cases.append(bad)
    monkeypatch.setattr(art,'ROOT',fake)
    for n,bad in enumerate(cases):
        (fake/'patches/gfx/captions.json').write_text(json.dumps(bad));output=workspace/f'output-{n}'
        with pytest.raises(ValueError):art.apply(SOURCE,output,workspace/'evidence')
        assert not output.exists()

def test_optimal_codec_roundtrip_and_extent_efficiency():
    rng=random.Random(1729)
    for data in [b'\0'*8192,bytes(range(256))*3,bytes(rng.randrange(256)for _ in range(400)),b'abc'*34+b'z'*71+b'abc'*34,bytes(range(34))*3]:
        encoded=art.optimal_encode(data)
        decoded,end=art.scd_gfx.decode(encoded,0,len(data))
        assert decoded==data and end==len(encoded)
        assert len(encoded)<=len(art.scd_gfx.encode(data))
