"""Graphics codec integration tests against private disc resources."""
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import scd_gfx as gfx
import pce_gfx as pce


@pytest.fixture(scope='module')
def dumped_graphics():
    work=gfx.ROOT/'build/gfx-test-dump'
    manifest=gfx.dump(output=work)
    return work,manifest


def test_all_graphics_source_files_unchanged(dumped_graphics):
    work,manifest=dumped_graphics
    assert len(manifest['files'])==98
    assert all(not row['errors'] for row in manifest['files'])
    report=gfx.insert(work=work,output=gfx.ROOT/'build/gfx-test-reinsert')
    assert len(report)==98 and all(row['identical'] for row in report)
    assert sum(len(row['streams']) for row in manifest['files'])>=1436


def test_encoder_every_actual_stream(dumped_graphics):
    work,manifest=dumped_graphics
    count=0
    for row in manifest['files']:
        data=(gfx.SOURCE/row['file']).read_bytes()
        for stream in row['streams']:
            raw=gfx.stream_bytes(data,stream)
            assert gfx.sheet_data(gfx.tile_sheet(raw,pixel_format=stream['pixel_format']),len(raw),pixel_format=stream['pixel_format'])==raw
            encoded=gfx.encode(raw)
            assert gfx.decode(encoded,0,len(raw))[0]==raw
            count+=1
    assert count>=1436


def test_genuine_png_edit_encodes_changed_bytes(dumped_graphics):
    work,manifest=dumped_graphics;row=next(r for r in manifest['files'] if r['file']=='DATA_D2.BIN')
    stream=next(s for s in row['streams'] if s['offset']==0x58ac)
    original=(gfx.SOURCE/row['file']).read_bytes();raw,_=gfx.decode(original,stream['offset']+2,stream['decoded_size'])
    image=gfx.tile_sheet(raw)
    for y in range(image.height):
        for x in range(image.width):image.putpixel((x,y),0)
    replacement=gfx.sheet_data(image,len(raw));assert replacement!=raw
    encoded=gfx.encode(replacement);assert len(encoded)<=stream['end']-stream['offset']-2
    changed=bytearray(original);changed[stream['offset']+2:stream['offset']+2+len(encoded)]=encoded
    assert gfx.decode(changed,stream['offset']+2,len(raw))[0]==replacement
    assert changed[:stream['offset']+2]==original[:stream['offset']+2]


def test_bad_png_or_compressed_stream_rejected():
    with pytest.raises(ValueError):gfx.decode(b'\1\x80',0,32)
    with pytest.raises(ValueError):gfx.sheet_data(gfx.tile_sheet(bytes(32)).convert('RGB'),32)


def test_pce_filetable_and_codec():
    data=pce.user_data(pce.TRACK);table=pce.filetable(data)
    assert {k:len(v) for k,v in table.items()}=={'0':6,'1':33,'2':111,'3':6}
    sample=bytes([3,0xaa,0x42,0x82,1,2,0xff])
    assert pce.decode(sample,0)==(bytes([0xaa]*3+[0,0,1,2]),len(sample))


def test_insertion_rejects_source_overwrite(dumped_graphics):
    work,_=dumped_graphics
    with pytest.raises(ValueError,match='overwrite source'):
        gfx.insert(work,gfx.SOURCE)


def test_insertion_rejects_tampered_metadata(dumped_graphics):
    source_work,_=dumped_graphics
    # Private disc bytes independently regenerate the descriptor being checked.
    manifest=json.loads((source_work/'manifest.json').read_text())
    stream=next(row for row in manifest['files'] if row['streams'])['streams'][0]
    stream['end']+=1
    work=gfx.ROOT/'build/gfx-tampered-metadata';work.mkdir(exist_ok=True)
    (work/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='metadata changed'):
        gfx.insert(work,gfx.ROOT/'build/gfx-tampered-output')
    assert not (gfx.ROOT/'build/gfx-tampered-output').exists()


def test_insertion_rejects_missing_source_file(dumped_graphics):
    source_work,_=dumped_graphics
    manifest=json.loads((source_work/'manifest.json').read_text());manifest['files'].pop()
    work=gfx.ROOT/'build/gfx-tampered-inventory';work.mkdir(exist_ok=True)
    (work/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='file inventory changed'):
        gfx.insert(work,gfx.ROOT/'build/gfx-tampered-output')


def test_pce_sprite_bitplane_layout():
    raw=bytearray(128);raw[1]=0x80;raw[32]=1;raw[65]=0x80;raw[96]=1
    pixels=pce.sprite_pixels(raw)[0]
    assert pixels[0]==5
    assert pixels[15]==10
    assert sum(pixels[16:])==0


