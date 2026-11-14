#!/usr/bin/env python3
"""Dump and edit Sega CD script text without changing bytecode or extents.

SP00-SP38 use a fixed 0x3800-byte bytecode region followed by FF-terminated
ASCII strings. SP31 is a short, text-free module. Script controls are byte
escapes ({F2} is a line break; {F6} is a page break). Direct renderer strings
have a different control grammar and are not treated as script strings.

Insertion requires each encoded string to retain its original byte length.
Growth requires verified relocation of every bytecode reference, which this
fixed-layout editor deliberately rejects rather than guessing pointers.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import source_text_recipe

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'private/extracted/segacd-usa'
DUMPS = ROOT/'private/work/text'
TEXT_START = 0x3800
FILE_LIMIT = 55296


def digest(data):
    return hashlib.sha1(data).hexdigest()


def decode(data):
    # Escape braces as well as non-ASCII bytes, so parsing is unambiguous.
    return ''.join(chr(b) if 32 <= b <= 126 and b not in (123,125)
                   else '{%02X}' % b for b in data)


def encode(text):
    output = bytearray()
    position = 0
    while position < len(text):
        if text[position] == '{':
            match = re.match(r'\{([0-9A-Fa-f]{2})\}',text[position:])
            if not match:
                raise ValueError('Controls must use a two-digit byte escape, such as {F2}')
            output.append(int(match[1],16));position += 4
        else:
            b = ord(text[position])
            if not 32 <= b <= 126 or b == 125:
                raise ValueError('Only printable ASCII and explicit byte escapes are supported')
            output.append(b);position += 1
    return bytes(output)


def pool(data):
    if len(data) < TEXT_START:
        return [], data
    entries = []
    position = TEXT_START
    while position < len(data):
        end = data.find(b'\xff',position)
        if end < 0:
            if data[position:] not in (b'',b'\0'):
                raise ValueError(f'Unterminated pool data at {position:#x}')
            break
        raw = data[position:end]
        entries.append(dict(id=len(entries),offset=position,
                            relative_offset=position-TEXT_START,length=len(raw),
                            raw=raw.hex(),sha1=digest(raw),text=decode(raw),
                            controls=[dict(offset=i,byte=f'{b:02X}')
                                      for i,b in enumerate(raw) if b>=0xec or b<32]))
        position = end+1
    return entries,data[position:]


def references(data, entry):
    """Byte-pattern candidates, recorded as evidence but never used to relocate."""
    offset = entry['relative_offset'].to_bytes(2,'big')
    code = data[:TEXT_START]
    found = []
    for pattern,kind,displacement in ((b'\x38'+offset,'menu',1),
                                      (b'\x44'+offset,'anonymous-dialogue',1)):
        for m in re.finditer(re.escape(pattern),code):
            found.append(dict(offset=m.start()+displacement,kind=kind))
    for m in re.finditer(b'\x43\x20\x00[\x01-\x7f]'+re.escape(offset),code):
        found.append(dict(offset=m.start()+4,kind='speaker-dialogue',speaker=code[m.start()+3]))
    return found



def speakers(source=SOURCE):
    """SUBCODE's 48 dialogue-heading slots, signed offsets from table 0x6152."""
    data=(Path(source)/'SUBCODE.BIN').read_bytes()
    table=0x6152;rows=[];source_sha1=digest(data)
    for slot in range(48):
        relative=int.from_bytes(data[table+slot*2:table+slot*2+2],'big',signed=True)
        start=table+relative
        if not 0x5f9e<=start<0x6152:
            raise ValueError('Unexpected speaker-table pointer')
        end=data.find(b'\xff',start,0x6152)
        if end<0:
            raise ValueError('Unterminated speaker heading')
        raw=data[start:end]
        # Empty slot zero points directly at FF. Nonempty entries begin with a
        # packed attribute byte (low 3 bits select the heading colour).
        rows.append(dict(id=slot,file='SUBCODE.BIN',table_offset=table+slot*2,
                         offset=start,attribute=raw[0] if raw else None,
                         raw=raw.hex(),text=decode(raw[1:]) if raw else '',
                         source_sha1=source_sha1,source_size=len(data)))
    return rows


