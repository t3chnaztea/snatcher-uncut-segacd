# Install with Snatcher Patcher

Use your own compatible USA Sega CD dump. Keep the original files and back up your saves. The download includes patches and tools. It includes no game image or BIOS.

## Start with a preset

Open `browser/index.html` after extracting the entire player ZIP. Choose a preset:

- All available restorations: the same game output as the earlier default release.
- Restored art, original Sega CD dates: all restored artwork with dates that match the English chronology.
- Cameos only: original dates and Sega CD Alice/Lisa artwork.
- Japanese dates only: original Sega CD artwork.
- Cameos and Japanese dates: keeps the Sega CD artwork for Alice and Lisa.
- Original Sega CD: no patch, input read or download is needed.

The Dates selector changes all date choices together. The Outer Heaven switch changes all cameo choices together. Alice includes its required animation timing. Lisa has its own artwork switch.

## Fine-tune individual choices

Open **Fine-tune dates and cameo groups** for twelve choices:

- Japanese database chronology: all 26 approved date records together.
- Moscow caption: 1991 when enabled; 1996 when disabled.
- Newspaper dates: both printed dates use 2039 when enabled; 2044 when disabled.
- Neo Kobe caption: 2042 when enabled; 2047 when disabled.
- Mask Rider, Cornelius, Alyen, Miss Money and H2O/Gulliver: five guest groups with matching dialogue and headings. Each choice includes its rear/front views. Miss Money's views stay together. H2O and Gulliver share one choice.
- Wide-scene costumes: the bar crowd, independently of those five guest views.
- Alice animation: twitching guts, with graphic gore.
- Lisa artwork: adult android corpse artwork, with nudity.

Mixed dates can disagree with each other. The tool marks a mixed chronology. Japanese 1991 text still differs from the unchanged English recording, which says 1996. Use original Sega CD dates to keep that chronology.

All 4,096 selections have an exact expected data-track checksum. The all-off selection matches the original disc. The earlier sixteen settings retain their exact game outputs.

## Create your files

1. Choose settings under **01 · Restoration settings**.
2. Under **02 · Original disc BIN**, select your untouched USA BIN.
3. Under **03 · Matching CUE**, select the CUE from the same dump.
4. Under **04 · Verify, then restore**, select **Verify and patch**.
5. Download the verified BIN, CUE and receipt. Save them together in a new folder. Open the CUE to play.

Your files stay on your computer. No upload, account, analytics or network connection is required. Snatcher Patcher checks the original data, each selected patch component and the finished data track. Settings lock while it works. Changing a setting or input clears old downloads.

Output filenames and the receipt identify your choices. The browser changes only the CUE's BIN filename. Audio bytes and disc timing stay intact.

Use a single BIN containing all 21 tracks. A raw Track 1 BIN is also accepted with no CUE selected. A raw track is not a complete playable disc; keep the original audio and assemble a matching CUE. Use the offline installer for split-track sets or virtual PREGAP directives.

## Save, share or reuse settings

Open **Save, share or reuse settings** to export a small JSON file, import settings or a supported receipt, or copy a code such as `SP2:xfff`. Loading preferences clears old downloads. Imported preferences select choices only. The installed release supplies the trusted patches and checksums.

The tool accepts current settings files and receipts from the configurable releases. A receipt records an earlier installation; importing it does not verify that old disc again.

## Compare or identify

**Compare the changes** shows local reference captures. NSFW comparisons stay closed until selected. These show original and restored references; mixed cameo choices can look different.

For a BIN you already patched, select it in step 02 and open **Identify a patched BIN**. Identification reads Track 1 and reports a known configuration. It checks no audio and changes no files. Use the untouched source to create another configuration.

## Offline installer

Use Python 3.10 or newer and xdelta3. Keep the full extracted player folder, including `profiles.json`, `tools/` and `patches/`. Run commands from that folder. **Use these choices offline** shows the command for your current selection.

Default restoration:

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --output '/path/to/Snatcher Uncut'
```

Original Sega CD dates with all art restored:

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --dates segacd --output '/path/to/Snatcher Uncut Original Dates'
```

Use exported settings or a portable code:

```sh
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --settings '/path/to/settings.json' --output '/path/to/New Copy'
python3 tools/player_install.py '/path/to/Snatcher.cue' \
  --code 'SP2:x800' --output '/path/to/Wide Scene Only'
```

Identify an existing BIN without creating output:

```sh
python3 tools/player_install.py '/path/to/Patched.bin' --identify
```

The output folder must not exist. The offline installer keeps supplied filenames and CUE bytes. It supports raw Track 1, single-BIN CUE, split tracks with stored INDEX 00 samples, and split tracks with virtual PREGAP timing. Virtual timing cannot restore audio samples absent from your input.

[Offline details](OFFLINE-INSTALL.md) · [Verification](VERIFICATION.md) · [Known issues](KNOWN-ISSUES.md)
