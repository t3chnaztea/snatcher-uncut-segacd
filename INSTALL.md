# Install Snatcher Uncut

Supply your own compatible USA Sega CD dump. Keep the original files and back up
your saves. The release ZIP contains a patch and tools, not a game image or BIOS.

## Browser installer

Extract the complete release ZIP. Open `browser/index.html` from that folder.
Choose your original single BIN and its CUE. Select **Verify and patch**.
Download the patched BIN and CUE into a new folder. Open that CUE in your player.

The browser installer works locally. It has no upload endpoint, analytics,
external scripts or network dependency. It checks the data track before
patching. It checks the patched track before offering downloads. Your audio
bytes stay unchanged. The CUE keeps its timing and metadata. Only its BIN
filename changes to `Snatcher Uncut.bin`.

Use this route for a single BIN containing all 21 tracks. A raw Track 1 BIN is
also accepted, but that output alone cannot play the game. Keep the original
audio tracks and assemble a matching CUE separately. The browser route rejects
split-track CUE sets, virtual PREGAP directives and unsupported CUE layouts.
Use the offline installer for supported split-track sets.

Local-file download checks passed on macOS in Chromium 159, Playwright Firefox
159 and Playwright WebKit 27.2. Each downloaded full-disc BIN matched the accepted
emulator image. All 20 audio tracks, including stored pregaps, matched the
input. WebKit testing does not establish Safari application compatibility.
Windows, Linux and mobile browser operation have not been tested.

## Offline installer

The offline route needs Python 3.10 or newer and xdelta3. It accepts a single-BIN
CUE, a supported 21-BIN CUE, or raw Track 1. It preserves the CUE bytes and BIN
filenames inside a new output directory. Read [OFFLINE-INSTALL.md](OFFLINE-INSTALL.md)
for supported layouts, requirements and errors.

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --patch snatcher-uncut-track01.xdelta \
  --output '/path/to/Snatcher Uncut'
```

The destination must not exist. Its parent must exist. A completed offline
installation has `install-receipt.json` with verified file and track hashes.
Keep every output BIN beside the CUE. Local execution was tested on macOS.
Windows and Linux execution remain untested.

## Input checks

| Check | Value |
|---|---|
| Raw Track 1 format | Mode1/2352 |
| Raw Track 1 bytes | 131,744,928 |
| Original Track 1 SHA1 | `1f4164205ed736a0d9a03eb7972868e9aa737d35` |
| Patched Track 1 SHA256 | `f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba` |
| Release patch SHA256 | `1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4` |

Do not bypass validation. A wrong hash can indicate a different region,
revision, extraction, damaged dump or previous patch. Whole-disc hashes can
differ between dumps because their audio differs. The installer checks Track 1
and preserves the supplied audio.

CHD and ISO/2048 files are not direct inputs. Extract CHD to BIN/CUE with a local
tool first. The extracted files must pass the same checks. Renaming an ISO or
CHD to `.bin` does not convert it.

## After installation

Open the output CUE. Check the opening, voices and music. Start a new game or
use a backed-up save. Transfer of existing saves from the original disc has
not been verified. Normal saving and a fresh load passed with the patched
emulator image. [KNOWN-ISSUES.md](KNOWN-ISSUES.md) gives the remaining limits.

The owner reports this build working on a U.S. Genesis Model 2 with a Mega EverDrive Pro. Full console playthrough and console save/load coverage have not been documented. A successful browser patch alone does not establish hardware compatibility.
