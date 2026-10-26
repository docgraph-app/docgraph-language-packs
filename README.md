# DocGraph language packs

Offline word data for **DocGraph Languages** (ADR 0163): one file per
language, downloaded by the app when the user adds that language. German is
the only pack today.

| Pack | Contents | Download |
|---|---|---|
| `dict:de-en` (`de-pack-v<N>.sqlite3.gz`) | 93k nouns (gender, every case form), 14.9k verbs (conjugation, Perfekt auxiliary, separable prefix), 105k German–English senses, a 398k-row form → lemma index | ≈ 20 MB (≈ 56 MB unpacked) |

Packs are published as **GitHub Release assets** (tag `de-pack-v<N>`), never
committed. Each release carries the pack and its manifest (size, sha256,
counts, sources). The app pins tag + sha256.

## Build

```bash
python3 -I de/build.py --version 1
python3 -I de/check.py build/de-pack-v1.sqlite3
```

Standard library only. The build downloads the sources pinned in
`de/sources.json` into `sources/` and refuses any whose sha256 has changed.
`check.py` tests the pack against hand-verified grammar facts (20 verbs,
nouns, inflected forms, senses) and the coverage of `de/check-text.txt`.

## Schema (version 1)

- `meta(key, value)` — pack, version, schema, built, licence, credits, sources.
- `lemmas(id, lemma, pos)` — every noun and verb once.
- `nouns(id, genders)` — `m` / `f` / `n` or several (`m,n`).
- `verbs(id, aux, prefix, weak, pres_ich, pres_du, pres_er, past_ich,
  subj2_ich, imp_sg, imp_pl, part2, present, past)` — `aux` is `haben`,
  `sein` or both with the usual one first; `present`/`past` are JSON lists of
  six forms (ich … sie) when Wiktionary has the full table.
- `forms(form, id, tags, particle)` — single-word form → lemma; `tags` such
  as `nom_pl,dat_pl` or `pres_er`; `particle` holds a separated prefix
  (`ruft` + `an` → `anrufen`).
- `senses(lemma, pos, hom, num, definition, translations, importance)` —
  WikDict senses; `hom` separates homographs (`See` 1 = der, 2 = die).

## Licence

- **Build scripts:** MIT (`LICENSE`).
- **Packs and `de/check-text.txt`:** CC BY-SA 4.0 (`LICENSE-DATA.txt`),
  credits in `NOTICE.md`.

**Anyone redistributing or showing pack data** (including DocGraph) must:
credit the sources as in `NOTICE.md`; name the licence with a link; say the
data was changed; keep adapted data under CC BY-SA 4.0; add no further
terms; and not lock the data behind DRM or encryption (a checksum is fine).
