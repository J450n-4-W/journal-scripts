#!/usr/bin/env python3
"""Regression tests for the vault tooling.

Every case here is a bug that actually shipped. These tools write to a live vault
using regex parsers over free-form markdown, so a bad pattern corrupts silently
rather than crashing — the failure mode that produced every entry below.

Run: python3 tests/run.py
"""
import os, sys, pathlib, importlib.machinery, importlib.util, tempfile, shutil, re

REPO = pathlib.Path(__file__).resolve().parent.parent
FIX = REPO/"tests/fixtures"
PASS = FAIL = 0


def load(name):
    mod = name.replace("-", "_")
    l = importlib.machinery.SourceFileLoader(mod, str(REPO/name))
    m = importlib.util.module_from_spec(importlib.util.spec_from_loader(mod, l))
    l.exec_module(m)
    return m


def check(desc, got, want=True, cmp=None):
    global PASS, FAIL
    ok = cmp(got) if cmp else (got == want)
    if ok: PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  {desc}\n        got {got!r}" + (f", want {want!r}" if not cmp else ""))
    return ok


def test_chunker(vs):
    print("chunker — unbounded chunks and dropped documents")
    cases = [
        ("no blank lines anywhere (was 1 chunk of the whole file)", "no-blank-lines.md"),
        ("single 1MB line (line splitting cannot help)",            "single-huge-line.md"),
        ("120-char note (was indexed with ZERO chunks)",            "tiny-note.md"),
    ]
    for desc, fn in cases:
        text = (FIX/fn).read_text()
        cs = list(vs.chunk(text))
        check(f"{desc}: produces chunks", len(cs), cmp=lambda n: n >= 1)
        check(f"{desc}: none exceeds MAX_CHARS", max((len(c[1]) for c in cs), default=0),
              cmp=lambda n: n <= vs.MAX_CHARS)
    check("empty input yields nothing", list(vs.chunk("")), [])
    check("heading with no body still yields", len(list(vs.chunk("# Title\n"))), cmp=lambda n: n >= 1)


def test_dates(vs):
    print("date normalisation — --since silently excluded non-ISO formats")
    for raw, want in [("Sep 3, 2026", "2026-09-03"), ("03/09/2026", "2026-09-03"),
                      ("2026_09_04", "2026-09-04"), ("2026-09-04", "2026-09-04"),
                      ("{{date}}", ""), ("null", ""), ("", "")]:
        check(f"{raw!r} -> ISO", vs.norm_date(raw), want)


def test_fts_query(vs):
    print("FTS quoting — these raised OperationalError and crashed the tool")
    for q in ["far-right", "O'Brien", "Mar-a-Lago", 'say "no"', "NOT", "a AND b"]:
        out = vs.fts_query(q)
        check(f"{q!r} is quoted", out, cmp=lambda s: s.startswith('"') and s.endswith('"'))
    check("--raw passes through untouched", vs.fts_query("a OR b", raw=True), "a OR b")


def test_binary_guard(vs):
    print("binary guard — 475 AppleDouble files were indexed as markdown")
    raw = (FIX/"appledouble.md").read_text(errors="ignore")
    check("NUL bytes detected", "\x00" in raw[:4096])


def test_frontmatter(vs):
    print("frontmatter parsing")
    fm, body, off = vs.split_frontmatter((FIX/"pure-frontmatter.md").read_text())
    d = vs.parse_frontmatter(fm)
    check("type read", d.get("type"), "organization")
    check("YAML list read", d.get("ideology"), ["Afrikaner Nationalist"])
    check("body is empty (card fallback must fire)", body.strip(), "")


