# Offline Snatcher Patcher

Use the included Python installer for supported split-track sets or when the browser route is unsuitable. It needs Python 3.10 or newer and xdelta3. Keep your original dump and back up saves.

From the extracted player folder:

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --dates segacd \
  --output '/path/to/Snatcher Uncut'
```

The included `profiles.json` selects the patch and expected output. Default settings restore Japanese dates and all three art groups. `--dates segacd` keeps original English-release dates. `--no-cameos`, `--no-alice` and `--no-lisa` keep the corresponding original content. `--profile ID` selects one complete setting and cannot be mixed with those flags. The unchanged-disc selection produces no output.

## Supported layouts

- Single BIN/CUE with Track 1 data and 20 audio tracks. Pregaps are stored through INDEX 00.
- Twenty-one BINs with one CUE and one file per track, using supported INDEX 00/01 timing.
- Twenty-one BINs with supported virtual PREGAP timing. Supplied files and CUE bytes stay exact.
- Raw Track 1 BIN without a CUE. This output alone cannot play the game.

Every split BIN must start at its first stored index. CUE paths must be flat filenames in the same folder. Mixed layouts, WAVE audio, unsupported directives and unsafe filenames are rejected. Track 1 must match the supported USA raw data track.

The new output directory must not exist. Its parent must exist. The installer preserves original filenames and CUE bytes. It verifies the selected patch, resulting data track and each supplied audio track before completing the installation. Source files are checked again for changes. `install-receipt.json` records settings, checksums and track results.

## Evidence and limits

All 15 active selections passed real installation in all four layouts: 60 cases. The tests independently checked 900 supplied audio-track outputs. Stored split outputs rejoined to their corresponding verified full-disc BIN. Fifteen crossed-profile patches were rejected before output. The unchanged-disc selection read no input and created no files.

Split test fixtures were derived from the reference single-BIN dump. The virtual-pregap fixtures intentionally omit the original stored pregap samples and express their duration in the CUE. The installer preserves those supplied inputs; it cannot preserve samples absent from them. These tests do not establish compatibility with an independently sourced alternate audio dump.

Local execution was tested on macOS. Windows and Linux execution remain untested. Read [INSTALL.md](INSTALL.md) for browser instructions and [KNOWN-ISSUES.md](KNOWN-ISSUES.md) for game compatibility.
