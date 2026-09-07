"""Regression checks for fallback priority, ambiguity, and repeatability."""
import copy
import json
from unittest.mock import patch
from pathlib import Path
from chinese_lookup import ChineseLookup, has_chinese
from fill_chinese import fill

key = 'PYE: Test sentence.'
lookup = ChineseLookup({key:key}, {key:'派伊：测试句子。'})
assert lookup.find(key)[1] == 'official'
assert ChineseLookup({key:'派伊：模组译文。'}, {key:'派伊：官方译文。'}).find(key)[1] == 'mod'
assert lookup.find('PYE: Test different sentence.')[0] is None
assert ChineseLookup({}, {key:'甲', 'PYE: Test sentence!':'乙'}).find(key)[0] is None

sample = [{'location':'test', 'conversations':[{'spirals':[
    {'speaker':'PYE', 'text':'Test sentence.', 'zh':'派伊：官方译文。', 'zh_source':'official'},
    {'speaker':'PYE', 'text':'Test sentence.', 'zh':'派伊：保留的用户译文。'}]}]}]
with patch('fill_chinese.mod_zh', {key:'派伊：模组译文。'}), patch('fill_chinese.official_zh', {key:'派伊：官方译文。'}):
    updates, _ = fill(sample, prefer_mod=True)
assert len(updates) == 1 and updates[0]['source'] == 'mod'
assert sample[0]['conversations'][0]['spirals'][1]['zh'] == '派伊：保留的用户译文。'

data = json.loads((Path(__file__).resolve().parents[1] / 'docs/nomai_corpus.json').read_text(encoding='utf-8'))
original = copy.deepcopy(data)
changes, unresolved = fill(data)
assert not changes and data == original, 'Fallback must be idempotent'
rows = [s for l in data for c in l['conversations'] for s in c['spirals']]
print(f'PASS: placeholder rejection, mod priority, no fuzzy adoption, collision rejection, idempotence; Chinese {sum(has_chinese(s.get("zh")) for s in rows)}/{len(rows)}, unresolved {len(unresolved)}')
