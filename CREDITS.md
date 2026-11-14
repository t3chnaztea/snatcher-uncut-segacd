# Credits

Snatcher, its story, artwork, voices and music belong to Konami and their respective rights holders. The original Japanese and Sega CD development teams made the game. This patch preserves the Sega CD English voice recordings, music and story additions. The source artwork used for selected restorations comes from Snatcher CD-ROMantic for PC Engine CD.

TECH NASTY selected the patch scope and directed the project. AI coding agents assisted with research, format analysis, implementation, automated test controllers, evidence review and documentation. The [process disclosure](AI-DISCLOSURE.md) states the limits of that review.

## Technical references

[Luiz Perrella (pepa), pepasjc/snatcher-translated](https://github.com/pepasjc/snatcher-translated) supplied PC Engine format research and codec tools. The reproducible developer build uses revision `f181542e188a4c5bcd18080bb282518c53761acd`. Its [code license is MIT](https://github.com/pepasjc/snatcher-translated/blob/f181542e188a4c5bcd18080bb282518c53761acd/LICENSE). Its [translation and documentation license is CC BY-NC-SA 4.0](https://github.com/pepasjc/snatcher-translated/blob/f181542e188a4c5bcd18080bb282518c53761acd/LICENSE-DATA). The upstream notices reserve the game material to Konami. Those licenses have different scopes.

[athrxx's ScummVM Snatcher engine work](https://github.com/scummvm/scummvm/pull/8029) provided a reference for Sega CD formats and interpreter behavior. ScummVM source was consulted to understand formats. Its GPL code is not part of this patch's tools.

[girianshido's Sega CD Snatcher Language Patcher](https://github.com/girianshido/Sega-CD-Snatcher-Language-Patcher) provided earlier notes on the Sega CD script layout. Its code is not bundled.

[Genesis Plus GX](https://github.com/ekeeke/Genesis-Plus-GX) provided the emulator core used by the automated test harness. The core has its own license and component notices. No emulator core or BIOS is bundled with the player patch.

[Redump's USA disc record](http://redump.org/disc/20559/) provided the retail data-track identity used for comparison.

[Marc Robledo's Rom Patcher JS](https://github.com/marcrobledo/RomPatcher.js) supplies the browser patch engine at revision `4f17297cd1dc0835a0b0747497fa15f5f63f1623`. The browser bundle includes its MIT license and preserves the source notices. The project's installer interface is separate from that engine.

[xdelta](https://github.com/jmacd/xdelta) provided the binary patch tool. [MAME's chdman](https://github.com/mamedev/mame) provided local CHD packaging and verification. [Pillow](https://python-pillow.org/) provided raster conversion and comparison tools. These projects keep their own licenses. The patch does not grant rights to their software.

## Rights and distribution

This is an unofficial fan patch. Konami does not endorse it. The release contains no complete game or BIOS.

Original project code, third-party code, translation data, documentation and game assets must retain their separate license scopes. Consult the license notices supplied with the final package. A license for project tools does not license Snatcher or its extracted content. Patch-only distribution is not a claim of legal clearance.
