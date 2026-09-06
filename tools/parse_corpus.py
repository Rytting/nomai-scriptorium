"""Parse the Nomai text corpus into structured JSON.

Input:  docs/nomai_text_corpus.md   (English structure + speakers)
        docs/chinese_official.xml   (official Chinese from game assets)
        YmbsisOWTranslation XML     (user's improved Chinese, takes priority)

Output: docs/nomai_corpus.json

Conversation boundaries:
  - Location headers (bare title lines) start a new location
  - \\- on its own line separates unrelated conversations at the same location
  - ... connects related texts within the same conversation
  - {A ~ B} marks a projection-stone link (treated as a conversation attribute)
  - 🎥 marks a recording

Branching:
  - "- SPEAKER:" at base indent = branch from the last non-branch line
  - Indented continuation = continues the branch above
  - "  - SPEAKER:" = sub-branch from the branch above
"""

import re, json, html, sys, pathlib
from difflib import SequenceMatcher

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ── Load Chinese translations ───────────────────────────────────────────

def load_xml_translations(path):
    """Return dict: cleaned_english_key -> chinese_value."""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    table = {}
    for m in re.finditer(r"<key>\s*(.*?)\s*</key>\s*<value>\s*(.*?)\s*</value>",
                         content, re.DOTALL):
        key = html.unescape(m.group(1)).strip()
        val = html.unescape(m.group(2)).strip()
        key = re.sub(r"<color=[^>]*>|</color>", "", key)
        val = re.sub(r"\\\\[nN]", "\n", val)  # game uses \\n for newlines
        val = re.sub(r"</?i>", "", val)
        val = re.sub(r"<color=[^>]*>|</color>", "", val)
        table[key] = val
    return table

mod_xml = ROOT / "docs" / "chinese_official.xml"
mod_path_alt = pathlib.Path(r"D:\OWModProjects\YmbsisOWTranslation\assets\Translation.xml")

official_zh = load_xml_translations(mod_xml) if mod_xml.exists() else {}
mod_zh = load_xml_translations(mod_path_alt) if mod_path_alt.exists() else {}


def find_chinese(english_line):
    """Look up Chinese for an English speaker line. Mod first, then official."""
    clean = re.sub(r"\s+", " ", english_line.replace("*", "")).strip()
    if clean in mod_zh:
        return mod_zh[clean], "mod"
    if clean in official_zh:
        return official_zh[clean], "official"
    # fuzzy match within speaker bucket
    m = re.match(r"^([A-Z][A-Z]+): ", clean)
    if not m:
        return _fuzzy_all(clean)
    speaker = m.group(1)
    best_ratio, best_val, best_src = 0, None, None
    clean_norm = re.sub(r"\s+", " ", clean)
    for table, src in [(mod_zh, "mod"), (official_zh, "official")]:
        for key, val in table.items():
            if not key.startswith(speaker + ": "):
                continue
            key_norm = re.sub(r"\s+", " ", key)
            ratio = SequenceMatcher(None, clean_norm[:100], key_norm[:100]).ratio()
            if ratio > best_ratio:
                best_ratio, best_val, best_src = ratio, val, src
    if best_ratio > 0.75:
        return best_val, best_src
    return None, None


def _fuzzy_all(text):
    best_ratio, best_val, best_src = 0, None, None
    for table, src in [(mod_zh, "mod"), (official_zh, "official")]:
        for key, val in table.items():
            ratio = SequenceMatcher(None, text[:100], key[:100]).ratio()
            if ratio > best_ratio:
                best_ratio, best_val, best_src = ratio, val, src
    if best_ratio > 0.75:
        return best_val, best_src
    return None, None


# ── Parse corpus ────────────────────────────────────────────────────────

KNOWN_SPEAKERS = {
    "ANNONA", "AVENS", "BELLS", "BROMI", "BUR", "CANNA", "CASSAVA",
    "CLARY", "CLEM", "COLEUS", "CONOY", "CYCAD", "DAZ", "DIN",
    "ESCALL", "FILIX", "FOLI", "HYSSOP", "IDAEA", "IDEAE", "ILEX",
    "KEEK", "KOUSA", "LAEVI", "LAMI", "MALLOW", "MELORAE", "MITIS",
    "NEEM", "OENO", "PHLOX", "PLUME", "POKE", "PRIVET", "PYE",
    "RAMIE", "RHUS", "ROOT", "SOLANUM", "SPIRE", "TAGET", "THATCH",
    "YARROW",
}

