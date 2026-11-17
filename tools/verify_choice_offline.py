#!/usr/bin/env python3
"""Actual format-2 offline acceptance: 64 selections across four source layouts.

No game outputs are retained. Virtual fixtures omit stored pregap samples and
retain their duration through CUE PREGAP. Audio preservation covers only bytes
supplied in each fixture, not the omitted original pregap samples.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import patch_choices as choices
import player_install
from choice_install import parse_settings
from verify_offline_profiles import (prepare_fixtures, verify_case, file_hash,
                                     source_tracks, require, FREE_FLOOR, BLOCK)


def coverage_ids():
    # Same deterministic greedy coverage as verify_choice_browser.full_disc_ids.
    candidates=[]
    for cameo in range(1 << len(choices.FAMILY_MAP['cameos'][0])):
        for opening in range(4):
            flags=dict.fromkeys(choices.SETTING_KEYS,False)
            flags.update(database_dates=bool((cameo^opening)&1),moscow_date=bool(opening&1),
                         newspaper_date=bool(opening&2),neokobe_date=bool(((cameo>>1)^opening)&1),
                         alice=bool(((cameo>>2)^(opening>>1))&1),lisa=bool(((cameo>>3)^(opening>>1))&1))
            flags.update({key:bool(cameo&(1<<i)) for i,key in enumerate(choices.FAMILY_MAP['cameos'][0])})
            ident=choices.get_selection(flags).id
            if ident!='x000':candidates.append(ident)
    ids=[choices.DEFAULT_CHOICE_ID]
    pending={(name,value) for name,keys,_ in choices.FAMILIES for value in range(1,1<<len(keys))}
    pending-=set(choices.family_values(ids[0]).items())
    while pending:
        best=max(candidates,key=lambda ident:len(pending & set(choices.family_values(ident).items())))
        covered=pending & set(choices.family_values(best).items());require(covered,'Incomplete component coverage')
        ids.append(best);candidates.remove(best);pending-=covered
    for ident in candidates:
        if len(ids)>=1<<len(choices.FAMILY_MAP['cameos'][0]):break
        if ident not in ids:ids.append(ident)
    require(len(ids)==len(set(ids))==64,'Expected 64 active choices')
    return ids


def full_expected(track,binary,size):
    digest=hashlib.sha256()
    for path,start in ((track,0),(binary,size)):
        with path.open('rb') as stream:
            stream.seek(start)
            while data:=stream.read(BLOCK):digest.update(data)
    return digest.hexdigest()


def bindings(registry_path,registry):
    root=Path(__file__).resolve().parent
    return dict(code={name:file_hash(root/name) for name in ('player_install.py','choice_install.py','patch_choices.py','patch_profiles.py','verify_offline_profiles.py','verify_choice_offline.py')},registry=file_hash(registry_path),patches={v['id']:file_hash(registry_path.parent/v['patch']['file']) for family in registry['families'] for v in family['variants']})


def verify_timing(fixture,receipt,original):
    for track in receipt['tracks']:
        source=original[track['track']-1];gap=source['indices']['01']-source['start']
        if fixture.name=='single-bin-cue':
            indices=source['indices'];pregap=None
        elif track['track']==1:
            indices={'01':0};pregap=None
        elif fixture.name=='split-virtual-pregap':
            indices={'01':0};pregap=gap or None
        else:
            indices={'01':gap}
            if '00' in source['indices']:indices['00']=0
            pregap=None
        actual={str(k).zfill(2):v for k,v in track['indices'].items()}
        require(actual==indices and track['pregap_frames']==pregap,'Receipt timing differs from supplied CUE')


def cli_check(args,registry,output,ident=None,expected_hash=None):
    command=[sys.executable,str(Path(player_install.__file__)),*args,'--registry',str(registry)]
    completed=subprocess.run(command,capture_output=True,text=True)
    require(completed.returncode==0,'Offline CLI failed: '+completed.stderr)
    if output is not None:
        receipt=json.loads((output/'install-receipt.json').read_text())
        require(receipt['profile_id']==ident and receipt['target_track1_sha256']==expected_hash,'CLI selection/output mismatch')
        require(file_hash(output/receipt['files'][0]['name'],0,choices.SOURCE_TRACK_BYTES)==expected_hash,'CLI actual Track 1 hash mismatch')
    return dict(status='pass',stdout=completed.stdout.strip(),profile=ident)


def verify(registry_path,binary,cue,output):
    registry_path,binary,cue,output=map(lambda p:Path(p).resolve(),(registry_path,binary,cue,output))
    require(not output.exists(),'Evidence folder must be new')
    require(shutil.disk_usage(output.parent).free>FREE_FLOOR+5*1024**3,'Need reserve above 100 GiB floor')
    registry=choices.load_registry(registry_path);ids=coverage_ids()
    expected_components={(f['id'],v['value']) for f in registry['families'] for v in f['variants']}
    covered={item for ident in ids for item in choices.family_values(ident).items() if item[1]}
    require(covered==expected_components and len(covered)==70,'Coverage misses components')
    before=bindings(registry_path,registry)
    output.mkdir(parents=True)
    report=dict(format=1,status='running',expected_cases=256,selected_profiles=ids,component_coverage=sorted([list(c) for c in covered]),bindings_before=before,source_bin_sha256=file_hash(binary),source_cue_sha256=file_hash(cue),cases=[],patch_rejections=[],cli_checks=[],temporary_game_outputs_retained=False,virtual_fixture_limit='Virtual PREGAP substitutes timing for omitted stored pregap samples. Only supplied post-INDEX01 audio bytes are preserved in that fixture; original stored-pregap sample equality is not claimed.')
    def save(): (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='choice-fixtures-',dir=output) as temporary:
            folder=Path(temporary);fixtures,transforms=prepare_fixtures(binary,cue,folder,registry['source']['track1_bytes'])
            report['virtual_fixture_transformations']=transforms
            all_inputs={f:file_hash(f) for fixture in fixtures for f in fixture.files+([fixture.cue] if fixture.cue else [])}
            report['fixture_inputs']=[dict(layout=fixture.name,file=f.name,sha256=all_inputs[f],bytes=f.stat().st_size) for fixture in fixtures for f in fixture.files+([fixture.cue] if fixture.cue else [])]
            original=source_tracks(binary,cue);save()
            for ident in ids:
                selected=choices.get_selection(ident);entry=dict(id=ident,settings=selected.settings,target_track1_sha256=registry['targets'][ident]);expected_whole=None
                expected_ids={v['id'] for family in registry['families'] for v in family['variants'] if v['value']==choices.family_values(selected)[family['id']]}
                for fixture in fixtures:
                    require(shutil.disk_usage(output).free>FREE_FLOOR+2*1024**3,'100 GiB floor reached')
                    with tempfile.TemporaryDirectory(prefix='installed-',dir=folder) as stage:
                        installed=Path(stage)/'result'
                        case=verify_case(fixture,entry,registry_path,installed,expected_whole)
                        receipt=case['installer_receipt'];verify_timing(fixture,receipt,original)
                        require(receipt['format_version']==3 and {c['id'] for c in receipt['components']}==expected_ids,'Receipt component inventory mismatch')
                        if fixture.name=='raw-track1': expected_whole=full_expected(installed/fixture.files[0].name,binary,registry['source']['track1_bytes'])
                        if ident==choices.DEFAULT_CHOICE_ID and fixture.name in ('raw-track1','single-bin-cue'):
                            report['cli_checks'].append(cli_check([str(installed/fixture.files[0].name),'--identify'],registry_path,None))
                        case['timing_verified']=True
                    report['cases'].append(case);save()
                    print(f'{len(report["cases"]):03}/256 {ident} {fixture.name}: pass',flush=True)
            # Corrupt and crossed payload bytes at each component's reviewed path.
            copied=folder/'bad-release';copied.mkdir();bad_registry=copied/'profiles.json';shutil.copyfile(registry_path,bad_registry)
            variants=[(f,v) for f in registry['families'] for v in f['variants']]
            for _,variant in variants:
                path=copied/variant['patch']['file'];path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(registry_path.parent/variant['patch']['file'],path)
            for index,(family,variant) in enumerate(variants):
                path=copied/variant['patch']['file'];clean=path.read_bytes()
                other=variants[(index+1)%len(variants)][1]
                crossed=(registry_path.parent/other['patch']['file']).read_bytes()
                for label,payload in (('corrupt',clean[:-1]+bytes([clean[-1]^1])),('crossed',crossed)):
                    path.write_bytes(payload);dest=folder/'must-not-exist'
                    try:player_install.install(fixtures[0].input,None,dest,registry=bad_registry,profile_id=choices.family_selection(family['id'],variant['value']).id)
                    except player_install.InstallError as exc:require('Component patch checksum' in str(exc),'Payload rejected for unrelated reason')
                    else:raise ValueError('Bad component accepted')
                    require(not dest.exists(),'Bad component created output')
                    report['patch_rejections'].append(dict(component=variant['id'],kind=label,status='rejected-before-output'))
                    path.write_bytes(clean)
                save()
            class NoRead:
                def __fspath__(self):raise AssertionError('No-op touched source/output path')
            noop=player_install.install(NoRead(),None,NoRead(),registry=registry_path,profile_id='x000')
            require(noop['no_patch'] and not noop['input_verified'],'No-op contract failed');report['no_op']=noop
            # Real CLI paths exercise settings files, portable code and old receipts.
            default=choices.get_selection();settings=folder/'settings.json'
            settings.write_text(json.dumps(dict(format=1,kind='snatcher-patcher-settings',choice_id=default.id,settings=default.settings)))
            old=folder/'old-receipt.json';old.write_text(json.dumps(dict(format=2,installer='Snatcher Patcher',profile_id='d1-c1-a1-l1',settings=dict(dates='japanese',cameos=True,alice=True,lisa=True))))
            require(parse_settings(old.read_text()).id==default.id,'Legacy settings adapter failed')
            for option in (['--settings',str(settings)],['--code','SP2:'+default.id],['--settings',str(old)]):
                with tempfile.TemporaryDirectory(prefix='cli-',dir=folder) as stage:
                    dest=Path(stage)/'result';report['cli_checks'].append(cli_check([str(fixtures[0].input),*option,'--output',str(dest)],registry_path,dest,default.id,registry['targets'][default.id]))
            require(all(file_hash(path)==digest for path,digest in all_inputs.items()),'A source/fixture input changed')
            report['all_fixture_inputs_unchanged']=True
        report['bindings_after']=bindings(registry_path,registry)
        require(report['bindings_after']==before,'Code, registry or patch changed during verification')
        require(file_hash(binary)==report['source_bin_sha256'] and file_hash(cue)==report['source_cue_sha256'],'Original input changed')
        require(len(report['cases'])==256 and len(report['patch_rejections'])==140,'Acceptance incomplete')
        report.update(status='pass',original_inputs_unchanged=True,temporary_fixtures_removed=True,free_bytes_after=shutil.disk_usage(output).free);save();return report
    except Exception as exc:
        report.update(status='failed',error=f'{type(exc).__name__}: {exc}');save();raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('registry','bin','cue','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();report=verify(args.registry,args.bin,args.cue,args.output)
    print(json.dumps(dict(status=report['status'],cases=len(report['cases']),patch_rejections=len(report['patch_rejections']))))

if __name__=='__main__':main()
