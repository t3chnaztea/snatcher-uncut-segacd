<p align="center">
  <img src="media/assets/repo-banner.png" alt="Snatcher Uncut: Sega CD Restoration Patch" width="1200">
</p>

<h1 align="center">Snatcher for Sega CD, with the original cameos back</h1>

<p align="center">
  A partial restoration of the English Sega CD release.<br>
  Patch your own copy in your browser.
</p>

## RESTORED

- Dog guts: Alice's twitching intestines return, restoring the PC Engine animation.
- Lisa's dress: Her android corpse's exposed breast returns, reversing the Sega CD cover-up.
- Outer Heaven cameos: The six original film/TV costume views return, with matching dialogue and headings.
- Dates: Selected text and opening captions return to the Japanese chronology: 1991, 2039 and 2042.

## UNCHANGED

- English voices and music: Original recordings stay intact. Spoken 1996 still differs from restored 1991 text.
- Expanded Act 3: Sega CD's story additions stay.
- Shower scene and panty-sniffing: No restoration. Sexualized content involving the Japanese version's underage character is outside this patch's scope. The English ages stay 18.
- Other dialogue and optional menus: Most of the localization stays. Rebuilding omitted interactions and translating their dialogue is outside this release's scope.


<p align="center">
  <a href="https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-player-v0.9.0-rc1.zip"><strong>Download the player patch</strong></a><br>
  Free · v0.9.0-rc1 · 691 KB · You'll need your own USA disc dump<br>
  Tested on my U.S. Genesis Model 2 with a Mega EverDrive Pro.<br><br>
  <a href="#see-the-changes">See the changes</a> · <a href="https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-media-v0.9.0-rc1.zip">Download the comparison kit</a>
</p>

## See the changes

### The Outer Heaven patrons return

![Original Sega CD patrons beside restored costume cameos](media/assets/outer-heaven-hero.png)

The PC Engine costume cameos replace the Konami characters in the Sega CD bar. Their descriptions change too. The dancer and lighting stay as they were.


### Six restored costume views

![Six original and restored costume views from Outer Heaven](media/assets/costume-gallery.png)

The characters were captured at different points in their idle animations.

### The dates change on screen

![Original December 2047 Neo Kobe caption beside restored December 2042 caption](media/assets/neokobe-comparison.png)

Neo Kobe returns to 2042. The newspaper changes to 2039. The catastrophe caption changes to 1991. [Compare Moscow](media/assets/moscow-comparison.png) and [the newspaper](media/assets/newspaper-comparison.png).

## Patch your copy

1. [Download the player ZIP](https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-player-v0.9.0-rc1.zip). Extract the whole folder.
2. Open `browser/index.html`. Choose your original single BIN and CUE. Select **Verify and patch**.
3. Save the patched BIN and CUE together in a new folder. Open that CUE to play.

Your disc files stay on your computer. The installer checks the data track before and after patching. It keeps your audio and disc timing intact. No game or BIOS is included.

[Full instructions](INSTALL.md) · [Offline installer for split-track sets](OFFLINE-INSTALL.md). Keep your originals and back up your saves. Windows, Linux and mobile operation haven't been tested.

## Testing

Automated Genesis Plus GX tests reached the ending and credits. They covered required fights, transitions and a normal save followed by shutdown, fresh boot and loading from the game menu. Act 1 started from cold boot; the later tests continued from an Act 2 checkpoint. All 20 audio tracks and pregaps stayed byte-identical to the original dump.

[Verification and installer checks](VERIFICATION.md) · [Compatibility and known issues](KNOWN-ISSUES.md).

## Before you download

**How much is "Uncut"?** It restores selected artwork, cameos and dates. Some localized content stays. Adult ages remain 18. Optional menus and excluded age or sexualized-minor content are unchanged. The [changelog](CHANGELOG.md) lists the scope.

**Did you change the English script or voices?** Most of the English stays. Selected dates and cameo wording change. The opening and database say 1991 while the original speech says 1996. I kept the recordings unchanged.

**Did you use AI?** Yes. I used AI coding agents for research, code, automated testing and documentation. The restored art comes from the game data, not an image generator. The screenshots are emulator captures. [How it was made](AI-DISCLOSURE.md).

This is an unofficial fan patch with no Konami affiliation. [Credits and references](CREDITS.md) · [Rebuild from source](docs/setup.md) · [Report a bug](https://github.com/t3chnaztea/snatcher-uncut-segacd/issues).
