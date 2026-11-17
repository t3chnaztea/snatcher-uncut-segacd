# Patch recipes and release deltas

`text/` and `gfx/` contain guarded restoration recipes. Complete game assets stay in ignored private/build directories. Private builders write artifacts under ignored `build/` or `dist/` paths.

The curated public source also contains verified source-relative VCDIFF deltas: `profiles/` preserves the earlier direct patches; `components/` supplies the advanced choices. Each requires the matching original data track. No game image or BIOS is included.
