"""Integration checks against the private, manifest-verified source disc."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import scd_disc as disc


def test_full_disc_roundtrip():
    manifest = disc.extract()
    result = disc.rebuild(output=disc.ROOT/'build/test-roundtrip/Snatcher.cue')
    assert len(manifest['files']) == 100
    assert result['identical']
    assert result['changed_data_sectors'] == 0
    assert result['sha1'] == '9ff422fcbdb3cbd5a585d1c822f28930713ba4a8'
    source = disc.track_hashes(disc.DEFAULT_CUE)
    output = disc.track_hashes(disc.ROOT/'build/test-roundtrip/Snatcher.cue')
    assert source == output


def test_changed_payload_regenerates_checksums():
    source, _ = disc.tracks(disc.DEFAULT_CUE)
    with source.open('rb') as f:
        f.seek(100*2352)
        raw = f.read(2352)
    assert disc.mode1_sector(raw[16:2064],100) == raw
    payload = bytearray(raw[16:2064]); payload[10] ^= 1
    changed = disc.mode1_sector(payload,100)
    assert changed[:16] == raw[:16]
    assert changed[16:2064] == payload
    assert changed[2064:2068] != raw[2064:2068]
    assert changed[2076:] != raw[2076:]


def test_size_change_rejected():
    # Rebuild validates lengths before opening output. No mutation of inputs.
    import shutil
    manifest = json.loads((disc.DEFAULT_EXTRACT/'manifest.json').read_text())
    row = manifest['files'][0]
    testdir = disc.ROOT/'build/size-rejection'
    testdir.mkdir(parents=True,exist_ok=True)
    for name in ('manifest.json','_track01.raw','_boot.bin'):
        shutil.copyfile(disc.DEFAULT_EXTRACT/name,testdir/name)
    path = testdir/row['name'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'')
    with pytest.raises(ValueError,match='fixed-layout'):
        disc.rebuild(testdir,disc.ROOT/'build/size-rejection-output/Snatcher.cue')
