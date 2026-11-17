"""Reviewed restoration groups and strict release-profile metadata.

This module contains no game data. Profiles select only existing approved rows.
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import product
from pathlib import Path, PurePosixPath
import copy
import json
import re

DEFAULT_PROFILE_ID = 'd1-c1-a1-l1'
DEFAULT_PROFILE = DEFAULT_PROFILE_ID
SOURCE_TRACK_BYTES = 131744928
SOURCE_TRACK_SHA1 = '1f4164205ed736a0d9a03eb7972868e9aa737d35'
SOURCE_TRACK_SHA256 = '9592d44b3241b31f36d235acc651bfa9cd2ab9562eadf9aecd86735913f0495d'
ACCEPTED_TRACK_SHA256 = 'f543ea684608ab9c706be6f7e6ff9ba4408feb25e3a3bc4e1fa7ba4038aa5aba'
ACCEPTED_PATCH_SHA256 = '1485cc915dc0d2629049f7abcb8f724f608a8205c89456ad534acf2d26ac09a4'
DATE_TEXT_ROWS = frozenset('TEXT-'+str(n).zfill(3) for n in
    (1,2,3,4,5,6,7,8,9,10,11,13,14,15,16,17,18,19,20,21,22,23,24,25,26,33))
CAMEO_TEXT_ROWS = frozenset(('TERM-002','TERM-003','TERM-004','TERM-005','TERM-006'))
DATE_ART_ROWS = frozenset(('TEXT-034','TEXT-035','TEXT-036'))
GROUP_FILES = {
    'dates': frozenset(('SP04.BIN','SP05.BIN','DATA_D0.BIN','DATA_D1.BIN')),
    'cameos': frozenset(('DATA_O0.BIN','SP13.BIN','SUBCODE.BIN')),
    'alice': frozenset(('DATA_G0.BIN','SP25.BIN')),
    'lisa': frozenset(('DATA_F0.BIN',)),
}

@dataclass(frozen=True)
class Profile:
    id: str
    dates: bool
    cameos: bool
    alice: bool
    lisa: bool

    @property
    def text_rows(self):
        return (DATE_TEXT_ROWS if self.dates else frozenset()) | (CAMEO_TEXT_ROWS if self.cameos else frozenset())

    @property
    def art_rows(self):
        return (DATE_ART_ROWS if self.dates else frozenset()) | frozenset(
            row for flag,row in ((self.cameos,'GFX-002'),(self.alice,'GFX-001'),(self.lisa,'GFX-005')) if flag)

    @property
    def changed_files(self):
        return frozenset().union(*(GROUP_FILES[key] for key in GROUP_FILES if getattr(self,key)))

    @property
    def no_patch(self):
        return not any((self.dates,self.cameos,self.alice,self.lisa))

    @property
    def settings(self):
        return dict(dates='japanese' if self.dates else 'segacd',cameos=self.cameos,alice=self.alice,lisa=self.lisa)

PROFILES = {}
for flags in product((False, True), repeat=4):
    ident = '-'.join(letter+str(int(flag)) for letter,flag in zip('dcal', flags))
    PROFILES[ident] = Profile(ident, *flags)
PROFILE_IDS = tuple(PROFILES)


def get_profile(value=None):
    if value is None:
        value = DEFAULT_PROFILE_ID
    if isinstance(value, Profile):
        expected = PROFILES.get(value.id)
        if expected != value or any(type(getattr(value,k)) is not bool for k in GROUP_FILES):
            raise ValueError('Invalid restoration profile')
        return expected
    if not isinstance(value,str) or value not in PROFILES:
        raise ValueError('Unknown restoration profile')
    return PROFILES[value]


def profile_id(dates='japanese', cameos=True, alice=True, lisa=True):
    if dates not in ('japanese','segacd') or any(type(v) is not bool for v in (cameos,alice,lisa)):
        raise ValueError('Invalid profile settings')
    return '-'.join(letter+str(int(flag)) for letter,flag in zip('dcal',(dates=='japanese',cameos,alice,lisa)))


def _pairs(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate registry JSON field')
        result[key] = value
    return result


def load_registry(value):
    if isinstance(value,dict):
        return validate_registry(value)
    if not isinstance(value,(str,Path)):
        raise ValueError('Expected profile registry path or object')
    return validate_registry(json.loads(Path(value).read_text(),object_pairs_hook=_pairs))


def validate_registry(value):
    if not isinstance(value,dict) or set(value) != {'format','version','default_profile','source','profiles'}:
        raise ValueError('Invalid profile registry fields')
    if type(value['format']) is not int or value['format'] != 1:
        raise ValueError('Unsupported profile registry format')
    if not isinstance(value['version'],str) or not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[a-z0-9.]+)?',value['version']):
        raise ValueError('Invalid profile release version')
    if value['default_profile'] != DEFAULT_PROFILE_ID:
        raise ValueError('Unexpected default profile')
    source = value['source']
    if not isinstance(source,dict) or set(source) != {'track1_bytes','track1_sha1','track1_sha256'}:
        raise ValueError('Invalid source metadata')
    if type(source['track1_bytes']) is not int or source != dict(track1_bytes=SOURCE_TRACK_BYTES,track1_sha1=SOURCE_TRACK_SHA1,track1_sha256=SOURCE_TRACK_SHA256):
        raise ValueError('Registry source differs from supported USA disc')
    entries = value['profiles']
    if not isinstance(entries,list) or len(entries) != 16:
        raise ValueError('Registry must contain exactly 16 profiles')
    seen=set(); patches=set(); targets=set()
    for entry in entries:
        if not isinstance(entry,dict) or set(entry) != {'id','settings','no_patch','target_track1_sha256','patch'}:
            raise ValueError('Invalid profile entry fields')
        profile=get_profile(entry['id'])
        if profile.id in seen:
            raise ValueError('Duplicate profile ID')
        seen.add(profile.id)
        settings=entry['settings']
        if not isinstance(settings,dict) or set(settings) != {'dates','cameos','alice','lisa'} or any(type(settings[k]) is not bool for k in ('cameos','alice','lisa')) or settings != profile.settings:
            raise ValueError('Profile settings do not match ID')
        if type(entry['no_patch']) is not bool or entry['no_patch'] != profile.no_patch:
            raise ValueError('Invalid no-patch state')
        target=entry['target_track1_sha256']
        if not isinstance(target,str) or not re.fullmatch('[0-9a-f]{64}',target) or target in targets:
            raise ValueError('Invalid or duplicate profile target hash')
        targets.add(target)
        patch=entry['patch']
        if profile.no_patch:
            if patch is not None or target != SOURCE_TRACK_SHA256:
                raise ValueError('Original-disc profile must have no patch')
        else:
            expected_file='patches/profiles/'+profile.id+'.xdelta'
            if not isinstance(patch,dict) or set(patch) != {'file','sha256'} or patch['file'] != expected_file:
                raise ValueError('Invalid profile patch path')
            name=PurePosixPath(patch['file'])
            if name.is_absolute() or '..' in name.parts or '\\' in patch['file']:
                raise ValueError('Unsafe profile patch path')
            if not isinstance(patch['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',patch['sha256']) or patch['sha256'] in patches:
                raise ValueError('Invalid or duplicate patch hash')
            patches.add(patch['sha256'])
            if target == SOURCE_TRACK_SHA256:
                raise ValueError('Active profile cannot target the unchanged disc')
            if profile.id == DEFAULT_PROFILE_ID and (target != ACCEPTED_TRACK_SHA256 or patch['sha256'] != ACCEPTED_PATCH_SHA256):
                raise ValueError('Default profile differs from accepted release')
    if seen != set(PROFILE_IDS):
        raise ValueError('Incomplete profile selection map')
    return copy.deepcopy(value)
