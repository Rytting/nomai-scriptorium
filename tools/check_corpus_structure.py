"""Check source-defined chains, sibling branches, and preserved corpus fields."""
import json
from pathlib import Path
from parse_corpus import parse_corpus, assign_parents

ROOT = Path(__file__).resolve().parent.parent

# Source key: continuation, two sibling branches, two secondary branches.
example = [
    (0, False), (0, False), (1, True), (1, False),
    (1, True), (2, True), (2, True), (1, False),
]
spirals = [dict(depth=d, branch=b) for d, b in example]
assign_parents(spirals)
assert [s['parent'] for s in spirals] == [None, 0, 1, 2, 1, 4, 4, 6]

parsed = parse_corpus(ROOT / 'docs/nomai_text_corpus.md')
saved = json.loads((ROOT / 'docs/nomai_corpus.json').read_text(encoding='utf-8'))
assert len(parsed) == len(saved)
count = 0
for a, b in zip(parsed, saved):
    assert a['location'] == b['location']
    assert len(a['conversations']) == len(b['conversations'])
    for c, d in zip(a['conversations'], b['conversations']):
        assign_parents(c['spirals'])
        assert len(c['spirals']) == len(d['spirals'])
        for i, (s, t) in enumerate(zip(c['spirals'], d['spirals'])):
            assert all(s[k] == t[k] for k in ('speaker', 'text', 'parent'))
            assert s['parent'] is None if i == 0 else 0 <= s['parent'] < i
        count += 1
assert [s['parent'] for s in saved[0]['conversations'][0]['spirals']] == [None, 0, 1, 2, 1, 4, 5, 6]
print(f'PASS: source example, Sun Station branches, {count} single-root conversations')
