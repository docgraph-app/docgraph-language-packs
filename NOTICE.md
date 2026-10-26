# Credits and licence notice

The DocGraph language packs are **adapted material** under the Creative
Commons Attribution-ShareAlike 4.0 International licence (CC BY-SA 4.0).
Full licence text: `LICENSE-DATA.txt`, or
https://creativecommons.org/licenses/by-sa/4.0/legalcode.

**Changes made:** the sources below were filtered (German entries only),
trimmed (selected fields), merged and restructured into one SQLite file by
the build script in this repository (`de/build.py`). No entry text was
rewritten.

**No warranties.** The packs are provided as-is, without warranties of any
kind, as stated in section 5 of the licence. The licensors below do not
endorse DocGraph or any use of the packs.

## German pack (`dict:de-en`)

| Part | Source | Creators | Licence |
|---|---|---|---|
| All three parts | German Wiktionary, https://de.wiktionary.org | Wiktionary contributors (the history of each entry lists them) | CC BY-SA 4.0 (and GFDL) |
| Nouns: gender, case forms | `german-nouns`, https://github.com/gambolputty/german-nouns (commit `da71a2b`) | gambolputty | CC BY-SA 4.0 |
| Meanings: senses, German definitions, English translations | WikDict, https://www.wikdict.com, built on DBnary, https://kaiko.getalp.org/about-dbnary/ | Karl Bartel (WikDict); Gilles Sérasset (DBnary) | CC BY-SA (DBnary: CC BY-SA 3.0, adapted here under 4.0 as section 4(b) of 3.0 allows) |
| Verbs: conjugation, auxiliary, separable prefix | wiktextract data from kaikki.org, https://kaikki.org/dewiktionary/ | Tatu Ylonen (wiktextract) | CC BY-SA 4.0 (and GFDL) |

Exact source files, revisions and sha256 sums are in `de/sources.json` and in
each pack's `meta` table (`sources`) and manifest. Wiktextract: Tatu Ylonen,
"Wiktextract: Wiktionary as Machine-Readable Structured Data", LREC 2022,
pp. 1317–1325.
