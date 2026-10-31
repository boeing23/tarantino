"""Validate a story bible against bible.schema.json plus cross-reference checks.

Usage: python -I story/validate.py story/bible.json
Exit code 0 = valid, 1 = errors.
"""

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parent / "bible.schema.json"
MAX_LINE_WORDS = 15


def schema_errors(bible):
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(bible), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in err.path) or "(root)"
        yield f"{where}: {err.message}"


def duplicates(ids):
    seen, dupes = set(), set()
    for i in ids:
        (dupes if i in seen else seen).add(i)
    return dupes


def reference_errors(bible):
    """Checks JSON Schema cannot express: ids that must point at other ids."""
    characters = {c["id"] for c in bible["characters"]}
    beats = [b["id"] for b in bible["beats"]]
    moods = set(bible["moods"])
    flags = set(bible["state_seed"]["flags"])
    speakers = characters | {"narrator"}

    for name, ids in [
        ("characters", [c["id"] for c in bible["characters"]]),
        ("beats", beats),
        ("endings", [e["id"] for e in bible["endings"]]),
        ("clues", [c["id"] for c in bible["state_seed"]["clues"]]),
    ]:
        for d in duplicates(ids):
            yield f"{name}: duplicate id '{d}'"

    if "narrator" in characters:
        yield "characters: 'narrator' is reserved"

    for i, line in enumerate(bible["opening"]["lines"]):
        if line["speaker"] not in speakers:
            yield f"opening/lines/{i}: unknown speaker '{line['speaker']}'"

    shots = [("opening/shots", s) for s in bible["opening"]["shots"]]
    shots += [(f"beats/{b['id']}/shots", s) for b in bible["beats"] for s in b["shots"]]
    shots += [(f"endings/{e['id']}/shots", s) for e in bible["endings"] for s in e["shots"]]
    shots += [(f"bridges/{i}/shot", br["shot"]) for i, br in enumerate(bible["bridges"])]
    for where, shot in shots:
        for cid in shot.get("characters", []):
            if cid not in characters:
                yield f"{where}: unknown character '{cid}'"
        line = shot.get("line")
        if line:
            if line["speaker"] not in speakers:
                yield f"{where}: unknown speaker '{line['speaker']}'"
            if len(line["text"].split()) > MAX_LINE_WORDS:
                yield f"{where}: line over {MAX_LINE_WORDS} words; video models garble long lines"

    meta = bible["meta"]
    if meta["lock_seconds_before_end"] >= meta["beat_seconds"]:
        yield "meta: lock_seconds_before_end must be less than beat_seconds"

    for c in bible["characters"]:
        if c["can_die_after_beat"] is not None and c["can_die_after_beat"] not in beats:
            yield f"characters/{c['id']}: can_die_after_beat '{c['can_die_after_beat']}' is not a beat id"

    if not any(c["role"] == "protagonist" for c in bible["characters"]):
        yield "characters: need one protagonist"

    acts = [b["act"] for b in bible["beats"]]
    if acts != sorted(acts):
        yield "beats: acts must not go backwards"
    for f in bible["forbidden"]:
        if f["act"] not in acts:
            yield f"forbidden: act {f['act']} has no beats"

    for e in bible["endings"]:
        for m in e["trigger_moods"]:
            if m not in moods:
                yield f"endings/{e['id']}: trigger mood '{m}' not in moods"
        for fl in e["required_flags"]:
            if fl not in flags:
                yield f"endings/{e['id']}: required flag '{fl}' not in state_seed.flags"

    seed = bible["state_seed"]
    if seed["mood"] not in moods:
        yield f"state_seed: mood '{seed['mood']}' not in moods"
    for r in seed["relationships"]:
        for side in ("a", "b"):
            if r[side] not in characters:
                yield f"state_seed/relationships: unknown character '{r[side]}'"
        if r["a"] == r["b"]:
            yield f"state_seed/relationships: '{r['a']}' paired with itself"


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    bible = json.loads(Path(argv[1]).read_text())

    errors = list(schema_errors(bible))
    # Cross-reference checks assume the schema shape, so run them only on a schema-valid bible.
    if not errors:
        errors = list(reference_errors(bible))

    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print(f"{len(errors)} error(s)")
        return 1

    if bible["meta"]["placeholder"]:
        print("WARNING meta.placeholder is true: swap in the real story before the demo")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
