# Offline player installer

This installer applies the existing release patch to your own compatible USA
Sega CD dump. It needs Python 3.10 or newer and `xdelta3`. It does not need the
developer build, a PC Engine disc, BIOS files, a compiler, or extracted assets.
It never uploads game data. It does not overwrite source files.

## Install

Keep the patch and installer from the same release together. Check the release
ZIP checksum before extraction. Install Python and xdelta3 if they are absent.
Run:

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --patch snatcher-uncut-track01.xdelta \
  --output '/path/to/Snatcher Uncut'
```

The output directory must not exist. Its parent must exist. Use the produced
CUE in your emulator or device. Keep every BIN beside it. Existing BIN filenames
and the CUE contents stay unchanged inside the new directory.

Supply `--xdelta '/path/to/xdelta3'` if the program is not on PATH. On Windows,
use the installed Python command and the path to the xdelta3 executable.
Windows and Linux execution are not yet verified. Local tests used macOS.

For an extracted raw Track 1, supply the `.bin` instead of the `.cue`. The raw
output is **not a complete playable disc**. Reassembly is the caller's task.
Use CUE input for the complete-disc route.

## Accepted inputs

The verified raw Mode1/2352 Track 1 must have:

| Check | Value |
|---|---|
| Bytes | 131,744,928 |
| SHA1 | `1f4164205ed736a0d9a03eb7972868e9aa737d35` |
| Patched SHA256 | `f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba` |
| Release xdelta SHA256 | `1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4` |

Supported layouts:

* One raw Track 1 `.bin`, with exactly the byte count above.
* One `.cue` referencing one full-disc BIN. Tracks run 01 through 21. Track 01
  uses MODE1/2352. Tracks 02 through 21 use AUDIO. Stored audio pregaps use
  INDEX 00. Track 01 begins at INDEX 01 00:00:00 without a pregap.
* One `.cue` referencing 21 BINs, one per track in that order. Each BIN starts
  at its first stored index, at 00:00:00. Audio pregaps may be stored with
  INDEX 00 or declared with PREGAP. The two forms cannot appear on one track.

CUE files must use ASCII or UTF-8. Referenced BINs must have flat relative filenames
in the same directory. Regular files are required; symlinks are rejected.
Quoted BINARY FILE entries, TRACK, INDEX 00/01, PREGAP and common metadata
(REM, TITLE, PERFORMER, SONGWRITER, CATALOG, ISRC, FLAGS) are accepted. Other
directives, mixed file groupings, subdirectories, unsupported sector modes,
overlapping indices and incomplete layouts fail with an error. The installer
does not rewrite or repair a malformed CUE.

CHD and ISO/2048 are not direct inputs. Extract a CHD to BIN/CUE with a local
tool first. The extracted Track 1 and CUE must pass the checks above. Any CHD
repack is a separate operation. Do not treat an ISO/2048 file as a raw BIN.

## Preservation and verification

Only the validated data track changes. All supplied audio samples, stored
pregap bytes, track order, index times, virtual pregap declarations and CUE
metadata remain intact. Audio hashes may differ between dumps. The installer
does not require our whole-BIN checksum or normalize your audio.

The installer validates the source Track 1 and release patch before staging.
It decodes into a temporary directory beside the destination. It verifies the
patched Track 1, every audio track and input-file stability. It then creates the
destination exclusively. It checks final output hashes before writing
`install-receipt.json`. The receipt lists per-file and per-track input/output
hashes. No absolute source paths appear in the receipt.

Leave free space for two complete copies of the output plus two data tracks
and a small buffer. Temporary staging is removed after success or failure.
An I/O failure during final copying can leave an incomplete destination. A
completed installation has a verified receipt. Do not use a partial directory.
Choose a fresh output directory for a retry. Source files remain unchanged.

An already-patched track fails explicitly. An unsupported source hash can
mean a different region, revision, bad dump, or previously changed data. Never
bypass the hash check. A patch checksum error means the patch does not match
this installer release.

## Verification scope

Generated-patch tests cover raw, single-BIN, split-BIN stored-pregap and
split-BIN virtual-pregap layouts. They check exact CUE/audio preservation and
errors for malformed geometry, unsupported input, changed hashes, overwrite,
symlinks, missing xdelta3, corrupted patch and wrong decoded target.

Actual-disc acceptance checks raw Track 1, the staged single-BIN/CUE, and a
split-BIN/CUE derived by losslessly slicing that same staged input. This proves
layout handling for that dump. It does not establish compatibility with an
independently sourced alternate audio dump. Emulator or console behavior is a
separate test. Original-console acceptance remains Not run.

Developer test command, with temporary files kept on the project drive:

```sh
mkdir -p build
python3 -m pytest tests/test_player_install.py -q \
  --basetemp=build/player-install-tests
```
