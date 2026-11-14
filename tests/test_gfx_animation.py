"""M4 animation recipes use staged sources and preserve unrelated native assets."""
import importlib.util,json,sys,tempfile
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import m4_animation as m

@pytest.fixture(scope='module')
def converted():
 with tempfile.TemporaryDirectory(prefix='m4-animation-test-',dir=ROOT/'build') as work:
  out=Path(work)/'output';evidence=Path(work)/'evidence'
  report=m.apply(m.s.SOURCE,out,evidence)
  yield out,report

def resource_at(data,offset):return m.s.decode(data,offset+2,m.s.u16(data,offset))[0]
def transfer_resources(data,seq):
 return {r['record']:resource_at(data,s['offset']) for s in m.s.resources(data,[seq])[0] for r in s['references']}

def test_complete_animation_and_unchanged_consumers(converted):
 out,report=converted;assert report['status']=='pass';assert {r['id'] for r in report['rows']}=={'GFX-001','GFX-002'}
 for row in report['rows']:
  data=(out/row['file']).read_bytes();assert not m.s.inventory(data,row['file'])[2];assert not m.s.frame_inventory(data,m.s.sequences(data))['errors']
 dog=next(r for r in report['rows'] if r['id']=='GFX-001');old=(m.s.SOURCE/'DATA_G0.BIN').read_bytes();new=(out/'DATA_G0.BIN').read_bytes()
 assert len(new)==123728 and dog['frame_count']==14 and dog['visible_objects']==5
 assert dog['preserved_control_objects']==[21,58,59,60,61]
 assert dog['color_class_geometry_mismatches']==0 and dog['retained_base_geometry_pixels']==22080
 assert len(m.s.sequences(old))==len(m.s.sequences(new))==49
 for before,after in zip(m.s.sequences(old),m.s.sequences(new)):
  if before['index']==10:continue
  assert transfer_resources(old,before)==transfer_resources(new,after)
 relocation=dog['relocations'][0];a=relocation['old_offset'];b=relocation['new_offset'];n=relocation['length'];assert new[b:b+n]==old[a:a+n]
 assert len(relocation['consumers'])==5
 assert resource_at(old,a)==resource_at(new,b)
 translation=[v for obj in dog['scripts'] for v in obj['translation']]
 assert {'F0','F3','FF','FE'}<={v['opcode'] for v in translation if 'opcode'in v}
 for script in dog['scripts']:
  code=new[script['script']:]
  for i,ins in enumerate(script['translation']):
   if 'frame'in ins:
    if ins['delay']==253:assert code[i*4:i*4+4]==bytes([ins['frame'],1,ins['lower']+1,ins['upper']+1])
    else:assert code[i*4:i*4+4]==bytes([ins['frame'],0])+m.be(ins['delay']+1)
 cameo=next(r for r in report['rows'] if r['id']=='GFX-002');old=(m.s.SOURCE/'DATA_O0.BIN').read_bytes();new=(out/'DATA_O0.BIN').read_bytes()
 assert len(old)==len(new)==75602;assert cameo['architecture_outside_mask_unchanged']
 assert {g['native_group'] for g in cameo['groups']}=={17,18,19,20,21}
 assert new[28956:34660]==old[28956:34660]
 prefix=next(a for a in cameo['allocations'] if a['label']=='retained_dancer_light_prefix')
 assert resource_at(new,prefix['offset'])==resource_at(old,34660)[:5120]
 oldtable=next(t for t in m.s.frame_inventory(old,m.s.sequences(old))['tables'] if t['table']==28956)
 newtable=next(t for t in m.s.frame_inventory(new,m.s.sequences(new))['tables'] if t['table']==28956)
 for idx in list(range(31))+list(range(37,41)):
  assert oldtable['frames'][idx]==newtable['frames'][idx]

def test_story_wait_preserves_text_and_original_audio_order(converted):
 out,report=converted;before=(m.s.SOURCE/'SP25.BIN').read_bytes();after=(out/'SP25.BIN').read_bytes()
 assert len(before)==len(after) and before[0x3800:]==after[0x3800:]
 assert after[1159:1162]==bytes.fromhex('0c0c8b')
 assert after[3211:3218]==bytes.fromhex('250a0064450014')
 assert after[1163:1166]==before[1163:1166]==bytes.fromhex('040187')
 assert not m.scd_script.inspect(after,m.scd_script.dispatch(m.s.SOURCE))['errors']