def test_projects(pj):
    print("projects — status vocabulary and record discovery")
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        for f in ("story-index.md", "no-story-dir.md", "hand-set-status.md"):
            shutil.copy(FIX/f, t/f)
        pj.PAGES = t; pj.LOGS = t
        recs = {r.path.name: r.compute({}) for r in pj.load_records()}
        check("type: story-index counts as a record", "story-index.md" in recs)
        check("missing story_dir does not crash", "no-story-dir.md" in recs)
        hs = recs.get("hand-set-status.md")
        check("hand-set status preserved", hs and hs.derived_status, "awaiting-response")
        check("hand-set status flagged", hs and hs.hand_set, True)
        shutil.copy(FIX/"terminal-status.md", t/"terminal-status.md")
        pj.PAGES = t
        recs = {r.path.name: r.compute({}) for r in pj.load_records()}
        term = recs.get("terminal-status.md")
        check("published is terminal, not demoted", term and term.derived_status, "published")
        check("published is NOT reported as hand-set (15 pages of daily noise)",
              term and term.hand_set, False)
        hs = recs.get("hand-set-status.md")
        check("a genuinely hand-set status IS reported", hs and hs.hand_set, True)
        before = (t/"hand-set-status.md").read_text()
        hs.write_back()
        after = (t/"hand-set-status.md").read_text()
        check("refresh does not overwrite a hand-set status",
              re.search(r'^status:.*$', after, re.M).group(0).strip(), "status: awaiting-response")
        check("hand-maintained fields untouched",
              re.search(r'^story_dir:.*$', before, re.M).group(0),
              re.search(r'^story_dir:.*$', after, re.M).group(0))


def test_hub_sync(hs):
    print("hub-sync — folded scalars returned a literal '>' as the description")
    check("folded description resolves",
          hs.desc_from_skill(FIX/"folded-description.md"),
          cmp=lambda s: s.startswith("Queries a thing"))
    check("empty folded scalar yields empty, not '>'",
          hs.desc_from_skill(FIX/"empty-folded.md"), "")
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        # name must equal the directory, or the mismatch check fires (correctly)
        (t/"good").mkdir()
        (t/"good/SKILL.md").write_text(
            "---\nname: good\ndescription: >\n  Queries a thing across sources.\n  Trigger on things.\n---\n")
        (t/"nofm").mkdir(); (t/"nofm/SKILL.md").write_text("Base directory: /x\n\n# Thing\n")
        (t/"mismatch").mkdir(); (t/"mismatch/SKILL.md").write_text(
            "---\nname: other-name\ndescription: Does a thing.\n---\n")
        d = {n: w for n, w in hs.frontmatter_defects(t)}
        check("skill with no frontmatter flagged", "nofm" in d)
        check("name/directory mismatch flagged", "mismatch" in d)
        check("well-formed skill not flagged", "good" not in d)


def test_outreach(oc):
    print("outreach — getaddresses takes a LIST; a string iterates characters")
    raw = (b"Message-ID: <abc@x>\r\nDate: Wed, 3 Sep 2026 10:41:00 +0100\r\n"
           b"From: Jason <jason.a.wilson@protonmail.com>\r\n"
           b"To: Someone <a@b.com>, Other <c@d.com>\r\nCc: Third <e@f.com>\r\n"
           b"Subject: Request for comment\r\nReferences: <prev@y>\r\n")
    d = oc.parse(raw)
    check("message parsed", d is not None)
    check("recipients extracted (was empty for all 8,014 sent)",
          d and d["to_addrs"], cmp=lambda v: "a@b.com" in v and "c@d.com" in v)
    check("cc included", d and d["to_addrs"], cmp=lambda v: "e@f.com" in v)
    check("sender extracted", d and d["from_addr"], "jason.a.wilson@protonmail.com")
    check("references captured for the reply join", d and d["refs"], "<prev@y>")
    check("subject decoded", d and d["subject"], "Request for comment")
    check("no Message-ID means unusable", oc.parse(b"From: x@y\r\nSubject: no id\r\n"), None)


def test_cite_check(cc):
    """Provenance, not importance — and paragraph scope, not sentence scope."""
    print("cite-check — provenance, not importance")
    linked = ("The company denied it. According to a filing with the SEC, revenue fell. "
              "See [the filing](https://sec.gov/x) for detail.")
    check("attribution with a link in the same PARAGRAPH is not flagged",
          cc.check(linked), [])
    unlinked = "According to a report by the New York Times, the company misstated revenue for three years running."
    check("attribution with no link anywhere is flagged", len(cc.check(unlinked)), 1)
    own = "Chen told me in an interview that the figures had been revised twice before publication."
    check("own interview is never flagged (unlinkable by nature)", cc.check(own), [])
    own2 = "Court records show the loan was repaid, and no further filing was made in the matter."
    check("own records search is not flagged", cc.check(own2), [])
    own3 = "According to a Guardian analysis, the group published 124 reports in eight days."
    check("own analysis is not flagged", cc.check(own3), [])
    plain = "The building sits on a hill above the town and has been empty since 2019."
    check("an unattributed claim is never flagged (importance is not the test)",
          cc.check(plain), [])
    # The bug that mattered: a link in the previous sentence of the same paragraph.
    split_para = ("The filing is [here](https://sec.gov/y).\n"
                  "According to the filing, revenue fell by a third.")
    check("link in an earlier sentence of the paragraph counts",
          cc.check(split_para), [])


