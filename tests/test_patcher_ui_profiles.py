"""Browser-only UI lifecycle checks. Real patch outputs are checked by the release matrix."""
import json
from pathlib import Path
import shutil

import pytest
from playwright.sync_api import sync_playwright

from test_installer_profiles import registry_fixture


@pytest.fixture
def ui(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = root/'release/installer'
    if not source.is_dir():
        source = root/'browser'
    for name in ('index.html', 'style.css', 'app.js'):
        shutil.copyfile(source/name, tmp_path/name)
    (tmp_path/'patch-data.js').write_text('const SNATCHER_PROFILE_REGISTRY = '+json.dumps(registry_fixture())+'; const SNATCHER_PATCHES_BASE64 = {};\n')
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chromium')
        context = browser.new_context(viewport={'width':1280,'height':1000})
        page = context.new_page()
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto((tmp_path/'index.html').as_uri())
        yield page,errors
        context.close()
        browser.close()


def test_all_setting_states_and_noop(ui):
    page,errors=ui
    assert page.locator('h1').inner_text()=='Snatcher Patcher'
    states=set()
    for dates in ('japanese','segacd'):
        page.locator('#dates').select_option(dates)
        for c in (False,True):
            page.locator('#cameos').set_checked(c)
            for a in (False,True):
                page.locator('#alice').set_checked(a)
                for l in (False,True):
                    page.locator('#lisa').set_checked(l)
                    ident=page.evaluate("SnatcherInstaller.profileId({dates:document.querySelector('#dates').value,cameos:document.querySelector('#cameos').checked,alice:document.querySelector('#alice').checked,lisa:document.querySelector('#lisa').checked})")
                    states.add(ident)
                    assert page.locator('#apply').is_disabled() == (ident=='d0-c0-a0-l0')
                    assert page.locator('#results').is_hidden()
                    if ident=='d0-c0-a0-l0':
                        assert 'No patch or downloads are needed' in page.locator('#status').inner_text()
                        assert not page.locator('#bin').get_attribute('required')
    assert len(states)==16
    assert not errors,errors


def test_busy_freeze_and_setting_changes_revoke_stale_outputs(ui,tmp_path):
    page,errors=ui
    # A deferred fake decoder isolates real UI freeze/invalidation behavior; full
    # browser downloads exercise the actual engine and profile hashes elsewhere.
    page.evaluate("""() => {
      window.revoked=[];const revoke=URL.revokeObjectURL.bind(URL);
      URL.revokeObjectURL=u=>{window.revoked.push(u);revoke(u);};
      SnatcherInstaller.patch=async (bin,cue,progress,options)=> {
        window.submittedProfile=options.profileId;
        const row=SnatcherInstaller.getProfile(options.profileId);
        await new Promise(resolve=>{window.finishPatch=resolve;});
        return {receipt:{layout:'single-bin-cue',settings:row.settings,no_patch:false},downloads:[
          {name:'test.bin',blob:new Blob(['bin'])},{name:'test.cue',blob:new Blob(['cue'])}]};
      };
    }""")
    data=tmp_path/'source.bin';data.write_bytes(b'fixture input')
    page.locator('#bin').set_input_files(str(data))
    page.locator('#apply').click()
    page.wait_for_function('typeof window.finishPatch === "function"')
    assert page.evaluate('window.submittedProfile')=='d1-c1-a1-l1'
    for selector in ('#dates','#cameos','#alice','#lisa','#bin','#cue','#apply'):
        assert page.locator(selector).is_disabled(),selector
    page.evaluate('window.finishPatch()')
    page.wait_for_selector('#results:not([hidden])')
    assert page.locator('#downloads a').count()==2
    for selector in ('#dates','#cameos','#alice','#lisa','#bin','#cue','#apply'):
        assert page.locator(selector).is_enabled(),selector
    page.locator('#dates').select_option('segacd')
    assert page.locator('#results').is_hidden()
    assert page.locator('#downloads a').count()==0
    assert page.evaluate('window.revoked.length')==2
    assert not errors,errors


def test_mobile_layout_and_keyboard_focus(ui):
    page,errors=ui
    page.set_viewport_size({'width':390,'height':844});page.reload()
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.locator('#dates').focus()
    assert page.evaluate('document.activeElement.id')=='dates'
    assert page.locator('#dates').evaluate('(e)=>getComputedStyle(e).outlineStyle')!='none'
    assert not errors,errors
