"""Synthetic source-delta tests contain no game text or binary fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import source_text_recipe as recipe


def make(before, after):
    return recipe.derive(dict(old_hash=recipe.digest(before), new_text='discard'), before, after)


def test_source_text_delta_retains_controls_and_unchanged_bytes():
    before = b'\xfeSynthetic date 2098\xf2sample 73\xf9'
    after = b'\xfeSynthetic date 2093\xf2sample 73\xf9'
    edit = make(before, after)
    assert recipe.apply(edit, before) == after
    assert edit['spans'] == [dict(offset=19, old_length=1,
        old_hash=recipe.digest(b'8'), xor_hex=bytes([ord('8') ^ ord('3')]).hex())]
    assert 'new_text' not in edit


def test_variable_spans_preserve_total_record_length():
    before, after = b'prefix AABB suffix', b'prefix XYZB suffix'
    edit = make(before, after)
    assert recipe.apply(edit, before) == after
    assert all('old_text' not in span for span in edit['spans'])


@pytest.mark.parametrize('mutation', ['source', 'span_hash', 'new_hash', 'bounds', 'order', 'terminator'])
def test_corrupt_or_overlapping_recipe_rejected(mutation):
    before, after = b'left 2098 right 2098', b'left 2093 right 2093'
    edit = deepcopy(make(before, after))
    if mutation == 'source':
        before = b'Left 2098 right 2098'
    elif mutation == 'span_hash':
        edit['spans'][0]['old_hash'] = '0'*40
    elif mutation == 'new_hash':
        edit['new_hash'] = '0'*40
    elif mutation == 'bounds':
        edit['spans'][0]['offset'] = len(before)+1
    elif mutation == 'order':
        edit['spans'].reverse()
    elif mutation == 'terminator':
        edit['spans'][0]['xor_hex'] = bytes([ord('8') ^ 255]).hex()
    with pytest.raises(ValueError):
        recipe.apply(edit, before)


def test_derive_rejects_wrong_source_and_record_growth():
    with pytest.raises(ValueError):
        recipe.derive(dict(old_hash='0'*40), b'synthetic', b'Synthetic')
    with pytest.raises(ValueError):
        make(b'synthetic', b'synthetic extra')
