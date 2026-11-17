'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const c=require(fs.existsSync(path.join(root,'release/installer/choices.js'))?path.join(root,'release/installer/choices.js'):path.join(root,'browser/choices.js'));
for(let mask=0;mask<c.CHOICE_COUNT;mask++) {
  const id='x'+mask.toString(16).padStart(3,'0');
  assert.equal(c.choiceId(c.settings(id)),id);
  assert.equal(c.choiceId(c.parseSettings(c.exportSettings(id))),id);
  assert.equal(c.choiceId(c.parsePortableCode(c.portableCode(id))),id);
}
assert.equal(c.choiceId(c.legacySelection('d1-c1-a1-l1')),c.DEFAULT_CHOICE_ID);
assert.equal(c.choiceId(c.legacySelection('d0-c0-a0-l0')),'x000');
assert.throws(()=>c.parseSettings('{"format":1,"kind":"snatcher-patcher-settings","choice_id":"x000","settings":{}}'));
assert.throws(()=>c.parseSettings('x'.repeat(65537)));
assert.throws(()=>c.parsePortableCode('file:///private/SP2:xfff'));
assert.throws(()=>c.choiceId({...c.settings('x000'),bar_background:1}));
assert.equal(c.settings('x800').bar_background,true);
assert.equal(c.familyValues('x800').cameos,32);
console.log('4096 settings/code roundtrips and fail-closed contracts passed');