CELESTIAL_BODIES = {
    "The Sun Station": "Hourglass Twins",
    "Ember Twin": "Hourglass Twins",
    "Ash Twin": "Hourglass Twins",
    "Timber Hearth": "Timber Hearth",
    "Timber hearth": "Timber Hearth",
    "The Attlerock": "Timber Hearth",
    "Brittle hollow": "Brittle Hollow",
    "Brittle Hollow": "Brittle Hollow",
    "Giant's deep": "Giant's Deep",
    "Giant's Deep": "Giant's Deep",
    "Dark bramble": "Dark Bramble",
    "Dark Bramble": "Dark Bramble",
    "The Interloper": "The Interloper",
    "Quantum Moon": "Quantum Moon",
    "The Vessel": "Dark Bramble",
    "White Hole Station": "White Hole",
    "Orbital Probe Cannon": "Giant's Deep",
    "Construction Yard Island": "Giant's Deep",
    "Statue island": "Giant's Deep",
    "Control Module": "Giant's Deep",
    "Launch Module": "Giant's Deep",
    "Probe Tracking Module": "Giant's Deep",
    "Hollow's lantern": "Brittle Hollow",
}


def parse_corpus(path):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    locations = []
    current_body = None
    current_location = None
    current_conversations = []
    current_conv_spirals = []
    current_conv_attrs = {}  # recording, projection_stone
    in_header = True  # skip the key and name table at top

    def flush_conv():
        nonlocal current_conv_spirals, current_conv_attrs
        if current_conv_spirals:
            current_conversations.append({
                **current_conv_attrs,
                "spirals": current_conv_spirals,
            })
        current_conv_spirals = []
        current_conv_attrs = {}

    def flush_location():
        nonlocal current_location, current_conversations
        flush_conv()
        if current_location and current_conversations:
            locations.append({
                "celestial_body": current_body,
                "location": current_location,
                "conversations": current_conversations,
            })
        current_conversations = []

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip("\n")
        stripped = line.strip().replace("\u200b", "")
        i += 1

        # Skip empty lines
        if not stripped:
            continue

        # Skip the header section (key, name table)
        if in_header:
            if stripped == "---" and i > 50:
                in_header = False
            continue

        # Horizontal rule (---) at top level is a section break
        if stripped == "---":
            continue

        # Conversation separator: \- on its own
        if stripped == "\\-":
            flush_conv()
            continue

        # Ellipsis: separates related but distinct wall texts
        if stripped == "..." or stripped == "…":
            flush_conv()
            continue

        # Projection stone link: {A ~ B}
        proj_m = re.match(r"^\{(.+?)\s*~\s*(.+?)\}$", stripped)
        if proj_m:
            flush_conv()
            current_conv_attrs["projection_stone"] = [
                proj_m.group(1).strip(), proj_m.group(2).strip()
            ]
            continue

        # Question combination: {A + B} (Solanum's Quantum Moon dialogue)
        combo_m = re.match(r"^\{(.+?)\s*\+\s*(.+?)\}$", stripped)
        if combo_m:
            flush_conv()
            current_conv_attrs["question_pair"] = [
                combo_m.group(1).strip(), combo_m.group(2).strip()
            ]
            continue

        # Check if this is a location header:
        # A line that doesn't start with a speaker, bullet, or tab,
        # and is title-cased or matches known locations
        is_speaker_line = bool(re.match(
            r"^[-\s]*(?:🎥\s*)?([A-Z][A-Z]+):\s", stripped
        ))
        is_bullet = stripped.startswith("-") and not is_speaker_line
        is_indented = raw.startswith("\t") or raw.startswith("  ")

        if (not is_speaker_line and not is_bullet and not is_indented
                and not stripped.startswith("🎥")
                and len(stripped) < 60
                and not stripped.startswith("(")
                and not stripped.endswith("?")
                and not stripped.endswith(".")
                and not stripped.endswith("!")
                and re.match(r"^[A-Z]", stripped)
                and not re.match(r"^(How |What |The early|Suppose |Did |Is |We |Perhaps|Maybe|It |Enter|Seek|Observ|This is the last|Our |Remember|If the|Be welcomed|Solution|An ellipsis|A dash|Two names|A '|From |Over |These |Should |Not )", stripped)):
            # Looks like a location header
            flush_location()
            loc_name = stripped
            current_location = loc_name
            current_body = CELESTIAL_BODIES.get(loc_name, current_body)
            continue

        # Speaker line: optional bullet/indent + optional 🎥 + SPEAKER: text
        sp_m = re.match(
            r"^([-\s]*)(?:🎥\s*)?([A-Z][A-Z]+):\s+(.+)", stripped
        )
        if sp_m:
            indent_str = sp_m.group(1)
            speaker = sp_m.group(2)
            text = re.sub(r"\s+", " ", sp_m.group(3)).strip()
            is_recording = "🎥" in stripped

            if is_recording and not current_conv_spirals:
                current_conv_attrs["recording"] = True

            # Fix known typo
            if speaker == "IDEAE":
                speaker = "IDAEA"

            # Determine depth: 0 = root, 1 = branch, 2 = sub-branch
            has_bullet = bool(re.match(r"^-\s", indent_str.lstrip()))
            leading = len(indent_str) - len(indent_str.lstrip())
            if has_bullet:
                depth = 1 + (leading > 0)
            else:
                depth = 1 if leading > 0 else 0

            current_conv_spirals.append({
                "speaker": speaker,
                "text": text,
                "depth": depth,
            })
            continue

        # Unsigned text (part of a conversation, no speaker)
        if current_location and (is_indented or current_conv_spirals):
            has_bullet = stripped.startswith("-")
            clean_text = re.sub(r"^-\s*", "", stripped).strip()
            leading = len(raw) - len(raw.lstrip())
            if has_bullet:
                depth = 1 + (leading > 2)
            else:
                depth = 1 if leading > 2 else 0

            current_conv_spirals.append({
                "speaker": "",
                "text": clean_text,
                "depth": depth,
            })
            continue

        # Bare text at root level (unsigned, not indented) — start of conv or continuation
        if current_location:
            current_conv_spirals.append({
                "speaker": "",
                "text": stripped,
                "depth": 0,
            })

    flush_location()
    return locations


