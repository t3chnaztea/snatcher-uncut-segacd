# Compatibility and known issues

## Tested scope

| Check | Result |
|---|---|
| Approved restoration records | All 37 passed emulator checks |
| Act 1 | Cold automated route reached Act 2 |
| Acts 2 and 3 | Continued accepted route reached the ending and original credits |
| Normal save and fresh load | Passed through the game's menus after normal shutdown |
| Reference audio data | All 20 tracks and pregaps remained byte-identical |
| Captured audio output | Callback accounting and selected source comparisons passed |
| Developer reproduction | A fresh private source clone reproduced eight accepted artifacts |
| U.S. Genesis Model 2 + Mega EverDrive Pro | Owner reports successful operation; test coverage unspecified |
| Batocera cabinet | Not tested |
| FPGA hardware | Not tested |
| Existing unpatched saves used with this patch | Not established |

The emulator evidence uses the pinned Genesis Plus GX test core. It does not establish compatibility with every Genesis Plus GX version or frontend. The accepted route spans several sessions. The Act 2 continuation began from an accepted emulator checkpoint. Later save/load checks used normal in-game saving and fresh boot. Targeted scene checks do not establish that every restored view was reached naturally during that route.

Installer layout and operating-system support must come from the release install instructions. Developer-build reproduction is a separate check. It does not prove that the player installer works on another operating system.

## Owner console report

The owner reports this build working on a U.S. Genesis Model 2 with a Mega EverDrive Pro. Full console playthrough and console save/load coverage have not been documented. Cartridge firmware, BIOS and the tested scene list were not supplied. This report does not replace the full emulator evidence or establish compatibility with every device.

## Text and speech

The opening caption and HQ database display the catastrophe year as 1991. The original English speech retains 1996. The two text contexts describe the same date discrepancy. Voices and music remain unchanged.

Some retained Sega CD additions still use their localized chronology. The patch changes selected approved records. It does not rewrite all port-specific material to one timeline.

## Source images

The reference data track matches the retail USA data-track hashes. Its 20 audio tracks differ from the referenced Redump audio set. The cause of that difference is unknown. The patch preserves audio from the supplied dump. A matching data-track hash alone does not prove that an alternative audio layout has been tested.

Do not apply the raw data-track patch directly to a whole BIN, ISO/2048 file, or CHD. Use the install route documented for that input type. Keep the original disc files and a separate backup of saves.

## Verification limits

Automated source checks, graphics checks, and gameplay controllers supplied the current evidence. They are not an independent human language or full-game listening review. AI-agent review is not human expert review.

## Reporting a problem

Give the release version, source data-track hash, input layout, emulator/core or hardware details, scene, and reproduction steps. State whether the problem also occurs with the original disc. Attach a small relevant log or screenshot where useful. Do not attach game images, BIOS files, or extracted assets.
