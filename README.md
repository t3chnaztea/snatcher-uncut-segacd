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
  <a href="https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-player-v0.9.0-rc1-ui2.zip"><strong>Download the player patch</strong></a><br>
  Free · v0.9.0-rc1 · UI2 installer · You'll need your own USA disc dump<br>
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

![Before: December 2047. After: restored December 2042 Neo Kobe caption.](media/assets/neokobe-comparison.png)

Neo Kobe returns to 2042. The opening captions and selected database dates follow the Japanese chronology.

## NSFW

<details>
<summary>Show Alice and Lisa comparisons: graphic gore, nudity and story spoilers</summary>

### Alice the dog's twitching guts

![Original static Sega CD dog scene beside the restored scene, with three captured animation phases.](media/assets/alice-dog-comparison-NSFW.png)

The Sega CD scene is static. The patch restores the animation. The three close-ups show different phases as separate stills.

### Lisa Nielsen's android corpse

![Sega CD dress cover-up beside the restored exposed-breast artwork for Lisa's adult android double.](media/assets/lisa-android-comparison-NSFW.png)

The original exposed breast returns. The surrounding scene stays intact.

</details>

## Misc

### Joy Division / Plato's Cavern: unchanged

![Plato's Cavern in Sega CD, unchanged by the patch, beside the Japanese PC Engine Joy Division sign.](media/assets/shop-name-reference.png)

The Japanese shop is Joy Division. This patch keeps Plato's Cavern because the English dialogue still uses that name. Changing only the sign would make them disagree. This comparison records the difference; it is not a restored change.

### Moscow: 1996 → 1991

![Before: Moscow catastrophe caption says 1996. After: restored caption says 1991.](media/assets/moscow-comparison.png)

The caption returns to 1991. The retained English voice recording still says 1996.

### Newspaper: 2044 → 2039

![Before: newspaper date says 2044. After: restored newspaper date says 2039.](media/assets/newspaper-comparison.png)

Both newspaper date elements return to 2039.

Game comparisons use actual emulator captures from graphics QA. Crops remove empty borders and enlarge the original pixels by whole numbers. No game artwork is generated or retouched.

## Patch your copy

![Snatcher Uncut disc patcher with numbered BIN, CUE and Verify and patch steps.](media/assets/patcher-desktop.png)

1. [Download the player ZIP](https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.9.0-rc1/snatcher-uncut-player-v0.9.0-rc1-ui2.zip). Extract the entire folder.
2. Open `browser/index.html` in your browser.
3. Under **01 · Original disc BIN**, choose your untouched USA BIN.
4. Under **02 · Matching CUE**, choose the CUE from the same dump.
5. Select **Verify and patch**. Wait for **Your patched files are ready**.
6. Download the patched BIN and CUE. Save both in a new folder. Open the CUE in your emulator or compatible player.

Your files stay on your computer. The installer verifies the original and patched data tracks. Your audio and disc timing stay intact. No game or BIOS is included.

The UI2 download has the interface shown above. It uses the same restoration patch as the original release.

[Full instructions](INSTALL.md) · [Offline installer for split-track sets](OFFLINE-INSTALL.md). Keep your originals and back up your saves. Windows, Linux and mobile operation haven't been tested.

## Testing

Automated Genesis Plus GX tests reached the ending and credits. They covered required fights, transitions and a normal save followed by shutdown, fresh boot and loading from the game menu. Act 1 started from cold boot; the later tests continued from an Act 2 checkpoint. All 20 audio tracks and pregaps stayed byte-identical to the original dump.

[Verification and installer checks](VERIFICATION.md) · [Compatibility and known issues](KNOWN-ISSUES.md).

## Before you download

**How much is "Uncut"?** It restores selected artwork, cameos and dates. Some localized content stays. Adult ages remain 18. Optional menus and excluded age or sexualized-minor content are unchanged. The [changelog](CHANGELOG.md) lists the scope.

**Did you change the English script or voices?** Most of the English stays. Selected dates and cameo wording change. The opening and database say 1991 while the original speech says 1996. I kept the recordings unchanged.

**Did you use AI?** Yes. I used AI coding agents for research, code, automated testing and documentation. The restored art comes from the game data, not an image generator. The screenshots are emulator captures. [How it was made](AI-DISCLOSURE.md).

This is an unofficial fan patch with no Konami affiliation. [Credits and references](CREDITS.md) · [Rebuild from source](docs/setup.md) · [Report a bug](https://github.com/t3chnaztea/snatcher-uncut-segacd/issues).