def test_png_edit_through_full_insert_pipeline(dumped_graphics):
    work,manifest=dumped_graphics
    row=next(r for r in manifest['files'] if r['file']=='DATA_D2.BIN')
    stream=next(s for s in row['streams'] if s['offset']==0x58ac)
    png=work/'DATA_D2'/stream['image'];saved=png.read_bytes()
    replacement=bytes(stream['decoded_size'])
    try:
        gfx.tile_sheet(replacement).save(png)
        report=gfx.insert(work,gfx.ROOT/'build/gfx-edited-reinsert')
        assert [r['file'] for r in report if not r['identical']]==['DATA_D2.BIN']
        rebuilt=(gfx.ROOT/'build/gfx-edited-reinsert/DATA_D2.BIN').read_bytes()
        assert len(rebuilt)==row['size']
        assert gfx.stream_bytes(rebuilt,stream)==replacement
    finally:png.write_bytes(saved)


def test_oversized_compressed_edit_is_rejected(dumped_graphics):
    import random
    work,manifest=dumped_graphics
    row=next(r for r in manifest['files'] if r['file']=='DATA_D2.BIN');stream=next(s for s in row['streams'] if s['offset']==0x58ac)
    png=work/'DATA_D2'/stream['image'];saved=png.read_bytes();replacement=random.Random(57).randbytes(stream['decoded_size'])
    try:
        gfx.tile_sheet(replacement).save(png)
        with pytest.raises(ValueError,match='compressed edit needs'):
            gfx.insert(work,gfx.ROOT/'build/gfx-oversized-output')
        assert not (gfx.ROOT/'build/gfx-oversized-output').exists()
    finally:png.write_bytes(saved)


def test_retained_dog_art_is_included_in_unused_inventory():
    data=(gfx.SOURCE/'DATA_G0.BIN').read_bytes()
    _,streams,errors=gfx.inventory(data,'DATA_G0.BIN')
    assert not errors
    retained=next(s for s in streams if s['offset']==0xd416)
    assert retained['usage']=='unreferenced_candidate'
    assert retained['decoded_size']==1408
    assert retained['end']==0xd794
    assert len(gfx.stream_bytes(data,retained))==44*32
    # Native sprite table addresses exactly those 44 tiles when uploaded at 4000.
    table=0xd9f6
    for frame in range(6):
        at=table+int.from_bytes(data[table+frame*2:table+frame*2+2],'big')
        count=gfx.u16(data,at)+1
        for i in range(count):
            word=gfx.u16(data,at+2+i*8+4)
            assert 0x200<=word&0x7ff<0x22c


def test_pce_native_object_banks_and_black_palette():
    result=pce.render_objects(pce.TRACK,35,0x195,pce.ROOT/'build/gfx-test-pce-dog.png',
                              {16:0,17:3,18:5,19:7,20:9},32)
    assert not result['errors']
    assert len(result['objects'])==6
    assert result['objects'][0]['script']==0xcd3c
    assert result['objects'][0]['table']==0xc925
    from PIL import Image
    with Image.open(pce.ROOT/'build/gfx-test-pce-dog.png') as image:
        assert image.getpixel((0,0))==(0,0,0)
        assert image.getpixel((0,70))==(0,0,0)
    data=pce.user_data(pce.TRACK);row=pce.filetable(data)['2'][41]
    block=data[row['rec']*2048:(row['rec']+row['sectors'])*2048]
    first=pce.object_initializers(block,0x3b,row['bank'])[0]
    assert first['table']==0x5f4f
    assert first['script']==0x6177
    assert block[first['script']]==0xf3


def test_bounded_resource_coverage_audit(dumped_graphics):
    work,_=dumped_graphics
    report=gfx.audit(work,gfx.ROOT/'build/gfx-test-coverage.json')
    assert not report['issues']
    assert report['source_files']==98
    assert report['counts']['resource_pngs']>=1675
    assert report['counts']['sprite_frame_tables']==467
    assert report['counts']['sprite_frame_definitions']==5595
    assert report['counts']['native_boot']==4
    assert report['counts']['native_font']==1


def test_pce_native_graphics_program_universe():
    track=pce.user_data(pce.TRACK);table=pce.filetable(track);programs=displays=references=0
    for index,row in enumerate(table['2']):
        if index==1:continue  # rec750: resident item close-ups, a different layout.
        block=track[row['rec']*2048:(row['rec']+row['sectors'])*2048]
        programs+=len(pce.graphics_programs(block))
        native=pce.program_display_lists(block,row['bank']);displays+=len(native)
        for display in native:
            _,streams=pce.build_vram(block,display['records']);references+=len(streams)
    assert programs==407
    assert displays==401
    assert references==2242
