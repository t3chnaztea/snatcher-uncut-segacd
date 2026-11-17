/* Pure profile/package contract tests; no private inputs. */
'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const crypto = require('node:crypto');
const app = require(process.argv[2] || path.resolve(__dirname, '../release/installer/app.js'));
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const registry = {format: 1, version: 'v0.10.0-rc1', default_profile: app.DEFAULT_PROFILE_ID,
 source: {track1_bytes: app.TRACK_BYTES, track1_sha1: '1f4164205ed736a0d9a03eb7972868e9aa737d35',track1_sha256: '9592d44b3241b31f36d235acc651bfa9cd2ab9562eadf9aecd86735913f0495d'},profiles: []};
for (const id of app.PROFILE_IDS) {
 const flags = id.match(/[01]/g).map(x => x === '1');
 const settings = {dates: flags[0] ? 'japanese' : 'segacd',cameos: flags[1],alice: flags[2],lisa: flags[3]};
 const noPatch = id === 'd0-c0-a0-l0';
 const target = noPatch ? registry.source.track1_sha256 : id === app.DEFAULT_PROFILE_ID ? 'f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba' : sha('target-' + id);
 const patchHash = id === app.DEFAULT_PROFILE_ID ? '1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4' : sha('patch-' + id);
 registry.profiles.push({id, settings,no_patch:noPatch,target_track1_sha256: target,patch: noPatch ? null : {file:`patches/profiles/${id}.xdelta`,sha256:patchHash}});
 assert.equal(app.profileId(settings), id);
}
app.validateRegistry(registry);
let checks = 16;
for (const mutate of [r => r.profiles.pop(),r => r.profiles.push(r.profiles[0]),r => r.profiles[1].settings.dates='japanese',r=>r.source.track1_sha256='0'.repeat(64),r=>r.profiles[1].patch.file='../payload',r=>r.profiles[1].patch.sha256=r.profiles[2].patch.sha256,r=>r.profiles[1].target_track1_sha256=r.profiles[2].target_track1_sha256,r=>r.profiles[15].target_track1_sha256='1'.repeat(64),r=>r.profiles[0].patch={file:'x',sha256:'0'.repeat(64)},r=>r.profiles[1].no_patch=true]) {
 const copy=structuredClone(registry);mutate(copy);assert.throws(()=>app.validateRegistry(copy));checks++;
}
assert.throws(()=>app.getProfile('unknown',registry));checks++;
assert.throws(()=>app.profileId({dates:'segacd',cameos:1,alice:true,lisa:true}));checks++;
(async()=>{
 const result=await app.patch(null,null,()=>{throw new Error('No-op must not begin input work');},{profileId:'d0-c0-a0-l0',registry});
 assert.equal(result.downloads.length,0);assert.equal(result.receipt.no_patch,true);assert.equal(result.receipt.input_verified,false);checks++;
 await assert.rejects(app.patch(null,null,()=>{},{profileId:'d1-c1-a1-l0',registry,payloads:{}}),/missing/);checks++;
 console.log(JSON.stringify({status:'pass',profile_contract_checks:checks}));
})().catch(e=>{console.error(e);process.exitCode=1;});
