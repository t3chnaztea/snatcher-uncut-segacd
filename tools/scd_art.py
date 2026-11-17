#!/usr/bin/env python3
"""Compose approved M4 art edits with verified M3 text, then audit every file.

Conversion recipes remain in patches/gfx. Source and converted game assets
remain private or in ignored build outputs. No disc/release build occurs here.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import tempfile
from patch_profiles import get_profile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'private/extracted/segacd-usa'
OUTPUT=ROOT/'build/m4/patched'
EXPECTED={'GFX-001','GFX-002','GFX-005','TEXT-034','TEXT-035','TEXT-036'}
MODULES=('m4_animation','m4_captions')


def digest(data):
    return hashlib.sha1(data).hexdigest()


def approved_records(patches=ROOT/'patches/gfx'):
    import csv
    rows=[]
    for path in sorted(Path(patches).glob('*.json')):
        record=json.loads(path.read_text())
        if record.get('version')!=1:
            raise ValueError('Unknown art patch format')
        rows.extend(record['rows'])
    ids=[row['id'] for row in rows]
    decisions=list(csv.DictReader((ROOT/'docs/diff-ledger.csv').open()))
    approved={r['id'] for r in decisions if r["decision"]=='restore' and r['restore method']!='text edit'}
    if approved!=EXPECTED or len(ids)!=6 or set(ids)!=EXPECTED:
        raise ValueError('Art records must exactly cover the six approved M4 rows')
    return rows


def source_inventory(source):
    source=Path(source)
    manifest=json.loads((source/'manifest.json').read_text())
    # The 98 game-asset files are 97 BINs plus the boot area. The three ISO
    # copyright/bibliography TXT files stay untouched in the extracted source.
    names={r['name'] for r in manifest['files'] if r['name'].endswith('.BIN')}|{'_boot.bin'}
    if len(names)!=98 or any(Path(n).name!=n for n in names):
        raise ValueError('Unexpected source asset inventory')
    for record in manifest['files']:
        data=(source/record['name']).read_bytes()
        if len(data)!=record['size'] or digest(data)!=record['sha1']:
            raise ValueError(f'Source file hash changed: {record["name"]}')
    # Validate the boot-area asset against the corresponding staged raw sectors.
    with (source/'_track01.raw').open('rb') as stream:
        raw=stream.read(16*2352)
    boot=b''.join(raw[i+16:i+2064] for i in range(0,len(raw),2352))
    if (source/'_boot.bin').read_bytes()!=boot:
        raise ValueError('Source boot area no longer matches raw track template')
    return sorted(names)


def changed_spans(old,new):
    if len(new)<len(old):
        raise ValueError('M4 composition does not shrink source files')
    spans=[];start=None
    for i,(a,b) in enumerate(zip(old,new)):
        if a!=b and start is None:
            start=i
        elif a==b and start is not None:
            spans.append((start,i));start=None
    if start is not None:
        spans.append((start,len(old)))
    if len(new)>len(old):
        spans.append((len(old),len(new)))
    return spans


def apply(source=SOURCE,output=OUTPUT,evidence=ROOT/'build/evidence/m4/composition',profile=None):
    import scd_text
    selected=get_profile(profile)
    source,output,evidence=map(Path,(source,output,evidence))
    if source.resolve()==output.resolve():
        raise ValueError('Output cannot overwrite source')
    catalogue=approved_records();names=source_inventory(source)
    rows=[row for row in catalogue if row['id'] in selected.art_rows]
    if {row['id'] for row in rows} != selected.art_rows:
        raise ValueError('Profile art rows do not match the validated catalogue')
    evidence.mkdir(parents=True,exist_ok=True)
    # Generate all guarded art outputs before touching the composed tree.
    (ROOT/'build/m4').mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='art-compose-',dir=ROOT/'build/m4') as temp:
        temp=Path(temp);generated=[];reports={}
        for name in MODULES:
            folder=temp/name;folder.mkdir()
            lane_evidence=evidence/name;lane_evidence.mkdir(parents=True,exist_ok=True)
            reports[name]=importlib.import_module(name).apply(source=source,output=folder,evidence=lane_evidence,profile=selected)
            files=[p for p in folder.iterdir() if p.is_file() and (p.suffix=='.BIN' or p.name=='_boot.bin')]
            for path in files:
                if path.name not in names:
                    raise ValueError('Unknown generated art file')
                original=(source/path.name).read_bytes();new=path.read_bytes()
                capacity=((len(original)+2047)//2048)*2048
                if path.name=='DATA_G0.BIN':
                    capacity+=2048
                if len(new)!=len(original) and not (path.name=='DATA_G0.BIN' and len(original)<len(new)<=capacity):
                    raise ValueError('Only approved dog data may use last-sector slack and one verified zero-gap sector')
                spans=changed_spans(original,new)
                if spans:
                    generated.append((name,path.name,original,new,spans))
        output.mkdir(parents=True,exist_ok=True)
        if any(p.name not in names for p in output.iterdir()):
            raise ValueError('Composed output contains unexpected files')
        for name in names:
            shutil.copyfile(source/name,output/name)
        scd_text.apply_patches(ROOT/'patches/text',source=source,output=output,profile=selected)
        changes=[]
        for module,name,original,new,spans in generated:
            current=bytearray((output/name).read_bytes())
            for start,end in spans:
                if start<len(original) and current[start:min(end,len(original))]!=original[start:min(end,len(original))]:
                    raise ValueError(f'Overlapping M3/M4 or art-lane edits: {name} at {start:#x}')
                current[start:end]=new[start:end]
            (output/name).write_bytes(current)
            changes.append(dict(module=module,file=name,source_sha1=digest(original),art_sha1=digest(new),spans=[dict(start=a,end=b) for a,b in spans]))
    files=[]
    for name in names:
        old=(source/name).read_bytes();new=(output/name).read_bytes()
        if name.startswith('SP') and len(new)>scd_text.FILE_LIMIT:
            raise ValueError('SP buffer cap exceeded')
        files.append(dict(file=name,size=len(new),source_size=len(old),sector_capacity=((len(old)+2047)//2048)*2048+(2048 if name=='DATA_G0.BIN' else 0),source_sha1=digest(old),sha1=digest(new),changed_bytes=sum(a!=b for a,b in zip(old,new))+max(0,len(new)-len(old))))
    actual_changed={row['file'] for row in files if row['sha1'] != row['source_sha1']}
    if actual_changed != selected.changed_files:
        raise ValueError(f'Profile changed-file inventory mismatch: {actual_changed}')
    report=dict(status='pass',profile=selected.id,catalogue_rows=len(catalogue),approved_rows=sorted(row['id'] for row in rows),source_files=len(names),files=files,art_changes=changes,lane_reports=reports,m3_preserved='Composition rejects intersecting changed byte spans',output=str(output))
    (evidence/'apply.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def verify(source=SOURCE,output=OUTPUT,evidence=ROOT/'build/evidence/m4/verification',profile=None):
    selected=get_profile(profile)
    source,output,evidence=map(Path,(source,output,evidence))
    evidence.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='art-verify-',dir=ROOT/'build/m4') as temp:
        expected=Path(temp)/'expected'
        report=apply(source,expected,evidence/'regenerated',profile=selected)
        names=source_inventory(source)
        if {p.name for p in output.iterdir()}!=set(names):
            raise ValueError('Patched output inventory changed')
        for name in names:
            if (output/name).read_bytes()!=(expected/name).read_bytes():
                raise ValueError(f'Missing approved art or unapproved byte change: {name}')
    report['output']=str(output);report['verification']='All98 files equal fresh guarded M3+M4 recipe composition'
    (evidence/'verify.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['apply','verify'])
    parser.add_argument('--profile')
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--evidence',type=Path)
    args=vars(parser.parse_args());command=args.pop('command')
    if args['evidence'] is None:
        args['evidence']=ROOT/'build/evidence/m4'/command
    result=globals()[command](**args)
    print(json.dumps({k:result[k] for k in ('status','approved_rows','source_files','output')}))

if __name__=='__main__':
    main()
