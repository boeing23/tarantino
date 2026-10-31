# Story Bible

The story bible is the single file that defines one live story: its world, characters, fixed opening, must-hit beats and endings. The engine is genre-agnostic and loads `bible.json` as data, so changing the story means editing this file, not code.

The current `bible.json` is a **placeholder** (`meta.placeholder: true`) so the rest of the pipeline can be built before the genre is chosen.

## Files

| File | Purpose |
|---|---|
| `bible.schema.json` | Shape every bible must follow (JSON Schema 2020-12) |
| `bible.json` | The active story (placeholder for now) |
| `validate.py` | Schema check plus cross-reference checks |

## Validate

```bash
pip install jsonschema
python -I story/validate.py story/bible.json
```

Prints `OK` (with a warning while the placeholder is in use) or one `ERROR` line per problem.

Beyond the schema, the validator checks that ids are unique, opening speakers are real characters (or `narrator`), `can_die_after_beat` points at a real beat, ending moods come from `moods`, ending flags exist in `state_seed.flags`, relationships name real characters, and acts never go backwards.

## What each field feeds

| Field | Used by | Notes |
|---|---|---|
| `meta` | Everything | `beat_seconds` is the chapter length; comments lock `lock_seconds_before_end` before it ends |
| `world` | Beat generator | `tone` and `rules` go into the system prompt |
| `moods` | Aggregation, State, Endings | Closed list: the crowd's mood must map to one of these |
| `style` | Render | `visual_prompt` and `motion` are added to every clip so all clips share one look; `clip_seconds` sets clip length |
| `characters` | State, Beat generator, Render, Guardrails | `voice.description` is repeated in every clip prompt so the voice stays the same (and picks the backup TTS voice); `portrait_prompt` is pre-rendered into a reference image passed to the video model |
| `opening` | Pipelining | `shots` and audio are fully pre-rendered before the show so beat 1 plays instantly |
| `beats` | Beat generator, Guardrails, Render | `must_hit` always happens; the crowd only steers `flexible`; `shots` are anchor shots the live writer adapts and fills out to chapter length |
| `endings` | State, Beat generator, Pipelining | Crowd moods add up across windows; the ending with the highest tally whose `required_flags` are true wins; its `shots` are pre-rendered. Ties go to the ending listed first, so **the first ending is what a silent room gets** |
| `forbidden` | Guardrails | Per act; a generated beat that does one of these is retried or replaced |
| `state_seed` | State | Starting state right after the opening |
| `bridges` | Pipelining | Pre-rendered clips played, in order, whenever the next chapter is late; they open no comment window and must not move the plot |
| `audience_hooks` | Phone page | `seed_suggestions` fill the feed when the room is quiet |

## Shots

Every visual is a `shot`, and the video model generates its picture and sound together.

- `frame`: the first frame, written like a still photo.
- `motion`: one short action plus camera move. Video models handle one clear action per clip far better than a sequence.
- `characters` (optional): who is in frame, so their reference images keep faces consistent.
- `line` (optional): one speaker, 15 words or fewer, spoken on camera by the video model.
- `sound` (optional): ambience and effects.

Write shots in one chapter as distinct camera setups (wide, close-up, insert). They are generated at the same time and cut together, so they should not depend on matching frame to frame.

## Writing the real story

1. Copy `bible.json`, keep the structure, replace the content.
2. Keep it small: 3–4 characters, 4–6 beats, 2–3 endings, one location.
3. Write the `opening` in full. It is the only beat the audience sees without influence, and it sets tone and voice for everything after.
4. Make each `must_hit` a concrete event, not a feeling ("the case is found", not "tension rises").
5. Give every ending at least one mood from `moods`, and make sure the flags it needs can be set by the beats.
6. Use original characters and scenes.
7. Set `meta.placeholder` to `false` and run the validator.

## Change rules

Downstream code reads these fields, so after the team agrees on the shape:

- Add new fields freely.
- Never rename or remove a field or an id.
- Change the schema and `bible.json` in the same commit.