def insert_speakers(dumps=DUMPS,source=SOURCE,output=ROOT/'build/speaker-roundtrip'):
    """Edit only fixed-length heading text; preserve attributes and signed pointers."""
    dumps,source,output=Path(dumps),Path(source),Path(output)
    name='SUBCODE.BIN';destination=output/name
    if destination.resolve()==(source/name).resolve():
        raise ValueError('Output must not overwrite an extracted source file')
    original=(source/name).read_bytes()
    actual=speakers(source)
    rows=json.loads((dumps/'speakers.json').read_text())
    if not isinstance(rows,list) or len(rows)!=len(actual):
        raise ValueError('Speaker insertion requires all 48 heading slots')
    result=bytearray(original);changed=[]
    for authoritative,row in zip(actual,rows):
        if not isinstance(row,dict):
            raise ValueError('Invalid speaker-heading record')
        for key in ('source_sha1','source_size'):
            if authoritative[key]!=row.get(key):
                raise ValueError('SUBCODE.BIN: source no longer matches speaker dump')
        for key in ('id','file','table_offset','offset','attribute','raw'):
            if authoritative[key]!=row.get(key):
                raise ValueError(f'SUBCODE.BIN: immutable speaker metadata changed ({key})')
        new=encode(row['text'])
        old=bytes.fromhex(authoritative['raw'])[1:]
        if b'\xff' in new:
            raise ValueError('Speaker heading contains an embedded terminator')
        if len(new)!=len(old):
            raise ValueError(f'Speaker {row["id"]}: fixed-length edit requires {len(old)} bytes; got {len(new)}. Growth or shrinkage requires verified heading relocation.')
        if new!=old:
            changed.append(row['id'])
        start=authoritative['offset']+1
        result[start:start+len(new)]=new
    output.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(result)
    return dict(file=name,sha1=digest(result),identical=result==original,changed=changed)


