/* Original installer interface. Patch decoding is provided by Rom Patcher JS. */
'use strict';
const SnatcherInstaller = (() => {
  const TRACK_BYTES = 131744928;
  const SOURCE_SHA1 = '1f4164205ed736a0d9a03eb7972868e9aa737d35';
  const SOURCE_SHA256 = '9592d44b3241b31f36d235acc651bfa9cd2ab9562eadf9aecd86735913f0495d';
  const TARGET_SHA256 = 'f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba';
  const PATCH_SHA256 = '1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4';
  const fail = text => { throw new Error(text); };
  const DEFAULT_PROFILE_ID = 'd1-c1-a1-l1';
  const PROFILE_IDS = [];
  for (let d = 0; d <= 1; d++) for (let c = 0; c <= 1; c++) for (let a = 0; a <= 1; a++) for (let l = 0; l <= 1; l++) PROFILE_IDS.push(`d${d}-c${c}-a${a}-l${l}`);
  const hex = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
  function keys(value, expected) {
    return value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).sort().join('|') === [...expected].sort().join('|');
  }
  function profileId(settings) {
    if (!keys(settings, ['dates', 'cameos', 'alice', 'lisa']) || !['japanese', 'segacd'].includes(settings.dates) || ['cameos', 'alice', 'lisa'].some(k => typeof settings[k] !== 'boolean')) fail('Invalid restoration settings.');
    return `d${Number(settings.dates === 'japanese')}-c${Number(settings.cameos)}-a${Number(settings.alice)}-l${Number(settings.lisa)}`;
  }
  function validateRegistry(value) {
    if (!keys(value, ['format', 'version', 'default_profile', 'source', 'profiles']) || value.format !== 1 || typeof value.version !== 'string' || !/^v\d+\.\d+\.\d+(?:-[a-z0-9.]+)?$/.test(value.version) || value.default_profile !== DEFAULT_PROFILE_ID) fail('The profile registry is invalid. Extract a complete release again.');
    const source = value.source;
    if (!keys(source, ['track1_bytes', 'track1_sha1', 'track1_sha256']) || source.track1_bytes !== TRACK_BYTES || source.track1_sha1 !== SOURCE_SHA1 || source.track1_sha256 !== SOURCE_SHA256) fail('The profile registry has unsupported source data.');
    if (!Array.isArray(value.profiles) || value.profiles.length !== 16) fail('The release must contain all 16 restoration settings.');
    const seen = new Set(), targets = new Set(), patches = new Set();
    for (const row of value.profiles) {
      if (!keys(row, ['id', 'settings', 'no_patch', 'target_track1_sha256', 'patch']) || !PROFILE_IDS.includes(row.id) || seen.has(row.id) || profileId(row.settings) !== row.id || typeof row.no_patch !== 'boolean' || !hex(row.target_track1_sha256)) fail('The release has an invalid or repeated profile.');
      seen.add(row.id);
      const noPatch = row.id === 'd0-c0-a0-l0';
      if (row.no_patch !== noPatch || targets.has(row.target_track1_sha256)) fail('Profile output checksums are inconsistent.');
      targets.add(row.target_track1_sha256);
      if (noPatch) {
        if (row.patch !== null || row.target_track1_sha256 !== source.track1_sha256) fail('The original-disc profile is invalid.');
      } else if (!keys(row.patch, ['file', 'sha256']) || row.patch.file !== `patches/profiles/${row.id}.xdelta` || !hex(row.patch.sha256) || row.target_track1_sha256 === source.track1_sha256) fail('An active profile patch is missing or invalid.');
      if (!noPatch) { if (patches.has(row.patch.sha256)) fail('Profile patch checksums are repeated.'); patches.add(row.patch.sha256); }
      if (row.id === DEFAULT_PROFILE_ID && (row.target_track1_sha256 !== TARGET_SHA256 || row.patch.sha256 !== PATCH_SHA256)) fail('The default profile does not match the accepted release.');
    }
    // Snapshot the package data so asynchronous work cannot change its selection.
    return JSON.parse(JSON.stringify(value));
  }
  function getProfile(id = DEFAULT_PROFILE_ID, registry) {
    if (typeof id !== 'string' || !PROFILE_IDS.includes(id)) fail('Unknown restoration profile.');
    const actual = registry ?? (typeof SNATCHER_PROFILE_REGISTRY !== 'undefined' ? SNATCHER_PROFILE_REGISTRY : undefined);
    return validateRegistry(actual).profiles.find(row => row.id === id);
  }
  function summary(settings) {
    profileId(settings);
    return `${settings.dates === 'japanese' ? 'Japanese' : 'Sega CD'} dates · Cameos ${settings.cameos ? 'on' : 'off'} · Alice ${settings.alice ? 'on' : 'off'} · Lisa ${settings.lisa ? 'on' : 'off'}`;
  }
  async function digest(algorithm, bytes) {
    if (!globalThis.crypto?.subtle) fail('This browser cannot verify files here. Use the offline installer.');
    return Array.from(new Uint8Array(await crypto.subtle.digest(algorithm, bytes)), b => b.toString(16).padStart(2, '0')).join('');
  }
  function frames(value) {
    const m = /^(\d{2,3}):([0-5]\d):([0-7]\d)$/.exec(value);
    if (!m || Number(m[3]) > 74) fail('The CUE has an invalid track time.');
    return (Number(m[1]) * 60 + Number(m[2])) * 75 + Number(m[3]);
  }
  function parseCue(text, binName, binSize) {
    if (text.includes('\0')) fail('The CUE is not a plain text file.');
    const files = [], tracks = [];
    let current;
    for (const raw of text.replace(/^\uFEFF/, '').split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || /^(REM\b|TITLE\s|PERFORMER\s|SONGWRITER\s|CATALOG\s|ISRC\s)/i.test(line)) continue;
      let m;
      if ((m = /^FILE\s+"([^"\r\n]+)"\s+BINARY$/i.exec(line))) {
        files.push(m[1]); current = undefined;
      } else if ((m = /^TRACK\s+(\d{2})\s+(MODE1\/2352|AUDIO)$/i.exec(line))) {
        if (files.length !== 1) fail('Use the offline installer for split-track CUE files.');
        current = {number: Number(m[1]), mode: m[2].toUpperCase(), indices: {}};
        tracks.push(current);
      } else if ((m = /^INDEX\s+(00|01)\s+(\S+)$/i.exec(line))) {
        if (!current || m[1] in current.indices) fail('The CUE has an invalid or repeated index.');
        if (m[1] === '00' && '01' in current.indices) fail('CUE INDEX 00 must precede INDEX 01.');
        current.indices[m[1]] = frames(m[2]);
      } else fail('This CUE uses an unsupported layout. Use the offline installer.');
    }
    if (files.length !== 1 || /[\\/:]/.test(files[0]) || files[0] !== binName) fail('Choose the BIN named in this CUE. Keep both files in the same folder.');
    if (tracks.length !== 21 || tracks.some((t, i) => t.number !== i + 1 || t.mode !== (i ? 'AUDIO' : 'MODE1/2352') || t.indices['01'] === undefined)) fail('The CUE must contain Track 1 data followed by 20 audio tracks.');
    if (tracks[0].indices['01'] !== 0 || '00' in tracks[0].indices) fail('Track 1 must start with INDEX 01 at the beginning of the BIN.');
    if ((tracks[1].indices['00'] ?? tracks[1].indices['01']) * 2352 !== TRACK_BYTES) fail('The CUE data-track length does not match the supported dump.');
    let end = -1;
    for (const t of tracks) {
      const start = t.indices['00'] ?? t.indices['01'];
      if ('00' in t.indices && t.indices['00'] >= t.indices['01']) fail('CUE INDEX 00 must precede INDEX 01.');
      if (start <= end || start > t.indices['01'] || t.indices['01'] * 2352 >= binSize) fail('The CUE has overlapping tracks or points past the BIN.');
      end = t.indices['01'];
    }
    return {fileName: files[0], tracks};
  }
  async function patch(bin, cue, progress = () => {}, options = {}) {
    const id = options.profileId ?? DEFAULT_PROFILE_ID;
    const registry = validateRegistry(options.registry ?? (typeof SNATCHER_PROFILE_REGISTRY !== 'undefined' ? SNATCHER_PROFILE_REGISTRY : undefined));
    const selected = getProfile(id, registry);
    if (selected.no_patch) return {downloads: [], receipt: {format: 2, installer: 'Snatcher Patcher', profile_id: id, settings: selected.settings, no_patch: true, input_verified: false, status: 'no-patch-needed'}};
    const payloads = options.payloads ?? (typeof SNATCHER_PATCHES_BASE64 !== 'undefined' ? SNATCHER_PATCHES_BASE64 : undefined);
    if (!payloads || typeof payloads[id] !== 'string' || !payloads[id]) fail('The selected profile patch is missing. Extract the complete release again.');
    const encodedPatch = payloads[id];
    const outputBase = `Snatcher Uncut ${id}`;
    if (!bin) fail('Choose your original BIN first.');
    if (!/\.bin$/i.test(bin.name) || bin.size < TRACK_BYTES || bin.size > 1073741824 || bin.size % 2352) fail('Choose a complete raw Mode1/2352 BIN file. ISO and CHD files are not supported here.');
    let cueBytes, cueText, layout;
    if (bin.size > TRACK_BYTES) {
      if (!cue) fail('Choose the matching CUE for this full-disc BIN.');
      if (cue.size > 65536) fail('The CUE is too large.');
      cueBytes = new Uint8Array(await cue.arrayBuffer());
      try { cueText = new TextDecoder('utf-8', {fatal: true}).decode(cueBytes); }
      catch { fail('Use the offline installer for a CUE with non-UTF-8 text.'); }
      layout = parseCue(cueText, bin.name, bin.size);
    } else if (cue) fail('For a raw Track 1 BIN, leave the CUE field empty. Use the offline installer for a split-track disc.');
    progress('Checking the original data track.');
    const sourceBytes = await bin.slice(0, TRACK_BYTES).arrayBuffer();
    const sha1 = await digest('SHA-1', sourceBytes);
    if (sha1 !== SOURCE_SHA1) fail('Track 1 does not match the supported USA dump. Check the region, revision and extraction. Already-patched files are not accepted.');
    if (await digest('SHA-256', sourceBytes) !== registry.source.track1_sha256) fail('The original data track checksum failed.');
    const patchBytes = Uint8Array.from(atob(encodedPatch), c => c.charCodeAt(0));
    if (await digest('SHA-256', patchBytes) !== selected.patch.sha256) fail('The release patch checksum failed. Download the release again.');
    progress('Applying the patch. Your audio stays unchanged.');
    await new Promise(resolve => setTimeout(resolve, 30));
    const source = new BinFile(sourceBytes); source.fileName = 'track01.bin';
    const input = new BinFile(patchBytes); input.fileName = 'restoration.xdelta';
    const parsed = RomPatcher.parsePatchFile(input);
    const output = RomPatcher.applyPatch(source, parsed, {requireValidation: true, fixChecksum: false, outputSuffix: false});
    if (output.fileSize !== TRACK_BYTES || await digest('SHA-256', output._u8array) !== selected.target_track1_sha256) fail('Patched Track 1 verification failed. No files were prepared.');
    const downloads = [{name: layout ? outputBase + '.bin' : outputBase + ' Track 01.bin', blob: new Blob([output._u8array, bin.slice(TRACK_BYTES)], {type: 'application/octet-stream'})}];
    if (layout) {
      // Only the FILE operand changes. All timing and other CUE bytes stay intact.
      const fileLine = /^(\s*FILE\s+")[^"\r\n]+("\s+BINARY\s*)$/im;
      const adjusted = cueText.replace(fileLine, (_all, prefix, suffix) => prefix + outputBase + '.bin' + suffix);
      downloads.push({name: outputBase + '.cue', blob: new Blob([cueBytes[0] === 0xef && cueBytes[1] === 0xbb && cueBytes[2] === 0xbf ? '\uFEFF' : '', adjusted], {type: 'application/octet-stream'})});
    }
    const receipt = {format: 2, installer: 'Snatcher Patcher', version: registry.version, profile_id: id, settings: selected.settings, no_patch: false, layout: layout ? 'single-bin-cue' : 'raw-track-1', input_bytes: bin.size, source_track1_sha1: sha1, patched_track1_sha256: selected.target_track1_sha256, patch_sha256: selected.patch.sha256, output_bytes: bin.size, audio: layout ? 'Original BIN bytes after Track 1 reused without decoding or modification.' : 'No audio in this input.', cue_change: layout ? 'FILE operand only; output BIN renamed.' : null, tracks: layout?.tracks, hardware_tested: false};
    downloads.push({name: `snatcher-install-${id}.json`, blob: new Blob([JSON.stringify(receipt, null, 2) + '\n'], {type: 'application/json'})});
    return {downloads, receipt};
  }
  return {patch, parseCue, frames, TRACK_BYTES, DEFAULT_PROFILE_ID, PROFILE_IDS, profileId, validateRegistry, getProfile, summary};
})();

