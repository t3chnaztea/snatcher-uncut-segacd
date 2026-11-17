/* Advanced restoration choices. Components always decode from the original disc. */
'use strict';
const SnatcherChoices = (() => {
  const KEYS = ['database_dates','moscow_date','newspaper_date','neokobe_date','mask_rider','cornelius','alyen','miss_money','h2o_gulliver','alice','lisa','bar_background'];
  const FAMILIES = [
    ['database', ['database_dates'], ['SP04.BIN','SP05.BIN']],
    ['opening', ['moscow_date','newspaper_date'], ['DATA_D1.BIN']],
    ['city', ['neokobe_date'], ['DATA_D0.BIN']],
    ['cameos', [...KEYS.slice(4,9),'bar_background'], ['DATA_O0.BIN','SP13.BIN','SUBCODE.BIN']],
    ['alice', ['alice'], ['DATA_G0.BIN','SP25.BIN']],
    ['lisa', ['lisa'], ['DATA_F0.BIN']]
  ];
  const CHOICE_COUNT=1<<KEYS.length;
  const DEFAULT_CHOICE_ID='x'+(CHOICE_COUNT-1).toString(16).padStart(3,'0');
  const SOURCE = {track1_bytes:131744928,track1_sha1:'1f4164205ed736a0d9a03eb7972868e9aa737d35',track1_sha256:'9592d44b3241b31f36d235acc651bfa9cd2ab9562eadf9aecd86735913f0495d'};
  const DEFAULT_TARGET = 'f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba';
  const fail = message => { throw new Error(message); };
  const hex = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
  const exactKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join('|') === [...keys].sort().join('|');
  const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
  function choiceId(value) {
    if (typeof value === 'string') { if (!/^x[0-9a-f]{3}$/.test(value)) fail('Unknown restoration choice.'); return value; }
    if (!exactKeys(value,KEYS) || KEYS.some(key=>typeof value[key]!=='boolean')) fail('Invalid advanced settings.');
    return 'x'+KEYS.reduce((n,key,i)=>n+(value[key] ? 1<<i : 0),0).toString(16).padStart(3,'0');
  }
  function settings(value=DEFAULT_CHOICE_ID) {
    const mask=parseInt(choiceId(value).slice(1),16);
    return Object.fromEntries(KEYS.map((key,i)=>[key,Boolean(mask & (1<<i))]));
  }
  function legacySelection(value) {
    if (typeof value==='string') {
      const m=/^d([01])-c([01])-a([01])-l([01])$/.exec(value);
      if (!m) fail('Unknown legacy profile.');
      value={dates:m[1]==='1'?'japanese':'segacd',cameos:m[2]==='1',alice:m[3]==='1',lisa:m[4]==='1'};
    }
    if (!exactKeys(value,['dates','cameos','alice','lisa']) || !['japanese','segacd'].includes(value.dates) || ['cameos','alice','lisa'].some(k=>typeof value[k]!=='boolean')) fail('Invalid legacy settings.');
    return Object.fromEntries(KEYS.map((key,i)=>[key,i<4?value.dates==='japanese':i<9 || key==='bar_background'?value.cameos:value[key]]));
  }
  function familyValues(value) {
    const flags=settings(value);
    return Object.fromEntries(FAMILIES.map(([name,keys])=>[name,keys.reduce((n,key,i)=>n+(flags[key]?1<<i:0),0)]));
  }
  function validateRegistry(value) {
    if (!exactKeys(value,['format','version','default_profile','source','families','targets']) || value.format!==2 || typeof value.version!=='string' || !/^v\d+\.\d+\.\d+(?:-[a-z0-9.]+)?$/.test(value.version) || value.default_profile!==DEFAULT_CHOICE_ID) fail('The advanced registry is invalid. Extract the complete release again.');
    if (!exactKeys(value.source,Object.keys(SOURCE)) || Object.keys(SOURCE).some(k=>value.source[k]!==SOURCE[k])) fail('The advanced registry source changed.');
    if (!value.targets || Array.isArray(value.targets) || Object.keys(value.targets).length!==CHOICE_COUNT || Array.from({length:CHOICE_COUNT},(_,n)=>'x'+n.toString(16).padStart(3,'0')).some(id=>!hex(value.targets[id])) || new Set(Object.values(value.targets)).size!==CHOICE_COUNT || value.targets.x000!==SOURCE.track1_sha256 || value.targets[DEFAULT_CHOICE_ID]!==DEFAULT_TARGET) fail('Advanced target checksums are incomplete or inconsistent.');
    if (!Array.isArray(value.families) || value.families.length!==6) fail('The component families are incomplete.');
    const occupied=new Set(), names=new Set(), patches=new Set(), outputs=new Set();
    for (const family of value.families) {
      if (!exactKeys(family,['id','setting_keys','files','ranges','variants'])) fail('Invalid component family.');
      const expected=FAMILIES.find(([name])=>name===family.id);
      if (!expected || names.has(family.id) || !same(family.setting_keys,expected[1]) || !same(family.files,expected[2])) fail('Component ownership changed.');
      names.add(family.id);
      if (!Array.isArray(family.ranges) || !family.ranges.length || family.ranges.length>1024) fail('Invalid component sector ranges.');
      let previous=-1;const local=new Set();
      for (const range of family.ranges) {
        if (!exactKeys(range,['lba','count']) || !Number.isInteger(range.lba) || !Number.isInteger(range.count) || range.lba<0 || range.count<1 || range.lba+range.count>SOURCE.track1_bytes/2352 || range.lba<=previous) fail('Overlapping or out-of-bounds component sectors.');
        for (let n=range.lba;n<range.lba+range.count;n++) { if (occupied.has(n)) fail('Component families overlap.');local.add(n); }
        previous=range.lba+range.count-1;
      }
      if (local.size>1024) fail('Component family exceeds its sector budget.');
      for (const n of local) occupied.add(n);
      const maximum=1<<family.setting_keys.length;
      if (!Array.isArray(family.variants) || family.variants.length!==maximum-1) fail('Incomplete component variants.');
      const seen=new Set();
      for (const variant of family.variants) {
        if (!exactKeys(variant,['value','id','patch','decoded_bytes','decoded_sha256']) || !Number.isInteger(variant.value) || variant.value<1 || variant.value>=maximum || seen.has(variant.value) || variant.id!==family.id+'-'+variant.value.toString(16).padStart(2,'0') || variant.decoded_bytes!==local.size*2352 || !hex(variant.decoded_sha256) || outputs.has(variant.decoded_sha256)) fail('Invalid component variant.');
        seen.add(variant.value);outputs.add(variant.decoded_sha256);
        if (!exactKeys(variant.patch,['file','sha256']) || variant.patch.file!==`patches/components/${variant.id}.xdelta` || !hex(variant.patch.sha256) || patches.has(variant.patch.sha256)) fail('Invalid component patch.');
        patches.add(variant.patch.sha256);
      }
    }
    if (occupied.size>4096) fail('Component sector budget exceeded.');
    return JSON.parse(JSON.stringify(value));
  }
  function getRegistry(value) { return validateRegistry(value ?? (typeof SNATCHER_PROFILE_REGISTRY!=='undefined'?SNATCHER_PROFILE_REGISTRY:undefined)); }
  function getProfile(value=DEFAULT_CHOICE_ID, registry) {
    const id=choiceId(value),flags=settings(id),r=getRegistry(registry),values=familyValues(flags),components=[];
    for (const [name] of FAMILIES) {
      if (!values[name]) continue;
      const family=r.families.find(f=>f.id===name),variant=family.variants.find(v=>v.value===values[name]);
      components.push({...variant,family:name,ranges:family.ranges});
    }
    return {id,settings:flags,no_patch:id==='x000',target_track1_sha256:r.targets[id],components};
  }
  function summary(value) {
    const flags=settings(value),dates=KEYS.slice(0,4).map(k=>flags[k]),guests=KEYS.slice(4,9).filter(k=>flags[k]).length;
    const chronology=dates.every(Boolean)?'Japanese dates':dates.every(x=>!x)?'Sega CD dates':'Mixed dates';
    return `${chronology} · ${guests}/5 cameo groups · Wide scene ${flags.bar_background?'on':'off'} · Alice ${flags.alice?'on':'off'} · Lisa ${flags.lisa?'on':'off'}`;
  }
  function exportSettings(value) {const id=choiceId(value);return JSON.stringify({format:1,kind:'snatcher-patcher-settings',choice_id:id,settings:settings(id)},null,2)+'\n';}
  function parseSettings(text) {
    if (typeof text!=='string' || text.length>65536) fail('Choose a settings file or receipt smaller than 64 KB.');
    let doc;try {doc=JSON.parse(text);} catch {fail('The settings file is not valid JSON.');}
    if (!doc || typeof doc!=='object' || Array.isArray(doc)) fail('Invalid settings document.');
    let selected;
    if (doc.kind==='snatcher-patcher-settings') {
      if (!exactKeys(doc,['format','kind','choice_id','settings']) || doc.format!==1) fail('Unknown settings document format.');
      selected=settings(doc.settings);if (doc.choice_id!==choiceId(selected)) fail('Settings ID does not match its choices.');
    } else if (doc.installer==='Snatcher Patcher' && ([2,3].includes(doc.format) || [2,3].includes(doc.format_version))) {
      selected=exactKeys(doc.settings,KEYS)?settings(doc.settings):legacySelection(doc.settings);
      const id=choiceId(selected);
      if (typeof doc.profile_id!=='string' || (/^d/.test(doc.profile_id)?choiceId(legacySelection(doc.profile_id)):choiceId(doc.profile_id))!==id) fail('Receipt choices do not match its profile.');
    } else fail('This file does not contain supported Snatcher Patcher settings.');
    return selected;
  }
  function portableCode(value) {return 'SP2:'+choiceId(value);}
  function parsePortableCode(code) {
    if (typeof code!=='string' || code.length>80) fail('Invalid settings code.');
    const m=/^SP2:(x[0-9a-f]{3})$/.exec(code.trim());
    if (!m) fail('Use a Snatcher Patcher settings code such as SP2:xfff.');
    return settings(m[1]);
  }
  async function digest(data) {
    if (!globalThis.crypto?.subtle) fail('This browser cannot verify files here. Use the offline installer.');
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data)),b=>b.toString(16).padStart(2,'0')).join('');
  }
  async function composeTrack(source, value=DEFAULT_CHOICE_ID, payloads, options={}) {
    const registry=getRegistry(options.registry),profile=getProfile(value,registry);
    if (profile.no_patch) return {bytes:null,profile,components:[],sha256:SOURCE.track1_sha256,no_patch:true};
    if (!(source instanceof Uint8Array) || source.byteLength!==SOURCE.track1_bytes || await digest(source)!==SOURCE.track1_sha256) fail('The original data track does not match this release.');
    payloads=payloads ?? (typeof SNATCHER_COMPONENTS_BASE64!=='undefined'?SNATCHER_COMPONENTS_BASE64:undefined);
    const selected=profile.components.map(component=>{
      if (!payloads || typeof payloads[component.id]!=='string' || !payloads[component.id]) fail('A selected component is missing. Extract the full release again.');
      return {...component,encoded:payloads[component.id]};
    });
    const original=new BinFile(source.slice().buffer);original.fileName='original-track01.bin';
    const output=source.slice(),applied=[];
    for (const component of selected) {
      options.progress?.('Applying '+component.family+' restoration.');
      const patch=Uint8Array.from(atob(component.encoded),c=>c.charCodeAt(0));
      if (await digest(patch)!==component.patch.sha256) fail('Component patch checksum failed.');
      const input=new BinFile(patch);input.fileName=component.id+'.xdelta';
      const parsed=RomPatcher.parsePatchFile(input);
      const decoded=RomPatcher.applyPatch(original,parsed,{requireValidation:true,fixChecksum:false,outputSuffix:false});
      if (decoded.fileSize!==component.decoded_bytes || await digest(decoded._u8array)!==component.decoded_sha256) fail('Decoded component failed verification.');
      let at=0;
      for (const range of component.ranges) {const length=range.count*2352;output.set(decoded._u8array.subarray(at,at+length),range.lba*2352);at+=length;}
      if (at!==decoded.fileSize) fail('Component sector length mismatch.');
      applied.push({id:component.id,family:component.family,value:component.value,decoded_sha256:component.decoded_sha256,patch_sha256:component.patch.sha256});
    }
    const actual=await digest(output);
    if (actual!==profile.target_track1_sha256 || await digest(source)!==SOURCE.track1_sha256) fail('Final restoration verification failed. No files were prepared.');
    return {bytes:output,profile,components:applied,sha256:actual,no_patch:false};
  }
  return {KEYS,FAMILIES,SOURCE,DEFAULT_CHOICE_ID,CHOICE_COUNT,choiceId,settings,legacySelection,familyValues,validateRegistry,getProfile,summary,exportSettings,parseSettings,portableCode,parsePortableCode,composeTrack,digest};
})();
if (typeof module!=='undefined') module.exports=SnatcherChoices;
