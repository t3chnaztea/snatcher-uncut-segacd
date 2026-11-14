# Reproduce the local artifacts

The repository contains tools, tests and source-derived patch recipes. Supply
your own matching game discs and BIOS files. It contains no disc images,
extracted assets, translation corpus, emulator checkpoints or raw capture batches.
Approved promotional comparisons are included under media/.

## Tested host

The verified build uses macOS on an APFS volume. The builder uses `cp -c` for
copy-on-write disc copies. Linux and Windows are not verified build hosts.
Allow at least 8 GiB for build output above the project's 100 GiB free-space
floor. Keep the checkout, dependencies and output on the same volume.

Tested tools: CPython 3.14.10, Pillow 13.0.0, chdman 0.289 and xdelta3 3.2.2.
Python packages are pinned in `requirements-dev.txt`. chdman and xdelta3 must
be on PATH. Homebrew provides these commands in `rom-tools` and `xdelta`:

```sh
brew install rom-tools xdelta uv
uv venv --python 3.14.10 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
```

Homebrew installs its current formula versions. For exact artifact identity,
use the tested command versions. A different CHD encoder version can change
container bytes even when its extracted disc content matches.

## User-supplied inputs

`config/input-manifest.json` lists all 32 required relative paths, lengths
and SHA1 values. Stage each file under `private/` at its listed path. It
includes the USA Sega CD single BIN/CUE and reference CHD, Japanese PC Engine
CD tracks/CUE, and four BIOS files. Do not rename tracks without preserving
CUE references.

The input specification contains metadata only. The staging command reads
and verifies files. It does not download or copy game data. Missing or wrong
files stop setup. A mismatched existing private manifest is not overwritten.

## Pinned reference tools

The build reads the PC Engine codec and reference metadata from this checkout:

```sh
mkdir -p .deps
git clone https://github.com/pepasjc/snatcher-translated.git .deps/snatcher-translated
git -C .deps/snatcher-translated checkout f181542e188a4c5bcd18080bb282518c53761acd
.venv/bin/python tools/setup_inputs.py
```

Keep the reference checkout read-only after setup. Its MIT codec is imported
at runtime. Its translation JSON files are used for private alignment and
are never added to this repository. The reference project licenses its
translation and documents under CC BY-NC-SA 4.0. See [CREDITS.md](../CREDITS.md) for their license scopes.
ScummVM, Genesis Plus GX and the assembler are investigation/harness tools;
they are not needed for the default artifact build. The public source subset does not bundle these investigation tools.

## Build and verify

```sh
.venv/bin/python tools/build.py
.venv/bin/python tools/verify_build.py
```

The build derives the approved text and artwork from untouched inputs. It
creates BIN/CUE, CHD and a raw-track-1 xdelta in `dist/`. It also creates the
numbered Mega EverDrive Pro BIN/CUE folder. The build receipt is
`build/m5/build-manifest.json`. Verification checks ISO file extents, both
size encodings, boot data, approved asset composition, sector EDC/ECC,
all 20 audio tracks and pregaps, xdelta decode, CHD extraction and the
EverDrive copy. These are packaging checks, not a new gameplay run.

Text recipes contain hash-guarded XOR spans over source records. Complete
original or replacement passages are materialized only in memory and ignored
working files. Recipe conversion preserves all 72 approved encoded outputs.

## Tests and private evidence

Synthetic tests do not need game files. Source-dependent tests require staged
inputs, extracted source and generated private reference records. The default
build creates those derivable records. Existing acceptance reports also refer
to local native states and golden screenshots. Those files are deliberately
excluded from GitHub. A clean clone does not recreate the old acceptance run
merely by running the build or its packaging verifier.

Full-game verification used a separate controller session and normal in-game
save/reload checks. Diagnostic captures and emulator states remain private.
Read ../KNOWN-ISSUES.md for the accepted scope and separate hardware limits.


## Prepare source integration tests

The builder extracts into its build directory. Source integration tests also
need the default private extraction. Derive it from your staged disc before
running those tests:

```sh
.venv/bin/python tools/scd_disc.py extract
.venv/bin/python -m pytest tests -q --basetemp=build/source-tests
```

This creates local ignored files. It does not download or publish game data.