if (typeof document !== 'undefined') {
  const form = document.querySelector('#installer'), status = document.querySelector('#status');
  const bin = document.querySelector('#bin'), cue = document.querySelector('#cue');
  const button = document.querySelector('#apply'), results = document.querySelector('#results'), links = document.querySelector('#downloads');
  const controls = [...document.querySelectorAll('[data-setting]')], selection = document.querySelector('#selection-summary'), dateNote = document.querySelector('#date-note');
  let urls = [], busy = false, registryError;
  try { SnatcherInstaller.getProfile(); } catch (error) { registryError = error.message; }
  function settings() { return {dates: document.querySelector('#dates').value, cameos: document.querySelector('#cameos').checked, alice: document.querySelector('#alice').checked, lisa: document.querySelector('#lisa').checked}; }
  function clear() { for (const url of urls) URL.revokeObjectURL(url); urls = []; links.replaceChildren(); results.hidden = true; }
  function sync() {
    const value = settings(), id = SnatcherInstaller.profileId(value), noPatch = id === 'd0-c0-a0-l0';
    selection.textContent = SnatcherInstaller.summary(value);
    dateNote.textContent = value.dates === 'japanese' ? '1991 / 2039 / 2042. Retained English speech still says 1996.' : '1996 / 2044 / 2047. Keeps the English release’s original chronology.';
    bin.required = !noPatch;
    button.disabled = busy || noPatch || Boolean(registryError);
    button.querySelector('.action-label').textContent = noPatch ? 'No patch needed' : 'Verify and patch';
    if (!busy) { status.dataset.error = String(Boolean(registryError)); status.textContent = registryError || (noPatch ? 'These settings match the original disc. No patch or downloads are needed.' : 'Choose your original BIN and CUE, then select Verify and patch.'); }
  }
  for (const field of [bin, cue, ...controls]) field.addEventListener('change', () => { if (busy) return; clear(); sync(); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || registryError) return;
    clear(); busy = true; button.disabled = true; bin.disabled = true; cue.disabled = true; controls.forEach(field => {field.disabled = true;}); status.dataset.error = 'false';
    const profileId = SnatcherInstaller.profileId(settings());
    try {
      const result = await SnatcherInstaller.patch(bin.files[0], cue.files[0], text => {status.textContent = text;}, {profileId});
      if (result.receipt.no_patch) { status.textContent = 'These settings match the original disc. No patch or downloads are needed.'; return; }
      for (const item of result.downloads) {
        const a = document.createElement('a'); a.href = URL.createObjectURL(item.blob); urls.push(a.href); a.download = item.name; a.textContent = item.name; links.append(a);
      }
      results.hidden = false;
      status.textContent = (result.receipt.layout === 'raw-track-1' ? 'Track 1 verified. Keep the original audio tracks and assemble a matching CUE to play.' : 'Patch verified. Download the BIN and CUE together, then open the CUE to play.') + ' ' + SnatcherInstaller.summary(result.receipt.settings);
    } catch (error) { status.textContent = error.message; status.dataset.error = 'true'; }
    finally {busy = false; bin.disabled = false; cue.disabled = false; controls.forEach(field => {field.disabled = false;}); button.disabled = profileId === 'd0-c0-a0-l0';}
  });
  sync();
}
if (typeof module !== 'undefined') module.exports = SnatcherInstaller;
