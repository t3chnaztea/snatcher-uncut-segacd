# Verification

## Advanced choices

Twelve controls provide 4,096 selections. The original-disc selection needs no patch, input read or download. The other selections use combinations of 70 source-relative VCDIFF components. [profiles.json](profiles.json) records component hashes, owned sectors and every expected data-track hash.

All sixteen configurations from v0.10.0-rc1 retain their exact game output. The default remains the earlier accepted game:

- Track 1 SHA256: `f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba`.
- Whole BIN with the reference audio: `5b502e0a5b52175ebc16d66b88078ce22d652e9fb38e1250bde9b2774561e7bd`.

Different audio dumps can produce different whole-disc hashes. The selected data-track checksum identifies the restoration.

## Independent disc and component checks

The build derives six families: database dates, Moscow/newspaper captions, Neo Kobe caption, guest views/wide crowd, Alice, and Lisa. Their 76 local states include six shared original states and 70 active components. Each component decodes against the original Track 1 into a compact concatenation of owned sectors.

An independent verifier checked all 56,014 source sectors, 70 decoded components, 6,860 active-family asset comparisons, 535 distinct component-sector parity proofs, and all 4,096 final hashes. It independently placed file bytes and directory-size fields rather than calling the build's overlay function. All sixteen legacy target hashes match.

The families own 54 disjoint sectors. Alice alone includes its approved extra sector and ISO directory-size change. Duplicate or overlapping ownership, out-of-range sectors, incorrect lengths, changed patches, wrong source and wrong final hashes are rejected. Unchanged portions remain source-exact.

## Browser matrix

| Check | Result |
|---|---|
| Chromium raw composition | All 4,096 selections |
| Firefox raw composition | 256 pairwise family selections |
| WebKit raw composition | 256 pairwise family selections |
| Full-disc downloads | 64 selections per engine, 192 total |
| Full-disc supplied audio | 3,840 track comparisons |
| Error guards | 27 checks across three engines |
| Original-disc selection | Three zero-input, zero-download checks |
| Application requests and page errors | None |

The full-disc set covers every component. The pairwise sets cover family interactions in transformed data. These are separate from the complete-disc output checks; the matrix does not claim 4,096 full-disc downloads in every engine.

Every downloaded data track matched the selected hash. All 20 audio tracks and stored pregaps matched the supplied source. CUE edits were limited to the BIN filename. Default whole-BIN hashes matched the accepted game. Controls stayed disabled during work; changed preferences and inputs cleared old downloads. Corrupt or swapped components, bad source, overlapping sectors, invalid lengths and wrong target hashes failed verification.

Testing used pinned Playwright Chromium 159.0.8154.6, Firefox 159 and WebKit 27.2 on macOS. WebKit testing does not establish Safari application compatibility. Windows, Linux and mobile installation are not accepted.

## Offline matrix and CLI

The offline matrix passed 256 installs: 64 selections across raw Track 1, single-BIN CUE, stored-pregap split tracks and virtual-pregap split tracks. It covered all 70 components, checked 3,840 supplied audio tracks, preserved CUE bytes/timing and input files, and rejected 140 crossed or corrupt component attempts without output.

Virtual PREGAP fixtures omit stored pregap samples and preserve their duration as timing. Checks cover the audio supplied to those fixtures, not omitted samples.

Real CLI checks covered settings files, portable codes, legacy configurable-release receipts and Track 1 identification. After the matrix, a CLI error-boundary fix removed tracebacks for malformed input. Every function and class outside the CLI entry point stayed unchanged. Twelve negative CLI tests, affected interface tests and a fresh nondefault installation/identification passed afterward.

## Guest-view runtime checks

All 64 combinations of the five guest groups and wide crowd passed resource limits, source guards and independent pose raster comparisons. Selected rear/front poses equal the accepted restoration. Disabled poses equal the original. Dancer/light animation, protected architecture, palette indices, opacity and priority checks passed.

Fresh native QA captured seven views per combination: 448 captures, including Miss Money's rear view. Each capture checked the complete loaded DATA_O0 module, SP13 text pool, visible object/frame-table/sprite pointers and media binding. All 20 audio tracks stayed original. Independent composition matched all 64 baseline Track 1 and whole-BIN hashes.

These use documented graphics QA prefixes. They do not establish a natural story route or visibly displayed dialogue for every setting. The wide crowd is its own source-bound restoration; it is not assigned to the five interactive identities by proximity.

## Dates, Alice, Lisa and earlier acceptance

The date controls select existing approved database and caption records. All 26 database chronology records stay together. Both printed newspaper dates stay together. Alice's animation and required timing remain paired. Lisa's artwork is independent.

Earlier source-bound opening, date-window, Alice and Lisa checks remain evidence for those exact assets. The default game is byte-identical to the earlier build that reached the ending, all nine credit programs, required fights, transitions, normal saving, shutdown and a fresh game-menu load. Act 1 began from cold boot; later testing continued from an accepted Act 2 checkpoint.

The default restoration worked on a U.S. Genesis Model 2 with a Mega EverDrive Pro. That report does not establish a full console playthrough or console save/load acceptance. Other selections have no console acceptance. There is no claim of thousands of new full-game playthroughs, new variant CHD checks or new Mega EverDrive package checks.

## Source reproduction

A fresh curated source tree, without an external asset cache, reproduced all 70 deltas, the complete 4,096-target registry, all 76 family states across 7,448 asset hashes, and all six default artifacts including CHD. All 32 staged inputs stayed unchanged. The only private-to-public source adaptation was the sanitized approval-column label in the ledger readers.

The initial exported test suite exposed a CSP-sensitive polling method in a test. Locator assertions and explicit DOM readiness replaced string evaluation in tests. The app's security policy remained intact. Affected tests passed after that test-only change. The final source and package include those fixes and the CLI error-boundary fix.
