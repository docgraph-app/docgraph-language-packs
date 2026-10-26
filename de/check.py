#!/usr/bin/env python3
"""Check a built German pack against hand-verified facts.

    python3 -I de/check.py build/de-pack-v1.sqlite3

Exits non-zero if any check fails. The facts below were checked by hand
against standard German grammar, not taken from the sources.
"""
import json, re, sqlite3, sys

# verb: du present, er present, er Präteritum, Partizip II, usual Perfekt auxiliary
VERBS = {
    "machen": ("machst", "macht", "machte", "gemacht", "haben"),
    "arbeiten": ("arbeitest", "arbeitet", "arbeitete", "gearbeitet", "haben"),
    "reisen": ("reist", "reist", "reiste", "gereist", "sein"),
    "fahren": ("fährst", "fährt", "fuhr", "gefahren", "sein"),
    "sehen": ("siehst", "sieht", "sah", "gesehen", "haben"),
    "nehmen": ("nimmst", "nimmt", "nahm", "genommen", "haben"),
    "sein": ("bist", "ist", "war", "gewesen", "sein"),
    "werden": ("wirst", "wird", "wurde", "geworden", "sein"),
    "wissen": ("weißt", "weiß", "wusste", "gewusst", "haben"),
    "bringen": ("bringst", "bringt", "brachte", "gebracht", "haben"),
    "anrufen": ("rufst an", "ruft an", "rief an", "angerufen", "haben"),
    "aufstehen": ("stehst auf", "steht auf", "stand auf", "aufgestanden", "sein"),
    "verstehen": ("verstehst", "versteht", "verstand", "verstanden", "haben"),
    "studieren": ("studierst", "studiert", "studierte", "studiert", "haben"),
    "schlafen": ("schläfst", "schläft", "schlief", "geschlafen", "haben"),
    "essen": ("isst", "isst", "aß", "gegessen", "haben"),
    "laufen": ("läufst", "läuft", "lief", "gelaufen", "sein"),
    "bleiben": ("bleibst", "bleibt", "blieb", "geblieben", "sein"),
    "einkaufen": ("kaufst ein", "kauft ein", "kaufte ein", "eingekauft", "haben"),
    "treffen": ("triffst", "trifft", "traf", "getroffen", "haben"),
}
WEAK = {"machen": 1, "arbeiten": 1, "reisen": 1, "studieren": 1, "einkaufen": 1, "fahren": 0, "sein": 0, "bringen": 0, "treffen": 0}
NOUNS = {"Haus": ("n", "Häuser"), "Kollege": ("m", "Kollegen"), "Frau": ("f", "Frauen"), "Teil": ("m,n", None),
         "Dorf": ("n", "Dörfer"), "Brötchen": ("n", "Brötchen"), "Straße": ("f", "Straßen")}
FORMS = {"Häusern": "Haus", "Dörfer": "Dorf", "fuhr": "fahren", "war": "sein", "gegangen": "gehen", "liest": "lesen"}
SENSES = {"Schloss": ["lock", "castle"], "Leiter": ["ladder", "leader"], "Eichhörnchen": ["squirrel"], "Gift": ["poison"]}

db = sqlite3.connect(sys.argv[1])
fails = []
def check(ok, msg):
    if not ok:
        fails.append(msg)

for v, (du, er, past, p2, aux) in VERBS.items():
    r = db.execute("SELECT v.pres_du, v.pres_er, v.past_ich, v.part2, v.aux, v.weak, v.present FROM verbs v "
                   "JOIN lemmas l ON l.id = v.id WHERE l.lemma = ?", (v,)).fetchall()
    if not r:
        fails.append(f"verb {v}: missing"); continue
    got = r[0]
    for name, want, have in (("du", du, got[0]), ("er", er, got[1]), ("past", past, got[2]), ("part2", p2, got[3]), ("aux", aux, got[4].split(",")[0])):
        check(have == want, f"verb {v}.{name}: {have!r} != {want!r}")
    if v in WEAK:
        check(got[5] == WEAK[v], f"verb {v}.weak: {got[5]} != {WEAK[v]}")
for n, (g, pl) in NOUNS.items():
    r = db.execute("SELECT n.genders, n.id FROM nouns n JOIN lemmas l ON l.id = n.id WHERE l.lemma = ?", (n,)).fetchall()
    if not r:
        fails.append(f"noun {n}: missing"); continue
    have = {gg for x in r for gg in x[0].split(",")}
    check(set(g.split(",")) <= have, f"noun {n}: genders {sorted(have)} lack {g!r}")
    if pl:
        ok = any(db.execute("SELECT 1 FROM forms WHERE id = ? AND form = ? AND tags LIKE '%nom_pl%'", (x[1], pl)).fetchone() for x in r)
        check(ok, f"noun {n}: plural {pl!r} missing")
for f, lemma in FORMS.items():
    ls = {x[0] for x in db.execute("SELECT l.lemma FROM forms f JOIN lemmas l ON l.id = f.id WHERE f.form = ?", (f,))}
    check(lemma in ls, f"form {f}: lemmas {ls} lack {lemma!r}")
r = db.execute("SELECT particle FROM forms f JOIN lemmas l ON l.id = f.id WHERE f.form = 'ruft' AND l.lemma = 'anrufen'").fetchall()
check(r and r[0][0] == "an", f"separable: ruft→anrufen particle {r}")
for w, wants in SENSES.items():
    t = " | ".join(x[0] for x in db.execute("SELECT translations FROM senses WHERE lemma = ?", (w,)))
    for want in wants:
        check(want in t, f"senses {w}: no {want!r} in {t!r}")
see = {x[0]: x[1] for x in db.execute("SELECT hom, translations FROM senses WHERE lemma = 'See'")}
check("lake" in see.get(1, "") and "sea" in see.get(2, ""), f"senses See homographs: {see}")

# coverage of the sample text: a token counts when it is a known form or lemma
text = open(__file__.replace("check.py", "check-text.txt"), encoding="utf-8").read()
toks = re.findall(r"[A-Za-zÄÖÜäöüßé]+", text)
known = 0
for t in toks:
    q = (t, t.lower(), t[:1].upper() + t[1:])
    if any(db.execute("SELECT 1 FROM forms WHERE form = ? LIMIT 1", (x,)).fetchone()
           or db.execute("SELECT 1 FROM senses WHERE lemma = ? LIMIT 1", (x,)).fetchone() for x in q):
        known += 1
cov = known / len(toks)
print(f"sample-text coverage: {known}/{len(toks)} = {cov:.0%}")
check(cov >= 0.9, f"coverage {cov:.0%} < 90%")
meta = dict(db.execute("SELECT key, value FROM meta"))
check(meta.get("licence") == "CC BY-SA 4.0" and "Wiktionary" in meta.get("credits", ""), "meta: licence/credits missing")

checks = len(VERBS) * 5 + len(WEAK) + len(NOUNS) * 2 + len(FORMS) + 1 + sum(map(len, SENSES.values())) + 3
print(f"{checks - len(fails)}/{checks} checks passed")
for f in fails:
    print("FAIL", f)
sys.exit(1 if fails else 0)
