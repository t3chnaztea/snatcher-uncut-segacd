#!/usr/bin/env python3
"""Deterministic approved M4 still-art and date-caption conversion recipes."""
import argparse
from collections import Counter,defaultdict
import hashlib,json,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
# A lane may read current shared format tooling from the authoritative checkout.
TOOLS=ROOT/'tools'
if not (TOOLS/'scd_gfx.py').exists():TOOLS=ROOT.parent.parent/'snatcher-uncut/tools'
sys.path.insert(0,str(TOOLS))
import scd_gfx
from patch_profiles import get_profile

def digest(b):return hashlib.sha1(b).hexdigest()

def optimal_encode(data):
    """Shortest valid token path, including each eight-token control byte.

    Format facts come from verified disc tokens. This encoder is independently
    implemented; it does not copy the primary engine's compression code.
    """
    n=len(data);matches=[]
    for p in range(n):
        short=None;long=None
        for length in range(min(5,n-p),1,-1):
            at=data.rfind(data[p:p+length],max(0,p-15),p+length-1)
            if at>=0:short=(length,p-at);break
        for length in range(min(34,n-p),2,-1):
            at=data.rfind(data[p:p+length],max(0,p-1023),p+length-1)
            if at>=0:
                distance=p-at
                if length==34 and distance<256:
                    at=data.rfind(data[p:p+length],max(0,p-1023),p+length-256) if p>=256 else -1
                    if at<0:continue
                    distance=p-at
                long=(length,distance);break
        matches.append((short,long))
    costs=[[0]*8 for _ in range(n+1)];choices=[None]*n
    for mod in range(8):costs[n][mod]=1+(mod==0)
    for p in range(n-1,-1,-1):
        opts=[(1,1,0,None)]
        short,long=matches[p]
        if short:
            opts += [(length,1,1,short[1])for length in range(2,short[0]+1)]
        if long:
            opts += [(length,2,2,long[1])for length in range(3,long[0]+1) if not(length==34 and long[1]<256)]
        opts +=[(length,length+1,3,None)for length in range(8,min(71,n-p)+1)]
        row=[]
        for mod in range(8):
            length,size,kind,distance=min(opts,key=lambda o:o[1]+costs[p+o[0]][(mod+1)%8])
            costs[p][mod]=size+(mod==0)+costs[p+length][(mod+1)%8]
            row.append((length,kind,distance))
        choices[p]=row
    tokens=[];p=0;mod=0
    while p<n:
        length,kind,distance=choices[p][mod]
        if kind==0:token=(0,data[p:p+1])
        elif kind==1:token=(1,bytes([((length+6)<<4)|distance]))
        elif kind==2:token=(1,bytes([((distance>>8)<<5)|(length-3),distance&255]))
        else:token=(1,bytes([length+184])+data[p:p+length])
        tokens.append(token);p+=length;mod=(mod+1)%8
    tokens.append((1,b'\x1f'));out=bytearray()
    for p in range(0,len(tokens),8):
        group=tokens[p:p+8];out.append(sum(bit<<i for i,(bit,_) in enumerate(group)))
        for _,payload in group:out.extend(payload)
    result=bytes(out);assert len(result)==costs[0][0]
    decoded,end=scd_gfx.decode(result,0,len(data));assert decoded==data and end==len(result)
    return result

def _load_manifest(source,name):
    blob=(Path(source)/name).read_bytes()
    seqs,streams,errors=scd_gfx.inventory(blob,name)
    if errors:raise ValueError('Source graphics inventory does not validate')
    return blob,dict(file=name,sha1=digest(blob),streams=streams,sequences=seqs)

def _context(blob,meta,sequence):
    vram=bytearray(65536);streams={};placements={}
    for s in meta['streams']:
        for ref in s['references']:
            if ref.get('sequence')==sequence:
                decoded=scd_gfx.stream_bytes(blob,s);vram[ref['vram']:ref['vram']+len(decoded)]=decoded
                streams[s['offset']]=bytearray(decoded);placements[s['offset']]=ref['vram']
    colors,pals=scd_gfx.palette(blob,meta['sequences'][sequence]['commands'])
    return dict(vram=vram,streams=streams,placements=placements,colors=colors,palettes=pals)

