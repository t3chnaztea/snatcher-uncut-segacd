#!/usr/bin/env python3
"""Real browser component parity plus bounded full-disc wrapper coverage."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import re

import patch_choices as choices
from verify_player_browser import file_hash, _verify_downloads, _assert_cleared

TRACK_BYTES = choices.SOURCE_TRACK_BYTES
ROOT = Path(__file__).resolve().parents[1]


def pairwise_ids():
    """Factorial settings cover every pair of local family variant values."""
    result = []
    for cameo in range(1 << len(choices.FAMILY_MAP['cameos'][0])):
        for opening in range(4):
            flags = dict.fromkeys(choices.SETTING_KEYS,False)
            flags.update(database_dates=bool((cameo^opening)&1),
                         moscow_date=bool(opening&1), newspaper_date=bool(opening&2),
                         neokobe_date=bool(((cameo>>1)^opening)&1),
                         alice=bool(((cameo>>2)^(opening>>1))&1),
                         lisa=bool(((cameo>>3)^(opening>>1))&1))
            flags.update({key:bool(cameo & (1 << i)) for i,key in enumerate(choices.FAMILY_MAP['cameos'][0])})
            result.append(choices.get_selection(flags).id)
    values = [choices.family_values(ident) for ident in result]
    for left,right in itertools.combinations(choices.FAMILIES,2):
        expected = set(itertools.product(range(1 << len(left[1])),range(1 << len(right[1]))))
        assert {(row[left[0]],row[right[0]]) for row in values} == expected
    return result


def full_disc_ids():
    """One output per cameo state cover every nonzero component, plus accepted default."""
    ids = [choices.DEFAULT_CHOICE_ID]
    pending = {(name,value) for name,keys,_ in choices.FAMILIES for value in range(1,1 << len(keys))}
    pending -= set(choices.family_values(ids[0]).items())
    candidates = [ident for ident in pairwise_ids() if ident != 'x000']
    while pending:
        best = max(candidates,key=lambda ident:len(pending & set(choices.family_values(ident).items())))
        covered = pending & set(choices.family_values(best).items())
        assert covered
        ids.append(best); candidates.remove(best); pending -= covered
    for ident in candidates:
        if len(ids) >= (1 << len(choices.FAMILY_MAP['cameos'][0])):break
        if ident not in ids:ids.append(ident)
    assert len(ids) == len(set(ids)) == (1 << len(choices.FAMILY_MAP['cameos'][0]))
    return ids


def select(page, ident):
    page.locator('details').evaluate_all('(nodes) => {for (const node of nodes) node.open=true;}')
    for key,enabled in choices.get_selection(ident).settings.items():
        page.locator(f'[data-choice="{key}"]').set_checked(enabled)


def raw_compositions(page, ids, registry, save, report, engine):
    page.evaluate('''async () => {
      globalThis.choiceAuditSource=new Uint8Array(await document.querySelector('#bin').files[0].slice(0,131744928).arrayBuffer());
    }''')
    for start in range(0,len(ids),8):
        batch=ids[start:start+8]
        rows=page.evaluate('''async ids => {
          const rows=[];
          for (const id of ids) {
            const result=await SnatcherChoices.composeTrack(globalThis.choiceAuditSource,id);
            rows.push({id,sha256:result.sha256,no_patch:result.no_patch,
              length:result.bytes?.byteLength??0,components:result.components.map(c=>c.id)});
          }
          return rows;
        }''',batch)
        assert [row['id'] for row in rows]==batch
        for row in rows:
            assert row['id'] in batch
            assert row['no_patch'] == (row['id']=='x000')
            assert row['length'] == (0 if row['no_patch'] else TRACK_BYTES)
            if not row['no_patch']:
                assert row['sha256']==registry['targets'][row['id']]
            expected=[choices.variant_id(name,value) for name,value in choices.family_values(row['id']).items() if value]
            assert sorted(row['components'])==sorted(expected)
            row['engine']=engine
            report['raw_compositions'].append(row)
        save()
        print(json.dumps(dict(engine=engine,raw_done=start+len(batch),raw_total=len(ids))),flush=True)


def error_states(page):
    return page.evaluate('''async () => {
      const reject=async (action)=>{try{await action();return false;}catch{return true;}};
      const source=globalThis.choiceAuditSource;
      const payloads={...SNATCHER_COMPONENTS_BASE64};
      const ids=Object.keys(payloads);
      const swapped={...payloads,[ids[0]]:payloads[ids[1]]};
      const family=SNATCHER_PROFILE_REGISTRY.families.find(f=>f.variants.some(v=>v.id===ids[0]));
      const variant=family.variants.find(v=>v.id===ids[0]);
      const flags=Object.fromEntries(SNATCHER_PROFILE_REGISTRY.families.flatMap(f=>f.setting_keys.map(k=>[k,false])));
      family.setting_keys.forEach((k,i)=>flags[k]=Boolean(variant.value&(1<<i)));
      const id=SnatcherChoices.choiceId(flags);
      const corrupt={...payloads,[ids[0]]:btoa('invalid VCDIFF')};
      const overlap=structuredClone(SNATCHER_PROFILE_REGISTRY);
      overlap.families[1].ranges[0].lba=overlap.families[0].ranges[0].lba;
      const bounds=structuredClone(SNATCHER_PROFILE_REGISTRY);
      bounds.families[0].ranges[0].lba=56014;
      const length=structuredClone(SNATCHER_PROFILE_REGISTRY);
      length.families[0].variants[0].decoded_bytes++;
      const target=structuredClone(SNATCHER_PROFILE_REGISTRY);target.targets[id]='0'.repeat(64);
      const wrong=new Uint8Array(source);wrong[100]^=1;
      const nop=await SnatcherChoices.composeTrack(new Proxy({}, {get(){throw Error('no-op read input')}}),'x000');
      return {
        swapped:await reject(()=>SnatcherChoices.composeTrack(source,id,swapped)),
        corrupt:await reject(()=>SnatcherChoices.composeTrack(source,id,corrupt)),
        overlap:await reject(()=>SnatcherChoices.composeTrack(source,id,payloads,{registry:overlap})),
        bounds:await reject(()=>SnatcherChoices.composeTrack(source,id,payloads,{registry:bounds})),
        length:await reject(()=>SnatcherChoices.composeTrack(source,id,payloads,{registry:length})),
        target:await reject(()=>SnatcherChoices.composeTrack(source,id,payloads,{registry:target})),
        wrong_source:await reject(()=>SnatcherChoices.composeTrack(wrong,id)),
        unknown:await reject(()=>SnatcherChoices.composeTrack(source,'x1000')),
        no_op_unread:nop.no_patch===true && nop.bytes===null
      };
    }''')


def verify(candidate,source_bin,source_cue,registry_path,output,engines,exhaustive=True,full_outputs=True,resume=None):
    from playwright.sync_api import sync_playwright
    candidate,source_bin,source_cue,registry_path,output=map(lambda p:Path(p).resolve(),
        (candidate,source_bin,source_cue,registry_path,output))
    registry=choices.load_registry(registry_path)
    output.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',runner_sha256=file_hash(Path(__file__)),registry_sha256=file_hash(registry_path),candidate_files={str(p.relative_to(candidate)):file_hash(p) for p in sorted(candidate.rglob('*')) if p.is_file()},
                source_bin_sha256=file_hash(source_bin),source_cue_sha256=file_hash(source_cue),
                raw_compositions=[],full_disc_downloads=[],errors=[],no_op=[],engines=engines,runtime_versions={},
                coverage=f'{len(choices.CHOICE_IDS)} Chromium raw transforms;{len(pairwise_ids())} pairwise transforms per other engine;{len(full_disc_ids())} full-disc downloads per engine covering every component. Pairwise data and full-disc wrapper are separate checks.')
    if resume is not None:
        resume=Path(resume).resolve();prior=json.loads(resume.read_text())
        assert prior['status'] in ('interrupted','interrupted-for-HomeLab-downloads-policy') and not prior['full_disc_downloads']
        assert prior.get('candidate_unchanged_after_interrupt') is True
        for key in ('registry_sha256','candidate_files','source_bin_sha256','source_cue_sha256'):
            assert prior[key]==report[key],f'Resume input differs: {key}'
        seen=set()
        for row in prior['raw_compositions']:
            ident=row['id'];engine=row['engine'];assert engine in engines and ident in choices.CHOICE_IDS
            assert (engine,ident) not in seen;seen.add((engine,ident))
            assert row['no_patch']==(ident=='x000') and row['length']==(0 if ident=='x000' else TRACK_BYTES)
            assert row['sha256']==registry['targets'][ident]
            expected=[choices.variant_id(name,value) for name,value in choices.family_values(ident).items() if value]
            assert sorted(row['components'])==sorted(expected)
        report['raw_compositions']=prior['raw_compositions']
        assert re.fullmatch('[0-9a-f]{64}',prior['runner_sha256'])
        report['resumed_from']=dict(path=str(resume),sha256=file_hash(resume),runner_sha256=prior['runner_sha256'],verified_raw_cases=len(seen))
    def save():(output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    original_cue=source_cue.read_bytes();starts=[]
    for block in re.split(rb'\bTRACK\s+\d+\s+AUDIO',original_cue)[1:]:
        match=re.search(rb'INDEX\s+(?:00|01)\s+(\d+):(\d+):(\d+)',block)
        minute,second,frame=map(int,match.groups());starts.append(((minute*60+second)*75+frame)*2352)
    assert len(starts)==20 and starts[0]==TRACK_BYTES
    ends=starts[1:]+[source_bin.stat().st_size]
    audio_hashes=[file_hash(source_bin,a,b) for a,b in zip(starts,ends)]
    runtime=ROOT/'.deps/playwright-browsers'
    if runtime.is_dir():os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(runtime.resolve()))
    runtime_tmp=output/'runtime-tmp';runtime_tmp.mkdir()
    os.environ['TMPDIR']=str(runtime_tmp)
    try:
        with sync_playwright() as playwright:
            for engine in engines:
                downloads=output/'native-downloads'/engine;downloads.mkdir(parents=True)
                browser=getattr(playwright,engine).launch(downloads_path=str(downloads))
                report['runtime_versions'][engine]=browser.version
                context=browser.new_context(accept_downloads=True,service_workers='block',viewport={'width':1280,'height':1000})
                page=context.new_page();page.set_default_timeout(120000)
                errors=[];external=[];download_events=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda req:external.append(req.url) if not req.url.startswith(('file:','blob:','data:')) else None)
                page.on('download',lambda download:download_events.append(download))
                page.goto((candidate/'index.html').as_uri())
                assert page.evaluate('typeof SnatcherChoices.composeTrack')=='function'
                page.locator('#bin').set_input_files(str(source_bin));page.locator('#cue').set_input_files(str(source_cue))
                ids=list(choices.CHOICE_IDS) if engine=='chromium' and exhaustive else pairwise_ids()
                completed={row['id'] for row in report['raw_compositions'] if row['engine']==engine}
                pending=[ident for ident in ids if ident not in completed]
                raw_compositions(page,pending,registry,save,report,engine)
                actual=[row['id'] for row in report['raw_compositions'] if row['engine']==engine]
                assert len(actual)==len(set(actual)) and set(actual)==set(ids)
                checks=error_states(page);assert all(checks.values()),checks
                report['errors'].append(dict(engine=engine,checks=checks));save()
                if full_outputs:
                    for ident in full_disc_ids():
                        select(page,ident);_assert_cleared(page)
                        page.locator('#apply').click()
                        busy=page.evaluate('''() => ({apply:document.querySelector('#apply').disabled,
                          flags:[...document.querySelectorAll('[data-choice]')].every(n=>n.disabled),
                          bin:document.querySelector('#bin').disabled,cue:document.querySelector('#cue').disabled})''')
                        assert all(busy.values()),busy
                        page.locator('#results').wait_for(state='visible',timeout=300000)
                        profile=dict(id=ident,settings=choices.get_selection(ident).settings,target_track1_sha256=registry['targets'][ident])
                        prior_download_count=len(download_events)
                        result=_verify_downloads(page,output/engine/ident,profile,source_bin,original_cue,starts,ends,audio_hashes)
                        # The shared helper deletes each native Download immediately
                        # after save_as, then removes the verified duplicate BIN.
                        assert len(download_events)-prior_download_count==3
                        assert not any(p.is_file() for p in downloads.rglob('*'))
                        result['native_download_temps_deleted']=3
                        if ident==choices.DEFAULT_CHOICE_ID:
                            assert result['whole_bin_sha256']=='5b502e0a5b52175ebc16d66b88078ce22d652e9fb38e1250bde9b2774561e7bd'
                        result.update(engine=engine,busy_controls_frozen=busy)
                        report['full_disc_downloads'].append(result);save()
                        key=choices.SETTING_KEYS[0]
                        page.locator(f'[data-choice="{key}"]').set_checked(not profile['settings'][key]);_assert_cleared(page)
                        print(json.dumps(dict(engine=engine,full_done=len([r for r in report['full_disc_downloads'] if r['engine']==engine]),full_total=len(full_disc_ids()))),flush=True)
                    assert [row['profile'] for row in report['full_disc_downloads'] if row['engine']==engine]==full_disc_ids()
                select(page,'x000');assert page.locator('#apply').is_disabled();_assert_cleared(page)
                nop=page.evaluate('''async () => {
                  const unread={name:'unread.bin',size:0,slice(){throw Error('input read')}};
                  const r=await SnatcherInstaller.patch(unread,null,()=>{}, {profileId:'x000'});
                  return r.downloads.length===0 && r.receipt.no_patch===true && r.receipt.input_verified===false;
                }''')
                assert nop;report['no_op'].append(dict(engine=engine,input_unread=True,downloads=0))
                assert not errors and not external,(errors,external)
                context.close();browser.close();save()
        final_files={str(p.relative_to(candidate)):file_hash(p) for p in sorted(candidate.rglob('*')) if p.is_file()}
        assert final_files==report['candidate_files']
        assert file_hash(source_bin)==report['source_bin_sha256'] and file_hash(source_cue)==report['source_cue_sha256']
        assert file_hash(Path(__file__))==report['runner_sha256']
        report.update(status='pass',raw_compositions_verified=len(report['raw_compositions']),full_disc_outputs_verified=len(report['full_disc_downloads']))
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:save()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','source-bin','source-cue','registry','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--engines',nargs='+',default=['chromium','firefox','webkit'],choices=['chromium','firefox','webkit'])
    parser.add_argument('--pairwise-only',action='store_true')
    parser.add_argument('--no-full-outputs',action='store_true')
    parser.add_argument('--resume',type=Path,help='Validated interrupted receipt with no full-disc outputs yet')
    args=parser.parse_args()
    result=verify(args.candidate,args.source_bin,args.source_cue,args.registry,args.output,args.engines,
                  exhaustive=not args.pairwise_only,full_outputs=not args.no_full_outputs,resume=args.resume)
    print(json.dumps({k:v for k,v in result.items() if k in ('status','raw_compositions_verified','full_disc_outputs_verified')}))


if __name__=='__main__':main()
