"""Real browser tests for advanced settings and output lifetime."""
import json
from pathlib import Path
import shutil
import pytest
from playwright.sync_api import sync_playwright, expect
from test_choice_installer import registry_fixture

@pytest.fixture
def ui(tmp_path):
    root=Path(__file__).resolve().parents[1]
    source=root/'release/installer'
    if not source.is_dir(): source=root/'browser'
    for name in ('index.html','style.css','choices.js','app.js'):
        shutil.copyfile(source/name,tmp_path/name)
    (tmp_path/'patch-data.js').write_text('const SNATCHER_PROFILE_REGISTRY='+json.dumps(registry_fixture())+';const SNATCHER_COMPONENTS_BASE64={};')
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto((tmp_path/'index.html').as_uri())
        yield page,errors
        browser.close()


def test_presets_advanced_mixed_and_import(ui,tmp_path):
    page,errors=ui
    assert page.locator('[data-choice]').count()==12
    page.locator('#preset').select_option('original')
    assert page.locator('#apply').is_disabled()
    assert page.locator('#settings-code').input_value()=='SP2:x000'
    page.locator('.fine-tune summary').click()
    page.locator('#moscow_date').check()
    assert page.locator('#mixed-date-warning').is_visible()
    assert page.locator('#dates').input_value()=='custom'
    page.locator('#bar_background').check()
    assert page.locator('#cameos').evaluate('(e)=>e.indeterminate')
    page.locator('#cameos').check()
    assert page.evaluate('[...document.querySelectorAll("[data-choice]")].filter(e=>["mask_rider","cornelius","alyen","miss_money","h2o_gulliver","bar_background"].includes(e.id)).every(e=>e.checked)')
    page.locator('#preset').select_option('english')
    assert page.locator('#settings-code').input_value()=='SP2:xff0'
    assert not page.locator('#mixed-date-warning').is_visible()
    page.locator('.settings-tools summary').click()
    page.locator('#import-code').fill('SP2:x800');page.locator('#load-code').click()
    assert page.locator('#settings-code').input_value()=='SP2:x800'
    settings=tmp_path/'settings.json';settings.write_text(page.evaluate('SnatcherChoices.exportSettings("x001")'))
    page.locator('#import-settings').set_input_files(str(settings))
    expect(page.locator('#settings-code')).to_have_value('SP2:x001')
    assert not errors,errors


def test_busy_freeze_stale_outputs_and_no_external_requests(ui,tmp_path):
    page,errors=ui
    page.evaluate('''() => {
      window.revoked=[];const original=URL.revokeObjectURL.bind(URL);URL.revokeObjectURL=u=>{revoked.push(u);original(u)};
      SnatcherInstaller.patch=async (bin,cue,progress,options)=>{
        const profile=SnatcherChoices.getProfile(options.profileId);
        await new Promise(resolve=>{window.finish=resolve;document.querySelector('#installer').dataset.patchReady='true';});
        return {receipt:{layout:'single-bin-cue',settings:profile.settings,no_patch:false},downloads:[{name:'test.bin',blob:new Blob(['b'])},{name:'test.cue',blob:new Blob(['c'])}]};
      };
    }''')
    source=tmp_path/'source.bin';source.write_bytes(b'fixture')
    page.locator('#bin').set_input_files(str(source));page.locator('#apply').click()
    page.locator('#installer[data-patch-ready="true"]').wait_for()
    assert page.evaluate('[...document.querySelectorAll("input,select,button")].every(e=>e.disabled)')
    page.evaluate('window.finish()');page.wait_for_selector('#results:not([hidden])')
    assert page.locator('#downloads a').count()==2
    page.locator('#preset').select_option('original')
    assert page.locator('#downloads a').count()==0
    assert page.evaluate('revoked.length')==2
    assert page.locator('#results').is_hidden()
    assert not errors,errors


def test_mobile_keyboard_and_nsfw_closed(ui):
    page,errors=ui
    page.set_viewport_size({'width':390,'height':844})
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.locator('#preset').focus()
    assert page.locator('#preset').evaluate('(e)=>getComputedStyle(e).outlineStyle')!='none'
    assert not page.locator('.nsfw-previews').get_attribute('open')
    assert not errors,errors
