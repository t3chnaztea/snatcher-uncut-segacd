# Install with Snatcher Patcher

Use your own compatible USA Sega CD dump. Keep the original files and back up your saves. The download contains restoration patches and tools. It contains no game image or BIOS.

## Choose your restorations

Snatcher Patcher has four controls:

- Dates: restored Japanese chronology or original Sega CD chronology.
- Outer Heaven cameos: original costume references with matching dialogue.
- Alice animation: twitching guts, with graphic gore.
- Lisa artwork: the original adult android corpse artwork, with nudity.

The default restores all four groups and reproduces the earlier release. Original Sega CD dates keep the 1996 catastrophe, 2044 newspaper and 2047 setting. Japanese dates use 1991, 2039 and 2042; the English recording still says 1996.

Cameo artwork and dialogue stay together. Alice's animation includes its required timing. All 16 settings are supported. Fifteen produce a patched disc. Original dates with all three art groups off matches the original disc, so no patch or download is needed.

## Browser tool

1. Extract the entire player ZIP. Open `browser/index.html`.
2. Choose the date setting and the three content switches.
3. Choose your untouched BIN and matching CUE.
4. Select **Verify and patch**. Wait for the verified downloads.
5. Save the BIN and CUE together in a new folder. Open the CUE to play.

The tool runs locally. No upload, account, analytics or network connection is required. It checks the original data, selected patch and finished data track. Changing a setting or input clears old downloads. The settings lock while a patch is running.

The output filenames include a settings ID. The receipt records the selected options and checksums. Keep each BIN with its matching CUE. The browser changes only the CUE's BIN filename; timing and other metadata stay intact. All original audio bytes are reused.

Use one BIN containing all 21 tracks. A raw Track 1 BIN is also accepted with the CUE field empty. Its output is not a complete playable disc: it still needs the original audio tracks and a matching CUE. Split-track inputs and CUE files with virtual PREGAP directives use the offline installer.

## Offline installer

The offline route needs Python 3.10 or newer and xdelta3. It reads the included `profiles.json` and selects the matching patch automatically.

Keep the default settings:

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --output '/path/to/Snatcher Uncut'
```

Keep the original Sega CD dates with all art restored:

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --dates segacd \
  --output '/path/to/Snatcher Uncut Original Dates'
```

Add `--no-cameos`, `--no-alice` or `--no-lisa` to keep that group's Sega CD content. Use `--dates japanese` for the restored chronology. Advanced callers can select one ID with `--profile`; it cannot be combined with the individual setting flags.

The destination must not exist. Its parent must exist. Offline installation preserves input BIN filenames, CUE bytes, audio and supplied pregaps in a new folder. The completed folder includes `install-receipt.json`. [Offline layout details](OFFLINE-INSTALL.md).

## Supported input and verification

Track 1 must be raw Mode1/2352, 131,744,928 bytes, SHA1 `1f4164205ed736a0d9a03eb7972868e9aa737d35`. Wrong regions, revisions, damaged data and previously patched tracks fail validation. Extract CHD files before installation. ISO/2048 is unsupported.

Each active selection has its own verified patch and target data-track checksum in [profiles.json](profiles.json). Whole-disc hashes depend on the supplied audio. Compare the data-track hash and receipt instead.

All 15 active settings passed actual full-disc browser downloads in Chromium, Playwright Firefox and Playwright WebKit on macOS. Raw-track downloads passed in Chromium. All 15 passed real offline installation in four supported layouts. Audio and CUE checks passed for every tested output. [Verification](VERIFICATION.md).

These engine tests do not establish Safari application, Windows, Linux or mobile installation compatibility. The mobile interface was checked for layout and controls. The default game output matches the earlier console-tested build; other combinations have no console acceptance.
