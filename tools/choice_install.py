"""Verified format-2 component composition over the original Track 1."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from patch_choices import load_registry, get_selection, legacy_selection, family_values, SETTING_KEYS


def parse_settings(text: str):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 65536:
        raise ValueError('Settings documents must be smaller than 64 KB.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate settings field')
            result[key] = value
        return result
    doc = json.loads(text, object_pairs_hook=pairs)
    if not isinstance(doc, dict): raise ValueError('Invalid settings document')
    if doc.get('kind') == 'snatcher-patcher-settings':
        if set(doc) != {'format','kind','choice_id','settings'} or type(doc['format']) is not int or doc['format'] != 1:
            raise ValueError('Unsupported settings document')
        selection = get_selection(doc['settings'])
        if doc['choice_id'] != selection.id: raise ValueError('Settings ID mismatch')
    elif doc.get('installer') == 'Snatcher Patcher' and (doc.get('format') in (2,3) or doc.get('format_version') in (2,3)):
        selection = get_selection(doc['settings']) if set(doc.get('settings',{})) == set(SETTING_KEYS) else legacy_selection(doc['settings'])
        ident = doc.get('profile_id')
        if not isinstance(ident,str): raise ValueError('Receipt is missing its profile ID')
        expected = legacy_selection(ident) if isinstance(ident,str) and ident.startswith('d') else get_selection(ident)
        if expected.id != selection.id: raise ValueError('Receipt settings mismatch')
    else: raise ValueError('Unsupported settings document')
    return selection


def install(source, patch, output, xdelta='xdelta3', *, registry, profile_id=None):
    # Delayed import keeps the v1 installer independent of this format dispatcher.
    import player_install as old
    catalogue = load_registry(registry)
    selected = legacy_selection(profile_id) if isinstance(profile_id,str) and profile_id.startswith('d') else get_selection(profile_id)
    if selected.no_patch:
        return dict(format_version=3,installer='Snatcher Patcher',status='no-patch-needed',
                    profile_id=selected.id,settings=selected.settings,no_patch=True,input_verified=False,
                    files=[],tracks=[],audio_tracks_unchanged=0)
    if patch is not None: raise old.InstallError('Component releases do not accept a single --patch override.')
    if isinstance(registry,dict): raise old.InstallError('Component installation requires the registry file and its reviewed patches.')
    registry_path=Path(registry); registry_before=registry_path.read_bytes()
    source,output=Path(source),Path(output)
    if output.exists() or output.is_symlink(): raise old.InstallError('Output directory must not exist.')
    if not output.parent.is_dir(): raise old.InstallError('Output parent directory must already exist.')
    layout=old.inspect_input(source)
    executable=shutil.which(xdelta)
    if not executable: raise old.InstallError('xdelta3 was not found.')
    values=family_values(selected); components=[]
    for family in catalogue['families']:
        value=values[family['id']]
        if not value: continue
        variant=next(v for v in family['variants'] if v['value']==value)
        file=registry_path.parent / variant['patch']['file']; old.regular_file(file)
        if file.resolve().parent != (registry_path.parent/'patches/components').resolve() or old.digest(file)!=variant['patch']['sha256']:
            raise old.InstallError('Component patch checksum or path mismatch.')
        components.append((family,variant,file))
    before={f.name:old.digest(f) for f in layout.files}
    tracks_before=[old.digest(t.file,start=t.start*old.SECTOR,length=(t.end-t.start)*old.SECTOR) for t in layout.tracks]
    size=catalogue['source']['track1_bytes']; target_hash=catalogue['targets'][selected.id]
    needed=2*sum(f.stat().st_size for f in layout.files)+3*size+old.CHUNK
    if shutil.disk_usage(output.parent).free < needed: raise old.InstallError('Not enough free disk space.')
    with tempfile.TemporaryDirectory(prefix='.snatcher-choices-',dir=output.parent) as temporary:
        stage=Path(temporary); original=stage/'original'; target=stage/'target'
        with layout.files[0].open('rb') as src,original.open('xb') as dst: old.copy_bytes(src,dst,size)
        if old.digest(original)!=catalogue['source']['track1_sha256']: raise old.InstallError('Source changed after validation.')
        shutil.copyfile(original,target)
        for family,variant,file in components:
            decoded=stage/variant['id']
            result=subprocess.run([executable,'-d','-s',str(original),str(file.resolve()),str(decoded)],capture_output=True,text=True)
            if result.returncode: raise old.InstallError('Component decode failed: '+variant['id'])
            if old.digest(file)!=variant['patch']['sha256'] or decoded.stat().st_size!=variant['decoded_bytes'] or old.digest(decoded)!=variant['decoded_sha256']:
                raise old.InstallError('Decoded component verification failed.')
            with decoded.open('rb') as src,target.open('r+b') as dst:
                for segment in family['ranges']:
                    dst.seek(segment['lba']*old.SECTOR);old.copy_bytes(src,dst,segment['count']*old.SECTOR)
        if old.digest(target)!=target_hash or old.digest(original)!=catalogue['source']['track1_sha256']:
            raise old.InstallError('Final Track 1 verification failed.')
        package=stage/'package';package.mkdir()
        for file in layout.files:
            with file.open('rb') as src,(package/file.name).open('xb') as dst:
                if file==layout.files[0]:
                    with target.open('rb') as replacement: old.copy_bytes(replacement,dst)
                    src.seek(size)
                old.copy_bytes(src,dst)
        if layout.cue:
            if layout.cue.read_bytes()!=layout.cue_bytes: raise old.InstallError('CUE changed during installation.')
            (package/layout.cue.name).write_bytes(layout.cue_bytes)
        tracks=[]
        for t,previous in zip(layout.tracks,tracks_before):
            actual=old.digest(package/t.file.name,start=t.start*old.SECTOR,length=(t.end-t.start)*old.SECTOR)
            if actual!=(target_hash if t.number==1 else previous): raise old.InstallError('Output track verification failed.')
            tracks.append(dict(track=t.number,file=t.file.name,indices={str(k):v for k,v in t.indices.items()},pregap_frames=t.pregap,bytes=(t.end-t.start)*old.SECTOR,source_sha256=previous,output_sha256=actual,unchanged=actual==previous))
        if registry_path.read_bytes()!=registry_before or any(old.digest(f)!=before[f.name] for f in layout.files) or any(old.digest(f)!=v['patch']['sha256'] for _,v,f in components):
            raise old.InstallError('An input changed during installation.')
        receipt=dict(format_version=3,installer='Snatcher Patcher',version=catalogue['version'],status='verified',profile_id=selected.id,settings=selected.settings,no_patch=False,layout=layout.kind,source_track1_sha1=catalogue['source']['track1_sha1'],target_track1_sha256=target_hash,cue_unchanged=layout.cue is not None,audio_tracks_unchanged=len(tracks)-1,tracks=tracks,components=[dict(id=v['id'],family=f['id'],value=v['value'],patch_sha256=v['patch']['sha256'],decoded_sha256=v['decoded_sha256']) for f,v,_ in components],files=[dict(name=f.name,source_sha256=before[f.name],output_sha256=old.digest(package/f.name)) for f in layout.files])
        output.mkdir()
        for artifact in package.iterdir():
            with artifact.open('rb') as src,(output/artifact.name).open('xb') as dst: old.copy_bytes(src,dst)
        if any(old.digest(output/f['name'])!=f['output_sha256'] for f in receipt['files']) or (layout.cue and (output/layout.cue.name).read_bytes()!=layout.cue_bytes):
            raise old.InstallError('Final output verification failed; inputs remain unchanged.')
        (output/'install-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
