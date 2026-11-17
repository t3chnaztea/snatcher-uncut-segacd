#!/usr/bin/env python3
"""Assemble an offline browser installer from a pinned, read-only engine checkout."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from patch_profiles import load_registry, DEFAULT_PROFILE_ID
from patch_choices import load_registry as load_choices_registry

ENGINE_COMMIT = "4f17297cd1dc0835a0b0747497fa15f5f63f1623"
PATCH_SHA256 = "1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4"


def assemble(engine: Path, patch: Path | None, output: Path, registry: Path | None = None, media: Path | None = None) -> dict:
    commit = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
    if commit != ENGINE_COMMIT:
        raise ValueError("Patch engine checkout does not match the pinned commit")
    if subprocess.check_output(["git", "-C", str(engine), "status", "--porcelain"], text=True).strip():
        raise ValueError("Patch engine checkout has local changes")
    if registry is None:
        raise ValueError("The full Snatcher Patcher requires a verified profile registry")
    registry = Path(registry)
    raw = json.loads(registry.read_text())
    advanced = isinstance(raw, dict) and raw.get('format') == 2
    profiles = load_choices_registry(registry) if advanced else load_registry(registry)
    payloads = {}
    patch_hashes = {}
    entries = [v for family in profiles['families'] for v in family['variants']] if advanced else [row for row in profiles['profiles'] if not row['no_patch']]
    for row in entries:
        relative = Path(row['patch']['file'])
        candidate = registry.parent / relative
        expected_parent = registry.parent / ('patches/components' if advanced else 'patches/profiles')
        if candidate.is_symlink() or not candidate.is_file() or candidate.resolve().parent != expected_parent.resolve():
            raise ValueError("Profile patch path is missing or unsafe")
        data = candidate.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != row['patch']['sha256']:
            raise ValueError("Profile patch checksum mismatch: " + row['id'])
        payloads[row['id']] = base64.b64encode(data).decode('ascii')
        patch_hashes[row['id']] = actual
    if patch is not None and hashlib.sha256(Path(patch).read_bytes()).hexdigest() != PATCH_SHA256:
        raise ValueError("Default release patch checksum mismatch")
    if output.exists():
        raise ValueError("Output path already exists; choose a new candidate folder")
    root = Path(__file__).resolve().parent.parent
    source = root / "release" / "installer"
    if not source.is_dir():
        source = root / "browser"
    templates = ('index.html', 'style.css', 'choices.js', 'app.js')
    if any((source / name).is_symlink() or not (source / name).is_file() for name in templates):
        raise ValueError("Installer templates are missing or unsafe")
    previews = ('costume-gallery.png', 'moscow-comparison.png', 'newspaper-comparison.png',
                'neokobe-comparison.png', 'alice-dog-comparison-NSFW.png', 'lisa-android-comparison-NSFW.png')
    if advanced:
        if media is None:
            media = next((p for p in (root/'media/assets', root/'build/m8/media/assets', source/'previews') if p.is_dir()), None)
        if media is None or any((Path(media)/name).is_symlink() or not (Path(media)/name).is_file() for name in previews):
            raise ValueError('Reviewed comparison previews are missing; supply --media with their assets directory')
    output.mkdir(parents=True)
    for name in templates:
        shutil.copyfile(source / name, output / name)
    if advanced:
        (output/'previews').mkdir()
        for name in previews:
            shutil.copyfile(Path(media)/name, output/'previews'/name)
    vendor = output / "vendor"
    (vendor / "modules").mkdir(parents=True)
    shutil.copy2(engine / "LICENSE", vendor / "LICENSE")
    shutil.copy2(engine / "rom-patcher-js" / "RomPatcher.js", vendor / "RomPatcher.js")
    for module in (engine / "rom-patcher-js" / "modules").glob("*.js"):
        if module.is_file():
            shutil.copy2(module, vendor / "modules" / module.name)
    (output / "patch-data.js").write_text(
        "const SNATCHER_PROFILE_REGISTRY = " + json.dumps(profiles, separators=(',', ':')) + ";\n" +
        ("const SNATCHER_COMPONENTS_BASE64 = " if advanced else "const SNATCHER_PATCHES_BASE64 = ") + json.dumps(payloads, separators=(',', ':')) + ";\n")
    receipt = {
        "engine_repository": "https://github.com/marcrobledo/RomPatcher.js",
        "engine_commit": commit,
        "registry_format": profiles["format"],
        "profile_registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
        "profiles": profiles,
        "component_patch_sha256" if advanced else "profile_patch_sha256": patch_hashes,
        "files": {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(output.rglob("*")) if p.is_file()},
    }
    if not advanced:
        receipt["patch_sha256"] = patch_hashes[DEFAULT_PROFILE_ID]
    (output / "browser-build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--patch", type=Path, help="Optional immutable default patch cross-check")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--media", type=Path, help="Reviewed comparison assets directory")
    args = parser.parse_args()
    receipt = assemble(args.engine, args.patch, args.output, registry=args.registry, media=args.media)
    print(json.dumps({"engine_commit": receipt["engine_commit"], "files": len(receipt["files"])}))


if __name__ == "__main__":
    main()
