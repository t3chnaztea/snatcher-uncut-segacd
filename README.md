<p align="center">
  <img src="media/assets/repo-banner.png" alt="Snatcher Uncut: Sega CD Restoration Patch" width="1200">
</p>

<h1 align="center">Snatcher for Sega CD, mostly uncensored</h1>

<p align="center">
  A partial restoration of the English Sega CD release.<br>
  Unofficial fan patch. Includes browser-based patch tool.
</p>

Choose your restorations with **Snatcher Patcher**. Start with a preset or pick individual dates, guest views and wide-scene costumes. Keep the original Sega CD dates to match the English voices. Save your choices, reuse a receipt or share a short settings code.

## RESTORED

- Dog guts: Alice's twitching intestines return, restoring the PC Engine animation.
- Lisa's dress: Her android corpse's exposed breast returns, reversing the Sega CD cover-up.
- Outer Heaven cameos: Choose each of five guest groups, with matching dialogue and headings. The wide-scene crowd has its own switch.
- Dates: Choose database chronology, Moscow, newspaper and Neo Kobe captions separately. Japanese dates use 1991, 2039 and 2042. **Original Sega CD dates** keep 1996, 2044 and 2047.

## UNCHANGED

- English voices and music: Original recordings stay intact. Choose the original dates to match the voices. Japanese dates retain the spoken 1996 / on-screen 1991 difference.
- Expanded Act 3: Sega CD's story additions stay.
- Shower scene and panty-sniffing: No restoration. Sexualized content involving the Japanese version's underage character is outside this patch's scope. The English ages stay 18.
- Other dialogue and optional menus: Most of the localization stays. Rebuilding omitted interactions and translating their dialogue is outside this release's scope.


<p align="center">
  <a href="https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.11.0-rc1/snatcher-uncut-player-v0.11.0-rc1.zip"><strong>Download Snatcher Patcher</strong></a><br>
  Free · v0.11.0-rc1 · 12 choices · You'll need your own USA disc dump<br>
  The default restoration worked on my U.S. Genesis Model 2 with a Mega EverDrive Pro.<br>Other combinations have not been tested on the console.<br><br>
  <a href="#see-the-changes">See the changes</a>
</p>

## See the changes

### The Outer Heaven patrons return

![Original Sega CD patrons beside restored costume cameos](media/assets/outer-heaven-hero.png)

The complete restoration brings back the PC Engine costume cameos. You can now choose each guest group and the wide-scene crowd independently. Guest views keep their matching descriptions and headings. The dancer and lighting stay as they were.


### Six restored costume views

![Six original and restored costume views from Outer Heaven](media/assets/costume-gallery.png)

These images show the complete restoration. The characters were captured at different points in their idle animations.

### Choose which dates appear on screen

![Before: December 2047. After: restored December 2042 Neo Kobe caption.](media/assets/neokobe-comparison.png)

With Japanese dates selected, Neo Kobe returns to 2042. The opening captions and selected database dates change together. Original Sega CD dates keep 2047.

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

Japanese dates return the caption to 1991. The retained English voice recording still says 1996. Choose original Sega CD dates to keep both at 1996.

### Newspaper: 2044 → 2039

![Before: newspaper date says 2044. After: restored newspaper date says 2039.](media/assets/newspaper-comparison.png)

Japanese dates return both newspaper date elements to 2039. Original Sega CD dates keep 2044.

Game comparisons use actual emulator captures from graphics QA. Crops remove empty borders and enlarge the original pixels by whole numbers. No game artwork is generated or retouched.

## Snatcher Patcher

![Snatcher Patcher with presets, twelve individual choices and numbered BIN/CUE steps.](media/assets/patcher-desktop.png)

1. [Download the player ZIP](https://github.com/t3chnaztea/snatcher-uncut-segacd/releases/download/v0.11.0-rc1/snatcher-uncut-player-v0.11.0-rc1.zip). Extract the entire folder.
2. Open `browser/index.html` in your browser.
3. Under **01 · Restoration settings**, choose a preset. Open **Fine-tune dates and cameo groups** for individual choices.
4. Under **02 · Original disc BIN**, choose your untouched USA BIN. Under **03 · Matching CUE**, choose the CUE from the same dump.
5. Under **04 · Verify, then restore**, select **Verify and patch**. Wait for **Your patched files are ready**.
6. Download the patched BIN, CUE and verification receipt. Save them in a new folder. Open the CUE in your emulator or compatible player.

Twelve choices give 4,096 combinations: four date controls, five guest groups, the wide-scene crowd, Alice and Lisa. Guest views keep matching dialogue. Miss Money's front and rear stay together. H2O and Gulliver share one choice. Alice includes its required timing. Turning everything off needs no patch, file read or download.

Save your settings as JSON, import a supported receipt or share a code such as `SP2:xfff`. Local comparison previews include a separate, closed NSFW section. **Identify a patched BIN** checks its data track and shows a known configuration; it does not check audio or change the file. The tool also shows the offline command for your choices.

Your files stay on your computer. Snatcher Patcher verifies the original data, selected components and final data track. Audio and disc timing stay intact. Output filenames and the receipt identify your settings. Changing a setting clears old downloads. No game or BIOS is included.

[Full instructions](INSTALL.md) · [Offline installer for split-track sets](OFFLINE-INSTALL.md). Keep your originals and back up your saves. Windows, Linux and mobile installation have not been tested.

## Testing

The default build is byte-identical to the earlier accepted release. Automated Genesis Plus GX tests reached the ending and credits. They covered required fights, transitions and a normal save followed by shutdown, fresh boot and loading from the game menu. Act 1 started from cold boot; the later tests continued from an Act 2 checkpoint. All 20 audio tracks and pregaps stayed byte-identical to the original dump.

All 4,096 data-track targets passed independent checks and Chromium composition. Firefox and WebKit each passed 256 pairwise compositions. The browser matrix passed 192 complete disc downloads. The offline matrix passed 256 installs across four layouts. All 64 guest/crowd combinations passed 448 fresh native captures. A fresh source build reproduced every patch and target hash. These checks do not mean every combination received a new full-game playthrough.

[Verification and installer checks](VERIFICATION.md) · [Compatibility and known issues](KNOWN-ISSUES.md).

## Before you download

**How much is "Uncut"?** It restores selected artwork, cameos and dates. Some localized content stays. Adult ages remain 18. Optional menus and excluded age or sexualized-minor content are unchanged. The [changelog](CHANGELOG.md) lists the scope.

**Did you change the English script or voices?** Most of the English stays. Selected dates and cameo wording change when enabled. Japanese dates can make the opening and database say 1991 while the original speech says 1996. Choose original Sega CD dates to avoid that mismatch. Fine-tuning individual dates can mix chronologies; the tool marks that state. I kept the recordings unchanged.

**Did you use AI?** Yes. I used AI coding agents for research, code, automated testing and documentation. The restored art comes from the game data, not an image generator. The screenshots are emulator captures. [How it was made](AI-DISCLOSURE.md).

This is an unofficial fan patch with no Konami affiliation. [Credits and references](CREDITS.md) · [Rebuild from source](docs/setup.md) · [Report a bug](https://github.com/t3chnaztea/snatcher-uncut-segacd/issues).