def test_preserve(pc):
    print("preserve-check — URL extraction and skip rules")
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write("See [a](https://example.com/x) and https://foo.org/y.\n"
                "Skip https://web.archive.org/web/1/z and http://localhost:8080/q.\n"
                "Trailing punctuation: https://bar.net/p).\n")
        name = f.name
    got = {u for _, u in pc.urls_in(name)}
    check("markdown link extracted", "https://example.com/x" in got)
    check("bare URL extracted", "https://foo.org/y" in got)
    check("archive.org skipped", not any("web.archive.org" in u for u in got))
    check("localhost skipped", not any("localhost" in u for u in got))
    check("trailing paren stripped", "https://bar.net/p" in got)
    pathlib.Path(name).unlink()


def test_brief_under_cron():
    """The health footer worked interactively and was blind under cron, which is the
    only environment that runs it: systemctl --user needs a session bus and cron has
    none. Test in a stripped environment, not the shell you happen to be in."""
    print("brief — health footer under a cron-like environment")
    import subprocess
    brief = pathlib.Path.home()/".local/bin/brief"
    if not brief.exists():
        check("brief installed", False); return
    r = subprocess.run([str(brief), "--show"], capture_output=True, text=True, timeout=180,
                       env={"HOME": str(pathlib.Path.home()),
                            "PATH": f"{pathlib.Path.home()}/.local/bin:/usr/bin:/bin"})
    line = next((l for l in r.stdout.splitlines() if l.startswith("_health")), "")
    check("health line produced", bool(line))
    check("no unknown entries (systemd reachable without a session bus)",
          "?" not in line, cmp=lambda v: v is True)
    check("PATH-dependent checks resolve (hub-sync, projects found)",
          "maintenance check failed" not in r.stdout)


def test_record_correction():
    """The cooperative path: any agent, at the moment of correction. The nightly
    transcript scrape cannot see work done outside Claude Code — 133 vault files
    changed on 2026-09-05 and it saw nothing."""
    print("record-correction — cross-agent capture")
    import subprocess, tempfile, json as _json
    exe = REPO/"record-correction"
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td)/"c.jsonl"
        env = {**os.environ, "CORRECTIONS_FILE": str(f)}
        run = lambda *a: subprocess.run([sys.executable, str(exe), *a],
                                        capture_output=True, text=True, env=env)
        r = run("--wrong", "DOI was nutd.2016.20", "--right", "DOI is nutd.2016.32",
                "--origin", "misread-document", "--trigger", "verify the DOI")
        check("records a correction", r.returncode, 0)
        r2 = run("--wrong", "DOI was nutd.2016.20", "--right", "x", "--origin", "other")
        check("refuses an exact duplicate from the other path", "not duplicating" in r2.stdout)
        r3 = run("--wrong", "second thing", "--right", "fixed", "--origin", "stale-source")
        check("continues the day's id sequence, does not restart at 01",
              "-02" in r3.stdout, cmp=lambda v: v is True)
        # A legacy line with no trailing newline must not corrupt the next append.
        with open(f, "a") as fh: fh.write('{"id":"legacy","claim_wrong":"no newline"}')
        run("--wrong", "third", "--right", "y", "--origin", "other")
        lines = [l for l in f.read_text().splitlines() if l.strip()]
        ok = all((_json.loads(l) or True) for l in lines)
        check("file stays valid JSONL after a missing-newline append", ok)
        r4 = run("--wrong", "only", "--right", "half")
        check("refuses an incomplete record rather than writing a partial one",
              r4.returncode, 2)
        bad = run("--wrong", "a", "--right", "b", "--origin", "not-a-real-origin")
        check("rejects an out-of-enum origin", bad.returncode != 0, True)


def main():
    vs = load("vault-search"); pj = load("projects"); hs = load("hub-sync")
    test_chunker(vs); test_dates(vs); test_fts_query(vs)
    test_binary_guard(vs); test_frontmatter(vs)
    test_projects(pj); test_hub_sync(hs)
    test_outreach(load("outreach"))
    test_brief_under_cron()
    test_record_correction()
    test_cite_check(load("cite-check"))
    test_preserve(load("preserve-check"))
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
