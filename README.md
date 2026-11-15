<p align="center">
  <img src="media/assets/repo-banner.png" alt="Snatcher Uncut: Sega CD Restoration Patch" width="1200">
</p>

<h1 align="center">Restore the cameos. Keep the English dub.</h1>

<p align="center">
  Play Snatcher's English Sega CD release with selected artwork and dates restored.<br>
  The original voice cast, music and expanded Act 3 stay.<br>
  Patch locally in your browser.
</p>

<p align="center">
  <a href="https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-player-v0.9.0-rc1.zip"><strong>Download the player patch</strong></a><br>
  Free · v0.9.0-rc1 · 691,239 bytes · Supply your own USA disc dump<br><br>
  <a href="#see-the-changes">See the changes</a> · <a href="https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-media-v0.9.0-rc1.zip">Download the comparison kit</a>
</p>

## See the changes

### The Outer Heaven patrons return

![Original Sega CD patrons beside the restored source costume cameos](media/assets/outer-heaven-hero.png)

The costume patrons from the PC Engine version replace the Sega CD's Konami cameos. Their descriptions change with them. The original dancer and lighting remain. These are patron crops from actual emulator graphics checks.

<table>
<tr>
<td width="50%"><img src="media/assets/outer-heaven-still-loop.gif" alt="Alternating original and restored Outer Heaven patron stills" width="560"></td>
<td width="50%"><img src="media/assets/chronology-still-loop.gif" alt="Alternating original and restored Neo Kobe year-caption stills" width="560"></td>
</tr>
<tr>
<td>Outer Heaven: original and restored stills.</td>
<td>Neo Kobe: 2047 becomes 2042.</td>
</tr>
</table>

Both six-second GIFs alternate captured stills. They are comparisons, not gameplay video. The source pixels use integer scaling.

### Six restored costume views

![Six original and restored costume views from Outer Heaven](media/assets/costume-gallery.png)

These graphics-check captures use different idle-animation phases. Six costume views share the existing five identity groups; H2O and Gulliver keep their combined menu branch.

### The dates change on screen

![Original December 2047 Neo Kobe caption beside restored December 2042 caption](media/assets/neokobe-comparison.png)

Neo Kobe returns to 2042. The newspaper dates change to 2039. The catastrophe caption changes to 1991. [Compare Moscow](media/assets/moscow-comparison.png) and [the newspaper](media/assets/newspaper-comparison.png).

### Watch the 42-second comparison

[![Watch the silent Snatcher Uncut comparison reel](media/assets/release-reel-poster.png)](media/assets/release-reel.mp4)

[Play the MP4](media/assets/release-reel.mp4) · [WebM version](media/assets/release-reel.webm). The reel is a silent edit of actual comparison stills.

<details>
<summary>Optional animation comparison: graphic animal gore and story spoiler</summary>

The dog scene animates again. This five-second clip compares native emulator samples. The source selection stays static here; the restored sequence moves.

![Graphic animal gore: original dog scene beside restored native animation](media/assets/dog-native-comparison-GORE.gif)

The patch also restores an adult corpse pose. Neither scene appears in the lead images or reel.

</details>

## Patch your copy in three steps

1. [Download the player ZIP](https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-player-v0.9.0-rc1.zip). Extract the whole folder.
2. Open `browser/index.html`. Choose your original single BIN and CUE. Select **Verify and patch**.
3. Save the patched BIN and CUE together in a new folder. Open that CUE in your player.

Patching runs locally. Your disc files stay on your computer. The installer verifies the data track before and after patching. It preserves your audio bytes and disc timing. The download contains no game or BIOS.

[Full instructions and supported inputs](INSTALL.md) · [Offline route for split-track sets](OFFLINE-INSTALL.md). Keep your originals. Back up saves before patching. Windows, Linux and mobile operation remain untested.

## Tested through the ending

Automated Genesis Plus GX testing reached the ending and original credits. Required fights, transitions, normal saving, shutdown and a fresh game-menu load passed. All 20 reference audio tracks and pregaps stayed byte-identical. The accepted route spans several sessions, including an Act 2 emulator checkpoint; it is not one uninterrupted cold playthrough.

Original-console acceptance remains pending. [Verification and installer checks](VERIFICATION.md) · [Compatibility and known issues](KNOWN-ISSUES.md).

## Before you download

**How much is "Uncut"?** Selected restorations: 31 text records and six art records, not 37 separate scenes. Those cover chronology, cameo identities, three opening captions and the visual changes above. Adult ages stay at 18. Optional menus and excluded age or sexualized-minor content stay unchanged. [Exact change list](CHANGELOG.md).

**Does it replace the English script or voices?** Most of the existing localization stays. Selected dates and cameo wording change. The opening and database show 1991 while the retained speech says 1996. No voices or music were re-recorded.

**Was AI used?** Yes. TECH NASTY developed this patch with AI coding agents for research, code, test controllers, evidence review and documentation. The art comes from source game data through deterministic conversion. The images are emulator captures. No generative image model made the game art. Automated review is not independent human QA. [Process disclosure](AI-DISCLOSURE.md).

This is an unofficial fan patch with no Konami affiliation. [Credits and references](CREDITS.md) · [Rebuild from source](docs/setup.md) · [Report a bug](https://github.com/t3chnaztea/snatcher-uncut-segacd/issues).
