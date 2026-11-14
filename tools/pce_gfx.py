#!/usr/bin/env python3
"""Inventory PC Engine Snatcher graphics from the disc file table.

Format reference: pepasjc/snatcher-translated docs/pce.md section 7 and
pce/tools/{pcetable,pcecodec,pcescene}.py. Implementation is independent.
Display lists are structural candidates; palette selection is a preview
heuristic and is recorded as such rather than asserted as runtime truth.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
TRACK=ROOT/'private/discs/pcenginecd-jp/Snatcher CD-ROMantic (Japan) (Track 02).bin'
OUT=ROOT/'private/work/gfx/pce'


def user_data(path):
    raw=Path(path).read_bytes()
    if len(raw)%2352:raise ValueError('Raw track size not sector aligned')
    # Track 02 cue INDEX 01 is 00:03:00; the file includes 225 pregap sectors.
    start=225*2352
    if raw[start+15]!=1:raise ValueError('Expected raw Mode 1 at cue INDEX 01')
    return b''.join(raw[i+16:i+2064] for i in range(start,len(raw),2352))


def filetable(data):
    stage=data[22*2048:37*2048];result={}
    for group,address,count in ((0,0x5505,6),(1,0x5535,33),(3,0x563d,6),(2,0x566d,None)):
        rows=[];off=address-0x4000
        while off+8<=len(stage) and (count is None or len(rows)<count):
            r=stage[off:off+8];rec=(r[0]<<16)|(r[2]<<8)|r[1]
            if not (r[7]==0 and 0<r[6]<=120 and rec<40000 and r[3]<16):
                if count is not None:raise ValueError('File table record invalid')
                break
            rows.append(dict(rec=rec,mode=r[3],bank=r[4],bh=r[5],sectors=r[6]));off+=8
        result[str(group)]=rows
    return result


def decode(data,start,limit=65536):
    out=bytearray();p=start
    def take(n):
        nonlocal p
        if p+n>len(data):raise ValueError('Truncated PCE stream')
        part=data[p:p+n];p+=n;return part
    while len(out)<=limit:
        c=take(1)[0]
        if c==255:return bytes(out),p
        if c==0:
            count,b=take(2);count=count or 256
            for value in take(count):out.extend((b,value))
        elif c==1:
            lo,hi,b=take(3);out.extend(bytes([b])*(lo+256*hi))
        elif c==2:
            count,a,b=take(3);out.extend(bytes([a,b])*(count or 256))
        elif c<64:out.extend(take(1)*c)
        elif c<128:out.extend(bytes((c&63) or 256))
        elif c==128:
            lo,hi=take(2);out.extend(take(lo+256*hi))
        elif c<192:out.extend(take(c&127))
        elif c<254:
            for value in take((c&63) or 256):out.extend((0,value))
        else:
            count=take(1)[0] or 256;out.extend(take(4)*count)
    raise ValueError('PCE decoded size exceeds limit')


def graphics_programs(block):
    """Native class-2 block table: LE16 CPU C000-based program addresses.

    Commands carry their complete byte length including the two-byte header.
    Individual command payloads may end in FF; the program itself also has an
    FF terminator outside the preceding command's declared length.
    """
    if len(block)<2:raise ValueError('Truncated graphics program table')
    bound=len(block);offsets=[];pos=0
    while pos+2<=bound:
        start=block[pos]+256*block[pos+1]-0xc000
        if start<pos+2 or start>=len(block):break
        bound=min(bound,start);offsets.append(start);pos+=2
    if not offsets:raise ValueError('No C000 graphics program table')
    result=[]
    for i,start in enumerate(offsets):
        p=start;commands=[]
        for _ in range(1024):
            if p>=len(block):raise ValueError('Truncated graphics program')
            if block[p]==255:break
            if p+2>len(block):raise ValueError('Truncated graphics command')
            op=block[p];length=block[p+1]
            if length<2 or p+length>len(block):raise ValueError('Invalid graphics command length')
            commands.append(dict(opcode=op,offset=p,length=length,body=p+2));p+=length
        else:raise ValueError('Unterminated graphics program')
        result.append(dict(index=i,offset=start,end=p+1,commands=commands))
    return result


def program_display_lists(block,bank):
    out=[]
    for program in graphics_programs(block):
        for command in program['commands']:
            if command['opcode']!=1:continue
            if command['length']<6 or (command['length']-6)%6 or block[command['offset']+command['length']-1]!=255:
                raise ValueError('Native display command boundaries invalid')
            records=[]
            for p in range(command['body']+3,command['offset']+command['length']-1,6):
                b,t,vl,vh,pl,ph=block[p:p+6];offset=(b-bank)*8192+pl+256*ph-32768
                if not 0<=offset<len(block):raise ValueError('Native display stream pointer outside block')
                records.append(dict(bank=b,type=t,vram=vl+256*vh,offset=offset,record=p))
            out.append(dict(offset=command['body']+3,records=records,program=program['index'],command=command['offset'],provenance='native_graphics_program'))
    return out


def display_lists(block,bank):
    result=[];i=0;nb=(len(block)+8191)//8192
    while i<len(block)-6:
        p=i;records=[]
        while p+6<=len(block):
            b,t,vl,vh,pl,ph=block[p:p+6]
            if b==255:break
            ptr=pl+256*ph;off=(b-bank)*8192+ptr-32768
            if not (bank<=b<bank+nb and 0x8000<=ptr<0xe000 and t<32 and 0<=off<len(block)):
                records=[];break
            records.append(dict(bank=b,type=t,vram=vl+256*vh,offset=off,record=p));p+=6
        if records and p<len(block) and block[p]==255:
            result.append(dict(offset=i,records=records));i=p+1
        else:i+=1
    return result


def pixels(data):
    result=[]
    for i in range(0,len(data)-31,32):
        tile=data[i:i+32];px=[]
        for y in range(8):
            for x in range(8):
                bit=7-x
                px.append(sum(((tile[y*2+(p&1)+(16 if p>=2 else 0)]>>bit)&1)<<p for p in range(4)))
        result.append(px)
    return result


def tile_sheet(data,wide=16):
    tiles=pixels(data);im=Image.new('P',(wide*8,max(1,(len(tiles)+wide-1)//wide)*8))
    im.putpalette([c for i in range(256) for c in (min(i,15)*17,)*3]);out=im.load()
    for t,tile in enumerate(tiles):
        for p,v in enumerate(tile):out[(t%wide)*8+p%8,(t//wide)*8+p//8]=v
    return im


def sprite_pixels(data):
    """VDC sprite patterns: four planes, sixteen little-endian rows each."""
    result=[]
    for i in range(0,len(data)-127,128):
        cell=data[i:i+128];pixels=[]
        for y in range(16):
            for x in range(16):
                value=0
                for plane in range(4):
                    offset=plane*32+y*2;word=cell[offset]+256*cell[offset+1]
                    value|=((word>>(15-x))&1)<<plane
                pixels.append(value)
        result.append(pixels)
    return result


def sprite_sheet(data,wide=8):
    cells=sprite_pixels(data);im=Image.new('P',(wide*16,max(1,(len(cells)+wide-1)//wide)*16))
    im.putpalette([c for i in range(256) for c in (min(i,15)*17,)*3]);out=im.load()
    for cell,values in enumerate(cells):
        for p,value in enumerate(values):out[(cell%wide)*16+p%16,(cell//wide)*16+p//16]=value
    return im


def palettes(block,bank):
    result=[];nb=(len(block)+8191)//8192
    for i in range(len(block)-5):
        lo,hi,pl,ph,b=block[i:i+5];vce=lo+256*hi;off=(b-bank)*8192+pl+256*ph-32768
        if hi>1 or vce%8 or not (bank<=b<bank+nb and 128<=ph<224 and 0<=off<len(block)-10):continue
        count=block[off]+1
        if count>32 or off+1+count*9>len(block):continue
        colors=[]
        for g in range(count):
            group=block[off+1+g*9:off+10+g*9]
            for k in range(8):
                word=group[k+1]|((group[0]>>(7-k)&1)<<8)
                colors.append(tuple(((word>>shift)&7)*255//7 for shift in (3,6,0)))
        result.append(dict(record=i,offset=off,vce=vce,colors=colors))
    return result


def build_vram(block,records):
    vram=bytearray(65536);streams=[]
    for rec in records:
        o=rec['offset'];flags=block[o];typ=rec['type'];header=2 if typ in (4,8) else 1+(flags&127)
        start=o+header
        decoded,end=decode(block,start)
        info=dict(**rec,stream=start,end=end,decoded_size=len(decoded),flags=flags)
        streams.append(info)
        if typ in (4,8) and flags&64:
            rowlen=block[o+1]
            if rowlen<2 or rowlen%2:raise ValueError('Invalid BAT row length')
            step,run=(64,1) if flags&32 else (1,64)
            for k in range(len(decoded)//2):
                addr=(rec['vram']+(k//(rowlen//2))*run+(k%(rowlen//2))*step)*2
                if addr+2<=65536:vram[addr:addr+2]=decoded[k*2:k*2+2]
        else:
            # Pixel remaps are preserved as metadata. Apply to planar bytes.
            if typ not in (4,8) and flags&127:
                remap=block[o+1:o+1+(flags&127)];new=bytearray()
                for tile in pixels(decoded):
                    mapped=[remap[v] if v<len(remap) else 0 for v in tile];encoded=bytearray(32)
                    for p,v in enumerate(mapped):
                        for plane in range(4):encoded[p//8*2+(plane&1)+(16 if plane>=2 else 0)]|=((v>>plane)&1)<<(7-p%8)
                    new.extend(encoded)
                decoded=bytes(new)
            a=rec['vram']*2
            if a<65536:vram[a:min(65536,a+len(decoded))]=decoded[:65536-a]
    return vram,streams


def screen(vram,palette):
    tiles=pixels(vram);im=Image.new('RGB',(256,224));out=im.load()
    for y in range(28):
        for x in range(32):
            off=(y*64+x)*2;word=vram[off]+256*vram[off+1];tile=tiles[(word&4095)%len(tiles)];pal=word>>12
            for i,value in enumerate(tile):out[x*8+i%8,y*8+i//8]=palette[pal*16+value]
    return im


def object_initializers(block,start,bank0):
    if start+3>len(block) or block[start]!=2:return []
    length=block[start+1]
    if length<15 or (length-3)%12 or start+length>len(block) or block[start+length-1]!=255:return []
    out=[]
    for at in range(start+2,start+length-1,12):
        row=block[at:at+12];bank=row[9]
        table=(bank-bank0)*8192+row[5]+256*row[6]-32768
        script=(row[10]-bank0)*8192+row[7]+256*row[8]-32768
        if row[0]>=64 or not 0<=table<len(block)-2 or not 0<=script<len(block)-4:return []
        out.append(dict(record=at,object=row[0],x=row[1]+256*row[2],y=row[3]+256*row[4],table=table,script=script,bank=bank,script_bank=row[10],flags=row[11]))
    return out


def object_frame_entries(block,table,frame):
    ptr=table+frame*2
    if ptr+2>len(block):raise ValueError('Object frame index outside block')
    offset=table+block[ptr]+256*block[ptr+1]
    if offset>=len(block):raise ValueError('Object frame offset outside block')
    count=block[offset]
    if count>64 or offset+1+count*5>len(block):raise ValueError('Invalid object sprite count')
    result=[]
    for i in range(count):
        size,dy,dx,lo,attr=block[offset+1+i*5:offset+6+i*5]
        height={0:1,1:2,3:4}.get((size>>4)&3)
        if height is None:raise ValueError('Reserved sprite height')
        result.append(dict(size=size,x=dx-256 if dx>127 else dx,y=dy-256 if dy>127 else dy,width=2 if size&1 else 1,height=height,cell=(lo+((attr&0x30)<<4))//2,palette=attr&15,attr=attr))
    return offset,result


def draw_object(image,vram,colors,block,obj,frame,cached_cells=None):
    at,entries=object_frame_entries(block,obj['table'],frame);cells=cached_cells if cached_cells is not None else sprite_pixels(vram);out=image.load()
    for entry in reversed(entries):
        first=entry['cell']
        if entry['width']==2:first&=~1
        for cy in range(entry['height']):
            for cx in range(entry['width']):
                cell=first+cy*2+cx
                if cell>=len(cells):continue
                for i,value in enumerate(cells[cell]):
                    if not value:continue
                    x=obj['x']+entry['x']+cx*16+i%16;y=obj['y']+entry['y']+cy*16+i//16-32
                    if 0<=x<image.width and 0<=y<image.height:out[x,y]=colors[256+entry['palette']*16+value]
    return dict(frame_data=at,entries=entries)


def dump(track=TRACK,output=OUT):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);data=user_data(track);table=filetable(data)
    manifest=dict(version=1,track=str(Path(track).resolve()),track_sha1=hashlib.sha1(Path(track).read_bytes()).hexdigest(),table=table,blocks=[],stream_count=0,image_count=0,native_program_count=0,native_display_count=0,image_count_scope='Static display-list candidates, not distinct scene images')
    for index,row in enumerate(table['2']):
        block=data[row['rec']*2048:(row['rec']+row['sectors'])*2048]
        programs=[];native=[]
        if index!=1:
            programs=graphics_programs(block);native=program_display_lists(block,row['bank'])
        native_offsets={dl['offset'] for dl in native}
        combined={dl['offset']:dict(dl,provenance='structural_candidate') for dl in display_lists(block,row['bank'])}
        combined.update({dl['offset']:dl for dl in native});lists=sorted(combined.values(),key=lambda dl:dl['offset'])
        manifest['native_program_count']+=len(programs);manifest['native_display_count']+=len(native)
        pals=palettes(block,row['bank']);folder=output/f'b{index:03d}_rec{row["rec"]}';folder.mkdir(exist_ok=True);entries=[];seen=set();errors=[];rejected_candidates=[]
        for li,dl in enumerate(lists):
            try:vram,streams=build_vram(block,dl['records'])
            except (ValueError,IndexError) as e:
                detail=dict(offset=dl['offset'],error=str(e))
                if dl['provenance']=='native_graphics_program':
                    errors.append(detail)
                    raise ValueError(f'Native graphics decode failed: block {index}, list {dl["offset"]:x}: {e}') from e
                rejected_candidates.append(detail);continue
            for stream in streams:
                if stream['stream'] in seen:continue
                seen.add(stream['stream']);decoded,_=decode(block,stream['stream'])
                if len(decoded)<32:continue
                tile_sheet(decoded).save(folder/f'stream_{stream["stream"]:05x}.png')
                sprite_sheet(decoded).save(folder/f'sprites_{stream["stream"]:05x}.png')
                stream.update(file_sector=row['rec'],track_user_offset=row['rec']*2048+stream['stream'],compression='pce-byte-rle',palette='diagnostic index ramp');(folder/f'stream_{stream["stream"]:05x}.json').write_text(json.dumps(stream,indent=2)+'\n');manifest['stream_count']+=1
            palette=[(0,0,0)]*256;filled=set();candidates=sorted((p for p in pals if p['vce']<256),key=lambda p:abs(p['record']-dl['offset']))[:8]
            for p in candidates:
                for k,color in enumerate(p['colors']):
                    target=p['vce']+k
                    if target<256 and target not in filled:
                        palette[target]=color;filled.add(target)
            image=screen(vram,palette);name=f'list_{dl["offset"]:05x}.png';image.save(folder/name)
            entry=dict(offset=dl['offset'],provenance=dl['provenance'],program=dl.get('program'),image=name,streams=streams,palette_records=[p['record'] for p in candidates],palette_confidence='heuristic nearest records, runtime confirmation required');entries.append(entry);manifest['image_count']+=1
        blockrow=dict(index=index,**row,programs=programs,native_display_count=len(native),lists=entries,errors=errors,rejected_structural_candidates=rejected_candidates);manifest['blocks'].append(blockrow);(folder/'manifest.json').write_text(json.dumps(blockrow,indent=2)+'\n')
    manifest['native_decode_errors']=sum(len(b['errors']) for b in manifest['blocks'])
    manifest['rejected_structural_candidate_count']=sum(len(b['rejected_structural_candidates']) for b in manifest['blocks'])
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(blocks=len(manifest['blocks']),streams=manifest['stream_count'],images=manifest['image_count'],native_programs=manifest['native_program_count'],native_displays=manifest['native_display_count'],native_decode_errors=manifest['native_decode_errors'],rejected_structural_candidates=manifest['rejected_structural_candidate_count'])));return manifest


def render_objects(track,block_index,list_offset,output,frames=None,background_y=0):
    track=Path(track);output=Path(output);data=user_data(track);table=filetable(data);row=table['2'][block_index]
    block=data[row['rec']*2048:(row['rec']+row['sectors'])*2048]
    display=next((dl for dl in display_lists(block,row['bank']) if dl['offset']==list_offset),None)
    if display is None:raise ValueError('Display list not found')
    vram,streams=build_vram(block,display['records']);start=display['records'][-1]['record']+7
    objects=object_initializers(block,start,row['bank'])
    if not objects:raise ValueError('No validated object initializer after display list')
    colors=[(0,0,0)]*512;palettes_used=[];filled=set()
    for pal in sorted(palettes(block,row['bank']),key=lambda x:abs(x['record']-display['offset'])):
        palettes_used.append(pal['record'])
        for k,color in enumerate(pal['colors']):
            target=pal['vce']+k
            if target<512 and target not in filled:
                colors[target]=color;filled.add(target)
    background=screen(vram,colors);image=Image.new('RGB',background.size);image.paste(background,(0,background_y));cells=sprite_pixels(vram);proof=[];errors=[];frames=frames or {}
    for obj in objects:
        script=obj['script'];at=script
        while at+4<len(block) and block[at]>=0xe0 and at-script<128:at+=4
        frame=frames.get(obj['object'],block[at])
        try:result=draw_object(image,vram,colors,block,obj,frame,cells)
        except ValueError as exc:errors.append(dict(object=obj['object'],error=str(exc)));continue
        proof.append(dict(**obj,frame=frame,selected_from_script=at,**result))
    output.parent.mkdir(parents=True,exist_ok=True);image.save(output)
    report=dict(track=str(track.resolve()),object_coordinate_adjustment=[0,-32],background_offset=[0,background_y],block=block_index,rec=row['rec'],list=list_offset,initializer=start,streams=streams,palette_records=palettes_used,objects=proof,errors=errors,
                limitation='Representative static frames. Native animation control token effects and timing not simulated. Palette selection uses nearest candidate records.')
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');return report


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('dump');d.add_argument('--track',type=Path,default=TRACK);d.add_argument('--output',type=Path,default=OUT)
    d=sub.add_parser('objects');d.add_argument('--track',type=Path,default=TRACK);d.add_argument('--block',type=int,required=True);d.add_argument('--list',type=lambda x:int(x,0),required=True);d.add_argument('--frames',default='');d.add_argument('--background-y',type=int,default=0);d.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='dump':dump(a.track,a.output)
    else:
        frames={int(k):int(v) for part in a.frames.split(',') if part for k,v in [part.split(':')]}
        result=render_objects(a.track,a.block,a.list,a.output,frames,a.background_y);print(json.dumps(dict(objects=len(result['objects']),errors=len(result['errors']))))
if __name__=='__main__':main()
