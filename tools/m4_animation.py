#!/usr/bin/env python3
"""Source-derived M4 dog and cameo conversions, with fixed layout and guards."""
import argparse,hashlib,json,struct
from pathlib import Path
from PIL import Image,ImageFilter
import scd_gfx as s,pce_gfx as p,scd_script
from m4_captions import optimal_encode
from patch_profiles import get_profile
ROOT=Path(__file__).resolve().parents[1]

def sha(b):return hashlib.sha1(b).hexdigest()
def be(n):return int(n).to_bytes(2,'big',signed=n<0)
def ptr(n):return (s.BASE+n).to_bytes(4,'big')
def native_palette(data,seq):return s.palette(data,seq['commands'])[0]
def pce_scene(user,index,program):
 row=p.filetable(user)['2'][index];b=user[row['rec']*2048:(row['rec']+row['sectors'])*2048]
 seq=next(x for x in p.graphics_programs(b) if x['index']==program)
 dl=next(x for x in p.program_display_lists(b,row['bank']) if x['program']==program)
 vram,streams=p.build_vram(b,dl['records']);colors=[(0,0,0)]*512
 c=next(x for x in seq['commands'] if x['opcode']==0)
 pals=[x for x in p.palettes(b,row['bank']) if c['body']<=x['record']<c['offset']+c['length']]
 for pal in pals:colors[pal['vce']:pal['vce']+len(pal['colors'])]=pal['colors']
 return b,row,seq,vram,colors,streams