def _raster(ctx,plane,columns=32,rows=32):
    vram=ctx['vram'];im=Image.new('RGB',(columns*8,rows*8));px=im.load()
    for y in range(rows*8):
        for x in range(columns*8):
            word=scd_gfx.u16(vram,plane+(y//8*columns+x//8)*2);tile=word&2047;pal=(word>>13)&3
            xx=7-x%8 if word&0x800 else x%8;yy=7-y%8 if word&0x1000 else y%8
            value=(vram[tile*32+yy*4+xx//2]>>(0 if xx&1 else 4))&15
            px[x,y]=ctx['colors'][pal*16+value]
    return im

def _pixel_patch(ctx,plane,desired,columns=32,rows=32):
    """Patch tile pixels, cloning a shared tile only when its consumers differ."""
    vram=ctx['vram'];mapping={};uses=defaultdict(list)
    for y in range(rows):
        for x in range(columns):
            at=plane+(y*columns+x)*2;word=scd_gfx.u16(vram,at);mapping[x,y]=(at,word);uses[word&2047].append((x,y))
    pending={};changes=[]
    for (x,y),rgb in desired.items():
        at,word=mapping[x//8,y//8];tile=word&2047;pal=(word>>13)&3
        xx=7-x%8 if word&0x800 else x%8;yy=7-y%8 if word&0x1000 else y%8
        offset=yy*4+xx//2;shift=0 if xx&1 else 4
        nearest=min(range(16),key=lambda i:sum((a-b)**2 for a,b in zip(rgb,ctx['colors'][pal*16+i])))
        old=(vram[tile*32+offset]>>shift)&15
        if old==nearest or ctx['colors'][pal*16+old]==ctx['colors'][pal*16+nearest]:continue
        cell=(x//8,y//8)
        if cell not in pending:pending[cell]=bytearray(vram[tile*32:tile*32+32])
        pending[cell][offset]=(pending[cell][offset]&~(15<<shift))|(nearest<<shift)
        changes.append((x,y))
    allocations=[]
    for cell,newtile in pending.items():
        at,word=mapping[cell];tile=word&2047
        candidates=[]
        for off,base in ctx['placements'].items():
            if base>=0xc000:continue
            raw=ctx['streams'][off]
            if base<=tile*32<base+len(raw):candidates.append((off,base,raw))
        if len(candidates)!=1:raise ValueError('Target tile has no unique source transfer')
        off,base,raw=candidates[0]
        if len(uses[tile])>1:
            free=[t for t in range(base//32,(base+len(raw))//32) if not uses[t] and not any(raw[(t*32-base):(t*32-base+32)])]
            if not free:raise ValueError(f'Shared tile{tile} cell{cell} uses{uses[tile]} needs an unused zero tile in its existing VRAM budget')
            new=min(free);uses[new]=[cell];word=(word&~2047)|new
            mapoff=next(o for o,b in ctx['placements'].items()if b<=at<b+len(ctx['streams'][o]))
            mapbase=ctx['placements'][mapoff];ctx['streams'][mapoff][at-mapbase:at-mapbase+2]=word.to_bytes(2,'big')
            allocations.append(dict(from_tile=tile,to_tile=new,cell=list(cell),reason='preserve all other shared-tile consumers'))
            tile=new
        raw[tile*32-base:tile*32-base+32]=newtile
    # Prove all pixels outside the explicit desired-coordinate set retain RGB.
    result=dict(ctx);result['vram']=bytearray(vram)
    for off,base in ctx['placements'].items():result['vram'][base:base+len(ctx['streams'][off])]=ctx['streams'][off]
    oldim=_raster(ctx,plane,columns,rows);newim=_raster(result,plane,columns,rows)
    changed=[]
    for y in range(oldim.height):
        for x in range(oldim.width):
            if oldim.getpixel((x,y))!=newim.getpixel((x,y)):
                if (x,y)not in desired:raise ValueError('Shared glyph edit changes an unapproved pixel')
                changed.append((x,y))
    return result,dict(changed_pixels=len(changed),changed_bbox=list(Image.frombytes('RGB',oldim.size,bytes(a^b for a,b in zip(oldim.tobytes(),newim.tobytes()))).getbbox() or ()),allocations=allocations),oldim,newim

def _newspaper_sprite_patch(ctx,blob,sequence,pce):
    objects=scd_gfx.sprite_frames(blob,sequence['commands'])
    obj=next(o for o in objects if o['object']==21)
    ox,oy=obj['initial_state']['x'],obj['initial_state']['y']
    normalized=dict(obj,sprites=[dict(cell,x=cell['x']-ox,y=cell['y']-oy)for cell in obj['sprites']])
    def picture(vram):return scd_gfx.draw_sprites(Image.new('RGB',(192,136)),vram,ctx['colors'],[normalized])
    old=picture(ctx['vram']);goals={}
    for y in range(5):
        for x in range(7):
            fg=sum(pce.getpixel((112+x,34+y)))<300
            goals[119+x,29+y]=old.getpixel((119,29))if fg else old.getpixel((118,29))
    writes={}
    for (x,y),rgb in goals.items():
        found=[]
        for cell in normalized['sprites']:
            xx,yy=x-cell['x'],y-cell['y'];w=cell['width']*8;h=cell['height']*8;word=cell['tile']
            if not(0<=xx<w and 0<=yy<h):continue
            sx=w-1-xx if word&0x800 else xx;sy=h-1-yy if word&0x1000 else yy
            tile=((word&2047)+(sx//8)*cell['height']+sy//8)&2047;off=tile*32+(sy%8)*4+(sx%8)//2;shift=0 if sx&1 else 4;pal=(word>>13)&3
            index=min(range(16),key=lambda i:sum((a-b)**2 for a,b in zip(rgb,ctx['colors'][pal*16+i])))
            found.append((off,shift,index))
        if len(found)!=1:raise ValueError('Foreground newspaper date has overlapping sprite cells')
        off,shift,index=found[0]
        for stream,base in ctx['placements'].items():
            raw=ctx['streams'][stream]
            if base<0xc000 and base<=off<base+len(raw):
                at=off-base;value=writes.get(off,raw[at]);writes[off]=(value&~(15<<shift))|(index<<shift)
    for off,value in writes.items():
        for stream,base in ctx['placements'].items():
            raw=ctx['streams'][stream]
            if base<0xc000 and base<=off<base+len(raw):raw[off-base]=value
    vram=bytearray(ctx['vram'])
    for stream,base in ctx['placements'].items():vram[base:base+len(ctx['streams'][stream])]=ctx['streams'][stream]
    new=picture(vram);changed=[]
    for y in range(136):
        for x in range(192):
            if old.getpixel((x,y))!=new.getpixel((x,y)):
                if(x,y)not in goals:raise ValueError('Foreground date edit changes an unapproved sprite pixel')
                changed.append((x,y))
    return dict(changed_pixels=len(changed),local_bbox=[119,29,126,34],native_bbox=[169,93,176,98],object=21,frame=obj['frame'],frame_table=obj['frame_table'],frame_data=obj['frame_data'],other_sprite_pixels_unchanged=True),old,new

_PCE_CACHE={}
def _pce_image(root,proof):
    import pce_gfx
    track=root/'private/discs/pcenginecd-jp/Snatcher CD-ROMantic (Japan) (Track 02).bin'
    key=(str(track.resolve()),track.stat().st_size,track.stat().st_mtime_ns)
    if key not in _PCE_CACHE:_PCE_CACHE[key]=pce_gfx.user_data(track)
    data=_PCE_CACHE[key];row=pce_gfx.filetable(data)['2'][proof['block']];blob=data[row['rec']*2048:(row['rec']+row['sectors'])*2048]
    if digest(blob)!=proof['block_sha1']:raise ValueError('PCE art source hash mismatch')
    lists=pce_gfx.program_display_lists(blob,row['bank']);dl=next(x for x in lists if x['offset']==proof['list_offset']);vram,_=pce_gfx.build_vram(blob,dl['records'])
    palette=[(0,0,0)]*256;filled=set();pals={p['record']:p for p in pce_gfx.palettes(blob,row['bank'])}
    for index in proof['palette_records']:
        p=pals[index]
        for k,color in enumerate(p['colors']):
            dest=p['vce']+k
            if dest<256 and dest not in filled:palette[dest]=color;filled.add(dest)
    image=pce_gfx.screen(vram,palette)
    if digest(image.tobytes())!=proof['image_rgb_sha1']:raise ValueError('PCE raster differs from reviewed source')
    return image

def _row_patch(source,row,root):
    blob,meta=_load_manifest(source,row['file'])
    if digest(blob)!=row['source_sha1']:raise ValueError('Art source hash mismatch')
    ctx=_context(blob,meta,row['program']);plane=row['plane'];rows=row.get('plane_rows',32);im=_raster(ctx,plane,rows=rows);desired={}
    if row['id']=='TEXT-034':
        # Reuse the original serif 1. Only the final 6's existing slot changes.
        for y in range(112,132):
            for x in range(181,192):desired[x,y]=(0,0,0)
            for x in range(9):desired[182+x,y]=im.getpixel((144+x,y))
    elif row['id']=='TEXT-035':
        pce=_pce_image(root,row['pce'])
        for y in range(5):
            for x in range(7):
                foreground=sum(pce.getpixel((112+x,34+y)))<300
                desired[112+x,26+y]=im.getpixel((114,26))if foreground else im.getpixel((111,26))
    elif row['id']=='TEXT-036':
        # In the source 32x64 plane the card is at y+256. Native scroll is768.
        for y in range(318,332):
            for x in range(160,170):desired[x,y]=(0,0,0)
            for x in range(9):desired[160+x,y]=im.getpixel((128+x,y))
    elif row['id']=='GFX-005':
        pce=_pce_image(root,row['pce'])
        for y in range(32,136):
            for x in range(32,224):
                # Preserve the shared door/floor palette. The source ports
                # have minor room differences outside the approved corpse.
                rgb=pce.getpixel((x,y));old=im.getpixel((x,y))
                room=set(ctx['colors'][32:48])
                if rgb not in room or old not in room:desired[x,y]=rgb
    else:raise ValueError('Unexpected M4 still-art row')
    newctx,visual,oldim,newim=_pixel_patch(ctx,plane,desired,rows=rows)
    if row['id']=='TEXT-035':
        front,oldfront,newfront=_newspaper_sprite_patch(newctx,blob,meta['sequences'][row['program']],pce)
        visual['foreground_date']=front
        # Previews retain both separately guarded date dependencies.
        # Native matched opening snapshot has object21 origin(50,64).
        # Source-local glyphs119..125 are independent of its scrolling origin.
        oldim.paste(oldfront,(50,64));newim.paste(newfront,(50,64))
    result=bytearray(blob);resources=[]
    for off,raw in ctx['streams'].items():
        stream=next(s for s in meta['streams']if s['offset']==off);old=scd_gfx.stream_bytes(blob,stream)
        if bytes(raw)==old:continue
        guard=next(x for x in row['resources']if x['offset']==off)
        if stream['references']!=guard['references']:raise ValueError('Graphics resource consumers changed')
        if digest(old)!=guard['decoded_sha1']or digest(blob[off:stream['end']])!=guard['encoded_sha1']:raise ValueError('Graphics resource hash mismatch')
        encoded=optimal_encode(bytes(raw));capacity=stream['end']-off-2
        if len(encoded)>capacity:raise ValueError(f'{row["id"]} stream{off:x} needs{len(encoded)} capacity{capacity}')
        result[off+2:stream['end']]=encoded+bytes(capacity-len(encoded));assert scd_gfx.stream_bytes(result,stream)==raw
        resources.append(dict(offset=off,end=stream['end'],decoded_size=len(raw),old_decoded_sha1=digest(old),new_decoded_sha1=digest(raw),capacity=capacity,encoded_size=len(encoded),references=stream['references']))
    for s in meta['streams']:
        if not any(s['offset']==c['offset']for c in resources):
            if scd_gfx.stream_bytes(result,s)!=scd_gfx.stream_bytes(blob,s):raise ValueError('Unapproved decoded asset changed')
    newseq,newstreams,errors=scd_gfx.inventory(result,row['file'])
    if errors or newseq!=meta['sequences']:raise ValueError('Graphics control programs changed')
    if len(newstreams)!=len(meta['streams']):raise ValueError('Graphics resource inventory changed')
    if scd_gfx.animation_inventory(blob,newseq)!=scd_gfx.animation_inventory(result,newseq):raise ValueError('Animation control graph changed')
    if scd_gfx.frame_inventory(blob,newseq)!=scd_gfx.frame_inventory(result,newseq):raise ValueError('Frame table changed')
    for seq in newseq:
        _,pals=scd_gfx.palette(blob,seq['commands'])
        for pal in pals:
            start=pal['offset'];end=start+pal['count']*2
            if blob[start:end]!=result[start:end]:raise ValueError('Unapproved palette changed')
    return bytes(result),dict(id=row['id'],file=row['file'],source_sha1=digest(blob),output_sha1=digest(result),program=row['program'],resources=resources,visual=visual,unapproved_resources_unchanged=True,control_programs_unchanged=True,animation_graph_unchanged=True,frame_tables_unchanged=True,palettes_unchanged=True,inventory_errors=0),oldim,newim

def _validate_catalogue(source,rows,root):
    """Validate inactive rows too; selection never waives source/donor guards."""
    for row in rows:
        blob,meta=_load_manifest(source,row['file'])
        if digest(blob)!=row['source_sha1']:raise ValueError('Art source hash mismatch')
        resources=row['resources']
        if len({r['offset'] for r in resources})!=len(resources):raise ValueError('Duplicate still-art resource')
        streams={r['offset']:r for r in meta['streams']}
        for guard in resources:
            stream=streams.get(guard['offset'])
            if stream is None or stream['end']!=guard['end'] or stream['references']!=guard['references']:
                raise ValueError('Graphics resource consumers changed')
            if digest(scd_gfx.stream_bytes(blob,stream))!=guard['decoded_sha1'] or digest(blob[guard['offset']:guard['end']])!=guard['encoded_sha1']:
                raise ValueError('Graphics resource hash mismatch')
        if not 0<=row['program']<len(meta['sequences']):raise ValueError('Invalid still-art program')
        if 'pce' in row:_pce_image(root,row['pce'])

def apply(source,output,evidence,profile=None):
    selected=get_profile(profile)
    source,output,evidence=Path(source),Path(output),Path(evidence)
    if source.resolve()==output.resolve():raise ValueError('Output must not overwrite source')
    root=source.parents[2];patch=json.loads((ROOT/'patches/gfx/captions.json').read_text())
    if patch.get('version')!=1 or len(patch['rows'])!=4 or {r['id']for r in patch['rows']}!={'GFX-005','TEXT-034','TEXT-035','TEXT-036'}:raise ValueError('Still-art approval inventory mismatch')
    _validate_catalogue(source,patch['rows'],root)
    # Each row starts from the same original module; compose only disjoint spans.
    outputs={};reports=[];images=[];seen=defaultdict(set)
    for row in patch['rows']:
        if row['id'] not in selected.art_rows:continue
        result,report,oldim,newim=_row_patch(source,row,root);name=row['file'];old=(source/name).read_bytes();dest=outputs.setdefault(name,bytearray(old))
        for n,(a,b)in enumerate(zip(old,result)):
            if a!=b:
                if n in seen[name]:raise ValueError('Still-art rows overlap')
                seen[name].add(n);dest[n]=b
        reports.append(report);images.append((row['id'],oldim,newim))
    output.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    for name,data in outputs.items():(output/name).write_bytes(data)
    for ident,old,new in images:
        old.save(evidence/f'{ident}-source.png');new.save(evidence/f'{ident}-converted.png')
    report=dict(status='pass',profile=selected.id,catalogue_rows=4,rows=reports,changed_files=sorted(outputs),source_hashes={n:digest((source/n).read_bytes())for n in outputs},output_hashes={n:digest(bytes(v))for n,v in outputs.items()},permitted_spans={n:[dict(start=c['offset']+2,end=c['end'])for r in reports if r['file']==n for c in r['resources']]for n in outputs},limits='Static conversion previews are not native harness proof. All palettes, programs and file sizes unchanged. Shared glyph blanks clone only within the existing tile budget.')
    (evidence/'apply.json').write_text(json.dumps(report,indent=2)+'\n');return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile');p.add_argument('--source',type=Path,default=ROOT/'private/extracted/segacd-usa');p.add_argument('--output',type=Path,default=ROOT/'build/m4/captions');p.add_argument('--evidence',type=Path,default=ROOT/'build/evidence/m4/captions-lane');a=p.parse_args();print(json.dumps(apply(a.source,a.output,a.evidence,profile=a.profile),indent=2))
if __name__=='__main__':main()
