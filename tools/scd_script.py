#!/usr/bin/env python3
"""Inspect Snatcher's typed script expressions using the on-disc opcode table.

Outputs resource/menu/audio references, not game text. This is an analysis
reader, not a script assembler or a proof of runtime reachability.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dispatch(extracted):
    data = (extracted/'SUBCODE.BIN').read_bytes()
    table = data[0x98dc:0x98dc+75*4]
    if len(table) != 300:
        raise ValueError('Truncated opcode table')
    return [dict(opcode=i, modes=[table[i*4],table[i*4+1]>>4,table[i*4+1]&15],
                 handler=int.from_bytes(table[i*4+2:i*4+4],'big')) for i in range(75)]


def inspect(data, table, limit=0x3800):
    """Parse encoded expression boundaries. Branch pointers are not executed."""
    limit = min(limit,len(data))
    nodes = {}
    errors = []
    def word(pos):
        if pos+2>limit:
            raise ValueError(f'Operand crosses code boundary at {pos:#x}')
        return int.from_bytes(data[pos:pos+2],'big')
    def node(pos,depth=0):
        if depth>128:
            raise ValueError(f'Expression nesting exceeds 128 at {pos:#x}')
        if pos in nodes:
            return nodes[pos]['end']
        if pos>=limit or data[pos]>=len(table):
            raise ValueError(f'Invalid opcode at {pos:#x}')
        op = data[pos]; modes=table[op]['modes']; cursor=pos+1
        operands=[]; children=[]
        target = None
        if (modes[1]|modes[2])&8:
            target=word(cursor);cursor+=2
            if target<=pos or target>limit:
                raise ValueError(f'Invalid expression continuation {target:#x} at {pos:#x}')
        for encoded_mode in modes:
            mode=encoded_mode & 7
            if mode==4:
                children.append(cursor);cursor=node(cursor,depth+1)
            elif mode not in (0,7):
                operands.append(dict(offset=cursor,mode=mode,value=word(cursor)));cursor+=2
        if target is not None:
            if cursor>target:
                raise ValueError(f'Expression exceeds continuation at {pos:#x}')
            while cursor<target:
                children.append(cursor)
                cursor=node(cursor,depth+1)
            if cursor!=target:
                raise ValueError(f'Branch body exceeds continuation at {pos:#x}')
        nodes[pos]=dict(offset=pos,opcode=op,end=cursor,continuation=target,operands=operands,children=children)
        return cursor
    cursor=0
    while cursor<limit:
        if all(byte in (0,255) for byte in data[cursor:limit]):
            break
        try:
            end=node(cursor)
            if end<=cursor:raise ValueError(f'No progress at {cursor:#x}')
            cursor=end
        except ValueError as exc:
            errors.append(str(exc));break
    refs=[]
    for pos,n in sorted(nodes.items()):
        op=n['opcode']; values=[v['value'] for v in n['operands']]
        if op==67:
            values=[v['value'] for child in n['children'] for v in nodes[child]['operands']]
        if op in (4,5,13,56,61,67,68) and values:
            kind={4:'portrait_pcm',5:'pcm',13:'cd_audio',56:'verb',61:'graphics',67:'dialogue',68:'dialogue'}[op]
            ref=dict(offset=pos,opcode=op,kind=kind,values=values)
            if op==56:ref['text_offset']=0x3800+values[0]
            if op in (67,68):
                ref.update(text_offset=0x3800+values[-1],scene_info=values[0] if op==67 else 0)
            refs.append(ref)
    return dict(nodes=sorted(nodes.values(),key=lambda n:n['offset']),references=refs,
                parsed_until=cursor,code_limit=limit,errors=errors)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--extracted',type=Path,default=ROOT/'private/extracted/segacd-usa')
    p.add_argument('--output',type=Path,default=ROOT/'build/evidence/script-index.json')
    args=p.parse_args();table=dispatch(args.extracted);files={}
    for path in sorted(args.extracted.glob('SP??.BIN')):
        data=path.read_bytes();result=inspect(data,table)
        result['sha1']=hashlib.sha1(data).hexdigest();files[path.name]=result
    report=dict(opcode_table=table,files=files)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({name:dict(nodes=len(r['nodes']),references=len(r['references']),errors=r['errors'],parsed_until=r['parsed_until']) for name,r in files.items()},indent=2))

if __name__=='__main__':main()