def test_guards_reject_wrong_sources_rows_and_donor(tmp_path,monkeypatch):
 original=json.loads((ROOT/'patches/gfx/animation.json').read_text());recipe=tmp_path/'patches/gfx';recipe.mkdir(parents=True)
 monkeypatch.setattr(m,'ROOT',tmp_path)
 for mutation in ['source','donor','binding','story_donor','story_source','rows']:
  d=json.loads(json.dumps(original))
  if mutation=='source':d['rows'][0]['source_sha1']='0'*40
  elif mutation=='donor':d['rows'][0]['pce_block_sha1']='0'*40
  elif mutation=='binding':d['rows'][0]['pce_table_record_sha1']='0'*40
  elif mutation=='story_donor':d['rows'][0]['control_edit']['pce_script_module_sha1']='0'*40
  elif mutation=='story_source':d['rows'][0]['control_edit']['source_sha1']='0'*40
  else:d['rows'].pop()
  (recipe/'animation.json').write_text(json.dumps(d))
  with pytest.raises(ValueError):m.apply(m.s.SOURCE,tmp_path/'output',tmp_path/'evidence')
 with pytest.raises(ValueError,match='overwrite'):m.apply(m.s.SOURCE,m.s.SOURCE,tmp_path/'evidence')

def background_fields(data):
 seq=m.s.sequences(data)[2];vram=bytearray(65536)
 for stream in m.s.resources(data,[seq])[0]:
  raw=resource_at(data,stream['offset'])
  for ref in stream['references']:vram[ref['vram']:ref['vram']+len(raw)]=raw
 pixels=[];words=[]
 for y in range(256):
  for x in range(256):
   word=m.s.u16(vram,0xc000+((y//8)*32+x//8)*2);sx=7-x%8 if word&0x800 else x%8;sy=7-y%8 if word&0x1000 else y%8
   packed=vram[(word&2047)*32+sy*4+sx//2];value=packed>>(0 if sx&1 else 4)&15
   pixels.append((((word>>13)&3)*16+value,bool(value),bool(word&0x8000)))
 for pos in range(0xc000,0xc800,2):words.append(m.s.u16(vram,pos))
 return pixels,words

def test_cameo_unmasked_indices_opacity_priority_and_donor_alpha(converted):
 from PIL import Image
 out,report=converted;old=(m.s.SOURCE/'DATA_O0.BIN').read_bytes();new=(out/'DATA_O0.BIN').read_bytes()
 before,oldwords=background_fields(old);after,newwords=background_fields(new)
 mask=Image.open(out.parent/'evidence/cameo-costume-mask.png');selected=mask.tobytes()+bytes(256*32)
 assert all(before[i]==after[i] for i,value in enumerate(selected) if not value)
 for ty in range(32):
  for tx in range(32):
   if not all(selected[(ty*8+y)*256+tx*8+x] for y in range(8) for x in range(8)):
    assert oldwords[ty*32+tx]&0xf800==newwords[ty*32+tx]&0xf800
 user=m.p.user_data(m.p.TRACK);block,row,seq,vram,colors,_=m.pce_scene(user,41,0);cells=m.p.pixels(vram)
 for y in range(224):
  for x in range(256):
   if not selected[y*256+x]:continue
   word=vram[(y//8*64+x//8)*2]|vram[(y//8*64+x//8)*2+1]<<8
   donor=cells[word&4095][(y%8)*8+x%8]
   assert after[y*256+x][1]==bool(donor)
 cameo=next(r for r in report['rows'] if r['id']=='GFX-002')
 assert cameo['outside_mask_global_palette_indices_unchanged']
 assert cameo['outside_mask_opacity_priority_unchanged'] and cameo['inside_mask_donor_opacity_preserved']

def test_cameo_front_opaque_black_is_not_transparent(converted):
 out,report=converted;data=(out/'DATA_O0.BIN').read_bytes();cameo=next(r for r in report['rows'] if r['id']=='GFX-002')
 alloc={a['label']:a['offset'] for a in cameo['allocations']};tiledata=resource_at(data,alloc['front_tiles']);table=alloc['new_frame_table']
 block,row,seq,pvram,colors,_=m.pce_scene(m.p.user_data(m.p.TRACK),41,0)
 cells=m.p.sprite_pixels(pvram);people={o['object']:o for o in m.p.object_initializers(block,59,row['bank'])}
 mdcolors=m.native_palette(data,m.s.sequences(data)[2]);black_checked=0
 for group in cameo['groups']:
  expected=[]
  for obj,frame in group['pce_objects_frames']:
   for entry in m.p.object_frame_entries(block,people[obj]['table'],frame)[1]:
    first=entry['cell']&~1 if entry['width']==2 else entry['cell']
    for cy in range(entry['height']):
     for cx in range(entry['width']):expected.append((cells[first+cy*2+cx],entry['palette']))
  frame_at=table+m.s.u16(data,table+group['new_frame']*2);count=m.s.u16(data,frame_at)+1;assert count==len(expected)
  for n,(values,pal) in enumerate(expected):
   word=m.s.u16(data,frame_at+2+n*8+4);first=word&2047
   for y in range(16):
    for x in range(16):
     tile=first+(x//8)*2+y//8;packed=tiledata[(tile-256)*32+(y%8)*4+(x%8)//2];value=packed>>(0 if x&1 else 4)&15;donor=values[y*16+x]
     assert bool(value)==bool(donor)
     if donor and colors[256+pal*16+donor]==(0,0,0):
      black_checked+=1;assert value and mdcolors[((word>>13)&3)*16+value]==(0,0,0)
 assert black_checked>0
