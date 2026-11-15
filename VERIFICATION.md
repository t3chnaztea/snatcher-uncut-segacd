# Verification

The patched data track is the release identity. Its SHA256 is
`f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba`.
The 40,631-byte xdelta patch has SHA256
`1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4`.

## Game checks

| Check | Evidence and limit |
|---|---|
| Selected restorations | 37 approved records passed emulator checks: 31 text and six art records |
| Act 1 | Automated cold route reached Act 2 |
| Acts 2 and 3 | Accepted continuation reached the full ending and all nine original credit programs |
| Saving | Normal in-game save followed by shutdown, fresh boot and game-menu load passed |
| Fights and transitions | Required fights and act transitions passed during the accepted route |
| Audio data | All 20 audio tracks and stored pregaps matched the reference input byte for byte |
| Audio output | Callback accounting and selected source-audio comparisons passed |
| U.S. Genesis Model 2 + Mega EverDrive Pro | Worked on my console; the full playthrough and save/load checks were in the emulator |

Genesis Plus GX supplied the test core. The accepted route spans several
sessions. Act 2 continued from an accepted emulator checkpoint. Later save/load
checks used the game's own menus in a fresh process. Targeted graphics checks
are separate from normal story progression. These results do not establish
compatibility with every core version or frontend.

Separate AI agents reviewed source and evidence. That work is automated review.
It does not establish independent human Japanese review, manual full-game QA or
a human full-route listening review.

## Player installer checks

The offline installer passed actual raw Track 1, single-BIN/CUE and split-BIN/CUE
checks on macOS. The split input was sliced without loss from the same reference
dump. Rejoining its output reproduced the single-BIN result. These checks do not
establish compatibility with an independently sourced alternate audio dump.

The browser installer passed actual full-disc downloads in Chromium 159,
Playwright Firefox 159 and Playwright WebKit 27.2 on macOS. Each downloaded BIN
matched the accepted emulator BIN. Each output preserved all 20 audio tracks
and stored pregaps. Only the BIN filename changed in the CUE. The checks recorded
no external requests or page errors.

Independent browser checks verified raw Track 1 downloads and rejection of an
unsupported source, missing patch and tampered patch. Parser tests cover
malformed track times, index order, unsupported layouts and filename handling.
These are local browser-engine tests. They do not establish Safari application,
Windows, Linux or mobile compatibility.

## Compare your result

Use the install receipt and data-track hash above. Whole-disc hashes depend on
the supplied audio. The reference input's 20 audio tracks differ from the
referenced Redump audio set. The installer preserves the supplied audio instead
of converting it to another dump's bytes.

Media provenance records the source capture hashes, crops, scaling and output
hashes. Comparison GIFs alternate still captures. The release reel is silent.
The optional dog clip uses native animation samples behind a gore warning.
Lossy MP4 and WebM copies do not preserve exact RGB values. PNG and still-GIF
checks cover the native game pixels at integer scale.