def dump(source=SOURCE, output=DUMPS):
    source,output = Path(source),Path(output)
    output.mkdir(parents=True,exist_ok=True)
    counts = {}; control_counts=Counter()
    files = sorted(source.glob('SP[0-9][0-9].BIN'))
    if len(files)!=39:
        raise ValueError(f'Expected 39 SP modules, found {len(files)}')
    for path in files:
        data = path.read_bytes()
        entries,tail = pool(data)
        for entry in entries:
            entry['reference_candidates'] = references(data,entry)
            control_counts.update(f'{b:02X}' for b in bytes.fromhex(entry['raw']) if b>=0xec)
        record = dict(version=1,file=path.name,size=len(data),sha1=digest(data),
                      pool_start=TEXT_START if entries else None,tail=tail.hex(),strings=entries)
        (output/(path.stem+'.json')).write_text(json.dumps(record,indent=2)+'\n')
        counts[path.name]=len(entries)
    names=speakers(source)
    (output/'speakers.json').write_text(json.dumps(names,indent=2)+'\n')
    summary=dict(files=len(files),strings=sum(counts.values()),speaker_slots=len(names),speaker_names=sum(bool(r['text']) for r in names),counts=counts,control_counts=dict(control_counts))
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def insert(dumps=DUMPS, source=SOURCE, output=ROOT/'build/text-roundtrip'):
    dumps,source,output=Path(dumps),Path(source),Path(output)
    report=[]
    paths=sorted(dumps.glob('SP[0-9][0-9].json'))
    expected={f'SP{i:02}.json' for i in range(39)}
    if {p.name for p in paths}!=expected:
        raise ValueError('Full insertion requires all 39 SP dump files (SP00 through SP38)')
    for path in paths:
        record=json.loads(path.read_text())
        name=record['file']
        if not re.fullmatch(r'SP[0-9][0-9]\.BIN',name) or name!=path.stem+'.BIN':
            raise ValueError('Invalid source file name')
        if (output/name).resolve()==(source/name).resolve():
            raise ValueError('Output must not overwrite an extracted source file')
        original=(source/name).read_bytes()
        if digest(original)!=record['sha1'] or len(original)!=record['size']:
            raise ValueError(f'{name}: source no longer matches dump')
        authoritative,_=pool(original)
        if len(authoritative)!=len(record['strings']):
            raise ValueError(f'{name}: string inventory changed')
        result=bytearray(original);changed=[]
        for actual,entry in zip(authoritative,record['strings']):
            for key in ('id','offset','relative_offset','length','raw','sha1'):
                if actual[key]!=entry[key]:
                    raise ValueError(f'{name}: immutable string metadata changed ({key})')
            new=encode(entry['text'])
            if b'\xff' in new:
                raise ValueError(f'{name}:{entry["id"]}: embedded terminator')
            if len(new)!=entry['length']:
                raise ValueError(f'{name}:{entry["id"]}: fixed-length edit requires {entry["length"]} bytes; got {len(new)}. Growth or shrinkage requires verified bytecode relocation.')
            if new!=bytes.fromhex(entry['raw']):
                changed.append(entry['id'])
            start=entry['offset'];result[start:start+len(new)]=new
        if len(result)>FILE_LIMIT:
            raise ValueError(f'{name}: exceeds the 55,296-byte module buffer limit')
        output.mkdir(parents=True,exist_ok=True)
        (output/name).write_bytes(result)
        report.append(dict(file=name,sha1=digest(result),identical=result==original,changed=changed))
    if not report:
        raise ValueError('No SP dump files found')
    return report


def scan_external(source=SOURCE,output=ROOT/'private/work/text/external-candidates.json'):
    """Find FF-terminated ASCII runs outside SP pools for manual review.

    This is an inventory of candidates, not a claim that arbitrary ASCII in
    binary/audio data is displayed. PCM files are excluded explicitly.
    """
    rows=[]
    for path in sorted(Path(source).glob('*.BIN')):
        if path.name.startswith(('SP','PCM')):
            continue
        data=path.read_bytes()
        for match in re.finditer(rb'[\x20-\x7e]{4,}\xff',data):
            rows.append(dict(file=path.name,offset=match.start(),length=len(match[0])-1,
                             text=decode(match[0][:-1]),raw=match[0].hex(),classification='unverified-direct-renderer-candidate'))
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(rows,indent=2)+'\n')
    return dict(candidates=len(rows),files=len({r['file'] for r in rows}))




def _read_pce_track(track=None,cue=None):
    track=Path(track or ROOT/'private/discs/pcenginecd-jp/Snatcher CD-ROMantic (Japan) (Track 02).bin')
    cues=list(track.parent.glob('*.cue'))
    if cue is None and len(cues)!=1:
        raise ValueError('PCE reference dump requires an unambiguous CUE file')
    cue=Path(cue or cues[0])
    cue_text=cue.read_text()
    block=re.search(r'FILE \"'+re.escape(track.name)+r'\" BINARY(.*?)(?=FILE|\Z)',cue_text,re.S)
    if not block or not re.search(r'TRACK 02 MODE1/2352',block[1]):
        raise ValueError('PCE CUE does not identify the supplied file as track 02 MODE1/2352')
    start=re.search(r'INDEX 01 (\d+):(\d+):(\d+)',block[1])
    if not start:
        raise ValueError('PCE CUE track 02 has no INDEX 01')
    m,s,f=map(int,start.groups());pregap=(m*60+s)*75+f
    raw=track.read_bytes()
    data=b''.join(raw[i+16:i+2064] for i in range(pregap*2352,len(raw),2352))
    return data,pregap,cue

