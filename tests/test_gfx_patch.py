"""M4 approval scope, M3 composition and exhaustive retail-asset verification."""
import json
from pathlib import Path
import sys
import tempfile
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import scd_art as art
import scd_text as text


@pytest.fixture(scope='module')
def applied():
    with tempfile.TemporaryDirectory(prefix='test-m4-',dir=ROOT/'build') as folder:
        folder=Path(folder);output=folder/'output'
        report=art.apply(output=output,evidence=folder/'evidence')
        yield folder,output,report


def test_every_approved_art_row_and_all_asset_bytes(applied):
    folder,output,report=applied
    assert set(report['approved_rows'])==art.EXPECTED
    assert report['source_files']==98
    verified=art.verify(output=output,evidence=folder/'verification')
    assert verified['status']=='pass'
    assert len(verified['files'])==98
    assert all(r['size']<=text.FILE_LIMIT for r in verified['files'] if r['file'].startswith('SP'))
    # Composition must preserve every byte of every approved M3 replacement.
    for row in text.patch_records(ROOT/'patches/text'):
        for edit in row['edits']:
            if edit['kind']=='pool':
                entry=text.pool((output/edit['file']).read_bytes())[0][edit['string_id']]
                actual=bytes.fromhex(entry['raw'])
            else:
                entry=text.speakers(output)[edit['string_id']]
                actual=bytes.fromhex(entry['raw'])[1:]
            assert actual==text.encode(edit['new_text'])


def test_unapproved_asset_byte_is_rejected(applied):
    folder,output,_=applied
    path=output/'DATA_D2.BIN';before=path.read_bytes();changed=bytearray(before)
    changed[-1]^=1;path.write_bytes(changed)
    try:
        with pytest.raises(ValueError,match='unapproved byte change'):
            art.verify(output=output,evidence=folder/'rejected-output')
    finally:
        path.write_bytes(before)


def test_source_hash_change_is_rejected_before_composition(applied):
    folder,_,_=applied;source=folder/'changed-source';source.mkdir()
    metadata=['manifest.json','_track01.raw','ABS.TXT','BIB.TXT','CPY.TXT']
    for name in art.source_inventory(art.SOURCE)+metadata:
        (source/name).symlink_to(art.SOURCE/name)
    # Replace only this symlink; never mutate the staged input.
    target=source/'DATA_F0.BIN';target.unlink()
    changed=bytearray((art.SOURCE/'DATA_F0.BIN').read_bytes());changed[-1]^=1
    target.write_bytes(changed)
    output=folder/'rejected-source-output'
    with pytest.raises((ValueError,AssertionError)):
        art.apply(source=source,output=output,evidence=folder/'rejected-source')
    assert not output.exists()


def test_dog_growth_stays_inside_existing_iso_allocation():
    import subprocess
    import scd_disc
    manifest=json.loads((art.SOURCE/'manifest.json').read_text())
    row=next(r for r in manifest['files'] if r['name']=='DATA_G0.BIN')
    capacity=(row['size']+2047)//2048*2048
    assert capacity-row['size']==1804
    original=(art.SOURCE/row['name']).read_bytes()
    with tempfile.TemporaryDirectory(prefix='test-m4-iso-',dir=ROOT/'build') as folder:
        target=Path(folder)/'variant.bin'
        subprocess.run(['cp','-c',manifest['source'],str(target)],check=True)
        before_size=target.stat().st_size
        with pytest.raises(ValueError,match='sector count'):
            scd_disc.patch_file_extent(target,manifest,row['name'],original+b'X')
        with pytest.raises(ValueError,match='sector count'):
            scd_disc.patch_file_extent(target,manifest,row['name'],original+bytes(capacity-row['size']+1),True)
        payload=original+b'X'*16
        report=scd_disc.patch_file_extent(target,manifest,row['name'],payload,True)
        assert report['lba']==row['lba'] and report['sector_capacity']==capacity
        assert report['size']==row['size']+16 and report['directory_records']==1
        assert target.stat().st_size==before_size
        with target.open('rb') as stream:
            def sector(lba):
                stream.seek(lba*2352);raw=stream.read(2352)
                assert scd_disc.mode1_sector(raw[16:2064],lba)==raw
                return raw[16:2064]
            assert sector(row['lba']+row['size']//2048)[row['size']%2048:row['size']%2048+16]==b'X'*16
            pvd=sector(16);root=pvd[156:190];lba=int.from_bytes(root[2:6],'little');size=int.from_bytes(root[10:14],'little')
            directory=b''.join(sector(lba+i) for i in range((size+2047)//2048));pos=0;found=[]
            while pos<size:
                length=directory[pos]
                if not length:pos=(pos//2048+1)*2048;continue
                rec=directory[pos:pos+length]
                if rec[33:33+rec[32]].decode('ascii').split(';')[0]=='DATA_G0.BIN':found.append(rec)
                pos+=length
            assert len(found)==1
            assert int.from_bytes(found[0][10:14],'little')==int.from_bytes(found[0][14:18],'big')==len(payload)
        with pytest.raises(ValueError,match='staged source'):
            scd_disc.patch_file_extent(Path(manifest['source']),manifest,row['name'],payload,True)


def test_dog_additional_sector_requires_empty_nonoverlapping_gap():
    import copy
    import subprocess
    import scd_disc
    manifest=json.loads((art.SOURCE/'manifest.json').read_text())
    row=next(r for r in manifest['files'] if r['name']=='DATA_G0.BIN')
    original=(art.SOURCE/row['name']).read_bytes();rounded=(row['size']+2047)//2048*2048
    payload=original+bytes(rounded-len(original))+b'X'
    with tempfile.TemporaryDirectory(prefix='test-m4-gap-',dir=ROOT/'build') as folder:
        folder=Path(folder);target=folder/'gap.bin'
        subprocess.run(['cp','-c',manifest['source'],str(target)],check=True)
        overlaps=copy.deepcopy(manifest)
        next(r for r in overlaps['files'] if r['name']=='DATA_H00.BIN')['lba']=row['lba']+rounded//2048
        with pytest.raises(ValueError,match='extents overlap'):
            scd_disc.patch_file_extent(target,overlaps,row['name'],payload,allow_zero_gap=True)
        report=scd_disc.patch_file_extent(target,manifest,row['name'],payload,allow_zero_gap=True)
        assert report['uses_zero_gap'] and report['sector_capacity']==rounded+2048
        assert report['size']==rounded+1
        blocked=folder/'blocked.bin';subprocess.run(['cp','-c',manifest['source'],str(blocked)],check=True)
        lba=row['lba']+rounded//2048
        with blocked.open('r+b') as stream:
            stream.seek(lba*2352);raw=stream.read(2352);body=bytearray(raw[16:2064]);body[0]=1
            stream.seek(lba*2352);stream.write(scd_disc.mode1_sector(body,lba))
        with pytest.raises(ValueError,match='not zero-filled'):
            scd_disc.patch_file_extent(blocked,manifest,row['name'],payload,allow_zero_gap=True)
