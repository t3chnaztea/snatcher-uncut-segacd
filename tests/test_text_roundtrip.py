"""Integration evidence from the staged retail disc; no copyrighted fixtures."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('scd_text',ROOT/'tools/scd_text.py')
text=importlib.util.module_from_spec(spec);spec.loader.exec_module(text)


def test_every_sp_string_roundtrip():
    output=ROOT/'build/test-text-dumps'
    summary=text.dump(output=output)
    report=text.insert(dumps=output,output=ROOT/'build/test-text-output')
    assert summary['files']==39
    assert summary['strings']==10728
    assert summary['counts']['SP31.BIN']==0
    assert len(report)==39
    assert all(r['identical'] and not r['changed'] for r in report)
    assert summary['control_counts'].get('F2',0)>10000
    assert summary['control_counts'].get('FD',0)==0


def test_one_edit_changes_only_selected_string():
    output=ROOT/'build/test-text-edit-dumps'
    text.dump(output=output)
    path=output/'SP01.json';record=json.loads(path.read_text())
    row=next(r for r in record['strings'] if r['offset']==0x3af4)
    assert row['text']=='NEW GAME'
    row['text']='NEW TEST';path.write_text(json.dumps(record))
    destination=ROOT/'build/test-text-edit-output'
    report=text.insert(dumps=output,output=destination)
    changed=[r for r in report if not r['identical']]
    assert len(changed)==1 and changed[0]['file']=='SP01.BIN'
    original=(text.SOURCE/'SP01.BIN').read_bytes();edited=(destination/'SP01.BIN').read_bytes()
    assert edited[:row['offset']]==original[:row['offset']]
    assert edited[row['offset']:row['offset']+8]==b'NEW TEST'
    assert edited[row['offset']+8:]==original[row['offset']+8:]


def test_growth_and_metadata_tampering_rejected():
    output=ROOT/'build/test-text-rejection'
    text.dump(output=output)
    path=output/'SP00.json';record=json.loads(path.read_text())
    record['strings'][0]['text']+='!';path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='fixed-length edit'):
        text.insert(dumps=output,output=ROOT/'build/test-text-rejection-output')
    record['strings'][0]['text']=text.decode(bytes.fromhex(record['strings'][0]['raw']))
    record['strings'][0]['offset']+=1;path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='immutable string metadata'):
        text.insert(dumps=output,output=ROOT/'build/test-text-rejection-output')


def test_codec_preserves_control_bytes():
    for b in range(256):
        assert text.encode(text.decode(bytes([b])))==bytes([b])
    with pytest.raises(ValueError,match='byte escape'):
        text.encode('{NEW}')


def test_pce_reference_inventory():
    report=text.reference_pce(output=ROOT/'build/test-pce-reference')
    assert report['modules']==33
    assert report['strings']==9322
    assert report['translated']==9309
    assert [r['rec'] for r in report['records']]==list(range(158,671,16))


def test_output_cannot_overwrite_input():
    output=ROOT/'build/test-text-source-protection'
    text.dump(output=output)
    with pytest.raises(ValueError,match='overwrite'):
        text.insert(dumps=output,output=text.SOURCE)


def test_all_speaker_headings_roundtrip_and_one_test_edit():
    dumps=ROOT/'build/test-speaker-dumps'
    text.dump(output=dumps)
    destination=ROOT/'build/test-speaker-output'
    report=text.insert_speakers(dumps=dumps,output=destination)
    original=(text.SOURCE/'SUBCODE.BIN').read_bytes()
    assert report['identical'] and report['changed']==[]
    assert (destination/'SUBCODE.BIN').read_bytes()==original
    path=dumps/'speakers.json';rows=json.loads(path.read_text())
    assert len(rows)==48 and sum(bool(r['text']) for r in rows)==47
    row=rows[36]
    assert row['text']=='Goemon'
    row['text']='TEST36';path.write_text(json.dumps(rows))
    report=text.insert_speakers(dumps=dumps,output=destination)
    edited=(destination/'SUBCODE.BIN').read_bytes()
    start=row['offset']+1
    assert report['changed']==[36] and not report['identical']
    assert edited[:start]==original[:start]
    assert edited[start:start+6]==b'TEST36'
    assert edited[start+6:]==original[start+6:]


def test_speaker_edit_validation_and_source_protection():
    dumps=ROOT/'build/test-speaker-rejection'
    text.dump(output=dumps)
    path=dumps/'speakers.json';original_rows=json.loads(path.read_text())
    destination=ROOT/'build/test-speaker-rejection-output'
    for field,value,error in [('text','TEST','fixed-length'),
                              ('text','TEST123','fixed-length'),
                              ('text','TEST{FF}X','embedded terminator'),
                              ('table_offset',0,'immutable speaker metadata'),
                              ('offset',0,'immutable speaker metadata'),
                              ('attribute',0,'immutable speaker metadata'),
                              ('source_sha1','0'*40,'source no longer matches')]:
        rows=json.loads(json.dumps(original_rows));rows[36][field]=value
        path.write_text(json.dumps(rows))
        with pytest.raises(ValueError,match=error):
            text.insert_speakers(dumps=dumps,output=destination)
    path.write_text(json.dumps(original_rows[:-1]))
    with pytest.raises(ValueError,match='all 48'):
        text.insert_speakers(dumps=dumps,output=destination)
    path.write_text(json.dumps(original_rows))
    with pytest.raises(ValueError,match='overwrite'):
        text.insert_speakers(dumps=dumps,output=text.SOURCE)
    changed_source=ROOT/'build/test-speaker-changed-source'
    changed_source.mkdir(parents=True,exist_ok=True)
    data=bytearray((text.SOURCE/'SUBCODE.BIN').read_bytes());data[0]^=1
    (changed_source/'SUBCODE.BIN').write_bytes(data)
    with pytest.raises(ValueError,match='source no longer matches'):
        text.insert_speakers(dumps=dumps,source=changed_source,output=destination)
