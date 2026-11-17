#!/usr/bin/env python3
"""Exercise the local browser installer and hash the files it downloads.

Requires Playwright in the developer environment, not on a player's computer.
Game inputs and downloaded outputs must remain in ignored local folders.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

TRACK_BYTES = 131744928
TARGET = "f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba"


def file_hash(path: Path, start: int = 0, end: int | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(start)
        remaining = (end if end is not None else path.stat().st_size) - start
        while remaining:
            data = stream.read(min(2**20, remaining))
            if not data:
                raise ValueError("Unexpected end of file")
            h.update(data)
            remaining -= len(data)
    return h.hexdigest()


def _verify_legacy(candidate: Path, source_bin: Path, source_cue: Path, output: Path, engines: list[str]) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "running", "candidate": str(candidate), "cases": []}
    def save():
        (output / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    save()
    original_cue = source_cue.read_bytes()
    # Independent byte ranges from the original CUE, including stored pregaps.
    starts = []
    for block in re.split(rb"\bTRACK\s+\d+\s+AUDIO", original_cue)[1:]:
        m = re.search(rb"INDEX\s+(?:00|01)\s+(\d+):(\d+):(\d+)", block)
        minutes, seconds, frames = map(int, m.groups())
        starts.append(((minutes * 60 + seconds) * 75 + frames) * 2352)
    assert len(starts) == 20 and starts[0] == TRACK_BYTES
    ends = starts[1:] + [source_bin.stat().st_size]
    audio_hashes = [file_hash(source_bin, a, b) for a, b in zip(starts, ends)]
    bad = output / "invalid.bin"
    bad.write_bytes(b"not a supported disc")
    with sync_playwright() as playwright:
        for engine_name in engines:
            # Full Chromium's documented new headless mode renders on this Mac.
            # The separate headless-shell binary stalled actionability frames.
            browser = getattr(playwright, engine_name).launch(**({"channel": "chromium"} if engine_name == "chromium" else {}))
            context = browser.new_context(accept_downloads=True, service_workers="block")
            page = context.new_page()
            errors, external = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: external.append(request.url) if not request.url.startswith(("file:", "blob:", "data:")) else None)
            page.goto((candidate / "index.html").resolve().as_uri())
            page.locator("#bin").set_input_files(str(bad))
            page.locator("#apply").click()
            page.locator('#status[data-error=\"true\"]').wait_for()
            assert page.locator("#results").is_hidden()
            invalid_error = page.locator("#status").inner_text()
            page.locator("#bin").set_input_files(str(source_bin))
            page.locator("#apply").click()
            page.locator('#status[data-error=\"true\"]').wait_for()
            assert "CUE" in page.locator("#status").inner_text()
            page.locator("#cue").set_input_files(str(source_cue))
            page.locator("#apply").click()
            page.wait_for_selector("#results:not([hidden])", timeout=120000)
            engine_output = output / engine_name
            engine_output.mkdir()
            downloads = []
            for anchor in page.locator("#downloads a").all():
                with page.expect_download(timeout=120000) as event:
                    anchor.click()
                download = event.value
                assert download.failure() is None
                destination = engine_output / download.suggested_filename
                download.save_as(destination)
                downloads.append(destination)
            patched = next(p for p in downloads if p.suffix == ".bin")
            cue = next(p for p in downloads if p.suffix == ".cue")
            assert patched.stat().st_size == source_bin.stat().st_size
            assert file_hash(patched, 0, TRACK_BYTES) == TARGET
            actual_audio = [file_hash(patched, a, b) for a, b in zip(starts, ends)]
            assert actual_audio == audio_hashes
            expected_cue = original_cue.replace(b'FILE "' + source_bin.name.encode() + b'" BINARY', b'FILE "Snatcher Uncut.bin" BINARY', 1)
            assert cue.read_bytes() == expected_cue
            # Selecting another file must invalidate all prior download links.
            page.screenshot(path=str(engine_output / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(engine_output / "mobile.png"), full_page=True)
            page.locator("#bin").set_input_files(str(bad))
            assert page.locator("#results").is_hidden()
            assert page.locator("#downloads a").count() == 0
            assert not errors, errors
            assert not external, external
            result["cases"].append({"engine": engine_name, "version": browser.version, "input_bytes": source_bin.stat().st_size, "patched_track1_sha256": TARGET, "whole_bin_sha256": file_hash(patched), "audio_tracks_including_stored_pregaps_verified": 20, "audio_sha256": actual_audio, "cue_only_filename_changed": True, "invalid_input_rejected": invalid_error, "missing_cue_rejected": True, "stale_download_links_cleared": True, "page_errors": errors, "external_requests": external, "surface": "Playwright engine on macOS, local file URL; not original hardware or Safari application"})
            save()
            context.close()
            browser.close()
    result["status"] = "pass"
    save()
    return result


def expected_cue_bytes(original: bytes, output_bin: str) -> bytes:
    """Change only the FILE operand, preserving BOM, case, spacing and timing."""
    bom = b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b''
    body = original[len(bom):]
    pattern = rb'(?im)^([ \t]*FILE[ \t]+")[^"\r\n]+("[ \t]+BINARY[ \t]*\r?$)'
    result, count = re.subn(pattern, lambda m:m[1]+output_bin.encode('utf-8')+m[2], body)
    if count != 1:
        raise ValueError('Expected one original CUE file operand')
    return bom+result


def select_profile(page, profile):
    settings=profile['settings']
    page.locator('#dates').select_option(settings['dates'])
    for name in ('cameos','alice','lisa'):
        page.locator('#'+name).set_checked(settings[name])


def settle_render(page):
    page.evaluate('document.fonts.ready')
    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')


def _verify_downloads(page, folder, profile, source_bin, original_cue, starts, ends,
                      audio_hashes, raw=False, keep_bins=False):
    folder.mkdir(parents=True,exist_ok=False)
    downloaded=[]
    for anchor in page.locator('#downloads a').all():
        with page.expect_download(timeout=120000) as event:
            anchor.click()
        download=event.value
        assert download.failure() is None
        name=download.suggested_filename
        assert Path(name).name == name and profile['id'] in name, name
        destination=folder/name
        download.save_as(destination)
        downloaded.append(destination)
        download.delete()
    bins=[p for p in downloaded if p.suffix=='.bin']
    cues=[p for p in downloaded if p.suffix=='.cue']
    receipts=[p for p in downloaded if p.suffix=='.json']
    assert len(bins)==1 and len(cues)==(0 if raw else 1) and len(receipts)==1
    binary=bins[0]
    assert binary.stat().st_size == (TRACK_BYTES if raw else source_bin.stat().st_size)
    track_hash=file_hash(binary,0,TRACK_BYTES)
    assert track_hash==profile['target_track1_sha256']
    audio=[]
    if not raw:
        audio=[file_hash(binary,a,b) for a,b in zip(starts,ends)]
        assert audio==audio_hashes
        assert cues[0].read_bytes()==expected_cue_bytes(original_cue,binary.name)
    receipt=json.loads(receipts[0].read_text())
    assert receipt['profile_id']==profile['id'] and receipt['settings']==profile['settings']
    assert receipt.get('no_patch') is False
    result=dict(profile=profile['id'],raw_track=raw,patched_track1_sha256=track_hash,
                whole_bin_sha256=file_hash(binary),output_bytes=binary.stat().st_size,
                audio_tracks_including_stored_pregaps_verified=len(audio),audio_sha256=audio,
                cue_only_filename_changed=not raw,receipt=receipt,
                downloaded_files=[p.name for p in downloaded])
    if not keep_bins:
        # Only this run's freshly downloaded game file is removed. Evidence and
        # user inputs are untouched; no constructed shell deletion is involved.
        assert binary.parent.resolve()==folder.resolve() and binary.is_file()
        binary.unlink()
        result['downloaded_bin_removed_after_verification']=True
    return result


def _assert_cleared(page):
    assert page.locator('#results').is_hidden()
    assert page.locator('#downloads a').count()==0


def verify(candidate: Path, source_bin: Path, source_cue: Path, output: Path,
           engines: list[str], registry_path: Path | None = None,
           profile_ids: list[str] | None = None, raw_tracks=True, keep_bins=False,
           chromium_channel='chromium') -> dict:
    if registry_path is None:
        return _verify_legacy(candidate,source_bin,source_cue,output,engines)
    from patch_profiles import load_registry
    candidate,source_bin,source_cue,output=map(lambda p:Path(p).resolve(),
                                              (candidate,source_bin,source_cue,output))
    registry=load_registry(registry_path)
    profiles={p['id']:p for p in registry['profiles']}
    ids=list(profile_ids or profiles)
    assert ids and len(ids)==len(set(ids)) and set(ids)<=set(profiles)
    cache=Path(__file__).resolve().parents[1]/'.deps/playwright-browsers'
    if cache.is_dir():
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(cache.resolve()))
    output.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',candidate=str(candidate),registry=str(registry_path),
                selected_profiles=ids,engines=engines,cases=[],raw_track_cases=[],no_patch_cases=[],
                page_errors=[],external_requests=[],scope='Playwright browser engines on macOS, local file URL; no console or Safari-application claim')
    def save():
        (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    original_cue=source_cue.read_bytes()
    starts=[]
    for block in re.split(rb'\bTRACK\s+\d+\s+AUDIO',original_cue)[1:]:
        m=re.search(rb'INDEX\s+(?:00|01)\s+(\d+):(\d+):(\d+)',block)
        minute,second,frame=map(int,m.groups());starts.append(((minute*60+second)*75+frame)*2352)
    assert len(starts)==20 and starts[0]==TRACK_BYTES
    ends=starts[1:]+[source_bin.stat().st_size]
    audio_hashes=[file_hash(source_bin,a,b) for a,b in zip(starts,ends)]
    bad=output/'invalid.bin';bad.write_bytes(b'not a supported disc')
    raw_bin=output/'Original Track 01.bin'
    if raw_tracks and 'chromium' in engines:
        with source_bin.open('rb') as src,raw_bin.open('xb') as dst:
            remaining=TRACK_BYTES
            while remaining:
                data=src.read(min(2**20,remaining));assert data;dst.write(data);remaining-=len(data)
    with sync_playwright() as playwright:
        for engine in engines:
            browser=getattr(playwright,engine).launch(**({'channel':chromium_channel} if engine=='chromium' else {}))
            for index,ident in enumerate(ids):
                profile=profiles[ident]
                context=browser.new_context(accept_downloads=True,service_workers='block',viewport={'width':1280,'height':1000})
                page=context.new_page();errors=[];external=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda r:external.append(r.url) if not r.url.startswith(('file:','blob:','data:')) else None)
                page.goto((candidate/'index.html').as_uri())
                select_profile(page,profile)
                if profile['no_patch']:
                    assert page.locator('#apply').is_disabled()
                    _assert_cleared(page)
                    assert 'no patch' in page.locator('#status').inner_text().lower()
                    result=page.evaluate("""async id => {
                      const unread={name:'unread.bin',size:0,slice(){throw Error('input read')},arrayBuffer(){throw Error('input read')}};
                      return await SnatcherInstaller.patch(unread,null,()=>{}, {profileId:id});
                    }""",ident)
                    assert result['downloads']==[] and result['receipt']['no_patch'] is True
                    assert result['receipt']['input_verified'] is False and result['receipt']['profile_id']==ident
                    assert not errors and not external
                    report['no_patch_cases'].append(dict(engine=engine,profile=ident,no_downloads=True,input_not_read=True))
                    save();context.close();continue
                # Each engine exercises bad input and missing CUE in a real page.
                if ident==registry['default_profile']:
                    page.locator('#bin').set_input_files(str(bad));page.locator('#apply').click()
                    page.locator('#status[data-error=\"true\"]').wait_for()
                    _assert_cleared(page)
                    page.locator('#bin').set_input_files(str(source_bin));page.locator('#apply').click()
                    page.locator('#status[data-error=\"true\"]').wait_for()
                    assert 'CUE' in page.locator('#status').inner_text();_assert_cleared(page)
                page.locator('#bin').set_input_files(str(source_bin));page.locator('#cue').set_input_files(str(source_cue))
                # Delay completion after the actual patch only to observe the
                # real disabled controls. No game bytes or verification is mocked.
                page.evaluate("""() => {
                  window.__realPatch=SnatcherInstaller.patch;
                  window.__patchGate=null;
                  SnatcherInstaller.patch=async(...args)=>{
                    const value=await window.__realPatch(...args);
                    await new Promise(resolve=>{window.__patchGate=resolve;document.documentElement.dataset.testPatchGate='ready'});return value;
                  };
                }""")
                page.locator('#apply').click()
                page.locator('html[data-test-patch-gate=\"ready\"], #status[data-error=\"true\"]').first.wait_for(state='attached',timeout=120000)
                assert page.evaluate('window.__patchGate!==null'), page.locator('#status').inner_text()
                before_settings=page.locator('#dates').input_value()
                for control in ('dates','cameos','alice','lisa','bin','cue','apply'):
                    assert page.locator('#'+control).is_disabled(),control
                try:
                    page.locator('#dates').select_option('segacd' if before_settings=='japanese' else 'japanese',timeout=250)
                    raise AssertionError('Disabled date control accepted a change')
                except PlaywrightTimeoutError:
                    pass
                assert page.locator('#dates').input_value()==before_settings
                page.evaluate('() => { window.__patchGate(); SnatcherInstaller.patch=window.__realPatch; }')
                page.wait_for_selector('#results:not([hidden])',timeout=120000)
                case=_verify_downloads(page,output/engine/ident,profile,source_bin,original_cue,
                                       starts,ends,audio_hashes,keep_bins=keep_bins)
                case.update(engine=engine,version=browser.version,settings_disabled_during_patch=True,
                            attempted_disabled_change_preserved_selection=True)
                # Track real revocations made by the application on a settings change.
                page.evaluate("""() => {window.__revocations=0;const real=URL.revokeObjectURL.bind(URL);
                  URL.revokeObjectURL=u=>{window.__revocations++;real(u)};}""")
                field=('dates','cameos','alice','lisa')[index%4]
                if field=='dates':
                    page.locator('#dates').select_option('segacd' if profile['settings']['dates']=='japanese' else 'japanese')
                else:
                    page.locator('#'+field).set_checked(not profile['settings'][field])
                _assert_cleared(page);assert page.evaluate('window.__revocations')>=3
                case.update(stale_setting_cleared=field,object_urls_revoked=True)
                select_profile(page,profile)
                if ident==registry['default_profile']:
                    # Real source read with a deliberately crossed reviewed payload.
                    other=next(p for p in profiles if not profiles[p]['no_patch'] and p!=ident)
                    rejection=page.evaluate("""async ({id,other})=>{
                      const payloads={...SNATCHER_PATCHES_BASE64,[id]:SNATCHER_PATCHES_BASE64[other]};
                      try {await SnatcherInstaller.patch(document.querySelector('#bin').files[0],
                        document.querySelector('#cue').files[0],()=>{}, {profileId:id,payloads});return null;}
                      catch(e){return e.message;}
                    }""",dict(id=ident,other=other))
                    assert rejection and ('checksum' in rejection.lower() or 'hash' in rejection.lower()),rejection
                    case['cross_profile_payload_rejected']=rejection
                    page.locator('#apply').click();page.wait_for_selector('#results:not([hidden])',timeout=120000)
                    page.locator('#bin').set_input_files(str(bad));_assert_cleared(page)
                    case['stale_input_cleared']=True
                if raw_tracks and engine=='chromium':
                    select_profile(page,profile);page.locator('#bin').set_input_files(str(raw_bin));page.locator('#cue').set_input_files([])
                    page.locator('#apply').click();page.wait_for_selector('#results:not([hidden])',timeout=120000)
                    raw_case=_verify_downloads(page,output/engine/(ident+'-raw'),profile,source_bin,original_cue,
                        starts,ends,audio_hashes,raw=True,keep_bins=keep_bins)
                    raw_case.update(engine=engine,version=browser.version);report['raw_track_cases'].append(raw_case)
                assert not errors,errors;assert not external,external
                case.update(page_errors=errors,external_requests=external)
                report['cases'].append(case);save()
                print(f'{engine} {ident}: full-disc download and selection contract pass',flush=True)
                context.close()
            browser.close()
    report.update(status='pass',active_profile_engine_cases=len(report['cases']),
                  no_patch_engine_cases=len(report['no_patch_cases']),raw_track_cases_count=len(report['raw_track_cases']))
    save();return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--bin',type=Path,required=True)
    parser.add_argument('--cue',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--registry',type=Path)
    parser.add_argument('--profiles',nargs='+')
    parser.add_argument('--engines',nargs='+',default=['chromium','firefox','webkit'])
    parser.add_argument('--skip-raw-tracks',action='store_true')
    parser.add_argument('--keep-bins',action='store_true')
    parser.add_argument('--chromium-channel',default='chromium')
    args=parser.parse_args()
    try:
        r=verify(args.candidate,args.bin,args.cue,args.output,args.engines,args.registry,args.profiles,
                 not args.skip_raw_tracks,args.keep_bins,args.chromium_channel)
    except Exception as error:
        receipt=args.output/'verification.json'
        if receipt.is_file():
            state=json.loads(receipt.read_text())
            if state.get('status') == 'running':
                state.update(status='failed',failure_type=type(error).__name__,failure=str(error))
                receipt.write_text(json.dumps(state,indent=2)+'\n')
        raise
    print(json.dumps({'status':r['status'],'cases':len(r['cases']),
                      'no_patch_cases':len(r.get('no_patch_cases',[])),
                      'raw_track_cases':len(r.get('raw_track_cases',[]))}))

if __name__=='__main__':main()
