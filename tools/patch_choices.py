"""Advanced choices over existing approved restorations; no game payloads.

Format 1 profiles stay immutable in patch_profiles. Format 2 uses six disjoint
sector families and an exact target checksum for each of 4,096 selections.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import copy
import json
import re
from patch_profiles import (DATE_TEXT_ROWS, SOURCE_TRACK_BYTES, SOURCE_TRACK_SHA1,
                            SOURCE_TRACK_SHA256, ACCEPTED_TRACK_SHA256)

VERSION = 'v0.11.0-rc1'
SETTING_KEYS = ('database_dates', 'moscow_date', 'newspaper_date', 'neokobe_date',
                'mask_rider', 'cornelius', 'alyen', 'miss_money', 'h2o_gulliver',
                'alice', 'lisa', 'bar_background')
CAMEO_KEYS = SETTING_KEYS[4:9]
CAMEO_ROWS = dict(zip(CAMEO_KEYS, ('TERM-002','TERM-003','TERM-004','TERM-005','TERM-006')))
CAMEO_GROUPS = dict(zip(CAMEO_KEYS, (18,21,19,20,17)))
CAPTION_ROWS = dict(zip(SETTING_KEYS[1:4], ('TEXT-034','TEXT-035','TEXT-036')))
DEFAULT_CHOICE_ID = 'xfff'
CHOICE_IDS = tuple(f'x{mask:03x}' for mask in range(4096))
# Local variant values use the order of setting_keys, starting with bit zero.
FAMILIES = (
    ('database', ('database_dates',), ('SP04.BIN','SP05.BIN')),
    ('opening', ('moscow_date','newspaper_date'), ('DATA_D1.BIN',)),
    ('city', ('neokobe_date',), ('DATA_D0.BIN',)),
    ('cameos', CAMEO_KEYS + ('bar_background',), ('DATA_O0.BIN','SP13.BIN','SUBCODE.BIN')),
    ('alice', ('alice',), ('DATA_G0.BIN','SP25.BIN')),
    ('lisa', ('lisa',), ('DATA_F0.BIN',)),
)
FAMILY_MAP = {name:(keys,files) for name,keys,files in FAMILIES}
SOURCE = dict(track1_bytes=SOURCE_TRACK_BYTES, track1_sha1=SOURCE_TRACK_SHA1,
              track1_sha256=SOURCE_TRACK_SHA256)

@dataclass(frozen=True)
class Selection:
    mask: int

    def __post_init__(self):
        if type(self.mask) is not int or not 0 <= self.mask < 4096:
            raise ValueError('Invalid advanced selection mask')

    @property
    def id(self): return f'x{self.mask:03x}'
    @property
    def settings(self): return {key:bool(self.mask & (1 << i)) for i,key in enumerate(SETTING_KEYS)}
    @property
    def dates(self): return self.settings['database_dates']
    @property
    def cameos(self): return bool(self.mask & 0x9f0)
    @property
    def cameo_groups(self): return frozenset(key for key in CAMEO_KEYS if self.settings[key])
    @property
    def bar_background(self): return self.settings['bar_background']
    @property
    def alice(self): return self.settings['alice']
    @property
    def lisa(self): return self.settings['lisa']
    @property
    def text_rows(self):
        return (DATE_TEXT_ROWS if self.dates else frozenset()) | frozenset(CAMEO_ROWS[key] for key in self.cameo_groups)
    @property
    def art_rows(self):
        return frozenset(row for key,row in CAPTION_ROWS.items() if self.settings[key]) | frozenset(
            row for flag,row in ((self.cameos,'GFX-002'),(self.alice,'GFX-001'),(self.lisa,'GFX-005')) if flag)
    @property
    def changed_files(self):
        files={file for name,keys,owned in FAMILIES if name!='cameos' and any(self.settings[key] for key in keys) for file in owned}
        if self.cameos: files.add('DATA_O0.BIN')
        if self.cameo_groups: files.update(('SP13.BIN','SUBCODE.BIN'))
        return frozenset(files)
    @property
    def no_patch(self): return self.mask == 0


def get_selection(value=None):
    if value is None: return Selection(4095)
    if isinstance(value,Selection): return Selection(value.mask)
    if isinstance(value,str) and re.fullmatch(r'x[0-9a-f]{3}',value): return Selection(int(value[1:],16))
    if isinstance(value,dict):
        if set(value)!=set(SETTING_KEYS) or any(type(v) is not bool for v in value.values()):
            raise ValueError('Invalid advanced settings')
        return Selection(sum(int(value[key]) << i for i,key in enumerate(SETTING_KEYS)))
    raise ValueError('Unknown advanced selection')


def legacy_selection(value):
    """Explicit adapter for a v1 ID or settings object, including old receipts."""
    if isinstance(value,str):
        from patch_profiles import get_profile
        value=get_profile(value).settings
    if not isinstance(value,dict) or set(value)!={'dates','cameos','alice','lisa'} or value['dates'] not in ('japanese','segacd') or any(type(value[k]) is not bool for k in ('cameos','alice','lisa')):
        raise ValueError('Invalid legacy selection')
    flags={key:value['dates']=='japanese' for key in SETTING_KEYS[:4]}
    flags.update({key:value['cameos'] for key in CAMEO_KEYS})
    flags.update(alice=value['alice'],lisa=value['lisa'],bar_background=value['cameos'])
    return get_selection(flags)


def family_values(selection):
    flags=get_selection(selection).settings
    return {name:sum(int(flags[key]) << i for i,key in enumerate(keys)) for name,keys,_ in FAMILIES}


def family_selection(name,value):
    if name not in FAMILY_MAP: raise ValueError('Unknown component family')
    keys,_=FAMILY_MAP[name]
    if type(value) is not int or not 0 <= value < 1 << len(keys): raise ValueError('Invalid component variant')
    flags=dict.fromkeys(SETTING_KEYS,False)
    flags.update({key:bool(value & (1 << i)) for i,key in enumerate(keys)})
    return get_selection(flags)


def variant_id(name,value):
    family_selection(name,value)
    return f'{name}-{value:02x}'


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate advanced registry field')
        result[key]=value
    return result


def load_registry(value):
    if isinstance(value,dict): return validate_registry(value)
    if not isinstance(value,(str,Path)): raise ValueError('Expected advanced registry path or object')
    return validate_registry(json.loads(Path(value).read_text(),object_pairs_hook=_pairs))


def validate_registry(value):
    """Validate bounded, disjoint components before any source input is read."""
    if not isinstance(value,dict) or set(value)!={'format','version','default_profile','source','families','targets'}:
        raise ValueError('Invalid advanced registry fields')
    if type(value['format']) is not int or value['format']!=2: raise ValueError('Unsupported advanced registry format')
    if not isinstance(value['version'],str) or not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[a-z0-9.]+)?',value['version']): raise ValueError('Invalid advanced release version')
    if value['default_profile']!=DEFAULT_CHOICE_ID or not isinstance(value['source'],dict) or value['source']!=SOURCE or type(value['source'].get('track1_bytes')) is not int:
        raise ValueError('Advanced registry source or default changed')
    targets=value['targets']
    if not isinstance(targets,dict) or set(targets)!=set(CHOICE_IDS) or any(not isinstance(x,str) or not re.fullmatch('[0-9a-f]{64}',x) for x in targets.values()):
        raise ValueError('Incomplete or invalid advanced target hashes')
    if len(set(targets.values()))!=4096 or targets['x000']!=SOURCE_TRACK_SHA256 or targets[DEFAULT_CHOICE_ID]!=ACCEPTED_TRACK_SHA256:
        raise ValueError('Advanced source/default oracle or unique targets changed')
    families=value['families']
    if not isinstance(families,list) or len(families)!=len(FAMILIES): raise ValueError('Invalid component family inventory')
    occupied=set();seen=set();patches=set();variant_hashes=set()
    for family in families:
        if not isinstance(family,dict) or set(family)!={'id','setting_keys','files','ranges','variants'}: raise ValueError('Invalid component family fields')
        name=family['id']
        if not isinstance(name,str) or name not in FAMILY_MAP or name in seen: raise ValueError('Unknown or duplicate component family')
        seen.add(name);keys,files=FAMILY_MAP[name]
        if family['setting_keys']!=list(keys) or family['files']!=list(files): raise ValueError('Component ownership differs from approved groups')
        ranges=family['ranges'];local=set();previous=-1
        if not isinstance(ranges,list) or not ranges or len(ranges)>1024: raise ValueError('Invalid component sector ranges')
        for item in ranges:
            if not isinstance(item,dict) or set(item)!={'lba','count'}: raise ValueError('Invalid sector range fields')
            lba,count=item['lba'],item['count']
            if type(lba) is not int or type(count) is not int or lba<0 or count<1 or lba+count>SOURCE_TRACK_BYTES//2352 or lba<=previous:
                raise ValueError('Overlapping or out-of-bounds component sectors')
            sectors=set(range(lba,lba+count));local.update(sectors);previous=lba+count-1
        if len(local)>1024 or occupied & local: raise ValueError('Component family sectors overlap or exceed bounds')
        occupied.update(local);variants=family['variants'];maximum=1 << len(keys)
        if not isinstance(variants,list) or len(variants)!=maximum-1: raise ValueError('Incomplete component variants')
        values=set()
        for variant in variants:
            if not isinstance(variant,dict) or set(variant)!={'value','id','patch','decoded_bytes','decoded_sha256'}: raise ValueError('Invalid component variant fields')
            number=variant['value']
            if type(number) is not int or not 1<=number<maximum or number in values: raise ValueError('Invalid or duplicate component variant')
            values.add(number);ident=variant_id(name,number)
            if variant['id']!=ident or type(variant['decoded_bytes']) is not int or variant['decoded_bytes']!=len(local)*2352:
                raise ValueError('Component identity or decoded length changed')
            digest=variant['decoded_sha256'];patch=variant['patch']
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest) or digest in variant_hashes: raise ValueError('Invalid or duplicate component output hash')
            variant_hashes.add(digest)
            if not isinstance(patch,dict) or set(patch)!={'file','sha256'} or patch['file']!=f'patches/components/{ident}.xdelta' or not isinstance(patch['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',patch['sha256']) or patch['sha256'] in patches:
                raise ValueError('Invalid component patch path or checksum')
            patches.add(patch['sha256'])
    if len(occupied)>4096: raise ValueError('Component sector budget exceeded')
    return copy.deepcopy(value)
