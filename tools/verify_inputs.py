#!/usr/bin/env python3
"""Verify staged sizes/SHA1s and compare BIN/CHD track hashes to Redump.

Redump page text must be fetched separately from the primary database and
stored under build/evidence/redump-20559.txt. This tool never downloads data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import scd_disc

ROOT=Path(__file__).resolve().parents[1]


def intake():
    root=ROOT/'private';rows=[]
    for path,size,expected in re.findall(r'^\| `([^`]+)` \| ([\d,]+) \| `([0-9a-f]{40})`',(root/'MANIFEST.md').read_text(),re.M):
        file=root/path
        with file.open('rb') as stream:
            actual=hashlib.file_digest(stream,'sha1').hexdigest()
        rows.append(dict(path=path,size=file.stat().st_size,sha1=actual,
                         ok=actual==expected and file.stat().st_size==int(size.replace(',',''))))
    if len(rows)!=32 or not all(r['ok'] for r in rows):
        raise ValueError('Input manifest verification failed')
    return rows


def identity(evidence):
    page=(evidence/'redump-20559.txt').read_text()
    expected={int(n):sha for n,sha in re.findall(r'^\| (\d+) \|.*?\| ([a-f0-9]{40}) \|$',page,re.M)}
    if set(expected)!=set(range(1,22)):
        raise ValueError('Redump page must provide all 21 track hashes')
    rows=scd_disc.track_hashes(scd_disc.DEFAULT_CUE)
    chd=scd_disc.track_hashes(ROOT/'build/chd-reference.cue')
    source,_=scd_disc.tracks(scd_disc.DEFAULT_CUE)
    with source.open('rb') as stream:
        sector=stream.read(2352)
    report=dict(redump_matches=[r['number'] for r in rows if r['sha1']==expected[r['number']]],
                redump_mismatches=[r['number'] for r in rows if r['sha1']!=expected[r['number']]],
                chd_bin_track_matches=[r['number'] for r,c in zip(rows,chd) if r['sha1']==c['sha1']],
                logical_header_0190=chr(sector[16+0x190]),logical_header_01f0=chr(sector[16+0x1f0]))
    if report['redump_matches']!=[1] or report['chd_bin_track_matches']!=list(range(1,22)):
        raise ValueError(f'Unexpected base image comparison: {report}')
    if sector[16+0x190]!=ord('J') or sector[16+0x1f0]!=ord('J'):
        raise ValueError('Unexpected retail header')
    for name,data in [('track-hashes',rows),('chd-track-hashes',chd),('identity',report)]:
        (evidence/(name+'.json')).write_text(json.dumps(data,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['intake','identity'])
    parser.add_argument('--evidence',type=Path,default=ROOT/'build/evidence')
    args=parser.parse_args();args.evidence.mkdir(parents=True,exist_ok=True)
    if args.command=='intake':
        rows=intake();(args.evidence/'intake.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps(dict(files=len(rows),passed=sum(r['ok'] for r in rows))))
    else:print(json.dumps(identity(args.evidence)))

if __name__=='__main__':main()
