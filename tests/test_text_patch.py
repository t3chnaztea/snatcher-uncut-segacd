"""M3 approval boundaries and exhaustive output comparison, using staged inputs."""
import copy
import os
import json
from pathlib import Path
import sys
import tempfile
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import scd_text as text
import source_text_recipe as recipe
# Explicit lane override keeps shared approval documents read-only.
LEDGER=Path(os.environ.get('SNATCHER_M3_LEDGER',ROOT/'docs/diff-ledger.csv'))
PATCHES=ROOT/'patches/text'

@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory(prefix='m3-test-',dir=ROOT/'build') as tmp:
        yield Path(tmp)

def test_approved_patch_and_unapproved_byte_rejection(workspace):
    output=workspace/'output'
    result=text.apply_patches(PATCHES,output=output,ledger=LEDGER)
    assert result['rows']==31
    report=text.verify(PATCHES,output=output,ledger=LEDGER)
    assert report['sp_files_within_cap']==39
    assert report['edit_records']==72
    assert len(report['remaining_2047'])==8
    # A code change and a changed speaker attribute both lie outside string edits.
    for name,offset in [('SP04.BIN',10),('SUBCODE.BIN',24787)]:
        path=output/name;original=path.read_bytes();changed=bytearray(original)
        changed[offset]^=1;path.write_bytes(changed)
        with pytest.raises(ValueError,match='unapproved byte change'):
            text.verify(PATCHES,output=output,ledger=LEDGER)
        path.write_bytes(original)

def test_approval_hash_and_age_guards(workspace):
    patchdir=workspace/'patches';patchdir.mkdir()
    original=json.loads((PATCHES/'m3.json').read_text())
    mutations=[]
    missing=copy.deepcopy(original);missing['rows'].pop();mutations.append(missing)
    invalid=copy.deepcopy(original);invalid['rows'][0]['edits'][0]['old_hash']='0'*40;mutations.append(invalid)
    source=copy.deepcopy(original);source['rows'][0]['edits'][0]['source_sha1']='0'*40;mutations.append(source)
    age=copy.deepcopy(original)
    for r in age['rows']:
        if r['id']=='TEXT-023':
            edit=r['edits'][0]
            original_bytes=bytes.fromhex(text.pool((text.SOURCE/edit['file']).read_bytes())[0][edit['string_id']]['raw'])
            approved=recipe.apply(edit,original_bytes)
            changed=approved.replace(b'18.',b'14.')
            assert changed!=approved
            r['edits'][0]=recipe.derive(edit,original_bytes,changed)
    mutations.append(age)
    pce=copy.deepcopy(original);pce['rows'][0]['pce_evidence']['strings'][0]['jp_sha1']='0'*40;mutations.append(pce)
    for mutation in mutations:
        (patchdir/'m3.json').write_text(json.dumps(mutation))
        with pytest.raises(ValueError):
            text.patch_records(patchdir,ledger=LEDGER)
