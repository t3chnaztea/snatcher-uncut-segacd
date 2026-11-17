#!/usr/bin/env python3
"""Prepare exact local release ZIPs for owner review. Never publish anything."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

VERSION = 'v0.9.0-rc1'
PATCH_SHA256 = '1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4'
PLAYER_DOCUMENTS = ('README.md', 'INSTALL.md', 'CHANGELOG.md', 'KNOWN-ISSUES.md',
                    'CREDITS.md', 'AI-DISCLOSURE.md', 'VERIFICATION.md', 'LICENSE', 'LICENSE-SCOPE.md')
MEDIA_ASSETS = (
    'outer-heaven-hero.png', 'costume-gallery.png', 'moscow-comparison.png',
    'newspaper-comparison.png', 'neokobe-comparison.png',
    'outer-heaven-still-loop.gif', 'outer-heaven-still-loop.mp4',
    'outer-heaven-still-loop.webm', 'outer-heaven-still-loop-poster.png',
    'chronology-still-loop.gif', 'chronology-still-loop.mp4',
    'chronology-still-loop.webm', 'chronology-still-loop-poster.png',
    'release-reel.mp4', 'release-reel.webm', 'release-reel-poster.png',
    'dog-native-comparison-GORE.gif',
)


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy(source: Path, target: Path):
    if source.is_symlink() or not source.is_file():
        raise ValueError(f'Expected a regular input file: {source.name}')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def zip_tree(folder: Path, target: Path):
    # Fixed ordering, permissions and timestamps make identical inputs reproducible.
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file in sorted(folder.rglob('*')):
            if file.is_file():
                item = zipfile.ZipInfo(file.relative_to(folder).as_posix(), (2026, 11, 14, 0, 0, 0))
                item.compress_type = zipfile.ZIP_DEFLATED
                item.external_attr = 0o100644 << 16
                archive.writestr(item, file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def package(root: Path, browser: Path, media: Path, patch: Path, output: Path):
    if output.exists():
        raise ValueError('Choose a new output folder')
    if sha(patch) != PATCH_SHA256:
        raise ValueError('Patch checksum does not match the accepted release')
    browser_receipt = json.loads((browser / 'browser-build.json').read_text())
    if browser_receipt['patch_sha256'] != PATCH_SHA256:
        raise ValueError('Browser patch receipt differs')
    for name, expected in browser_receipt['files'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or sha(browser / p) != expected:
            raise ValueError('Browser receipt or file differs')
    provenance = json.loads((media / 'provenance.json').read_text())
    accepted_media = {Path(item['file']).name: item for item in provenance['assets']}
    if set(accepted_media) != set(MEDIA_ASSETS):
        raise ValueError('Media inventory differs from the explicit review set')
    for name in MEDIA_ASSETS:
        if sha(media / 'assets' / name) != accepted_media[name]['sha256']:
            raise ValueError('Media hash differs from its provenance')
    player, kit = output / 'player', output / 'media'
    player.mkdir(parents=True)
    for name in PLAYER_DOCUMENTS:
        copy(root / 'release' / name, player / name)
    copy(root / 'docs/player-install.md', player / 'OFFLINE-INSTALL.md')
    copy(root / 'tools/player_install.py', player / 'tools/player_install.py')
    copy(patch, player / 'snatcher-uncut-track01.xdelta')
    for name in browser_receipt['files']:
        copy(browser / name, player / 'browser' / name)
    copy(browser / 'browser-build.json', player / 'browser/browser-build.json')
    for name in MEDIA_ASSETS:
        copy(media / 'assets' / name, kit / 'assets' / name)
    # These two relative README links must also work inside the player ZIP.
    for name in ('outer-heaven-hero.png', 'release-reel.mp4'):
        copy(media / 'assets' / name, player / 'media/assets' / name)
    for name in ('index.html', 'provenance.json'):
        copy(media / name, kit / name)
    for folder in (player, kit):
        files = sorted(p for p in folder.rglob('*') if p.is_file())
        (folder / 'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(folder).as_posix()}\n' for p in files))
    player_zip = output / f'snatcher-uncut-player-{VERSION}.zip'
    media_zip = output / f'snatcher-uncut-media-{VERSION}.zip'
    zip_tree(player, player_zip)
    zip_tree(kit, media_zip)
    artifacts = {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in (player_zip, media_zip)}
    (output / 'SHA256SUMS').write_text(''.join(f'{data["sha256"]}  {name}\n' for name, data in artifacts.items()))
    manifest = {'status': 'local candidate; owner approval required before publication', 'version': VERSION,
                'patch_sha256': PATCH_SHA256, 'artifacts': artifacts,
                'player_files': sum(p.is_file() for p in player.rglob('*')), 'media_assets': len(MEDIA_ASSETS),
                'gore_asset': 'media/assets/dog-native-comparison-GORE.gif',
                'reddit_writes_authorized': False}
    (output / 'candidate.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'browser', 'media', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--patch',type=Path)
    choice.add_argument('--registry',type=Path)
    a=parser.parse_args()
    if a.registry:
        metadata=json.loads(a.registry.read_text())
        if not isinstance(metadata,dict):raise ValueError('Invalid profile registry object')
        kind=metadata.get('format')
        method=package_choices if kind==2 else package_profiles
        result=method(a.root,a.browser,a.registry,a.media,a.output)
    else:
        result=package(a.root,a.browser,a.media,a.patch,a.output)
    print(json.dumps(result,indent=2))


# The configurator package is independent of the immutable single-profile ZIP.
PROFILE_MEDIA = (
    'repo-banner.png', 'outer-heaven-hero.png', 'costume-gallery.png',
    'neokobe-comparison.png', 'moscow-comparison.png', 'newspaper-comparison.png',
    'alice-dog-comparison-NSFW.png', 'lisa-android-comparison-NSFW.png',
    'shop-name-reference.png', 'patcher-desktop.png',
)


def package_profiles(root: Path, browser: Path, registry: Path, media: Path, output: Path):
    """Package only validated profile payloads, runtime code and reviewed media."""
    from patch_profiles import load_registry
    root,browser,registry,media,output=map(Path,(root,browser,registry,media,output))
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new profile package folder')
    if not output.parent.is_dir():
        raise ValueError('Package parent must exist')
    profiles=load_registry(registry)
    receipt=json.loads((browser/'browser-build.json').read_text())
    if receipt.get('profile_registry_sha256')!=sha(registry) or receipt.get('profiles')!=profiles:
        raise ValueError('Browser receipt does not bind this profile registry')
    expected_payloads={entry['id']:entry['patch']['sha256'] for entry in profiles['profiles'] if not entry['no_patch']}
    if receipt.get('profile_patch_sha256')!=expected_payloads:
        raise ValueError('Browser payload inventory differs from registry')
    files=[]
    for relative,expected in receipt['files'].items():
        name=Path(relative)
        if name.is_absolute() or '..' in name.parts or sha(browser/name)!=expected:
            raise ValueError('Browser packaged file differs from its receipt')
        files.append((browser/name,'browser/'+relative))
    files.append((browser/'browser-build.json','browser/browser-build.json'))
    for entry in profiles['profiles']:
        if entry['no_patch']:continue
        patch=registry.parent/entry['patch']['file']
        if sha(patch)!=entry['patch']['sha256']:
            raise ValueError('Release patch differs from registry')
        files.append((patch,entry['patch']['file']))
    readme_source = root/'release/REPO-README.md'
    if not readme_source.is_file():readme_source = root/'README.md'
    offline_source = root/'docs/player-install.md'
    if not offline_source.is_file():offline_source = root/'OFFLINE-INSTALL.md'
    files.extend([(readme_source,'README.md'),(offline_source,'OFFLINE-INSTALL.md')])
    for name in PLAYER_DOCUMENTS:
        if name=='README.md':continue
        source=root/'release'/name
        if not source.is_file():source=root/name
        files.append((source,name))
    files.extend([(registry,'profiles.json'),(root/'tools/player_install.py','tools/player_install.py'),
                  (root/'tools/patch_profiles.py','tools/patch_profiles.py')])
    for name in PROFILE_MEDIA:files.append((media/'assets'/name,'media/assets/'+name))
    if len({target for _,target in files})!=len(files):
        raise ValueError('Duplicate package destination')
    for source,_ in files:
        if source.is_symlink() or not source.is_file():raise ValueError('Missing or unsafe package input')
    # Validate all inputs before creating an output tree.
    output.mkdir();player=output/'player';player.mkdir()
    for source,target in files:copy(source,player/target)
    readme=player/'README.md'
    readme.write_text(readme.read_text().replace('[Rebuild from source](docs/setup.md)',
        '[Rebuild from source](https://github.com/t3chnaztea/snatcher-uncut-segacd/blob/main/docs/setup.md)'))
    sums=player/'SHA256SUMS';sums.write_text(''.join(sha(p)+'  '+p.relative_to(player).as_posix()+'\n'
        for p in sorted(player.rglob('*')) if p.is_file()))
    archive=output/('snatcher-uncut-player-'+profiles['version']+'.zip')
    zip_tree(player,archive)
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:raise ValueError('Package ZIP CRC failed')
    sidecar=output/'SHA256SUMS';sidecar.write_text(sha(archive)+'  '+archive.name+'\n')
    report=dict(version=profiles['version'],profiles=16,active_patches=15,files=len(files)+1,
        archive=dict(file=archive.name,bytes=archive.stat().st_size,sha256=sha(archive)),
        checksums=dict(file=sidecar.name,sha256=sha(sidecar)),browser_receipt_sha256=sha(browser/'browser-build.json'),
        profile_registry_sha256=sha(registry))
    (output/'package.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def package_choices(root: Path, browser: Path, registry: Path, media: Path, output: Path):
    """Package source-relative components and the exact reviewed advanced runtime."""
    from patch_choices import load_registry, CHOICE_IDS
    root,browser,registry,media,output=map(Path,(root,browser,registry,media,output))
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('Choose a new advanced package folder under an existing parent')
    specification=load_registry(registry)
    receipt=json.loads((browser/'browser-build.json').read_text())
    if receipt.get('registry_format')!=2 or receipt.get('profile_registry_sha256')!=sha(registry) or receipt.get('profiles')!=specification:
        raise ValueError('Browser receipt does not bind the advanced registry')
    if receipt.get('engine_commit')!='4f17297cd1dc0835a0b0747497fa15f5f63f1623':
        raise ValueError('Unexpected patch engine revision')
    variants=[v for family in specification['families'] for v in family['variants']]
    expected={v['id']:v['patch']['sha256'] for v in variants}
    if receipt.get('component_patch_sha256')!=expected:
        raise ValueError('Browser component inventory differs from the registry')
    required={'index.html','style.css','app.js','choices.js','patch-data.js',
              'vendor/LICENSE','vendor/RomPatcher.js','vendor/modules/BinFile.js',
              'vendor/modules/HashCalculator.js','vendor/modules/RomPatcher.format.vcdiff.js'}
    if not isinstance(receipt.get('files'),dict) or not required.issubset(receipt['files']):
        raise ValueError('Advanced browser runtime inventory is incomplete')
    files=[]
    for relative,digest in receipt['files'].items():
        name=Path(relative)
        if name.is_absolute() or '..' in name.parts or (browser/name).is_symlink() or not (browser/name).is_file() or sha(browser/name)!=digest:
            raise ValueError('Browser file differs from its receipt')
        files.append((browser/name,'browser/'+relative))
    files.append((browser/'browser-build.json','browser/browser-build.json'))
    for variant in variants:
        source=registry.parent/variant['patch']['file']
        if source.is_symlink() or not source.is_file() or sha(source)!=variant['patch']['sha256']:
            raise ValueError('Release component differs from its registry')
        files.append((source,variant['patch']['file']))
    for name in PLAYER_DOCUMENTS:
        source=(root/'release/REPO-README.md' if name=='README.md' else root/'release'/name)
        if not source.is_file():source=root/name
        files.append((source,name))
    source=root/'docs/player-install.md'
    if not source.is_file():source=root/'OFFLINE-INSTALL.md'
    files.append((source,'OFFLINE-INSTALL.md'))
    files.append((registry,'profiles.json'))
    for name in ('player_install.py','patch_profiles.py','patch_choices.py','choice_install.py'):
        files.append((root/'tools'/name,'tools/'+name))
    for name in PROFILE_MEDIA:files.append((media/'assets'/name,'media/assets/'+name))
    if len({destination for _,destination in files})!=len(files):
        raise ValueError('Duplicate advanced package destination')
    for source,_ in files:
        if source.is_symlink() or not source.is_file():raise ValueError('Missing or unsafe advanced package input')
    output.mkdir();player=output/'player';player.mkdir()
    for source,destination in files:copy(source,player/destination)
    readme=player/'README.md'
    readme.write_text(readme.read_text().replace('[Rebuild from source](docs/setup.md)',
        '[Rebuild from source](https://github.com/t3chnaztea/snatcher-uncut-segacd/blob/main/docs/setup.md)'))
    (player/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.relative_to(player).as_posix()+'\n'
        for p in sorted(player.rglob('*')) if p.is_file()))
    archive=output/('snatcher-uncut-player-'+specification['version']+'.zip')
    zip_tree(player,archive)
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None:raise ValueError('Advanced package ZIP CRC failed')
        for line in check.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1)
            if hashlib.sha256(check.read(name)).hexdigest()!=digest:raise ValueError('Advanced ZIP internal checksum failed')
    sidecar=output/'SHA256SUMS';sidecar.write_text(sha(archive)+'  '+archive.name+'\n')
    report=dict(version=specification['version'],registry_format=2,choices=len(CHOICE_IDS),
        active_selections=len(CHOICE_IDS)-1,component_patches=len(variants),files=len(files)+1,
        archive=dict(file=archive.name,bytes=archive.stat().st_size,sha256=sha(archive)),
        checksums=dict(file=sidecar.name,sha256=sha(sidecar)),
        browser_receipt_sha256=sha(browser/'browser-build.json'),profile_registry_sha256=sha(registry))
    (output/'package.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    main()
