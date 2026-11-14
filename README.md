# Snatcher Uncut: Sega CD Restoration Patch

Selected visual and chronology restorations for Snatcher's English Sega CD release. The original English voices, music and expanded Act 3 remain.

![Original Sega CD Outer Heaven patrons beside restored costume references](media/assets/outer-heaven-hero.png)

The comparison uses patron crops from graphics QA captures. The stage performer is outside the crop. [Watch the 42-second silent comparison reel](media/assets/release-reel.mp4).

This release candidate restores the Outer Heaven costume cameos, the dog animation, an adult corpse pose, and selected dates. Its scope is 37 approved change records: 31 text records and six art records. Those records are not 37 separate scenes. The patch retains most of the existing English localization.

## Install

Download `snatcher-uncut-player-v0.9.0-rc1.zip` from this repository's Releases page. Supply your own compatible USA Sega CD dump. Follow [INSTALL.md](INSTALL.md) to validate the input, apply the patch, and check the result. Keep your original files.

Applying the patch does not require the developer build or a Japanese PC Engine disc. The patch changes the data track. It preserves your audio tracks and disc timing. The download contains no game image or BIOS.

The supported raw data track has 131,744,928 bytes and SHA1 `1f4164205ed736a0d9a03eb7972868e9aa737d35`. The patched data track must have SHA256 `f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba`. Use the installer to check these values. A whole-disc checksum can differ when a dump has different audio bytes.

## What changes

The text changes cover 26 chronology records and five cameo identity groups. The art changes cover three opening date captions, the Outer Heaven patrons, the dog animation, and the adult corpse pose. Six costume views share the existing five identity groups. H2O and Gulliver keep their combined menu branch.

Some localized content remains by design. Adult ages remain 18. Optional menus, the port-specific additions, and excluded age or sexualized-minor content are unchanged. This is a selected restoration patch, not a new translation or a claim that every version difference has been removed.

The opening and database show the catastrophe year as 1991. The retained English speech says 1996. No voices or music were re-recorded. [CHANGELOG.md](CHANGELOG.md) lists the changes. [KNOWN-ISSUES.md](KNOWN-ISSUES.md) records the limits.

## Verification and compatibility

Automated Genesis Plus GX testing reached the ending and original credits. It covered required fights, transitions, normal in-game saving, shutdown, and loading through the game menu in a fresh process. All 37 approved records passed emulator checks. Selected scenes also received targeted graphics and text checks. Those targeted checks are separate from normal story progression.

[VERIFICATION.md](VERIFICATION.md) records the checks, output identity and limits.

The accepted route spans several emulator sessions. It is not a claim of one uninterrupted cold run through the whole game. The original 20 audio tracks and pregaps are byte-identical to the reference input. Captured output passed callback accounting and selected source-audio comparisons. These checks do not establish a full-route listening review.

Original-console testing has not run. Cabinet testing, FPGA compatibility, and transfer of existing saves to the patched game are not established. Back up saves before trying a patched disc. Use the tested combinations in [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

## Credits and development

TECH NASTY made this patch with AI assistance in research, code, test controllers, and documentation. The comparisons use actual game captures. The restored art comes from source game data through deterministic conversion. No generative image model made the game art. Read [AI-DISCLOSURE.md](AI-DISCLOSURE.md) for the process and limits.

[CREDITS.md](CREDITS.md) credits the original creators and technical references. This is an unofficial fan project. It has no affiliation with Konami.

The [developer setup](https://github.com/t3chnaztea/snatcher-uncut-segacd/blob/main/docs/setup.md) describes rebuilding the patch from user-supplied inputs. That route requires additional source material and tools.

For a bug report, include the patch version, source data-track hash, input layout, emulator or device version, affected scene, and steps to reproduce the problem. Do not upload a disc image, BIOS, or extracted game files.