def reference_pce(track=None, reference=None, output=None, cue=None):
    """Read the staged PCE script using the MIT reference project's codec.

    Translation strings remain private. Scene numbers are not assumed to map
    to Sega CD SP numbers. Every module boundary is checked against disc bytes.
    """
    import importlib
    import sys
    track=Path(track or ROOT/'private/discs/pcenginecd-jp/Snatcher CD-ROMantic (Japan) (Track 02).bin')
    reference=Path(reference or ROOT/'.deps/snatcher-translated')
    output=Path(output or ROOT/'private/work/text/pce')
    if not (reference/'pce/tools/pcescript.py').is_file():
        raise ValueError('Read-only .deps/snatcher-translated PCE tools are required')
    sys.path.insert(0,str(reference/'pce/tools'))
    cache_writes_disabled=sys.dont_write_bytecode
    sys.dont_write_bytecode=True
    try:
        codec=importlib.import_module('pcescript')
    finally:
        sys.dont_write_bytecode=cache_writes_disabled
    data,pregap,cue=_read_pce_track(track,cue)
    stage=data[22*2048:37*2048]
    translations={};source_for={}
    for name in ('dialogue.json','dialogue_hand.json'):
        entries=json.loads((reference/'pce/translation'/name).read_text())
        translations.update(entries);source_for.update({key:name for key in entries})
    output.mkdir(parents=True,exist_ok=True)
    summary=[]
    for index in range(33):
        position=0x1535+index*8
        entry=stage[position:position+8]
        rec=entry[0]*65536+entry[2]*256+entry[1]
        if rec!=158+16*index or entry[3]!=4 or not 0<entry[6]<=16:
            raise ValueError(f'Unexpected PCE scene-table record {index}')
        sectors=entry[6];module=data[rec*2048:(rec+sectors)*2048]
        strings,bad=codec.strings_of(module)
        if bad:
            raise ValueError(f'PCE record {rec}: references are not string boundaries')
        rows=[]
        for offset,jp in strings:
            key=codec.key(jp)
            rows.append(dict(offset=offset,jp=jp,key=key,
                             english_reference=translations.get(key),english_source=source_for.get(key)))
        record=dict(rec=rec,sectors=sectors,sha1=digest(module),bad_refs=bad,strings=rows)
        (output/f'{rec}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
        summary.append(dict(rec=rec,sectors=sectors,strings=len(rows),translated=sum(r['english_reference'] is not None for r in rows)))
    report=dict(cue=str(cue),pregap_sectors=pregap,modules=len(summary),strings=sum(r['strings'] for r in summary),
                translated=sum(r['translated'] for r in summary),records=summary)
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    return report



def parse_pce_expressions(module,table,limit):
    """Read expression boundaries, not runtime flag values or reachability.

    Descriptor nibbles come from the resident engine at file offset 0x2df9.
    The native evaluator at $898f extracts the modes. $9bd6 is a special
    execute-next prefix whose descriptor contains unused fields. Native RTS
    handlers similarly consume no operands. All remaining widths use the
    engine's descriptors: mode 4 is a child; 0/7 have no encoded operand;
    other unflagged modes use a little-endian word. Mode 8 saves a branch
    continuation word before the operands. Branch bodies are parsed fully.
    """
    nodes={};roles={}
    def mark(position,length,role):
        for offset in range(position,position+length):
            if offset in roles:
                raise ValueError(f'Overlapping expression bytes at {offset:#x}')
            roles[offset]=role
    def word(position):
        if position+2>limit:
            raise ValueError(f'Operand crosses code boundary at {position:#x}')
        return int.from_bytes(module[position:position+2],'little')
    def expression(position,depth=0):
        if depth>150:
            raise ValueError('Expression nesting exceeds 150')
        if position in nodes:
            return nodes[position]['end']
        if position>=limit or module[position]>=len(table):
            raise ValueError(f'Invalid PCE opcode at {position:#x}')
        opcode=module[position];descriptor=table[opcode]
        modes=descriptor['modes']
        if opcode==0x4c:
            if descriptor['handler']!=0x9bd6:
                raise ValueError('Unexpected execute-next handler')
            modes=[4,0,0]
        elif descriptor['handler'] in (0x8df6,0xa247):
            modes=[0,0,0]
        cursor=position+1;mark(position,1,'opcode')
        continuation=None;operands=[];children=[]
        if (modes[1]|modes[2])&8:
            continuation=word(cursor);mark(cursor,2,'continuation');cursor+=2
            if not cursor<=continuation<=limit:
                raise ValueError(f'Invalid continuation {continuation:#x} at {position:#x}')
        for encoded in modes:
            mode=encoded&7
            if mode==4:
                children.append(cursor);cursor=expression(cursor,depth+1)
            elif mode not in (0,7):
                value=word(cursor);operands.append(dict(offset=cursor,mode=mode,value=value))
                mark(cursor,2,'operand');cursor+=2
        if continuation is not None:
            while cursor<continuation:
                children.append(cursor);cursor=expression(cursor,depth+1)
            if cursor!=continuation:
                raise ValueError(f'Expression passes continuation at {position:#x}')
        nodes[position]=dict(offset=position,opcode=opcode,end=cursor,
                             continuation=continuation,operands=operands,children=children)
        return cursor
    cursor=0
    while cursor<limit:
        if all(byte in (0,255) for byte in module[cursor:limit]):
            break
        cursor=expression(cursor)
    gaps=[offset for offset in range(cursor) if offset not in roles]
    if gaps:
        raise ValueError(f'Unconsumed code bytes: {gaps[:8]}')
    return dict(nodes=sorted(nodes.values(),key=lambda row:row['offset']),
                code_limit=limit,parsed_until=cursor,covered_bytes=len(roles),
                coverage_gaps=gaps,fill_bytes=limit-cursor)


def inspect_pce(track=None,reference=None,output=None,cue=None):
    """Index all typed scene expressions and their menu/text/audio references."""
    import importlib
    import sys
    reference=Path(reference or ROOT/'.deps/snatcher-translated')
    if not (reference/'pce/tools/pcescript.py').is_file():
        raise ValueError('Read-only PCE MIT reference tools are required')
    sys.path.insert(0,str(reference/'pce/tools'))
    cache_writes_disabled=sys.dont_write_bytecode
    sys.dont_write_bytecode=True
    try:
        codec=importlib.import_module('pcescript')
    finally:
        sys.dont_write_bytecode=cache_writes_disabled
    data,pregap,cue=_read_pce_track(track,cue)
    stage=data[22*2048:37*2048];resident=data[110*2048:122*2048]
    table=[]
    for opcode in range(255):
        entry=resident[0x2df9+4*opcode:0x2dfd+4*opcode]
        modes=[entry[0]>>4,entry[0]&15,entry[1]>>4]
        if max(modes)>8:
            raise ValueError(f'Unexpected PCE operand descriptor {opcode:#x}')
        table.append(dict(opcode=opcode,modes=modes,handler=int.from_bytes(entry[2:],'little')))
    modules={}
    for index in range(33):
        entry=stage[0x1535+index*8:0x153d+index*8]
        rec=entry[0]*65536+entry[2]*256+entry[1];sectors=entry[6]
        if rec!=158+16*index or entry[3]!=4 or not 0<sectors<=16:
            raise ValueError('Unexpected PCE module table')
        module=data[rec*2048:(rec+sectors)*2048]
        strings,bad=codec.strings_of(module)
        if bad:
            raise ValueError(f'PCE module {rec} text boundaries do not validate')
        if strings:
            start,end,labels=codec.word_list(module,strings[0][0])
            if start is None:
                # A linear reel can have no menu word list. Its first verified
                # compressed string bounds the bytecode instead.
                start=end=strings[0][0];labels=[]
        else:
            # The ending module has no text pool. Its entire nonfill content
            # must still parse as VM expressions, not be assumed native code.
            start=end=len(module);labels=[]
        word_rows=[];cursor=start+(start<len(module) and module[start]==255)
        for label in labels:
            word_rows.append(dict(offset=cursor,length=len(label.encode('cp932'))))
            cursor+=len(label.encode('cp932'))+1
        result=parse_pce_expressions(module,table,start)
        nodes={node['offset']:node for node in result['nodes']};refs=[]
        for node in result['nodes']:
            values=[operand['value'] for operand in node['operands']]
            opcode=node['opcode'];ref=None
            if opcode==0xf1:
                ref=dict(kind='menu_or_data_label',label_offset=values[0])
            elif opcode==0xf3:
                ref=dict(kind='voice',line=values[0]&255,table=values[0]>>8)
            elif opcode==0x6b:
                ref=dict(kind='graphics',block=values[0]>>8,display_list=values[0]&255)
            elif opcode==0xf9 and node['children']:
                child=nodes[node['children'][0]]
                args=[operand['value'] for operand in child['operands']]
                if len(args)==2:
                    ref=dict(kind='scene_jump',scene_index=args[0],record=158+16*args[0],entry=args[1])
            elif opcode==0x58:
                ref=dict(kind='local_jump',entry=values[0])
            elif opcode==0x62:
                ref=dict(kind='text_placeholder',text_offset=values[0])
            elif opcode==0x63 and node['children']:
                child=nodes[node['children'][0]]
                if child['opcode']==0x12:
                    args=[operand['value'] for operand in child['operands']]
                    ref=dict(kind='dialogue',mode=args[0],text_offset=args[1])
            if ref is not None:
                refs.append(dict(offset=node['offset'],opcode=opcode,**ref))
        result.update(rec=rec,sectors=sectors,sha1=digest(module),references=refs,
                      word_list_start=start,word_list_end=end,word_records=word_rows,
                      text_offsets=[offset for offset,_ in strings])
        modules[rec]=result
    report=dict(cue=str(cue),pregap_sectors=pregap,resident_sha1=digest(resident),
                descriptor_table_offset=0x2df9,opcode_table=table,modules=modules,
                expression_nodes=sum(len(row.get('nodes',[])) for row in modules.values()))
    output=Path(output or ROOT/'build/evidence/pce-script-index.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return dict(modules=len(modules),typed_modules=sum('nodes'in row for row in modules.values()),
                expression_nodes=report['expression_nodes'],output=str(output))


def patch_records(patches, source=SOURCE, ledger=ROOT/'docs/diff-ledger.csv'):
    """Validate approved row inventory and original bytes before any output write."""
    import csv
    patches,source=Path(patches),Path(source)
    rows=[]
    for path in sorted(patches.glob('*.json')):
        record=json.loads(path.read_text())
        if record.get('version')!=2 or record.get('encoding')!='source-relative-encoded-xor-spans':
            raise ValueError('Unknown patch format')
        rows.extend(record['rows'])
    decisions=list(csv.DictReader(Path(ledger).open()))
    expected={r['id'] for r in decisions if r["decision"]=='restore' and r['restore method']=='text edit'}
    ids=[r['id'] for r in rows]
    if len(ids)!=len(set(ids)) or set(ids)!=expected or len(ids)!=31:
        raise ValueError('Patch rows must exactly match the 31 approved M3 rows')
    entries={};files={};seen=set()
    pce_data,_,_=_read_pce_track()
    pce_cache={}
    for row in rows:
        evidence=row['pce_evidence'];rec=evidence['record']
        if rec not in pce_cache:
            reference=json.loads((ROOT/'private/work/text/pce'/f'{rec}.json').read_text())
            module=pce_data[rec*2048:(rec+reference['sectors'])*2048]
            if digest(module)!=reference['sha1']:
                raise ValueError('PCE reference module no longer matches staged bytes')
            pce_cache[rec]=reference
        reference=pce_cache[rec]
        if evidence['module_sha1']!=reference['sha1']:
            raise ValueError('PCE evidence module hash changed')
        indexed={r['offset']:r for r in reference['strings']}
        for proof in evidence['strings']:
            actual=indexed[proof['offset']]
            if digest(actual['jp'].encode())!=proof['jp_sha1'] or actual['key']!=proof['key']:
                raise ValueError('PCE evidence string hash changed')
    for row in rows:
        if not row['edits']:
            raise ValueError('Approved row has no edit')
        for edit in row['edits']:
            name=edit['file'];sid=edit['string_id'];kind=edit['kind'];key=(name,sid)
            if key in seen:
                raise ValueError('Duplicate edit target')
            seen.add(key)
            if kind=='pool' and re.fullmatch(r'SP[0-9][0-9]\.BIN',name):
                if name not in entries:
                    files[name]=(source/name).read_bytes();entries[name]=pool(files[name])[0]
                actual=entries[name][sid];old=bytes.fromhex(actual['raw']);start=actual['offset']
            elif kind=='speaker' and name=='SUBCODE.BIN':
                files.setdefault(name,(source/name).read_bytes())
                actual=speakers(source)[sid];old=bytes.fromhex(actual['raw'])[1:];start=actual['offset']+1
            else:
                raise ValueError('Invalid patch target')
            if digest(files[name])!=edit['source_sha1']:
                raise ValueError('Source file hash changed')
            new=source_text_recipe.apply(edit,old)
            if digest(old)!=edit['old_hash'] or len(old)!=len(new) or old==new or b'\xff' in new:
                raise ValueError('Source hash, length or replacement check failed')
            if row['id'] in ('TEXT-023','TEXT-024','TEXT-026'):
                # Chronology approval expressly retains the localized adult age.
                old_age=re.findall(rb'(?:Age:|age)[^0-9]{0,12}18',old)
                new_age=re.findall(rb'(?:Age:|age)[^0-9]{0,12}18',new)
                if old_age!=new_age or b'18' not in new:
                    raise ValueError('Localized adult age changed')
            # Complete prose exists only in memory and ignored working dumps.
            edit['new_text']=decode(new)
            edit['_offset']=start;edit['_bytes']=new
    return rows


def apply_patches(patches, source=SOURCE, output=ROOT/'build/m3/text', ledger=ROOT/'docs/diff-ledger.csv'):
    """Apply bounded edit records through the existing pool and speaker inserters."""
    import tempfile
    rows=patch_records(patches,source,ledger)
    output,source=Path(output),Path(source)
    if output.resolve()==source.resolve():
        raise ValueError('Output must differ from source')
    # The private workspace holds complete original dump records; these never
    # enter the versioned patch directory.
    with tempfile.TemporaryDirectory(prefix='m3-dumps-',dir=ROOT/'build') as tmp:
        tmp=Path(tmp);dump(source,tmp)
        records={p.name:json.loads(p.read_text()) for p in tmp.glob('*.json')}
        for row in rows:
            for edit in row['edits']:
                if edit['kind']=='pool':
                    records[Path(edit['file']).stem+'.json']['strings'][edit['string_id']]['text']=edit['new_text']
                else:
                    records['speakers.json'][edit['string_id']]['text']=edit['new_text']
        for name,record in records.items():
            (tmp/name).write_text(json.dumps(record)+'\n')
        result=insert(tmp,source,output)
        heading=insert_speakers(tmp,source,output)
    return dict(rows=len(rows),files=result,speakers=heading,output=str(output))


def verify(patches, source=SOURCE, output=ROOT/'build/m3/text', ledger=ROOT/'docs/diff-ledger.csv'):
    """Compare every byte in all 39 SP files and SUBCODE with approved edits."""
    rows=patch_records(patches,source,ledger);source,output=Path(source),Path(output)
    by_file={};changed=[]
    for row in rows:
        for edit in row['edits']:
            by_file.setdefault(edit['file'],[]).append(edit)
            changed.append(dict(row=row['id'],file=edit['file'],string_id=edit['string_id'],kind=edit['kind'],sha1=digest(edit['_bytes'])))
    inventory=sorted(source.glob('SP[0-9][0-9].BIN'))
    if len(inventory)!=39:
        raise ValueError('Expected all 39 SP files')
    checks=[]
    for path in inventory+[source/'SUBCODE.BIN']:
        original=path.read_bytes();expected=bytearray(original)
        for edit in by_file.get(path.name,[]):
            start=edit['_offset'];expected[start:start+len(edit['_bytes'])]=edit['_bytes']
        actual=(output/path.name).read_bytes()
        if actual!=expected:
            raise ValueError(f'{path.name}: missing approved edit or unapproved byte change')
        if path.name.startswith('SP') and len(actual)>FILE_LIMIT:
            raise ValueError(f'{path.name}: module cap exceeded')
        checks.append(dict(file=path.name,size=len(actual),sha1=digest(actual),changed_bytes=sum(a!=b for a,b in zip(original,actual))))
    remaining=[]
    for path in inventory:
        for entry in pool((output/path.name).read_bytes())[0]:
            if b'2047' in bytes.fromhex(entry['raw']):
                remaining.append(dict(file=path.name,string_id=entry['id']))
    allowed={('SP05.BIN',i) for i in (162,163,189,190,214,215,217,218)}
    if {(x['file'],x['string_id']) for x in remaining}!=allowed:
        raise ValueError('Unexpected remaining localized year or missing kept memorial')
    return dict(status='pass',approved_rows=len(rows),edit_records=len(changed),unapproved_byte_changes=0,sp_files_within_cap=39,files=checks,edits=changed,remaining_2047=remaining,remaining_2047_disposition='Kept ADD-001 through ADD-004 memorial articles',adult_ages='Unchanged in date-only profile replacements')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('dump');p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,default=DUMPS)
    p=sub.add_parser('insert');p.add_argument('--patches',type=Path);p.add_argument('--ledger',type=Path,default=ROOT/'docs/diff-ledger.csv');p.add_argument('--dumps',type=Path,default=DUMPS);p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,default=ROOT/'build/text-roundtrip')
    p=sub.add_parser('insert-speakers');p.add_argument('--dumps',type=Path,default=DUMPS);p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,default=ROOT/'build/speaker-roundtrip')
    p=sub.add_parser('scan-external');p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,default=ROOT/'private/work/text/external-candidates.json')
    p=sub.add_parser('reference-pce');p.add_argument('--track',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path);p.add_argument('--cue',type=Path)
    p=sub.add_parser('inspect-pce');p.add_argument('--track',type=Path);p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path);p.add_argument('--cue',type=Path)
    p=sub.add_parser('verify');p.add_argument('patches',type=Path);p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,default=ROOT/'build/m3/text');p.add_argument('--ledger',type=Path,default=ROOT/'docs/diff-ledger.csv')
    args=vars(parser.parse_args());command=args.pop('command')
    if command=='insert':
        patches=args.pop('patches');ledger=args.pop('ledger')
        if patches:
            args.pop('dumps');print(json.dumps(apply_patches(patches,ledger=ledger,**args),indent=2));return
    print(json.dumps({'verify':verify,'dump':dump,'insert':insert,'insert-speakers':insert_speakers,'scan-external':scan_external,'reference-pce':reference_pce,'inspect-pce':inspect_pce}[command](**args),indent=2))

if __name__=='__main__':
    main()
