# Verification

## Configurable release

The release supports 16 selections across dates, cameos, Alice animation and Lisa artwork. Fifteen are active patches. The original-disc selection has no patch or downloads. [profiles.json](profiles.json) lists the reviewed settings, patch hashes and expected data-track hashes.

The default selection reproduces the earlier accepted Track 1 SHA256:
`f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba`.
Its xdelta remains byte-identical, SHA256:
`1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4`.

With the reference input audio, its whole BIN remains SHA256:
`5b502e0a5b52175ebc16d66b88078ce22d652e9fb38e1250bde9b2774561e7bd`.
Whole-disc hashes can differ with other audio dumps. Data-track hashes identify the selected restoration.

## Disc and content matrix

All 16 outputs passed independent comparison of 98 canonical game assets. Enabled groups equal the accepted restored assets. Disabled groups equal the original source. Original dates leave SP04, SP05, DATA_D0 and DATA_D1 retail-exact. The all-off selection is the exact original disc.

Every output passed checks for 100 ISO files, fixed layout, 56,014 data sectors, EDC/ECC, all 20 audio tracks with stored pregaps, and CUE timing. All 15 active deltas decoded to the expected target. The audit scanned each sector in each output; it reused a successful parity proof only when the LBA and complete sector bytes were identical. There were 56,067 distinct sector proofs across the matrix.

Profile builds use BIN/CUE and raw-track artifacts. They do not claim new CHD or EverDrive-package verification. Earlier CHD checks remain evidence for the earlier fixed release only.

## Installer matrix

| Check | Result |
|---|---|
| Full-disc browser downloads | 15 active profiles in each of Chromium, Playwright Firefox and Playwright WebKit: 45 cases |
| Browser raw Track 1 | All 15 profiles passed in Chromium |
| Original-disc selection | No downloads in all three engines |
| Offline installs | 15 profiles across raw, single-BIN, stored-pregap split and virtual-pregap split layouts: 60 cases |
| Offline supplied audio | 900 independent track checks passed |
| Wrong-profile patches | Rejected without output in browser and offline checks |
| Input and setting changes | Old downloads revoked; settings disabled during work |
| Browser requests and errors | No app network requests or page errors in the completed matrix |

Each downloaded data track matched its selected checksum. Full-disc browser checks independently compared all 20 audio tracks and stored pregaps. CUE changes were limited to the BIN FILE operand. Offline checks preserved the supplied CUE bytes and filenames. Parser tests retained all 25 existing CUE cases.

Tests used the reference dump on macOS. The derived virtual-pregap inputs intentionally omit stored pregap samples and preserve their duration through CUE PREGAP. Their output checks cover the supplied files, not the omitted samples. These results do not establish Safari application, Windows, Linux or mobile installation compatibility.

## Runtime checks

Freshly bound source, original-date/restored-art and Japanese-date/original-art profiles supplied nine opening captures. Original-date captions were pixel-identical to the fresh source captures. All matched intro audio outputs were PCM-identical with nonzero signal.

Six SP04/SP05 diagnostic date windows checked the actual loaded module and selected string. Original-date windows matched the source. Japanese-date windows differed in the expected digit regions. These are diagnostic render checks, not natural database navigation.

Fresh art QA checked enabled and disabled cameos, Alice and Lisa. QA disc overlays are separate from untouched profile media. Their baseline BINs matched the selected profile before the documented QA changes. Alice produced ten distinct restored frames versus one original frame in the sampled 180-frame holds.

Fresh natural continuation reached the original reception dialogue wait. It does not claim a new menu-selection or full-game run for each combination.

## Source reproduction

A fresh curated source tree, with user-supplied inputs and pinned dependencies, reproduced all 16 data tracks and whole BINs, all 15 deltas, the registry and 1,568 canonical asset comparisons. The default build also reproduced all six accepted artifacts, including CHD. Its complete test suite passed 152 tests with zero failures or skips. All 32 supplied inputs remained unchanged.

The final flat source layout rebuilt the browser bundle byte-for-byte and produced the same player ZIP as the private assembly layout. These assembly checks cover the final public path fallbacks.

## Earlier game acceptance and hardware

The default output remains the exact earlier game. Genesis Plus GX testing reached the ending and all nine original credit programs. Required fights, transitions, normal saving, shutdown and a fresh game-menu load passed. Act 1 began from cold boot; the later route continued from an accepted Act 2 checkpoint. Selected scene checks were separate from natural progression.

The default restoration worked on a U.S. Genesis Model 2 with a Mega EverDrive Pro. That report is not full-console-playthrough or console save/load acceptance. New combinations have not received console acceptance.

Other combinations reuse the established retail or restored assets and controls, with exact group boundaries checked across all selections. This bounds the reused evidence. It is not a claim of 15 new full-game playthroughs, human Japanese review or a full-route listening review.
