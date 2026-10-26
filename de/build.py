#!/usr/bin/env python3
"""Build the German pack (dict:de-en) for DocGraph Languages.

    python3 -I de/build.py --version 1 [--sources DIR] [--out DIR]

Downloads the pinned sources in de/sources.json (or reuses them from
--sources), refuses any whose sha256 differs, and writes
de-pack-v<N>.sqlite3.gz plus de-pack-v<N>.manifest.json to --out.
Standard library only.
"""
import argparse, csv, datetime, gzip, hashlib, json, os, re, shutil, sqlite3, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PRONOUNS = {"ich", "du", "er/sie/es", "wir", "ihr", "sie"}
PERSONS = [("first-person", "singular"), ("second-person", "singular"), ("third-person", "singular"),
           ("first-person", "plural"), ("second-person", "plural"), ("third-person", "plural")]
CASES = ["nominativ", "genitiv", "dativ", "akkusativ"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(sources, src_dir):
    os.makedirs(src_dir, exist_ok=True)
    for key, s in sources.items():
        path = os.path.join(src_dir, s["file"])
        if not os.path.exists(path):
            print(f"downloading {key}: {s['url']}", file=sys.stderr)
            with urllib.request.urlopen(s["url"]) as r, open(path + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
            os.replace(path + ".part", path)
        got = sha256(path)
        if got != s["sha256"]:
            sys.exit(f"{key}: sha256 {got} does not match the pin {s['sha256']} — update de/sources.json on purpose")
        s["path"] = path


def schema(db):
    db.executescript("""
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    -- Every noun and verb once; forms, nouns and verbs point here by id.
    CREATE TABLE lemmas (id INTEGER PRIMARY KEY, lemma TEXT NOT NULL, pos TEXT NOT NULL);
    -- One row per noun. genders: 'm', 'f', 'n' or several ('m,n'). Its case
    -- forms are the forms rows with this lemma id (tags nom_sg … akk_pl).
    CREATE TABLE nouns (id INTEGER PRIMARY KEY REFERENCES lemmas(id), genders TEXT NOT NULL);
    -- One row per distinct sense (WikDict): senses of one homograph with the same
    -- English translations are merged, their German definitions joined with ' | '.
    -- hom: homograph number (See 1 = lake, See 2 = sea).
    CREATE TABLE senses (lemma TEXT NOT NULL, pos TEXT NOT NULL, hom INTEGER NOT NULL, num TEXT,
                         definition TEXT, translations TEXT NOT NULL, importance REAL);
    -- Gender and plural of each noun homograph (See 1 = m 'Seen', See 2 = f 'Seen';
    -- Bank 1 = f 'Bänke', Bank 2 = f 'Banken'), matched to German Wiktionary by
    -- definition text; a lone homograph with no match takes the noun data's gender
    -- when that is unambiguous. Missing otherwise.
    CREATE TABLE homographs (lemma TEXT NOT NULL, hom INTEGER NOT NULL, genders TEXT NOT NULL, plural TEXT,
                             PRIMARY KEY (lemma, hom));
    -- One row per adjective: comparative and superlative ('besser', 'am besten').
    -- Its declined forms are forms rows (tags 'pos', 'comp', 'sup').
    CREATE TABLE adjectives (id INTEGER PRIMARY KEY REFERENCES lemmas(id), comparative TEXT, superlative TEXT);
    -- One row per verb. aux: 'haben', 'sein', or both with the usual one
    -- first ('sein,haben' for fahren), in Wiktionary's order. prefix: separable
    -- particle ('an' for anrufen) or ''. weak: 1 = regular (-te, ge-…-t), 0 = strong or mixed.
    -- present/past: JSON list of 6 forms ich, du, er, wir, ihr, sie (separable
    -- particle included, 'rufe an'); null when Wiktionary has no full table.
    CREATE TABLE verbs (id INTEGER PRIMARY KEY REFERENCES lemmas(id), aux TEXT NOT NULL, prefix TEXT NOT NULL, weak INTEGER NOT NULL,
                        pres_ich TEXT, pres_du TEXT, pres_er TEXT, past_ich TEXT, subj2_ich TEXT,
                        imp_sg TEXT, imp_pl TEXT, part2 TEXT, present TEXT, past TEXT);
    -- Every single-word form -> its lemma, one row per (form, lemma). tags:
    -- comma-separated, e.g. 'nom_sg,dat_sg,akk_sg', 'pres_er,pres_ihr', 'part2'.
    -- A separated particle is stored in particle ('ruft' + 'an').
    CREATE TABLE forms (form TEXT NOT NULL, id INTEGER NOT NULL REFERENCES lemmas(id), tags TEXT NOT NULL,
                        particle TEXT NOT NULL DEFAULT '');
    """)


def build_nouns(db, path):
    n = 0
    with open(path, newline="", encoding="utf-8") as f:
        rows = csv.reader(f)
        cols = next(rows)
        gcols = [i for i, c in enumerate(cols) if c.startswith("genus")]
        cells = {}
        for case in CASES:
            for num, short in (("singular", "sg"), ("plural", "pl")):
                cells[f"{case[:3] if case != 'akkusativ' else 'akk'}_{short}"] = [
                    i for i, c in enumerate(cols) if c.startswith(f"{case} {num}")]
        for r in rows:
            if len(r) < 2 or "Substantiv" not in r[1]:
                continue
            genders = sorted({r[i] for i in gcols if i < len(r) and r[i] in ("m", "f", "n")}, key="mfn".index)
            if not genders:
                continue
            forms = {}
            for tag, idx in cells.items():
                vals = []
                for i in idx:
                    v = r[i].strip() if i < len(r) else ""
                    if v and v not in vals:
                        vals.append(v)
                if vals:
                    forms[tag] = vals
            lid = db.execute("INSERT INTO lemmas (lemma, pos) VALUES (?, 'noun')", (r[0],)).lastrowid
            db.execute("INSERT INTO nouns VALUES (?,?)", (lid, ",".join(genders)))
            by_form = {}
            for tag, vals in forms.items():
                for v in vals:
                    if " " not in v and tag not in by_form.setdefault(v, []):
                        by_form[v].append(tag)
            db.executemany("INSERT INTO forms VALUES (?,?,?, '')", [(v, lid, ",".join(t)) for v, t in by_form.items()])
            n += 1
    return n


def norm(text):
    """A definition without its leading labels ('Geografie: …'), lowercased, for matching."""
    text = re.sub(r"^(?:[^:]{1,60}:\s*)+", "", text or "")
    return re.sub(r"\W+", " ", text).strip().lower()


def build_senses(db, path, noun_entries):
    src = sqlite3.connect(path)
    groups = {}
    for lexentry, num, sense, trans, imp in src.execute(
            "SELECT lexentry, sense_num, sense, trans_list, importance FROM translation "
            "WHERE lexentry IS NOT NULL ORDER BY lexentry, sense_num"):
        parts = lexentry.split("/", 1)[1].split("__")
        lemma, pos = parts[0], parts[1]
        hom = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        g = groups.setdefault((lemma, pos, hom, trans), [num, [], imp])
        if sense and sense not in g[1]:
            g[1].append(sense)
        g[2] = max(g[2] or 0, imp or 0)
    rows = 0
    for (lemma, pos, hom, trans), (num, defs, imp) in groups.items():
        db.execute("INSERT INTO senses VALUES (?,?,?,?,?,?,?)", (lemma, pos, hom, num, " | ".join(defs), trans, imp))
        rows += 1
    raw = src.execute("SELECT count(*) FROM translation WHERE lexentry IS NOT NULL").fetchone()[0]
    # link each noun homograph to the Wiktionary entry whose glosses match its definitions
    linked = unmatched = 0
    homs = {}
    for (lemma, pos, hom, _), (_, defs, _) in groups.items():
        if pos == "Substantiv":
            homs.setdefault(lemma, {}).setdefault(hom, set()).update(norm(d)[:40] for d in defs if norm(d))
    for lemma, by_hom in homs.items():
        entries = noun_entries.get(lemma, [])
        for hom, defs in sorted(by_hom.items()):
            best, score = None, 0
            for genders, plural, glosses in entries:
                sc = sum(1 for d in defs if any(d in gl or gl[:40] in d for gl in glosses))
                if sc > score:
                    best, score = (genders, plural), sc
            if best is None and len(by_hom) == 1 and len({e[0] for e in entries}) == 1:
                best = entries[0][:2]  # one homograph, one gender: nothing to tell apart
            if best is None and len(by_hom) == 1:
                # no Wiktionary entry matched: the noun data decides when it knows one gender
                known = db.execute("SELECT DISTINCT n.genders, n.id FROM lemmas l JOIN nouns n ON n.id = l.id "
                                   "WHERE l.lemma = ? AND l.pos = 'noun'", (lemma,)).fetchall()
                if len({k[0] for k in known}) == 1:
                    pl = db.execute("SELECT form FROM forms WHERE id = ? AND tags LIKE '%nom_pl%'", (known[0][1],)).fetchone()
                    best = (known[0][0], pl[0] if pl else None)
            if best:
                db.execute("INSERT INTO homographs VALUES (?,?,?,?)", (lemma, hom, best[0], best[1]))
                linked += 1
            else:
                unmatched += 1
    return {"senses": rows, "senses_merged": raw - rows, "homographs": linked, "homographs_unmatched": unmatched}


def strip_pronoun(form):
    w = form.split(" ", 1)
    return w[1] if len(w) == 2 and w[0] in PRONOUNS else form


def is_weak(lemma, prefix, past_ich, part2):
    base = lemma[len(prefix):] if prefix and lemma.startswith(prefix) else lemma
    stem = base[:-2] if base.endswith("en") else base[:-1] if base.endswith("n") else base
    past = (past_ich or "").split(" ")[0]
    return int(past in (stem + "te", stem + "ete") and (part2 or "").endswith("t"))


GENDER = {"masculine": "m", "feminine": "f", "neuter": "n"}
DEGREE = {"positive": "pos", "comparative": "comp", "superlative": "sup"}


def add_adjective(db, e):
    if any(s.get("form_of") for s in e.get("senses", [])):
        return False
    summary = {tuple(x.get("tags") or []): x["form"] for x in e.get("forms", []) if "source" not in x}
    if ("positive",) not in summary:
        return False
    lid = db.execute("INSERT INTO lemmas (lemma, pos) VALUES (?, 'adj')", (e["word"],)).lastrowid
    db.execute("INSERT INTO adjectives VALUES (?,?,?)", (lid, summary.get(("comparative",)), summary.get(("superlative",))))
    by_form = {e["word"]: ["pos"]}
    for x in e.get("forms", []):
        t = x.get("tags") or []
        deg = next((DEGREE[d] for d in DEGREE if d in t), None)
        w = x["form"].removeprefix("am ")
        if deg and " " not in w and deg not in by_form.setdefault(w, []):
            by_form[w].append(deg)
    db.executemany("INSERT INTO forms VALUES (?,?,?, '')", [(w, lid, ",".join(t)) for w, t in by_form.items() if t])
    return True


def noun_entry(e):
    """(genders, nominative plural, normalised glosses) of a Wiktionary noun entry."""
    if any(s.get("form_of") for s in e.get("senses", [])):
        return None
    genders = ",".join(dict.fromkeys(GENDER[t] for t in e.get("tags") or [] if t in GENDER))
    if not genders:
        return None
    plural = next((x["form"] for x in e.get("forms", []) if "source" not in x
                   and (x.get("tags") or []) == ["nominative", "plural"]), None)
    if plural:
        plural = plural.removeprefix("die ")
    glosses = [norm(g) for s in e.get("senses", []) for g in s.get("glosses", []) if norm(g)]
    return genders, plural, glosses


def build_wiktionary(db, path):
    n = adjectives = 0
    noun_entries = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if '"lang_code": "de"' not in line:
                continue
            e = json.loads(line)
            if e.get("lang_code") != "de":
                continue
            if e.get("pos") == "adj":
                adjectives += add_adjective(db, e)
                continue
            if e.get("pos") in ("noun", "name"):
                ne = noun_entry(e)
                if ne:
                    noun_entries.setdefault(e["word"], []).append(ne)
                continue
            if e.get("pos") != "verb":
                continue
            summary = [x for x in e.get("forms", []) if "source" not in x]
            def first(*tags, pron=None):
                for x in summary:
                    t = x.get("tags") or []
                    if all(tg in t for tg in tags) and (pron is None or pron in (x.get("pronouns") or [])):
                        return x["form"]
                return None
            part2 = first("participle-2")
            if not part2:
                continue  # an inflected-form page, not a verb entry
            aux = [x["form"] for x in summary if (x.get("tags") or []) == ["auxiliary", "perfect"]]
            aux = ",".join(dict.fromkeys(a for a in aux if a in ("haben", "sein"))) or "haben"
            lemma = e["word"]
            pres_ich, pres_du, pres_er = first("present", pron="ich"), first("present", pron="du"), first("present", pron="er")
            past_ich, subj2 = first("past", pron="ich"), first("subjunctive-ii", pron="ich")
            imp_sg, imp_pl = first("imperative", "singular"), first("imperative", "plural")
            prefix = ""
            if pres_ich and " " in pres_ich:
                p = pres_ich.rsplit(" ", 1)[1]
                if lemma.startswith(p):
                    prefix = p
            table = {}
            for x in e.get("forms", []):
                t = x.get("tags") or []
                if not x.get("source") or "indicative" not in t or "active" not in t or "perfect" in t or "auxiliary verb" in t:
                    continue
                for tense in ("present", "past"):
                    if tense in t and "future" not in t:
                        for i, (p, num) in enumerate(PERSONS):
                            if p in t and num in t:
                                table.setdefault(tense, [None] * 6)
                                if table[tense][i] is None:
                                    table[tense][i] = strip_pronoun(x["form"])
            present = table.get("present") if table.get("present") and None not in table["present"] else None
            past = table.get("past") if table.get("past") and None not in table["past"] else None
            lid = db.execute("INSERT INTO lemmas (lemma, pos) VALUES (?, 'verb')", (lemma,)).lastrowid
            db.execute("INSERT INTO verbs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                lid, aux, prefix, is_weak(lemma, prefix, past_ich, part2), pres_ich, pres_du, pres_er,
                past_ich, subj2, imp_sg, imp_pl, part2,
                json.dumps(present, ensure_ascii=False) if present else None,
                json.dumps(past, ensure_ascii=False) if past else None))
            idx = [(lemma, "inf"), (part2, "part2"), (pres_ich, "pres_ich"), (pres_du, "pres_du"),
                   (pres_er, "pres_er"), (past_ich, "past"), (subj2, "subj2")]
            for i, v in enumerate(present or []):
                idx.append((v, ["pres_ich", "pres_du", "pres_er", "pres_wir", "pres_ihr", "pres_sie"][i]))
            for i, v in enumerate(past or []):
                idx.append((v, ["past_ich", "past_du", "past_er", "past_wir", "past_ihr", "past_sie"][i]))
            by_form = {}
            for v, tag in idx:
                if not v:
                    continue
                word, particle = v, ""
                if prefix and v.endswith(" " + prefix):
                    word, particle = v[: -len(prefix) - 1], prefix
                if " " in word:
                    continue
                tags = by_form.setdefault((word, particle), [])
                if tag not in tags:
                    tags.append(tag)
            db.executemany("INSERT INTO forms VALUES (?,?,?,?)",
                           [(w, lid, ",".join(t), p) for (w, p), t in by_form.items()])
            n += 1
    return {"verbs": n, "adjectives": adjectives}, noun_entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, type=int)
    ap.add_argument("--sources", default=os.path.join(HERE, "..", "sources"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "build"))
    a = ap.parse_args()
    sources = json.load(open(os.path.join(HERE, "sources.json")))
    fetch(sources, a.sources)
    os.makedirs(a.out, exist_ok=True)
    name = f"de-pack-v{a.version}"
    db_path = os.path.join(a.out, name + ".sqlite3")
    if os.path.exists(db_path):
        os.remove(db_path)
    db = sqlite3.connect(db_path)
    schema(db)
    counts = {"nouns": build_nouns(db, sources["nouns"]["path"])}
    wk, noun_entries = build_wiktionary(db, sources["verbs"]["path"])
    counts.update(wk)
    counts.update(build_senses(db, sources["senses"]["path"], noun_entries))
    counts["forms"] = db.execute("SELECT count(*) FROM forms").fetchone()[0]
    db.executescript("""
    CREATE INDEX forms_form ON forms(form);
    CREATE INDEX forms_id ON forms(id);
    CREATE INDEX lemmas_lemma ON lemmas(lemma);
    CREATE INDEX senses_lemma ON senses(lemma);
    """)
    built = datetime.date.today().isoformat()
    meta = {"pack": "dict:de-en", "version": str(a.version), "schema": "2", "built": built,
            "licence": "CC BY-SA 4.0", "licence_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "changes": "Filtered, trimmed, merged and restructured from the sources; no entry text rewritten.",
            "credits": open(os.path.join(HERE, "..", "NOTICE.md"), encoding="utf-8").read(),
            "sources": json.dumps({k: {kk: v[kk] for kk in ("url", "sha256", "origin", "licence")} for k, v in sources.items()})}
    db.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    db.commit()
    db.execute("VACUUM")
    db.close()
    gz_path = db_path + ".gz"
    with open(db_path, "rb") as fi, gzip.GzipFile(gz_path, "wb", compresslevel=9, mtime=0) as fo:
        shutil.copyfileobj(fi, fo)
    manifest = {"pack": "dict:de-en", "version": a.version, "schema": 2, "built": built,
                "file": os.path.basename(gz_path), "size": os.path.getsize(gz_path), "sha256": sha256(gz_path),
                "sqlite_size": os.path.getsize(db_path), "sqlite_sha256": sha256(db_path),
                "counts": counts, "licence": "CC BY-SA 4.0",
                "sources": {k: {kk: v[kk] for kk in ("url", "sha256", "origin", "licence")} for k, v in sources.items()}}
    with open(os.path.join(a.out, name + ".manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps({k: manifest[k] for k in ("file", "size", "sqlite_size", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
