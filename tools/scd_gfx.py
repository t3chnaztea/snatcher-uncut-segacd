#!/usr/bin/env python3
"""Sega CD Snatcher graphics resources: independent codec and VRAM inventory.

Uses module graphics tables, not a scan for plausible compressed byte strings.
PNG stream sheets preserve palette indices; scene previews reconstruct static
background planes. Animated state, scrolling and sprite composition are reported
separately and must be confirmed in the emulator.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'private/extracted/segacd-usa'
OUT=ROOT/'private/work/gfx/segacd'
BASE=0x28000


def digest(data): return hashlib.sha1(data).hexdigest()
def u16(data,offset): return int.from_bytes(data[offset:offset+2],'big')
def u32(data,offset): return int.from_bytes(data[offset:offset+4],'big')


def decode(data, offset, expected=None):
    """Decode LSB-first control groups. Return decoded bytes and consumed end."""
    output=bytearray(); pos=offset; control=0; remaining=0
    while True:
        if not remaining:
            if pos>=len(data): raise ValueError('Missing control byte')
            control=data[pos];pos+=1;remaining=8
        command=control&1;control>>=1;remaining-=1
        if pos>=len(data): raise ValueError('Truncated token')
        token=data[pos];pos+=1
        if not command:
            output.append(token)
        elif token==0x1f:
            if expected is not None and len(output)!=expected: raise ValueError('Decoded length mismatch')
            return bytes(output),pos
        elif token>=0xc0:
            count=token-184
            if pos+count>len(data): raise ValueError('Truncated literal run')
            output.extend(data[pos:pos+count]);pos+=count
        else:
            if token>=0x80:
                count=(token>>4)-6;distance=token&15
            else:
                if pos>=len(data): raise ValueError('Truncated match')
                count=(token&31)+3;distance=((token&0xe0)<<3)|data[pos];pos+=1
            if not distance or distance>len(output): raise ValueError('Invalid match distance')
            for _ in range(count): output.append(output[-distance])
        if len(output)>(expected if expected is not None else 65536): raise ValueError('Decoded output exceeds limit')


def encode(data):
    """Greedy LZ encoder with indexed 3-byte matches and literal-run tokens."""
    groups=[]; tokens=[]; positions=defaultdict(list);pos=0;pending=bytearray()
    def emit(command,payload): tokens.append((command,payload))
    def flush():
        while pending:
            n=min(71,len(pending))
            if n>=8: emit(1,bytes([n+184])+bytes(pending[:n]));del pending[:n]
            else: emit(0,bytes([pending.pop(0)]))
    def remember(start,end):
        for p in range(start,end):
            if p+3<=len(data): positions[data[p:p+3]].append(p)
    while pos<len(data):
        best=0;distance=0
        if pos+3<=len(data):
            candidates=positions[data[pos:pos+3]]
            for previous in reversed(candidates[-128:]):
                d=pos-previous
                if d>0x3ff: break
                count=3
                while count<34 and pos+count<len(data) and data[pos+count]==data[pos+count-d]: count+=1
                # Opcode 1F is reserved for stream termination.
                if count==34 and d<256: count=33
                if count>best: best=count;distance=d
                if best==34: break
        if best>=3:
            flush()
            if distance<=15 and best<=5:
                emit(1,bytes([((best+6)<<4)|distance]))
            else:
                emit(1,bytes([((distance>>8)<<5)|(best-3),distance&255]))
            remember(pos,pos+best);pos+=best
        else:
            pending.append(data[pos]);remember(pos,pos+1);pos+=1
            if len(pending)==71: flush()
    flush();emit(1,b'\x1f')
    for i in range(0,len(tokens),8):
        group=tokens[i:i+8];groups.append(bytes([sum(c<<j for j,(c,_) in enumerate(group))])+b''.join(p for _,p in group))
    return b''.join(groups)


def tile_sheet(data, wide=16, pixel_format=None):
    if pixel_format=='mono-1bpp':
        glyphs=(len(data)+7)//8;im=Image.new('P',(wide*8,max(1,(glyphs+wide-1)//wide)*8));im.putpalette([0,0,0,255,255,255]+[0]*762);px=im.load()
        for off,byte in enumerate(data):
            glyph=off//8;y=off%8
            for x in range(8):px[glyph%wide*8+x,glyph//wide*8+y]=(byte>>(7-x))&1
        return im
    tiles=(len(data)+31)//32; rows=(tiles+wide-1)//wide
    im=Image.new('P',(wide*8,max(1,rows)*8));im.putpalette([v for i in range(256) for v in (min(i,15)*17,)*3])
    px=im.load()
    for t in range(tiles):
        for y in range(8):
            for x in range(8):
                off=t*32+y*4+x//2
                if off<len(data): px[t%wide*8+x,t//wide*8+y]=(data[off]>>(4 if x%2==0 else 0))&15
    return im


def sheet_data(image,length,wide=16,pixel_format=None):
    if pixel_format=='mono-1bpp':
        expected=(wide*8,max(1,((length+7)//8+wide-1)//wide)*8)
        if image.mode!='P' or image.size!=expected:raise ValueError('Font PNG format or dimensions changed')
        px=image.load();out=bytearray()
        for off in range(length):
            glyph=off//8;y=off%8;value=0
            for x in range(8):
                bit=px[glyph%wide*8+x,glyph//wide*8+y]
                if bit>1:raise ValueError('Font pixel index exceeds 1 bpp')
                value|=bit<<(7-x)
            out.append(value)
        return bytes(out)
    if image.mode!='P': raise ValueError('Keep indexed PNG mode P')
    expected=(wide*8,max(1,((length+31)//32+wide-1)//wide)*8)
    if image.size!=expected: raise ValueError('PNG dimensions changed')
    px=image.load();out=bytearray()
    for off in range(length):
        tile=off//32;row=off%32//4;x=(off%4)*2
        a=px[tile%wide*8+x,tile//wide*8+row];b=px[tile%wide*8+x+1,tile//wide*8+row]
        if max(a,b)>15: raise ValueError('Pixel index exceeds 4 bpp')
        out.append(a*16+b)
    return bytes(out)


def sequences(data):
    if len(data)<8 or u32(data,0) not in (BASE+8,BASE+12): return []
    table=u32(data,4)-BASE
    if not 8<=table<len(data)-2: raise ValueError('Invalid graphics table')
    return sequence_table(data,table)


def sequence_table(data,table):
    offsets=[];i=0;bound=len(data)-table
    while i+2<=bound:
        rel=struct.unpack_from('>h',data,table+i)[0]
        if rel<i+2 or table+rel>=len(data): break
        bound=min(bound,rel);offsets.append(rel);i+=2
    result=[]
    for index,rel in enumerate(offsets):
        pos=table+rel;commands=[]
        for _ in range(512):
            if pos>=len(data): raise ValueError('Truncated graphics sequence')
            op=data[pos]
            if op==255: break
            if pos+2>len(data): raise ValueError('Truncated command')
            length=data[pos+1];body=pos+2;end=body+length
            if op>9 or end>len(data): raise ValueError('Invalid graphics command')
            commands.append(dict(op=op,offset=pos,body=body,length=length));pos=end
        else: raise ValueError('Unterminated graphics sequence')
        result.append(dict(index=index,offset=table+rel,commands=commands))
    return result


def resources(data, seqs, base=BASE):
    found={};errors=[]
    for seq in seqs:
        for command in seq['commands']:
            if command['op']!=1: continue
            p=command['body'];end=p+command['length']
            while p+8<=end and u16(data,p)!=65535:
                pointer=u32(data,p)&0xffffff;start=pointer-base;vram=u16(data,p+6)
                if 0<=start<len(data)-2:
                    size=u16(data,start)
                    try:
                        decoded,stop=decode(data,start+2,size)
                        if start not in found: found[start]=dict(offset=start,end=stop,decoded_size=size,sha1=digest(decoded),references=[])
                        found[start]['references'].append(dict(sequence=seq['index'],record=p,vram=vram))
                    except ValueError as e: errors.append(dict(offset=start,record=p,error=str(e)))
                else: errors.append(dict(offset=start,record=p,error='Pointer outside module'))
                p+=8
    return list(found.values()),errors


def supplemental_streams(data,base,known):
    """Find exact-decode streams named by aligned pointer words.

    Pointer candidates are kept separate from graphics-VM transfer evidence.
    They include draw-command resources, but a pointer alone does not prove
    runtime image use or that a candidate is currently reachable.
    """
    found={}
    for p in range(0,len(data)-3,2):
        off=(u32(data,p)&0xffffff)-base
        if off in known or not 0<=off<len(data)-4:continue
        size=u16(data,off)
        if size<32 or size%2:continue
        try:decoded,stop=decode(data,off+2,size)
        except ValueError:continue
        if off not in found:found[off]=dict(offset=off,end=stop,decoded_size=size,sha1=digest(decoded),references=[],usage='pointer_candidate')
        found[off]['references'].append(dict(record=p,pointer_only=True))
    return list(found.values())


def animation_inventory(data,seqs):
    roots=set();draws=[];nodes=[];errors=[]
    for seq in seqs:
        for command in seq['commands']:
            if command['op']!=2:continue
            if command['length']%12:errors.append(dict(offset=command['offset'],error='Animation initializer not 12-byte aligned'))
            for p in range(command['body'],command['body']+command['length']-11,12):
                script=p+12+struct.unpack_from('>h',data,p+10)[0]
                roots.add(script)
    for script in sorted(roots):
        pending=[(0,False)];visited=set()
        while pending:
            index,paused=pending.pop()
            if (index,paused) in visited:continue
            visited.add((index,paused));at=script+index*4
            if not 0<=at<=len(data)-4:
                errors.append(dict(script=script,index=index,error='Animation node outside file'));continue
            op=data[at];node=dict(script=script,index=index,offset=at,opcode=op);nodes.append(node)
            if op>0xaf:
                errors.append(dict(script=script,index=index,error='Unknown animation opcode'));continue
            if op==0x80:continue
            if op in (0x90,0x91,0x92,0x93):paused=True
            if op<0x80 and paused:
                node['paused_exit']=True
                continue
            if op==0x8a:
                target=script+struct.unpack_from('>h',data,at+2)[0];draws.append(dict(offset=target,script=script,node=at))
            if op in (0x81,0x82,0x83):
                pending.append((data[at+1] if op==0x81 else data[at+3],paused))
                if op==0x81:continue
            pending.append((index+1,paused))
    return dict(roots=sorted(roots),nodes=nodes,draw_roots=draws,errors=errors)


def frame_inventory(data,seqs,base=BASE,animation=None):
    animation=animation or animation_inventory(data,seqs);by_script=defaultdict(set)
    for node in animation['nodes']:
        if node['opcode']<128:by_script[node['script']].add(node['opcode'])
    users=defaultdict(list)
    for seq in seqs:
        for command in seq['commands']:
            if command['op']!=2:continue
            for at in range(command['body'],command['body']+command['length']-11,12):
                table=u32(data,at+6)-base;script=at+12+struct.unpack_from('>h',data,at+10)[0]
                users[table].append(dict(sequence=seq['index'],record=at,object=data[at],flags=data[at+1],script=script))
    tables=[];control=[];errors=[];exceptions=[]
    for table,refs in sorted(users.items()):
        visible_refs=[r for r in refs if by_script[r['script']]]
        if not visible_refs:
            control.append(dict(table=table,initializers=refs,reason='No display-frame tokens in associated animation graphs'));continue
        if not 0<=table<len(data)-2:
            errors.append(dict(table=table,error='Sprite table outside file'));continue
        bound=len(data)-table;offsets=[];position=0
        while position+2<=bound and len(offsets)<128:
            rel=struct.unpack_from('>h',data,table+position)[0]
            if rel<position+2 or not 0<=table+rel<len(data):break
            bound=min(bound,rel);offsets.append(rel);position+=2
        frames=[]
        for frame,relative in enumerate(offsets):
            at=table+relative;count=(u16(data,at)+1)&0xffff
            if count>80 or at+2+count*8>len(data):
                errors.append(dict(table=table,frame=frame,error='Invalid sprite frame bounds'));continue
            entries=[]
            for i in range(count):
                p=at+2+i*8;entries.append(dict(offset=p,y=struct.unpack_from('>h',data,p)[0],size=u16(data,p+2),tile=u16(data,p+4),x=struct.unpack_from('>h',data,p+6)[0]))
            frames.append(dict(frame=frame,offset=at,sprites=entries))
        used=set().union(*(by_script[r['script']] for r in visible_refs))
        for frame in sorted(used-set(range(len(offsets)))):
            actual_refs=[r for r in visible_refs if frame in by_script[r['script']]]
            issue=dict(table=table,frame=frame,initializers=actual_refs)
            if all(r['flags']&2 for r in actual_refs):
                issue['reason']='Hidden initializer points at a native frame-index lookup prefix; not a rendered frame definition';exceptions.append(issue)
            else:errors.append(dict(**issue,error='Display token outside sprite frame table'))
        tables.append(dict(table=table,initializers=refs,frames=frames))
    return dict(tables=tables,control_only_tables=control,hidden_lookup_exceptions=exceptions,errors=errors)


def draw_resources(data,offset,base=BASE):
    if not 0<=offset<len(data)-2:raise ValueError('Draw root outside file')
    command=data[offset];kind=command&15;p=offset+2;records=[];streams=[]
    if kind>5:raise ValueError('Unknown draw command kind')
    if kind==5:return [],[dict(offset=offset,command=command,synthetic=True)]
    if command&128:return [],[dict(offset=offset,command=command,buffer_only=True)]
    first=True;source=None
    for _ in range(4096):
        if p+2>len(data):raise ValueError('Truncated draw terminator')
        if u16(data,p)==65535:break
        width=6 if kind==3 and not first else 10
        if p+width>len(data):raise ValueError('Truncated draw record')
        descriptor=p
        if width==10:
            source=u32(data,p)-base;p+=4
        target=u16(data,p);skip=struct.unpack_from('>h',data,p+2)[0];count=u16(data,p+4);p+=6
        if source is None or source<0 or source>=len(data):raise ValueError('Draw source outside file')
        if first or kind in (0,1,2):
            size=u16(data,source) if source<len(data)-2 else None
            if kind==2 or not size:
                if kind!=2 and (not count or skip!=0):raise ValueError('Unhandled zero-size draw resource')
                if source+count>len(data):raise ValueError('Raw draw resource outside file')
                stream=dict(offset=source,end=source+count,decoded_size=count,sha1=digest(data[source:source+count]),compression='none')
            else:
                decoded,stop=decode(data,source+2,size)
                stream=dict(offset=source,end=stop,decoded_size=size,sha1=digest(decoded))
            stream.update(usage='native_draw',references=[dict(draw_root=offset,record=descriptor,vram=target)])
            streams.append(stream)
        records.append(dict(offset=descriptor,command=command,source=source,vram=target,skip=skip,count=count));first=False
        if kind==4:break
    else:raise ValueError('Unterminated draw list')
    return streams,records


NATIVE_DRAW_ROOTS={
    'SUBCODE.BIN':[(addr-0xd400) for addr in (0xecb6,0xecc4,0x11ed8,0x11ee6,0x11ef4,0x11f02,0x14b4e,0x12ea8)],
    'DATA_D2.BIN':[0x29806-BASE],
}
NATIVE_DRAW_TABLES={'DATA_D2.BIN':[(0x29142,21,0),(0x29412,21,1),(0x29292,24,0),(0x29554,24,1),(0x296c6,20,0)]}


def native_draw_roots(data,name):
    roots=list(NATIVE_DRAW_ROOTS.get(name,[]))
    for address,count,first in NATIVE_DRAW_TABLES.get(name,[]):
        table=address-BASE
        for i in range(first,count):roots.append(table+struct.unpack_from('>h',data,table+i*2)[0])
    return sorted(set(roots))


def stream_bytes(data,stream):
    if stream.get('compression')=='none':return bytes(data[stream['offset']:stream['end']])
    return decode(data,stream['offset']+2,stream['decoded_size'])[0]


def unreferenced_streams(data,known):
    spans=sorted((s['offset'],s['end']) for s in known);gaps=[];pos=0
    for start,end in spans:
        if start>pos:gaps.append((pos,start))
        pos=max(pos,end)
    if pos<len(data):gaps.append((pos,len(data)))
    out=[]
    for low,high in gaps:
        off=(low+1)//2*2
        while off+4<=high:
            size=u16(data,off)
            if size>=32 and size%32==0:
                try:decoded,stop=decode(data,off+2,size)
                except ValueError:stop=high+1
                if stop<=high:
                    out.append(dict(offset=off,end=stop,decoded_size=size,sha1=digest(decoded),references=[],usage='unreferenced_candidate'))
                    off=(stop+1)//2*2;continue
            off+=2
    return out


def inventory(data,name):
    is_module=name.startswith('DATA_')
    seqs=sequences(data) if is_module else sequence_table(data,0x146ce-0xd400) if name=='SUBCODE.BIN' else []
    if name=='SUBCODE.BIN':
        body=0xed0e-0xd400;length=0
        while data[body+length]!=255:
            length+=12
            if length>1200:raise ValueError('Native initializer unterminated')
        seqs.append(dict(index=len(seqs),offset=body,commands=[dict(op=2,offset=body,body=body,length=length)],native_initializer=True))
    streams,errors=resources(data,seqs,0xd400 if name=='SUBCODE.BIN' else BASE)
    for stream in streams:stream['usage']='module_transfer'
    animation=animation_inventory(data,seqs) if seqs else dict(errors=[],draw_roots=[])
    errors.extend(animation['errors'])
    known={s['offset']:s for s in streams}
    draw_roots=animation['draw_roots']+[dict(offset=r) for r in native_draw_roots(data,name)]
    for root in draw_roots:
        try:extra,_=draw_resources(data,root['offset'],0xd400 if name=='SUBCODE.BIN' else BASE)
        except ValueError as e:
            errors.append(dict(offset=root['offset'],error=str(e),kind='animation_draw'));continue
        for stream in extra:
            if stream['offset'] in known:known[stream['offset']]['references'].extend(stream['references'])
            else:streams.append(stream);known[stream['offset']]=stream
    if is_module or name=='SUBCODE.BIN':
        streams.extend(supplemental_streams(data,BASE if is_module else 0xd400,{s['offset'] for s in streams}))
    if is_module or name=='SUBCODE.BIN':
        streams.extend(unreferenced_streams(data,streams))
    if name=='SUBCODE.BIN':
        start=0x14b7c-0xd400;length=816
        streams.append(dict(offset=start,end=start+length,decoded_size=length,sha1=digest(data[start:start+length]),references=[dict(source='snatcher.cpp setTextFont',address=0x14b7c)],usage='native_font',compression='none',pixel_format='mono-1bpp'))
    if name=='_boot.bin':
        for off in range(0,len(data)-4,2):
            size=u16(data,off)
            if size<32 or size%32:continue
            try:decoded,stop=decode(data,off+2,size)
            except ValueError:continue
            kind,address={0x1d9e:('tiles',0),0x26b4:('tilemap',0xe000),0x27c8:('tilemap',0xc000),0x2a6e:('font_tiles',0x2000)}.get(off,('unknown',None))
            streams.append(dict(offset=off,end=stop,decoded_size=size,sha1=digest(decoded),references=[dict(vram=address,evidence='boot runtime VRAM differential')] if address is not None else [],usage='native_boot' if address is not None else 'boot_candidate',resource_kind=kind))
    for stream in streams:
        stream.setdefault('compression','scd-lz');stream.setdefault('pixel_format','packed-4bpp')
        stream.setdefault('resource_kind','font' if stream['usage']=='native_font' else 'tilemap' if stream['references'] and all(r.get('vram') in (0xc000,0xe000) for r in stream['references']) else 'tiles_or_mixed')
    return seqs,streams,errors


def palette(data,commands,previous=None,base=BASE):
    colors=list(previous or [(0,0,0)]*64);records=[]
    for cmd in commands:
        if cmd['op']!=0 or cmd['length']<8: continue
        body=cmd['body'];kind=data[body]&0x7f
        if kind not in (1,2,9): continue
        dest=(data[body+2]>>1)&63;count=data[body+3]+1;off=u32(data,body+4)-base
        if not 0<=off<=len(data)-count*2:continue
        records.append(dict(command=cmd['offset'],offset=off,destination=dest,count=count))
        for k in range(min(count,64-dest)):
            word=u16(data,off+2*k);colors[dest+k]=tuple(((word>>shift)&7)*255//7 for shift in (1,5,9))
    return colors,records


def compose(vram,colors,plane=0xe000,columns=32,rows=28):
    im=Image.new('RGB',(256,rows*8));px=im.load()
    for table in (0xc000,plane):
        for y in range(rows):
            for x in range(32):
                word=u16(vram,table+(y*columns+x)*2);tile=word&0x7ff;pal=(word>>13)&3
                for yy in range(8):
                    for xx in range(8):
                        sx=7-xx if word&0x800 else xx;sy=7-yy if word&0x1000 else yy
                        off=tile*32+sy*4+sx//2
                        value=vram[off]>>(0 if sx&1 else 4)&15
                        if value:px[x*8+xx,y*8+yy]=colors[pal*16+value]
    return im


def initial_animation_state(data,script,x,y):
    index=0;visited=set();palette=None;draw_flags=0
    while index not in visited:
        visited.add(index);at=script+index*4
        if not 0<=at<=len(data)-4:return None
        op=data[at]
        if op<128:return dict(frame=op,x=x,y=y,palette=palette,draw_flags=draw_flags,node=at)
        if op==0x80:return None
        if op==0x81:index=data[at+1];continue
        if op==0x82 and data[at+1]!=0:index=data[at+3];continue
        if op==0x83:index=data[at+3];continue
        if op==0x84:x=struct.unpack_from('>h',data,at+2)[0]
        if op==0x85:y=struct.unpack_from('>h',data,at+2)[0]
        if op in (0xa0,0xa1):draw_flags=u16(data,at+2)
        if op==0xa7:palette=data[at+1]
        index+=1
    return None


def sprite_frames(data,commands,base=BASE):
    result=[]
    for command in commands:
        if command['op']!=2:continue
        for p in range(command['body'],command['body']+command['length']-11,12):
            obj,flags=data[p:p+2];x=struct.unpack_from('>h',data,p+2)[0];y=struct.unpack_from('>h',data,p+4)[0]
            table=u32(data,p+6)-base;script=p+12+struct.unpack_from('>h',data,p+10)[0]
            if not 0<=script<len(data) or not 0<=table<len(data)-2:continue
            state=initial_animation_state(data,script,x,y)
            if state is None:continue
            frame=state['frame'];x=state['x'];y=state['y'];palette_override=state['palette'];draw_flags=state['draw_flags']
            if table+frame*2+2>len(data):continue
            at=table+struct.unpack_from('>h',data,table+frame*2)[0]
            if not 0<=at<len(data)-2:continue
            count=(u16(data,at)+1)&0xffff
            if count>80 or at+2+count*8>len(data):continue
            records=[]
            for k in range(count):
                off=at+2+k*8;dy=struct.unpack_from('>h',data,off)[0];size=u16(data,off+2);tile=u16(data,off+4);dx=struct.unpack_from('>h',data,off+6)[0]
                if draw_flags&1:dx=-dx-(((size>>10)&3)+1)*8
                if draw_flags&2:dy=-dy-(((size>>8)&3)+1)*8
                tile^=(draw_flags&3)<<11
                if palette_override is not None and palette_override&128:tile=(tile&0x9fff)|((palette_override&3)<<13)
                records.append(dict(x=x+dx,y=y+dy,width=((size>>10)&3)+1,height=((size>>8)&3)+1,tile=tile))
            result.append(dict(object=obj,record=p,script=script,frame=frame,frame_table=table,frame_data=at,initial_state=state,sprites=records))
    return result


def draw_sprites(image,vram,colors,objects):
    px=image.load()
    for obj in reversed(objects):
        for sprite in obj['sprites']:
            w=sprite['width']*8;h=sprite['height']*8;word=sprite['tile'];palette=(word>>13)&3
            for yy in range(h):
                for xx in range(w):
                    x=sprite['x']+xx;y=sprite['y']+yy
                    if not (0<=x<image.width and 0<=y<image.height):continue
                    sx=w-1-xx if word&0x800 else xx;sy=h-1-yy if word&0x1000 else yy
                    tile=((word&0x7ff)+(sx//8)*sprite['height']+sy//8)&0x7ff
                    off=tile*32+(sy%8)*4+(sx%8)//2
                    value=vram[off]>>(0 if sx&1 else 4)&15
                    if value:px[x,y]=colors[palette*16+value]
    return image


def dump(source=SOURCE,output=OUT):
    source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    manifest=dict(version=2,source=str(source.resolve()),files=[],stream_count=0,preview_count=0,transfer_stream_count=0,candidate_stream_count=0,native_stream_count=0,coverage='Module transfer streams complete; pointer/boot candidates supplemental; full scene composition not yet verified')
    paths=sorted(source.glob('*.BIN'))+[source/'_boot.bin']
    for path in paths:
        data=path.read_bytes()
        seqs,streams,errors=inventory(data,path.name)
        manifest['transfer_stream_count']+=sum(v['usage']=='module_transfer' for v in streams)
        manifest['candidate_stream_count']+=sum(v['usage'] in ('pointer_candidate','boot_candidate','unreferenced_candidate') for v in streams)
        manifest['native_stream_count']+=sum(v['usage'].startswith('native_') for v in streams)
        folder=output/path.stem;folder.mkdir(exist_ok=True)
        for stream in streams:
            decoded=stream_bytes(data,stream)
            name=f'stream_{stream["offset"]:06x}'
            tile_sheet(decoded,pixel_format=stream['pixel_format']).save(folder/(name+'.png'))
            stream.update(file=path.name,width=128,height=tile_sheet(decoded,pixel_format=stream['pixel_format']).height,
                          image=name+'.png',palette='diagnostic index ramp; scene palettes in previews')
            (folder/(name+'.json')).write_text(json.dumps(stream,indent=2)+'\n')
        previews=[];vram=bytearray(65536);colors=[(0,0,0)]*64;baseline_vram=None;baseline_colors=None;baseline_objects=[]
        for seq in seqs:
            if baseline_vram is not None:
                vram=bytearray(baseline_vram);colors=list(baseline_colors)
            resets_planes=any(ref.get('sequence')==seq['index'] and ref.get('vram') in (0xc000,0xe000) for stream in streams for ref in stream['references'])
            if resets_planes:
                vram[0xc000:0xd000]=bytes(4096);vram[0xe000:0xf000]=bytes(4096)
            for stream in streams:
                for ref in stream['references']:
                    if ref.get('sequence')==seq['index']:
                        payload=stream_bytes(data,stream);a=ref['vram'];vram[a:min(a+len(payload),65536)]=payload[:65536-a]
            colors,pals=palette(data,seq['commands'],colors,0xd400 if path.name=='SUBCODE.BIN' else BASE)
            objects=sprite_frames(data,seq['commands'],0xd400 if path.name=='SUBCODE.BIN' else BASE)
            if baseline_vram is None:
                baseline_vram=bytes(vram);baseline_colors=list(colors);baseline_objects=objects
            elif not resets_planes:
                replacements={obj['object']:obj for obj in baseline_objects}
                replacements.update({obj['object']:obj for obj in objects});objects=list(replacements.values())
            image=draw_sprites(compose(vram,colors),vram,colors,objects)
            name=f'seq_{seq["index"]:03d}.png';image.save(folder/name)
            previews.append(dict(sequence=seq['index'],image=name,palette_records=pals,sprite_objects=objects,
                                 limitation='Static planes A/B plus initial sprite frames; sequence 0 baseline for deltas; full-map programs clear planes; runtime scroll not applied'))
        animation=animation_inventory(data,seqs);frame_defs=frame_inventory(data,seqs,0xd400 if path.name=='SUBCODE.BIN' else BASE,animation)
        row=dict(file=path.name,size=len(data),sha1=digest(data),streams=streams,sequences=seqs,previews=previews,errors=errors,animation=animation,sprite_frames=frame_defs,native_draw_roots=native_draw_roots(data,path.name))
        (folder/'manifest.json').write_text(json.dumps(row,indent=2)+'\n');manifest['files'].append(row)
        manifest['stream_count']+=len(streams);manifest['preview_count']+=len(previews)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(files=len(manifest['files']),streams=manifest['stream_count'],previews=manifest['preview_count'],transfer_streams=manifest['transfer_stream_count'],candidate_streams=manifest['candidate_stream_count'],native_streams=manifest['native_stream_count'],errors=sum(len(f['errors']) for f in manifest['files']))))
    return manifest


def insert(work=OUT,output=ROOT/'private/work/gfx/segacd-reinserted'):
    work=Path(work);output=Path(output)
    manifest=json.loads((work/'manifest.json').read_text());source=Path(manifest['source'])
    if output.resolve()==source.resolve():raise ValueError('Cannot overwrite source directory')
    expected_files={p.name for p in source.glob('*.BIN')}|{'_boot.bin'}
    rows=manifest['files']
    if len(rows)!=len(expected_files) or {r['file'] for r in rows}!=expected_files:
        raise ValueError('Manifest source file inventory changed')
    validated=[]
    fields=('offset','end','decoded_size','sha1','references','usage','compression','pixel_format','resource_kind')
    # Validate every source and every stream before creating any output file.
    for row in rows:
        if Path(row['file']).name!=row['file']:raise ValueError('Unsafe source filename')
        original=(source/row['file']).read_bytes()
        if len(original)!=row['size'] or digest(original)!=row['sha1']:raise ValueError('Source hash or size changed')
        _,expected_streams,errors=inventory(original,row['file'])
        if errors:raise ValueError('Source graphics inventory has decode errors')
        expected={s['offset']:s for s in expected_streams}
        if len(row['streams'])!=len(expected) or {s['offset'] for s in row['streams']}!=set(expected):
            raise ValueError('Manifest stream inventory changed')
        changes=[]
        for stream in row['streams']:
            if any(stream.get(k)!=expected[stream['offset']].get(k) for k in fields):
                raise ValueError('Manifest stream metadata changed')
            if Path(stream['image']).name!=stream['image']:raise ValueError('Unsafe image filename')
            image_path=work/Path(row['file']).stem/stream['image']
            with Image.open(image_path) as image:data=sheet_data(image,stream['decoded_size'],pixel_format=stream['pixel_format'])
            if digest(data)==stream['sha1']:continue
            for other in row['streams']:
                if other['offset']==stream['offset']:continue
                if stream['offset']<other['end'] and other['offset']<stream['end']:
                    raise ValueError(f'{row["file"]}@{stream["offset"]:x}: edit overlaps declared stream @{other["offset"]:x}; resolve shared resource before editing')
            prefix=0 if stream['compression']=='none' else 2
            encoded=data if not prefix else encode(data);capacity=stream['end']-stream['offset']-prefix
            if len(encoded)>capacity:raise ValueError(f'{row["file"]}@{stream["offset"]:x}: compressed edit needs {len(encoded)} bytes; capacity {capacity}')
            changes.append((stream,encoded,data))
        validated.append((row,original,changes))
    output.mkdir(parents=True,exist_ok=True);report=[]
    for row,original,changes in validated:
        result=bytearray(original);changed=[]
        for stream,encoded,data in changes:
            begin=stream['offset']+(0 if stream['compression']=='none' else 2);capacity=stream['end']-begin
            result[begin:stream['end']]=encoded+bytes(capacity-len(encoded));changed.append(stream['offset'])
            if stream_bytes(result,stream)!=data:raise ValueError('Encoded edit failed self verification')
        (output/row['file']).write_bytes(result);report.append(dict(file=row['file'],sha1=digest(result),identical=bytes(result)==original,changed_streams=changed))
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(files=len(report),identical=sum(r['identical'] for r in report),changed=sum(not r['identical'] for r in report))))
    return report


def audit(work=OUT,output=ROOT/'build/gfx-coverage.json'):
    work=Path(work);manifest=json.loads((work/'manifest.json').read_text());source=Path(manifest['source'])
    counts=defaultdict(int);issues=[];files=[];exceptions=[]
    expected_files={p.name for p in source.glob('*.BIN')}|{'_boot.bin'}
    if len(manifest['files'])!=len(expected_files) or {r['file'] for r in manifest['files']}!=expected_files:
        issues.append(dict(error='Source file universe mismatch'))
    for row in manifest['files']:
        original=(source/row['file']).read_bytes()
        if digest(original)!=row['sha1'] or len(original)!=row['size']:issues.append(dict(file=row['file'],error='Source identity changed'))
        _,expected,inventory_errors=inventory(original,row['file'])
        if inventory_errors:issues.extend(dict(file=row['file'],**e) for e in inventory_errors)
        actual={s['offset']:s for s in row['streams']}
        if set(actual)!={s['offset'] for s in expected}:issues.append(dict(file=row['file'],error='Stream inventory mismatch'))
        for stream in expected:
            meta=actual.get(stream['offset'])
            if meta is None:continue
            for key in ('end','decoded_size','sha1','usage','compression','pixel_format','resource_kind','references'):
                if stream.get(key)!=meta.get(key):issues.append(dict(file=row['file'],offset=stream['offset'],error='Metadata mismatch',field=key))
            with Image.open(work/Path(row['file']).stem/meta['image']) as image:
                raw=sheet_data(image,stream['decoded_size'],pixel_format=stream['pixel_format'])
            if digest(raw)!=stream['sha1']:issues.append(dict(file=row['file'],offset=stream['offset'],error='PNG omitted or changed resource bytes'))
            counts['resource_pngs']+=1;counts['decoded_bytes']+=stream['decoded_size'];counts[stream['usage']]+=1;counts['compression_'+stream['compression']]+=1
        spans=sorted((s['offset'],s['end']) for s in row['streams'])
        for (a,b),(c,d) in zip(spans,spans[1:]):
            if c<b:issues.append(dict(file=row['file'],offset=c,error='Overlapping declared resources'))
        animation=animation_inventory(original,row['sequences']);frame_defs=frame_inventory(original,row['sequences'],0xd400 if row['file']=='SUBCODE.BIN' else BASE,animation)
        counts['graphics_programs']+=len(row['sequences']);counts['animation_roots']+=len(animation['roots']);counts['animation_nodes']+=len(animation['nodes']);counts['animation_draw_references']+=len(animation['draw_roots']);counts['native_draw_roots']+=len(native_draw_roots(original,row['file']));counts['sprite_frame_tables']+=len(frame_defs['tables']);counts['sprite_frame_definitions']+=sum(len(t['frames']) for t in frame_defs['tables']);counts['control_only_tables']+=len(frame_defs['control_only_tables']);counts['hidden_lookup_exceptions']+=len(frame_defs['hidden_lookup_exceptions'])
        for table in frame_defs['tables']:
            counts['empty_sprite_frames']+=sum(not f['sprites'] for f in table['frames'])
        issues.extend(dict(file=row['file'],**e) for e in animation['errors']+frame_defs['errors'])
        exceptions.extend(dict(file=row['file'],**e) for e in frame_defs['hidden_lookup_exceptions'])
        files.append(dict(file=row['file'],sha1=row['sha1'],size=row['size'],resource_pngs=len(row['streams']),graphics_programs=len(row['sequences'])))
    report=dict(source_files=len(files),counts=dict(counts),issues=issues,hidden_lookup_exceptions=exceptions,files=files,
                universe='All 53 DATA module graphics-program tables, SUBCODE item/UI graphics programs and native initializer, animation draw references, direct native draw roots and D2 indexed draw tables, native font, four runtime-confirmed boot transfers, and aligned exact-decode LZ scans of uncovered DATA/SUBCODE regions.',
                limits=['Static scene previews are not runtime reachability or timing proofs.','Hidden frame-index lookup prefixes are listed separately from image-frame definitions.','Unreferenced raw graphics outside known roots are not recognizable by a compressed-stream scan. No such omitted graphic is currently identified.'])
    Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(source_files=len(files),counts=dict(counts),issues=len(issues))))
    if issues:raise ValueError('Graphics coverage audit failed')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('dump');p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,default=OUT)
    p=sub.add_parser('insert');p.add_argument('--work',type=Path,default=OUT);p.add_argument('--output',type=Path,default=ROOT/'private/work/gfx/segacd-reinserted')
    p=sub.add_parser('audit');p.add_argument('--work',type=Path,default=OUT);p.add_argument('--output',type=Path,default=ROOT/'build/gfx-coverage.json')
    a=parser.parse_args()
    if a.command=='dump':dump(a.source,a.output)
    elif a.command=='insert':insert(a.work,a.output)
    else:audit(a.work,a.output)
if __name__=='__main__':main()
