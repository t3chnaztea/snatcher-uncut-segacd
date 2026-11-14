"""Typed PCE reader integration checks from the staged Japanese disc."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('scd_text',ROOT/'tools/scd_text.py')
text=importlib.util.module_from_spec(spec);spec.loader.exec_module(text)


@pytest.fixture(scope='module')
def index():
    destination=ROOT/'build/test-pce-vm/index.json'
    summary=text.inspect_pce(output=destination)
    assert summary['modules']==33
    assert summary['typed_modules']==33
    assert summary['expression_nodes']==70688
    return json.loads(destination.read_text())


def test_all_pce_expression_bytes_are_accounted_for(index):
    assert index['pregap_sectors']==225
    assert index['descriptor_table_offset']==0x2df9
    assert index['opcode_table'][0xf1]['modes']==[2,4,0]
    for record in index['modules'].values():
        assert record['coverage_gaps']==[]
        assert record['covered_bytes']==record['parsed_until']
        assert record['parsed_until']+record['fill_bytes']==record['code_limit']


def test_every_typed_menu_and_dialogue_reference_is_a_real_boundary(index):
    count=0
    for record in index['modules'].values():
        labels={row['offset'] for row in record.get('word_records',[])}
        strings=set(record.get('text_offsets',[]))
        for reference in record.get('references',[]):
            if reference['kind']=='menu_or_data_label':
                assert reference['label_offset'] in labels
                count+=1
            elif reference['kind']=='dialogue':
                assert reference['text_offset'] in strings
    assert count==3965


def test_shower_targets_are_typed_menu_expressions(index):
    record=index['modules']['574']
    nodes={row['offset']:row for row in record['nodes']}
    for start,label,continuation in ((0x760,0x1572,0x77d),(0x780,0x1496,0x79d)):
        node=nodes[start]
        assert node['opcode']==0xf1
        assert node['operands'][0]['value']==label
        child=nodes[node['children'][0]]
        assert child['continuation']==continuation
        assert node['end']==continuation
        assert any(row['kind']=='dialogue' and start<row['offset']<continuation
                   for row in record['references'])


def test_ending_is_a_text_free_vm_and_has_canonical_entry(index):
    ending=index['modules']['670']
    assert ending['text_offsets']==[]
    assert ending['word_records']==[]
    assert ending['parsed_until']==2928
    assert len(ending['nodes'])==1680
    assert not any(row['kind']=='menu_or_data_label' for row in ending['references'])
    assert any(row['kind']=='scene_jump' and row['record']==670 and row['entry']==4
               for row in index['modules']['654']['references'])


def test_dog_event_has_typed_graphics_reference(index):
    assert any(row['offset']==0x46d and row['kind']=='graphics'
               and row['block']==35 and row['display_list']==1
               for row in index['modules']['526']['references'])
