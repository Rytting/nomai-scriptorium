"""Exact normalized lookup with explicitly reviewed source-key aliases.

English placeholders never count as translations. Similarity is not a lookup rule.
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def has_chinese(value):
    return bool(re.search(r'[\u3400-\u9fff]', value or ''))


def normalize(value):
    value = re.sub(r'</?[^>]+>', '', value).replace('*', '')
    value = unicodedata.normalize('NFKC', value).casefold()
    return ''.join(c for c in value if c.isalnum())


class ChineseLookup:
    def __init__(self, mod, official):
        aliases = json.loads((ROOT / 'docs/chinese-key-aliases.json').read_text(encoding='utf-8'))
        self.aliases = {normalize(k): normalize(v) for k, v in aliases.items()}
        self.tables = []
        for source, table in [('mod', mod), ('official', official)]:
            index = {}
            for key, value in table.items():
                if has_chinese(value):
                    index.setdefault(normalize(key), []).append((key, value))
            self.tables.append((source, index))

    def find(self, english):
        key = normalize(english)
        candidates = list(dict.fromkeys([key, self.aliases.get(key, key)]))
        for source, table in self.tables:
            for candidate in candidates:
                entries = table.get(candidate, [])
                if entries and len({v for _, v in entries}) == 1:
                    original_key, value = entries[0]
                    return value, source, original_key
        return None, None, None
