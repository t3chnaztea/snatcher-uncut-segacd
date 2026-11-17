# Offline Snatcher Patcher

Extract the entire player ZIP. Keep `profiles.json`, `patches/components/` and `tools/` together. Supply your own matching USA dump. Python 3.10 or newer and xdelta3 are required. No game or BIOS is included.

The browser is the easiest way to choose settings. Open **Use these choices offline** for the corresponding command. Export a settings file or copy its `SP2:x###` code to reuse all twelve choices offline.

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --settings '/path/to/settings.json' --output '/path/to/New Copy'
```

`--code 'SP2:x800'` selects only the wide-scene costumes. `--profile x800` selects the same choices. Legacy configurable-release IDs map to their identical outputs. The broad `--dates segacd`, `--no-cameos`, `--no-alice` and `--no-lisa` flags remain available. Use one selection method per command.

Supported layouts are raw Mode1/2352 Track 1, a single BIN/CUE, split BINs with stored INDEX 00 samples, and split BINs with virtual PREGAP timing. Keep every referenced BIN beside the CUE. Output goes into a new folder. Original files are never overwritten. Supplied filenames and CUE bytes stay unchanged.

The installer verifies source Track 1, selected component patches, decoded sector data, the final target, all supplied audio, and completed output files. It reads every component against the original source. A component is not applied over an earlier component's output. Wrong source, damaged patches, changed inputs, overlapping sectors and wrong final hashes stop installation.

Virtual PREGAP represents time without stored samples. Checks preserve the audio supplied in that layout. They cannot prove equality for samples omitted from the input.

The all-off selection creates no output and does not read the supplied source path. An exported settings file or supported installation receipt supplies preferences only. Its old hashes and file paths do not authorize an installation.

Use `--identify` with a raw BIN or supported CUE to identify a known data track. Identification does not check audio or modify files. It reports no whole-disc or hardware acceptance.

[Installation guide](INSTALL.md) · [Verification](VERIFICATION.md) · [Known issues](KNOWN-ISSUES.md)
