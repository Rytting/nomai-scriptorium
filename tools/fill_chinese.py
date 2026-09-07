"""Fill missing Chinese without rebuilding the corpus or changing its structure.

Default: official fallback only. --prefer-mod upgrades recorded official fallbacks
when the mod table contains actual Chinese for the same exact/reviewed key.
--check performs a dry run. Existing unmarked Chinese is always preserved.
"""
import argparse
import json
import re
from pathlib import Path
from chinese_lookup import ChineseLookup, has_chinese
from parse_corpus import official_zh, mod_zh

ROOT = Path(__file__).resolve().parents[1]


def fill(data, prefer_mod=False):
    lookup = ChineseLookup(mod_zh if prefer_mod else {}, official_zh)
    changes, unresolved = [], []
    for li, loc in enumerate(data):
        for ci, conv in enumerate(loc['conversations']):
            for si, sp in enumerate(conv['spirals']):
                before = sp.get('zh')
                if has_chinese(before) and not (prefer_mod and sp.get('zh_source') == 'official'):
                    continue
                english = (sp['speaker'] + ': ' if sp['speaker'] else '') + sp['text']
                value, source, key = lookup.find(english)
                record = dict(id=[li, ci, si], location=loc['location'], english=english)
                if not value:
                    if not has_chinese(before):
                        unresolved.append(record)
                    continue
                # Strip game display line wrapping, preserving all translated words.
                value = re.sub(r'\s*\n\s*', '', value).strip()
                if value == before:
                    continue
                changes.append(dict(record, previous=before, chinese=value, source=source, key=key))
                sp.update(zh=value, zh_source=source, zh_key=key)
    return changes, unresolved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--prefer-mod', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'docs/nomai_corpus.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    changes, unresolved = fill(data, args.prefer_mod)
    print(f'Changes: {len(changes)}; remaining without Chinese: {len(unresolved)}')
    if not args.check:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = ROOT / 'docs/chinese-fallback-audit.json'
        if report.exists():
            previous = json.loads(report.read_text(encoding='utf-8'))
            changes = previous['changes'] + changes
        report.write_text(json.dumps(dict(changes=changes, unresolved=unresolved), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