# ── Build parent indices from depth ─────────────────────────────────────

def assign_parents(spirals):
    """Convert depth-based nesting to explicit parent indices."""
    stack = []  # (depth, index) — track the current nesting
    for idx, sp in enumerate(spirals):
        d = sp["depth"]
        # Pop stack until we find a parent at a lower depth
        while stack and stack[-1][0] >= d:
            stack.pop()
        if stack:
            sp["parent"] = stack[-1][1]
        else:
            sp["parent"] = None
        stack.append((d, idx))
        del sp["depth"]


# ── Attach Chinese translations ────────────────────────────────────────

def attach_chinese(locations):
    stats = {"mod": 0, "official": 0, "missing": 0}
    for loc in locations:
        for conv in loc["conversations"]:
            for sp in conv["spirals"]:
                en_line = (f"{sp['speaker']}: {sp['text']}"
                           if sp["speaker"] else sp["text"])
                zh, src = find_chinese(en_line)
                if zh:
                    sp["zh"] = zh
                    stats[src] += 1
                else:
                    sp["zh"] = None
                    stats["missing"] += 1
    return stats


# ── Verify against hand tally ──────────────────────────────────────────

def verify_speaker_counts(locations):
    """Count conversations per speaker, compare with document tally."""
    counts = {}  # speaker -> set of (loc_idx, conv_idx)
    for li, loc in enumerate(locations):
        for ci, conv in enumerate(loc["conversations"]):
            speakers_here = set()
            for sp in conv["spirals"]:
                if sp["speaker"]:
                    speakers_here.add(sp["speaker"])
            for s in speakers_here:
                counts.setdefault(s, set()).add((li, ci))

    print("\n── Speaker conversation counts ──")
    for speaker in sorted(counts):
        print(f"  {speaker:12s}: {len(counts[speaker]):3d}")
    return {s: len(v) for s, v in counts.items()}


# ── Main ────────────────────────────────────────────────────────────────

def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    corpus_path = ROOT / "docs" / "nomai_text_corpus.md"
    locations = parse_corpus(corpus_path)

    total_convs = sum(len(loc["conversations"]) for loc in locations)
    total_spirals = sum(
        len(conv["spirals"])
        for loc in locations
        for conv in loc["conversations"]
    )
    print(f"Parsed: {len(locations)} locations, {total_convs} conversations, "
          f"{total_spirals} spirals")

    for loc in locations:
        for conv in loc["conversations"]:
            assign_parents(conv["spirals"])

    zh_stats = attach_chinese(locations)
    print(f"Chinese: {zh_stats['mod']} mod, {zh_stats['official']} official, "
          f"{zh_stats['missing']} missing")

    counts = verify_speaker_counts(locations)

    out_path = ROOT / "docs" / "nomai_corpus.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(locations, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
