"""Independent packaging checks, with corruption cases for silent changes."""
from pathlib import Path
import hashlib
import copy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_build as v


def test_sector_edc_and_both_ecc_planes():
    source = ROOT/'private/extracted/segacd-usa/_track01.raw'
    if not source.exists():
        pytest.skip('Private source track is not staged')
    with source.open('rb') as stream:
        for lba in [0,16,53425,56013]:
            stream.seek(lba*2352)
            sector = stream.read(2352)
            v.verify_sector(sector,lba)
            for offset,label in [(12,'address'),(16,'EDC'),(2068,'reserved'),(2076,'ECC P'),(2248,'ECC Q')]:
                corrupted = bytearray(sector)
                corrupted[offset] ^= 1
                with pytest.raises(ValueError,match=label):
                    v.verify_sector(corrupted,lba)


def _record(lba,size,name,flags=0):
    record = bytearray(34+len(name)+(not len(name)%2))
    record[0] = len(record)
    record[2:10] = lba.to_bytes(4,'little')+lba.to_bytes(4,'big')
    record[10:18] = size.to_bytes(4,'little')+size.to_bytes(4,'big')
    record[25] = flags
    record[28:32] = b'\x01\0\0\x01'
    record[32] = len(name)
    record[33:33+len(name)] = name
    return record


def _iso():
    image = bytearray(25*2048)
    pvd = 16*2048
    image[pvd:pvd+7] = b'\x01CD001\x01'
    image[pvd+80:pvd+88] = (25).to_bytes(4,'little')+(25).to_bytes(4,'big')
    image[pvd+128:pvd+132] = b'\0\x08\x08\0'
    root = _record(20,2048,b'\0',2)
    image[pvd+156:pvd+156+len(root)] = root
    first = _record(21,12,b'A.BIN;1')
    second = _record(22,13,b'B.BIN;1')
    image[20*2048:20*2048+len(first)+len(second)] = first+second
    return image


def test_iso_dual_endian_fields_and_overlaps():
    original = _iso()
    assert set(v.iso_inventory(original)) == {'A.BIN','B.BIN'}
    for offset in [20*2048+6,20*2048+14,16*2048+84]:
        image = bytearray(original)
        image[offset] ^= 1
        with pytest.raises(ValueError,match='dual-endian'):
            v.iso_inventory(image)
    image = bytearray(original)
    at = v.iso_inventory(image)['B.BIN']['record_offset']
    image[at+2:at+10] = (21).to_bytes(4,'little')+(21).to_bytes(4,'big')
    with pytest.raises(ValueError,match='Overlapping'):
        v.iso_inventory(image)


def test_iso_duplicate_and_unsafe_names():
    for second,match in [(b'A.BIN;1','Duplicate'),(b'../B;1','Unsafe')]:
        image = _iso()
        at = v.iso_inventory(image)['B.BIN']['record_offset']
        replacement = _record(22,13,second)
        image[at:at+len(replacement)] = replacement
        with pytest.raises(ValueError,match=match):
            v.iso_inventory(image)


def test_cue_index00_audio_ownership(tmp_path):
    binary = tmp_path/'disc.bin'
    binary.write_bytes(bytes(2352*500))
    cue = tmp_path/'disc.cue'
    cue.write_text('FILE "disc.bin" BINARY\nTRACK 01 MODE1/2352\nINDEX 01 00:00:00\nTRACK 02 AUDIO\nINDEX 00 00:02:00\nINDEX 01 00:04:00\n')
    _,tracks = v.cue_layout(cue)
    assert tracks[0]['end'] == 150
    assert tracks[1]['start'] == 150 and tracks[1]['indices']['01'] == 300
    cue.write_text(cue.read_text()+'PREGAP 00:02:00\n')
    with pytest.raises(ValueError,match='Synthetic'):
        v.cue_layout(cue)


def test_artifact_receipt_does_not_hide_corruption(tmp_path):
    artifact = tmp_path/'data.bin'
    original = b'guarded bytes'
    artifact.write_bytes(original)
    record = dict(bytes=len(original),sha1=hashlib.sha1(original).hexdigest(),
                  sha256=hashlib.sha256(original).hexdigest())
    v.check_artifact(artifact,record)
    artifact.write_bytes(b'changed bytes')
    with pytest.raises(ValueError,match='sha1 mismatch'):
        v.check_artifact(artifact,record)


def test_manifest_requires_complete_build_receipt(tmp_path):
    record = dict(path='file.bin',bytes=1,sha1='0'*40,sha256='0'*64)
    manifest = dict(version=1,source_cue='source.cue',source_manifest='source.json',canonical_tree='assets',
                    artifacts={k:dict(record) for k in ['bin','cue','chd','xdelta','track01','source_track01']},
                    everdrive={k:dict(record) for k in ['bin','cue']})
    v.validate_manifest(manifest)
    for field in ['version','source_cue','source_manifest','canonical_tree','everdrive']:
        bad = copy.deepcopy(manifest)
        del bad[field]
        with pytest.raises(ValueError):
            v.validate_manifest(bad)
    for key in manifest['artifacts']:
        bad = copy.deepcopy(manifest)
        del bad['artifacts'][key]
        with pytest.raises(ValueError,match='six mandatory'):
            v.validate_manifest(bad)
    with pytest.raises(ValueError,match='Missing required build manifest'):
        v.verify(tmp_path)


def test_dist_independent_verification():
    if not (ROOT/'dist/Snatcher Uncut (USA).chd').exists():
        pytest.skip('M5 artifacts have not been built')
    report = v.verify(ROOT,evidence='build/evidence/m5/verification-lane/test-run')
    assert report['status'] == 'pass'
    assert report['iso_files_verified'] == 100
    assert len(report['audio_tracks']) == 20
    assert report['edc_ecc_sectors_verified'] == 56014
