#!/usr/bin/env python3
"""Apply hash-guarded text deltas without storing complete game passages.

Offsets are relative to one decoded pool record's encoded bytes, excluding
its terminator. Source-file and record selection guards remain the caller's
responsibility. Every unchanged byte comes from the caller-supplied record.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha1(data).hexdigest()


def derive(edit, original, replacement):
    """Convert a legacy edit to source-relative spans; never retain old prose."""
    original, replacement = bytes(original), bytes(replacement)
    if digest(original) != edit['old_hash']:
        raise ValueError('Original text record hash differs')
    if len(original) != len(replacement) or original == replacement:
        raise ValueError('Text edit must change bytes without changing length')
    if b'\xff' in replacement:
        raise ValueError('Text replacement includes a record terminator')
    result = deepcopy(edit)
    result.pop('new_text', None)
    result['encoded_length'] = len(original)
    result['new_hash'] = digest(replacement)
    result['spans'] = []
    delta = bytes(a ^ b for a, b in zip(original, replacement))
    start = 0
    while start < len(delta):
        if delta[start] == 0:
            start += 1
            continue
        end = start + 1
        while end < len(delta) and delta[end] != 0:
            end += 1
        result['spans'].append(dict(offset=start, old_length=end-start,
            old_hash=digest(original[start:end]), xor_hex=delta[start:end].hex()))
        start = end
    if apply(result, original) != replacement:
        raise ValueError('Derived text spans do not reproduce replacement')
    return result


def apply(edit, original):
    """Validate the record and every span before returning replacement bytes."""
    original = bytes(original)
    if len(original) != edit['encoded_length'] or digest(original) != edit['old_hash']:
        raise ValueError('Original text record length or hash differs')
    spans = edit['spans']
    if not isinstance(spans, list) or not spans:
        raise ValueError('Text edit has no spans')
    parts, cursor = [], 0
    for span in spans:
        offset, length = span['offset'], span['old_length']
        if type(offset) is not int or type(length) is not int:
            raise ValueError('Text span offset and length must be integers')
        if offset < cursor or length < 0 or offset + length > len(original):
            raise ValueError('Text spans overlap, are unordered or exceed record')
        before = original[offset:offset+length]
        if digest(before) != span['old_hash']:
            raise ValueError('Original text span hash differs')
        try:
            delta = bytes.fromhex(span['xor_hex'])
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid text span replacement hex') from exc
        if len(delta) != length or not delta or 0 in delta:
            raise ValueError('Text span must contain only changed byte deltas')
        after = bytes(a ^ b for a, b in zip(before, delta))
        if before == after or b'\xff' in after:
            raise ValueError('Text span is unchanged or contains a terminator')
        parts.extend((original[cursor:offset], after))
        cursor = offset + length
    parts.append(original[cursor:])
    result = b''.join(parts)
    if len(result) != len(original) or digest(result) != edit['new_hash']:
        raise ValueError('Replacement text record length or hash differs')
    return result


def convert(record, source, codec):
    """Convert an existing v1 recipe using privately supplied source records."""
    if record.get('version') != 1:
        raise ValueError('Expected legacy version 1 text recipe')
    result = deepcopy(record)
    result['version'] = 2
    result['encoding'] = 'source-relative-encoded-xor-spans'
    pools, speakers = {}, None
    for row in result['rows']:
        for index, edit in enumerate(row['edits']):
            name = edit['file']
            data = (Path(source)/name).read_bytes()
            if digest(data) != edit['source_sha1']:
                raise ValueError('Source file hash differs')
            if edit['kind'] == 'pool':
                if name not in pools:
                    pools[name] = codec.pool(data)[0]
                original = bytes.fromhex(pools[name][edit['string_id']]['raw'])
            elif edit['kind'] == 'speaker' and name == 'SUBCODE.BIN':
                if speakers is None:
                    speakers = codec.speakers(Path(source))
                original = bytes.fromhex(speakers[edit['string_id']]['raw'])[1:]
            else:
                raise ValueError('Unsupported text edit target')
            row['edits'][index] = derive(edit, original, codec.encode(edit['new_text']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--patch', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # The existing codec is project code, not a bundled game-data dependency.
    import sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.root/'tools'))
    import scd_text
    patch = args.patch or args.root/'patches/text/m3.json'
    result = convert(json.loads(patch.read_text()),
                     args.source or args.root/'private/extracted/segacd-usa', scd_text)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