class Tiles:
 def __init__(self,colors,start=256):self.colors=colors;self.start=start;self.raw=bytearray();self.lookup={};self.errors=[]
 def indexed(self,rgb,opaque,palettes=(1,2,3)):
  options=[]
  for pal in palettes:
   cache={};inds=[];cost=0
   for color,alpha in zip(rgb,opaque):
    if not alpha:inds.append(0);continue
    if color not in cache:cache[color]=min(range(1,16),key=lambda k:sum((color[z]-self.colors[pal*16+k][z])**2 for z in range(3)))
    k=cache[color];inds.append(k);cost+=sum((color[z]-self.colors[pal*16+k][z])**2 for z in range(3))
   options.append((cost,pal,inds))
  cost,pal,indices=min(options);self.errors.append(cost);return pal,indices
 def cell(self,rgb,opaque,width=8,height=8):
  pal,ix=self.indexed(rgb,opaque);raw=bytearray()
  for tx in range(width//8):
   for ty in range(height//8):
    for y in range(8):
     for x in range(0,8,2):raw.append(ix[(ty*8+y)*width+tx*8+x]<<4|ix[(ty*8+y)*width+tx*8+x+1])
  key=bytes(raw)
  if key not in self.lookup:self.lookup[key]=self.start+len(self.raw)//32;self.raw.extend(key)
  return self.lookup[key]|pal<<13
 def bg(self,image):
  out=bytearray(2048)
  for y in range(28):
   for x in range(32):
    rgb=[image.getpixel((x*8+xx,y*8+yy)) for yy in range(8) for xx in range(8)]
    if not any(rgb):word=0
    else:word=self.cell(rgb,[c!=(0,0,0) for c in rgb])
    out[(y*32+x)*2:(y*32+x)*2+2]=be(word)
  return bytes(out)
 def frame(self,b,table,frame,vram,colors,x=0,y=0):
  cells=p.sprite_pixels(vram);_,entries=p.object_frame_entries(b,table,frame);out=[]
  for e in entries:
   first=e['cell']&~1 if e['width']==2 else e['cell']
   for cy in range(e['height']):
    for cx in range(e['width']):
     vals=cells[first+cy*2+cx];rgb=[colors[256+e['palette']*16+v] for v in vals];tile=self.cell(rgb,[bool(v) for v in vals],16,16)
     # Native PCE cell flips apply to the whole sprite. These frames have no
     # flagged cell flips; reject rather than silently transpose unknown art.
     assert not(e['size']&0xc0)
     out.append((y+e['y']+cy*16,x+e['x']+cx*16,tile,0x500))
  assert len(out)<=80
  return be(len(out)-1)+b''.join(be(dy)+be(size)+be(tile)+be(dx) for dy,dx,tile,size in out)

def frame_table(frames):
 out=bytearray(2*len(frames))
 for i,f in enumerate(frames):out[i*2:i*2+2]=be(len(out));out.extend(f)
 return bytes(out)
def resource(raw):return be(len(raw))+optimal_encode(bytes(raw))
def spans(old,new):
 out=[];start=None
 for i,(a,b) in enumerate(zip(old,new)):
  if a!=b and start is None:start=i
  if a==b and start is not None:out.append(dict(offset=start,length=i-start,old_sha1=sha(old[start:i]),new_sha1=sha(new[start:i])));start=None
 if start is not None:out.append(dict(offset=start,length=len(old)-start,old_sha1=sha(old[start:]),new_sha1=sha(new[start:len(old)])))
 if len(new)>len(old):out.append(dict(offset=len(old),length=len(new)-len(old),old_sha1=sha(b''),new_sha1=sha(new[len(old):]),append=True))
 return out
class Region:
 def __init__(self,data,start,end):self.data=data;self.pos=start;self.start=start;self.end=end;self.allocations=[]
 def add(self,label,data):
  if self.pos&1:self.pos+=1
  pos=self.pos
  if pos+len(data)>self.end:raise ValueError(f'{label}: region needs {pos+len(data)-self.start}, capacity {self.end-self.start}')
  self.data[pos:pos+len(data)]=data;self.pos+=len(data);self.allocations.append(dict(label=label,offset=pos,length=len(data),sha1=sha(data)));return pos

def dog(old,user,evidence):
 b,row,seq,vram,colors,streams=pce_scene(user,35,1);mdseq=s.sequences(old)[10];mdcolors=native_palette(old,mdseq)
 # The static source body/background is identical to the PCE background's
 # pixel-color equivalence classes on all184x120 pixels. Keep its tile data.
 bgraw=s.decode(old,49844,s.u16(old,49842))[0]
 bgmap=s.decode(old,55190,s.u16(old,55188))[0]
 original_vram=bytearray(65536);original_vram[0x2000:0x2000+len(bgraw)]=bgraw;original_vram[0xc000:0xc800]=bgmap
 sourcebg=s.compose(original_vram,mdcolors);pcebg=p.screen(vram,colors)
 pairs={}
 for y in range(16,136):
  for x in range(40,224):
   color=pcebg.getpixel((x,y));native=sourcebg.getpixel((x,y))
   if color in pairs and pairs[color]!=native:raise ValueError('Dog base geometry/color-class correspondence changed')
   pairs[color]=native
 # PCE sprite palette0/1 equal MD palette1/2 except opaque-black slot12.
 # The two new black entries alter only five original corpse pixels.
 data=bytearray(old)
 palette_changes=[]
 for pal in (1,2):
  at=49746+(pal*16+12-16)*2;palette_changes.append(dict(offset=at,old=old[at:at+2].hex(),new='0000'));data[at:at+2]=b'\0\0'
 mdcolors[28]=mdcolors[44]=(0,0,0)
 tiles=Tiles(mdcolors,256+len(bgraw)//32);cells=p.sprite_pixels(vram);frames=[]
 for frame in range(14):
  _,entries=p.object_frame_entries(b,51493,frame);parts=[]
  for ent in entries:
   first=ent['cell']&~1 if ent['width']==2 else ent['cell']
   assert ent['palette'] in (0,1) and not(ent['size']&0xc0)
   for cy in range(ent['height']):
    for cx in range(ent['width']):
     values=cells[first+cy*2+cx];assert all(not value or colors[256+ent['palette']*16+value]==mdcolors[(ent['palette']+1)*16+value] for value in values);raw=bytearray()
     for tx in range(2):
      for ty in range(2):
       for yy in range(8):
        for xx in range(0,8,2):raw.append(values[(ty*8+yy)*16+tx*8+xx]<<4|values[(ty*8+yy)*16+tx*8+xx+1])
     raw=bytes(raw)
     if raw not in tiles.lookup:tiles.lookup[raw]=tiles.start+len(tiles.raw)//32;tiles.raw.extend(raw)
     tile=tiles.lookup[raw]|((ent['palette']+1)<<13);parts.append((ent['y']+cy*16,ent['x']+cx*16,tile))
  frames.append(be(len(parts)-1)+b''.join(be(y)+be(0x500)+be(tile)+be(x) for y,x,tile in parts))
 table=frame_table(frames)
 # Reclaimed approved static-dog region and the same disc file's free extent.
 # Final exact size is reported for lead ISO guards; original LBAs remain.
 assert [i for i in range(len(old)-3) if old[i:i+4]==ptr(49746)]==[8896]
 data.extend(b'\0'*(124928-len(data)))
 arena=Region(data,49842,55188);tail=Region(data,len(old),124928)
 reloc_start,reloc_end=26350,26965
 encoded=old[reloc_start:reloc_end];copy=arena.add('unchanged-map-relocation',encoded)
 tileat=arena.add('retained-background-reencoded',resource(bgraw))
 spriteat=tail.add('converted-dog-sprites',resource(tiles.raw))
 # Small metadata can use the former dog frame-table extent.
 tabat=reloc_start+172;assert tabat+len(table)<=reloc_end;data[tabat:tabat+len(table)]=table
 scripts=[];inits=[];scriptpos=mdseq['offset']
 for obj in p.object_initializers(b,430,row['bank']):
  if obj['object']>20:continue
  start=obj['script'];code=bytearray();at=start;translated=[]
  while True:
   op,delay,lo,hi=b[at:at+4]
   if op<128:code.extend(bytes([op,1,lo+1,hi+1]) if delay==0xfd else bytes([op,0])+be(delay+1));translated.append(dict(pce_offset=at,frame=op,delay=delay,lower=lo,upper=hi));at+=4
   elif op==0xfe:code.extend(bytes.fromhex('81000000'));translated.append(dict(pce_offset=at,opcode='FE',md='81'));break
   elif op==0xf0:code.extend(bytes.fromhex('98000000'));translated.append(dict(pce_offset=at,opcode='F0',md='98'));at+=4
   elif op==0xf3:code.extend(bytes.fromhex('93000000'));translated.append(dict(pce_offset=at,opcode='F3',md='93'));at+=4
   elif op==0xff:code.extend(bytes.fromhex('80000000'));translated.append(dict(pce_offset=at,opcode='FF',md='80'));break
   else:raise ValueError(f'Unknown PCE dog animation opcode {op:02x}')
  if scriptpos+len(code)<=mdseq['offset']+106:scriptat=scriptpos;data[scriptat:scriptat+len(code)]=code;scriptpos+=len(code)
  else:
   scriptat=tabat+len(table);assert scriptat+len(code)<=reloc_end;data[scriptat:scriptat+len(code)]=code
  scripts.append(dict(object=obj['object'],pce_script=start,script=scriptat,translation=translated,code_sha1=sha(code)))
  inits.append((obj['object'],0,obj['x'],obj['y']-32,tabat,scriptat))
 for c in mdseq['commands']:
  if c['op']==2:
   for at in range(c['body'],c['body']+c['length'],12):inits.append((old[at],old[at+1],struct.unpack_from('>h',old,at+2)[0],struct.unpack_from('>h',old,at+4)[0],s.u32(old,at+6)-s.BASE,at+12+struct.unpack_from('>h',old,at+10)[0]))
 program=bytearray(old[mdseq['offset']:mdseq['offset']+12]);transfers=ptr(tileat)+be(0)+be(0x2000)+ptr(spriteat)+be(0)+be((256+len(bgraw)//32)*32)+ptr(26208)+be(0)+be(0xe000)+ptr(55188)+be(0)+be(0xc000)+b'\xff\xff'
 program.extend(bytes([1,len(transfers)])+transfers);program.extend(bytes([2,12*len(inits)]))
 for obj,flags,x,y,tab,script in inits:
  at=reloc_start+len(program);program.extend(bytes([obj,flags])+be(x)+be(y)+ptr(tab)+be(script-(at+12)))
 program.append(255);assert len(program)<=172;data[reloc_start:reloc_start+len(program)]=program
 tablebase=s.u32(old,4)-s.BASE;relative=reloc_start-tablebase;assert 0<relative<32768;data[tablebase+20:tablebase+22]=be(relative)
 consumers=[]
 for sq in s.sequences(old):
  for c in sq['commands']:
   if c['op']!=1:continue
   for at in range(c['body'],c['body']+c['length']-7,8):
    if s.u32(old,at)&0xffffff==s.BASE+reloc_start:data[at:at+4]=ptr(copy);consumers.append(dict(program=sq['index'],record=at,vram=s.u16(old,at+6)))
 assert len(consumers)==4
 # Animation draw-list root286 also consumes this map. Verify complete raw
 # pointer inventory, not only graphics-program transfer descriptors.
 assert old[288:292]==ptr(reloc_start);data[288:292]=ptr(copy);consumers.append(dict(kind='animation_draw',draw_root=286,record=288,vram=49152))
 rawhits=[i for i in range(len(old)-3) if old[i:i+4]==ptr(reloc_start)]
 assert rawhits==sorted(c['record'] for c in consumers)
 assert sha(data[copy:copy+len(encoded)])==sha(encoded)
 assert s.decode(data,copy+2,s.u16(data,copy))[0]==s.decode(old,reloc_start+2,s.u16(old,reloc_start))[0]
 assert len(s.sequences(data))==len(s.sequences(old))
 sourcebg.save(evidence/'dog-retained-source-background.png');pcebg.save(evidence/'dog-pce-background.png')
 end=max(len(old),tail.pos);data=data[:end]
 return bytes(data),dict(row='GFX-001',pce_block_sha1=sha(b),pce_record=row['rec'],retained_base_geometry_pixels=184*120,color_class_geometry_mismatches=0,palette_changes=palette_changes,palette_source_pointer_hits=[8896],palette_modified_background_pixels=[[120,40],[84,48],[81,64],[80,65],[80,66]],bg_encoded_old_sha1=sha(old[49842:54293]),bg_encoded_new_sha1=sha(data[tileat:tileat+4260]),bg_decoded_sha1=sha(bgraw),bg_tiles=len(bgraw)//32,all_tiles=(len(bgraw)+len(tiles.raw))//32,frame_count=14,visible_objects=5,sprite_color_rgb_error=0,display_duration_adjustment=1,preserved_control_objects=[21,58,59,60,61],allocations=arena.allocations+tail.allocations,program=dict(old_offset=mdseq['offset'],new_offset=reloc_start,length=len(program),signed_relative=relative),relocations=[dict(old_offset=reloc_start,new_offset=copy,length=len(encoded),encoded_sha1=sha(encoded),decoded_sha1=sha(s.decode(old,reloc_start+2,s.u16(old,reloc_start))[0]),consumers=consumers)],scripts=scripts)

CAMEO_GROUPS={'mask_rider':18,'cornelius':21,'alyen':19,'miss_money':20,'h2o_gulliver':17}
CAMEO_FRAMES={18:(31,),21:(32,),19:(35,),20:(33,36),17:(34,)}

def cameo(old,user,evidence,groups=None,background=True):
 # The wide scene contains additional non-interactive patrons. Its approved
 # union mask is separate from the five explicitly bound portrait callbacks.
 chosen=frozenset(CAMEO_GROUPS) if groups is None else frozenset(groups)
 if not chosen<=CAMEO_GROUPS.keys() or type(background) is not bool:raise ValueError('Invalid cameo choices')
 native_groups={CAMEO_GROUPS[key] for key in chosen}
 complete=background and len(chosen)==5
 if not chosen and not background:
  return old,dict(row='GFX-002',selected_groups=[],bar_background=False,unchanged=True)
 b,row,seq,vram,colors,streams=pce_scene(user,41,0);mdseq=s.sequences(old)[2];mdcolors=native_palette(old,mdseq)
 oldv=bytearray(65536)
 for stream in s.resources(old,[mdseq])[0]:
  raw=s.decode(old,stream['offset']+2,stream['decoded_size'])[0];at=stream['references'][0]['vram'];oldv[at:at+len(raw)]=raw
 base=s.compose(oldv,mdcolors);pcebase=p.screen(vram,colors)
 # Replace only costume silhouettes, preserving architecture, floor and all
 # original dancer/light animation data. Blue costume masks from both staged
 # images include outlines; a four-pixel guard covers their edge pixels.
 mask=Image.new('L',base.size)
 for y in range(24,128):
  for x in range(32,224):
   oldc=base.getpixel((x,y));newc=pcebase.getpixel((x,y))
   blue=lambda c:c[2]>c[0]+10 and c[2]>c[1]+10
   if blue(oldc) or blue(newc):mask.putpixel((x,y),255)
 mask=mask.filter(ImageFilter.MaxFilter(9))
 for y in range(224):
  for x in range(256):
   if not(32<=x<224 and 24<=y<128) or (88<=x<104 and 40<=y<56) or (176<=x<192 and 40<=y<56):mask.putpixel((x,y),0)
 if not background:mask=Image.new('L',base.size)
 base.paste(pcebase,(0,0),mask)
 bg=Tiles(mdcolors,1088);mapping=bytearray(2048);pce_cells=p.pixels(vram)
 # Preserve native palette indices and opacity outside the fixed costume
 # mask. RGB equivalence alone loses opaque black and palette-event behavior.
 for ty in range(32):
  for tx in range(32):
   pos=(ty*32+tx)*2;word=s.u16(oldv,0xc000+pos);pal=(word>>13)&3
   oldtile=word&2047;oldraw=oldv[oldtile*32:oldtile*32+32];flags=word&0xf800
   selected=[bool(mask.getpixel((tx*8+x,ty*8+y))) if ty<28 else False for y in range(8) for x in range(8)]
   if not any(selected):raw=bytes(oldraw)
   else:
    original=[];rgb=[];opaque=[]
    for yy in range(8):
     for xx in range(8):
      sx=7-xx if word&0x800 else xx;sy=7-yy if word&0x1000 else yy
      packed=oldraw[sy*4+sx//2];original.append(packed>>(0 if sx&1 else 4)&15)
      x=tx*8+xx;y=ty*8+yy;pword=vram[(y//8*64+x//8)*2]|vram[(y//8*64+x//8)*2+1]<<8
      value=pce_cells[pword&4095][(y%8)*8+x%8]
      rgb.append(colors[(pword>>12)*16+value]);opaque.append(bool(value))
    if all(selected):
     pal,indices=bg.indexed(rgb,opaque);flags=(flags&0x9fff)|(pal<<13)
    else:
     _,converted=bg.indexed(rgb,opaque,palettes=(pal,));indices=[converted[i] if selected[i] else original[i] for i in range(64)]
    oriented=[0]*64
    for yy in range(8):
     for xx in range(8):
      sx=7-xx if flags&0x800 else xx;sy=7-yy if flags&0x1000 else yy;oriented[sy*8+sx]=indices[yy*8+xx]
    raw=bytes(oriented[i]<<4|oriented[i+1] for i in range(0,64,2))
   if raw not in bg.lookup:bg.lookup[raw]=bg.start+len(bg.raw)//32;bg.raw.extend(raw)
   mapping[pos:pos+2]=be(bg.lookup[raw]|flags)
 mapping=bytes(mapping);assert bg.start+len(bg.raw)//32<=1536
 people={o['object']:o for o in p.object_initializers(b,59,row['bank'])}
 tiles=Tiles(mdcolors,256);frames=[];groups=[]
 plans=[('Mask Rider',18,[(19,11)]),('Cornelius',21,[(18,9)]),('Miss Money',20,[(22,17)]),('H2O / Gulliver',17,[(20,13),(23,19)]),('Alyen',19,[(21,15)]),('Miss Money rear',20,[(22,16)])]
 frame_mapping={}
 for oldframe,(label,group,pairs) in zip((31,32,33,34,35,36),plans):
  if group not in native_groups:continue
  frame_mapping[oldframe]=len(frames)
  parts=[]
  for obj,frame in pairs:
   o=people[obj];encoded=tiles.frame(b,o['table'],frame,vram,colors,o['x'],o['y']-32)
   count=s.u16(encoded,0)+1;parts.extend(encoded[2+i*8:10+i*8] for i in range(count))
  frames.append(be(len(parts)-1)+b''.join(parts));groups.append(dict(identity=label,native_group=group,pce_objects_frames=pairs,new_frame=len(frames)-1))
 assert tiles.start+len(tiles.raw)//32<=512
 prefix=s.decode(old,34662,s.u16(old,34660))[0][:5120]
 retained_tiles=set();stock_tail=b''
 if not complete:
  # Keep exact native tile indices for every disabled portrait. The unchanged
  # original frame table remains valid. Selected portraits use free tiles256+.
  original_frames=next(t for t in s.frame_inventory(old,s.sequences(old))['tables'] if t['table']==28956)['frames']
  for group,indices in CAMEO_FRAMES.items():
   if group in native_groups:continue
   for index in indices:
    for entry in original_frames[index]['sprites']:
     count=(((entry['size']>>10)&3)+1)*(((entry['size']>>8)&3)+1)
     retained_tiles.update(range(entry['tile']&2047,(entry['tile']&2047)+count))
  assert all(928<=tile<1088 for tile in retained_tiles)
  original_tail=s.decode(old,34662,s.u16(old,34660))[0][5120:]+s.decode(old,39976,s.u16(old,39974))[0]
  tail=bytearray(160*32)
  for tile in retained_tiles:
   start=(tile-928)*32;tail[start:start+32]=original_tail[start:start+32]
  prefix+=tail[:96*32];stock_tail=bytes(tail[96*32:])
 blobs={'front_tiles':resource(tiles.raw or b'\0'*32),'background_tiles':resource(stock_tail+bg.raw),'retained_dancer_light_prefix':resource(prefix),'new_map':resource(mapping)}
 if frames:blobs['new_frame_table']=frame_table(frames)
 print('CAMEO bgtiles',len(bg.raw)//32,'fronttiles',len(tiles.raw)//32,'blobs', {k:len(v) for k,v in blobs.items()},flush=True)
 data=bytearray(old);regions=[Region(data,23242,28955),Region(data,34660,41238)]
 # Exhaustive small two-bin packing keeps all unchanged frame definitions and
 # first sprite stream at their original locations.
 import itertools
 items=sorted(blobs.items(),key=lambda kv:-len(kv[1]));solution=None
 for bins in itertools.product(range(2),repeat=len(items)):
  if all(sum((len(items[i][1])+1)//2*2 for i,k in enumerate(bins) if k==which)<=r.end-r.start for which,r in enumerate(regions)):solution=bins;break
 if solution is None:raise ValueError('Cameo assets exceed approved fixed extents')
 at={}
 for (label,blob),which in zip(items,solution):at[label]=regions[which].add(label,blob)
 # All three wall programs consume the same costume-dependent transfers.
 consumers=[]
 for sq in s.sequences(old):
  for c in sq['commands']:
   if c['op']==1:
    for off in range(c['body'],c['body']+c['length']-7,8):
     oldoff=s.u32(old,off)&0xffffff
     replace={s.BASE+23900:('front_tiles',0x2000),s.BASE+34660:('retained_dancer_light_prefix',0x6000),s.BASE+39974:('background_tiles',0x8800 if complete else 0x8000),s.BASE+23242:('new_map',0xc000)}
     if oldoff in replace:
      label,vr=replace[oldoff];data[off:off+4]=ptr(at[label]);data[off+6:off+8]=be(vr);consumers.append(dict(program=sq['index'],record=off,old_source=oldoff-s.BASE,new_source=at[label],vram=vr,label=label))
 # Existing action groups and wait/resume controls remain the native script.
 mapping_frames=frame_mapping
 for c in mdseq['commands']:
  if c['op']!=2:continue
  for off in range(c['body'],c['body']+c['length'],12):
   group=old[off]
   if group not in native_groups:continue
   data[off+2:off+6]=b'\0'*4;data[off+6:off+10]=ptr(at['new_frame_table'])
   script=off+12+struct.unpack_from('>h',old,off+10)[0]
   for n in range(5):
    pos=script+n*4;op=old[pos]
    if op<128:data[pos]=mapping_frames[op]
    elif op==0x81:break
 assert bytes(data[28956:34660])==old[28956:34660]
 disabled_callbacks=[]
 for command in mdseq['commands']:
  if command['op']!=2:continue
  for off in range(command['body'],command['body']+command['length'],12):
   group=old[off]
   if group not in set(CAMEO_GROUPS.values())-native_groups:continue
   script=off+12+struct.unpack_from('>h',old,off+10)[0]
   assert data[off:off+12]==old[off:off+12]
   for n in range(5):
    pos=script+n*4;assert data[pos:pos+4]==old[pos:pos+4]
    if old[pos]==0x81:break
   disabled_callbacks.append(dict(group=group,record=off,script=script,initializer_unchanged=True,script_unchanged=True))
 # Reconstruct all preserved stock pixels by their original VRAM tile indices.
 if not complete:
  retained_vram=bytearray(65536);retained_vram[0x6000:0x6000+len(prefix)]=prefix;retained_vram[0x8000:0x8000+len(stock_tail)]=stock_tail
  for tile in retained_tiles:assert retained_vram[tile*32:tile*32+32]==oldv[tile*32:tile*32+32]
 # Every original native pointer consumer is enumerated, including potential
 # animation draw records outside graphics-program transfer lists.
 for oldoff in (23900,34660,39974,23242):
  hits=[i for i in range(len(old)-3) if old[i:i+4]==ptr(oldoff)]
  known=[c['record'] for c in consumers if c['old_source']==oldoff]
  assert hits==sorted(known),(oldoff,hits,known)
 testv=bytearray(65536);testv[0x8800:0x8800+len(bg.raw)]=bg.raw;testv[0xc000:0xc800]=mapping
 quantized=s.compose(testv,mdcolors);original=s.compose(oldv,mdcolors)
 assert all(mask.getpixel((x,y)) or quantized.getpixel((x,y))==original.getpixel((x,y)) for y in range(224) for x in range(256))
 def pixel(v,x,y):
  word=s.u16(v,0xc000+((y//8)*32+x//8)*2);sx=7-x%8 if word&0x800 else x%8;sy=7-y%8 if word&0x1000 else y%8
  packed=v[(word&2047)*32+sy*4+sx//2];value=packed>>(0 if sx&1 else 4)&15
  return ((word>>13&3)*16+value,bool(value),bool(word&0x8000))
 for y in range(256):
  for x in range(256):
   if y>=224 or not mask.getpixel((x,y)):assert pixel(oldv,x,y)==pixel(testv,x,y)
   else:
    w=vram[(y//8*64+x//8)*2]|vram[(y//8*64+x//8)*2+1]<<8;value=pce_cells[w&4095][(y%8)*8+x%8]
    assert pixel(testv,x,y)[1]==bool(value)
 base.save(evidence/'cameo-converted-base.png');mask.save(evidence/'cameo-costume-mask.png')
 return bytes(data),dict(row='GFX-002',selected_groups=sorted(chosen),bar_background=background,disabled_callbacks=disabled_callbacks,retained_stock_portrait_tiles=sorted(retained_tiles),pce_block_sha1=sha(b),pce_record=row['rec'],background_tiles=len(bg.raw)//32,front_tiles=len(tiles.raw)//32,groups=groups,preserved_dancer_light_tile_range=[512,928],preserved_prefix_decoded_sha1=sha(prefix),preserved_dancer_light_frames=list(range(31))+list(range(37,41)),consumers=consumers,allocations=[a for r in regions for a in r.allocations],mask_sha1=sha(mask.tobytes()),mask_pixels=sum(bool(v) for v in mask.tobytes()),background_quantization_squared_rgb_error=sum(bg.errors),front_quantization_squared_rgb_error=sum(tiles.errors),architecture_outside_mask_unchanged=True,outside_mask_global_palette_indices_unchanged=True,outside_mask_opacity_priority_unchanged=True,inside_mask_donor_opacity_preserved=True)

def story_wait(old,source,edit):
 if sha(old)!=edit['source_sha1']:raise ValueError('SP25.BIN: source hash changed')
 call,helper=edit['call_offset'],edit['helper_offset']
 if (call,helper)!=(1159,3211):raise ValueError('Unexpected dog story-wait patch location')
 if sha(old[call:call+3])!=edit['old_call_sha1'] or sha(old[helper:helper+7])!=edit['old_fill_sha1']:raise ValueError('Story call or unused fill hash changed')
 assert old[call:call+3]==bytes.fromhex('0a0064') and set(old[helper:helper+7])<={0,255}
 table=scd_script.dispatch(source);before=scd_script.inspect(old,table)
 assert not before['errors'] and before['parsed_until']==helper
 assert not any(helper<=a['value']<helper+7 for n in before['nodes'] for a in n['operands'])
 assert not any(n['continuation'] and helper<=n['continuation']<helper+7 for n in before['nodes'])
 data=bytearray(old);data[call:call+3]=b'\x0c'+be(helper);data[helper:helper+7]=b'\x25'+old[call:call+3]+bytes.fromhex('450014')
 after=scd_script.inspect(data,table);assert not after['errors'] and after['parsed_until']==helper+7
 assert data[0x3800:]==old[0x3800:] and len(data)==len(old)
 return bytes(data),dict(file='SP25.BIN',source_sha1=sha(old),output_sha1=sha(data),source_size=len(old),output_size=len(data),call_offset=call,helper_offset=helper,helper_length=7,old_fill_sha1=sha(old[helper:helper+7]),no_existing_tail_targets=True,typed_parse_errors=after['errors'],text_pool_unchanged=True,sequence=['original FM music100','animation completion flag object20','original following voice391'],primary_call_semantics='SCD0C synchronously evaluates one25 binary-sequence expression and restores its caller. No3A cross-file return opcode.',permitted_spans=spans(old,data))

def apply(source,output,evidence,profile=None):
 selected=get_profile(profile)
 source,output,evidence=map(Path,(source,output,evidence))
 if source.resolve()==output.resolve():raise ValueError('Output must not overwrite source')
 recipe=json.loads((ROOT/'patches/gfx/animation.json').read_text());rows=recipe['rows']
 if recipe.get('version')!=1 or len(rows)!=2 or {r['id'] for r in rows}!={'GFX-001','GFX-002'}:raise ValueError('Exactly two approved animation rows required')
 user=p.user_data(p.TRACK);table=p.filetable(user)['2']
 originals={}
 for row in rows:
  expected={'GFX-001':('DATA_G0.BIN',35),'GFX-002':('DATA_O0.BIN',41)}[row['id']]
  if (row['file'],row['pce_block'])!=expected:raise ValueError('Invalid approved animation target')
  old=(source/row['file']).read_bytes();originals[row['file']]=old
  if sha(old)!=row['source_sha1']:raise ValueError(f'{row["file"]}: source hash changed')
  ref=table[row['pce_block']];block=user[ref['rec']*2048:(ref['rec']+ref['sectors'])*2048]
  if sha(block)!=row['pce_block_sha1'] or ref['rec']!=row['pce_record']:raise ValueError('PCE donor block hash changed')
  record_at=22*2048+(0x566d-0x4000)+row['pce_block']*8
  if sha(user[record_at:record_at+8])!=row['pce_table_record_sha1']:raise ValueError('PCE donor table binding changed')
 dogrow=next(r for r in rows if r['id']=='GFX-001')
  # Dependency is validated before any output write.
 control=dogrow['control_edit'];script_index=(control['pce_record']-158)//16;scriptrow=p.filetable(user)['1'][script_index]
 control_module=user[scriptrow['rec']*2048:(scriptrow['rec']+scriptrow['sectors'])*2048]
 binding_at=22*2048+(0x5535-0x4000)+script_index*8
 if sha(control_module)!=control['pce_script_module_sha1'] or sha(user[binding_at:binding_at+8])!=control['pce_script_table_sha1']:raise ValueError('PCE dog story-control donor hash changed')
 wait_at=control['pce_wait_offset']
 if sha(control_module[wait_at:wait_at+3])!=control['pce_wait_sha1']:raise ValueError('PCE dog story-wait anchor changed')
 control_old=(source/'SP25.BIN').read_bytes();control_new,control_report=story_wait(control_old,source,control)
 control_report.update(pce_script_module_sha1=sha(control_module),pce_script_table_sha1=sha(user[binding_at:binding_at+8]),pce_wait_sha1=sha(control_module[wait_at:wait_at+3]))
 output.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True);reports=[]
 for row in rows:
  if row['id'] not in selected.art_rows:continue
  name=row['file'];old=originals[name]
  if row['id']=='GFX-002':
   converted,report=cameo(old,user,evidence,groups=getattr(selected,'cameo_groups',None),background=getattr(selected,'bar_background',True))
  else:converted,report=dog(old,user,evidence)
  assert len(converted)==len(old) or (name=='DATA_G0.BIN' and len(old)<len(converted)<=124928)
  if s.inventory(converted,name)[2] or s.frame_inventory(converted,s.sequences(converted))['errors']:raise ValueError('Converted animation inventory has errors')
  (output/name).write_bytes(converted);report.update(id=row['id'],file=name,source_size=len(old),output_size=len(converted),source_sha1=sha(old),output_sha1=sha(converted),permitted_spans=spans(old,converted));reports.append(report)
 if selected.alice:
  (output/'SP25.BIN').write_bytes(control_new);next(r for r in reports if r['id']=='GFX-001')['control_edit']=control_report
 report=dict(status='pass',profile=selected.id,catalogue_rows=2,rows=reports,changed_files=[r['file'] for r in reports]+(['SP25.BIN'] if selected.alice else []));(evidence/'animation-report.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--profile');a.add_argument('--source',type=Path,default=s.SOURCE);a.add_argument('--output',type=Path,required=True);a.add_argument('--evidence',type=Path,required=True);args=a.parse_args();print(json.dumps(apply(**vars(args)),indent=2))
