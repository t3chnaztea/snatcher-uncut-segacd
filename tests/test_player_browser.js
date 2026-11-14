/* Browser parser checks. Run with node; no private data or emulator needed. */
'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const template = path.join(__dirname, '../release/installer/app.js');
const appPath = process.argv[2] || (fs.existsSync(template) ? template : path.join(__dirname, '../browser/app.js'));
const app = require(appPath);
function stamp(frame) {
  return [Math.floor(frame / 4500), Math.floor(frame / 75) % 60, frame % 75]
    .map(n => String(n).padStart(2, '0')).join(':');
}
const first = app.TRACK_BYTES / 2352;
const lines = ['REM generated fixture', 'TITLE "Keep metadata"', 'FILE "Disc.bin" BINARY',
  '  TRACK 01 MODE1/2352', '    INDEX 01 00:00:00'];
for (let n = 2; n <= 21; n++) {
  const start = first + (n - 2) * 300;
  lines.push(`  TRACK ${String(n).padStart(2, '0')} AUDIO`,
    `    INDEX 00 ${stamp(start)}`, `    INDEX 01 ${stamp(start + 150)}`);
}
const cue = lines.join('\n') + '\n';
const bytes = (first + 20 * 300) * 2352;
let passed = 0;
function valid(text, label) {
  const parsed = app.parseCue(text, 'Disc.bin', bytes);
  assert.equal(parsed.tracks.length, 21, label);
  assert.equal(parsed.tracks[1].indices['00'], first, label);
  passed++;
}
function invalid(text, label, name = 'Disc.bin', size = bytes) {
  assert.throws(() => app.parseCue(text, name, size), Error, label);
  passed++;
}
valid(cue, 'plain');
valid('\uFEFF' + cue, 'BOM');
valid(cue.replaceAll('\n', '\r\n'), 'CRLF');
valid(cue.replace(/\b(FILE|TRACK|INDEX|BINARY|MODE1|AUDIO)\b/g, x => x.toLowerCase()), 'case-insensitive directives');
valid(cue.replace('REM generated fixture', 'REM generated fixture\nPERFORMER "Fixture author"\nISRC US0000000000'), 'metadata');
invalid(cue + '\0', 'NUL');
invalid(cue.replace('MODE1/2352', 'MODE1/2048'), '2048-sector data');
invalid(cue.replace('TRACK 21 AUDIO', 'TRACK 22 AUDIO'), 'wrong track sequence');
invalid(cue.replace('TRACK 02 AUDIO', 'TRACK 02 MODE1/2352'), 'second data track');
invalid(cue.replace('INDEX 01 00:00:00', 'INDEX 01 00:00:01'), 'nonzero first index');
invalid(cue.replace('INDEX 01 00:00:00', 'INDEX 00 00:00:00\nINDEX 01 00:00:00'), 'Track 1 INDEX 00');
invalid(cue.replace('INDEX 01 00:00:00', 'INDEX 01 00:00:75'), 'invalid frame');
invalid(cue.replace('INDEX 01 00:00:00', 'INDEX 01 00:60:00'), 'invalid seconds');
invalid(cue.replace('INDEX 01 00:00:00', 'INDEX 01 0:00:00'), 'malformed time');
invalid(cue.replace('INDEX 01 00:00:00', 'INDEX 02 00:00:00'), 'unsupported index');
invalid(cue.replace('INDEX 01 00:00:00', 'INDEX 01 00:00:00\nINDEX 01 00:00:00'), 'duplicate index');
invalid(cue.replace('Disc.bin', '../Disc.bin'), 'relative path traversal');
invalid(cue.replace('Disc.bin', 'C:\\Disc.bin'), 'Windows path');
invalid(cue, 'wrong selected filename', 'Other.bin');
const before = `INDEX 00 ${stamp(first)}\n    INDEX 01 ${stamp(first + 150)}`;
invalid(cue.replace(before, `INDEX 01 ${stamp(first + 150)}\n    INDEX 00 ${stamp(first)}`), 'reversed index declarations');
invalid(cue.replace(before, `INDEX 00 ${stamp(first)}\n    INDEX 01 ${stamp(first)}`), 'equal indices');
invalid(cue.replace(`INDEX 00 ${stamp(first)}`, `INDEX 00 ${stamp(first + 1)}`), 'wrong data-track boundary');
invalid(cue.replace('TRACK 02 AUDIO', 'TRACK 02 AUDIO\nPREGAP 00:02:00'), 'virtual pregap requires offline route');
invalid(cue.replace('TRACK 02 AUDIO', 'FILE "Second.bin" BINARY\nTRACK 02 AUDIO'), 'split layout requires offline route');
invalid(cue, 'audio outside file', 'Disc.bin', app.TRACK_BYTES);
console.log(JSON.stringify({status: 'pass', parser_cases: passed, app: appPath}));
