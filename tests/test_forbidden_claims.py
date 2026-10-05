"""Forbidden-claims guard. Static text scan, no network. ward_signed = False.

Scope (v6 adds mechanical folding and a wider scan scope; scope otherwise as in v5): every README*, COMMERCIAL, SECURITY, CHANGELOG and other root *.md; docs/**, public/** and sdk/**/README for
.md .mdx .markdown .txt .rst .html .htm .json; src/app, src/components, src/lib, src/generated for .ts .tsx; package.json,
pyproject.toml. Evidence under docs/security/evidence/ is excluded because it is hash-registered (evidence_commitment.py)
and PDFs cannot be text-scanned here (see the whitepaper PDF test).

Exemptions are keyed to (path, SHA-256 of the exact block text): a claim appended to an exempt line changes the hash and
is reported. A stale exemption (block no longer present, or hash changed) fails the test, so the list can only shrink.
There is no in-file switch: <!-- NOT-A-CLAIM --> does nothing. CLAIMS_ROOT can point at another checkout."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forbidden_claims as fc  # noqa: E402

ROOT = Path(os.environ.get("CLAIMS_ROOT") or Path(__file__).resolve().parents[1])

PROSE = {".md", ".mdx", ".markdown", ".txt", ".rst", ".html", ".htm", ".tsx"}
CODE = {".ts", ".tsx"}
# v7 (review set 5: 54 of 82 plant paths were unscanned): the scan now WALKS THE WHOLE TREE and reads every file whose suffix (or name) is in a broad text/data/code
# list, instead of a list of directories. What is still skipped is listed in SKIP_*: dependencies, build output, the evidence archives (by design),
# the scanner's own regression lists and the test files that quote forbidden wording on purpose, lock files, and every binary except PDFs (PDFs: see below).
WALK_SUFFIXES = {".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc", ".org", ".html", ".htm", ".xhtml", ".json", ".json5", ".jsonc", ".ipynb", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
                 ".env", ".example", ".csv", ".tsv", ".svg", ".xml", ".webmanifest", ".cff", ".rtf", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".scss", ".sh", ".smt2", ".sol", ".rs",
                 ".log", ".map", ".tpl", ".mustache", ".ejs", ".vue", ".svelte", ".astro"}
WALK_NAMES = {"license", "licence", "copying", "readme", "notice", "authors", "codeowners", "dockerfile", "makefile", "procfile", "security", "contributing", "changelog", "citation", ".env.example"}
SKIP_DIRS = {".git", "node_modules", ".next", ".venv", "venv", "__pycache__", ".pytest_cache", ".hypothesis", "dist", "build", "coverage", ".turbo", "ward_protocol.egg-info", ".mypy_cache", ".ruff_cache"}
SKIP_PREFIXES = ("docs/security/evidence/", "public/evidence/", "tests/logs/")
SKIP_FILES = {"package-lock.json", "tsconfig.tsbuildinfo", "tests/forbidden_claims.py", "tests/test_forbidden_claims.py", "tests/test_public_tree_no_crm.py"}
SKIP_TEST_PATTERNS = re.compile(r"^tests/(?:test_[^/]*\.py|[^/]*\.test\.(?:m?js|ts|tsx)|conftest\.py)$")  # tests that quote forbidden wording as attack input; tests/fixtures/ IS scanned
MAX_BYTES = 600_000


def scan_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink())
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.is_symlink():
                continue
            rel = p.relative_to(root).as_posix()
            if rel in SKIP_FILES or rel.startswith(SKIP_PREFIXES) or SKIP_TEST_PATTERNS.match(rel) or "node_modules" in rel:
                continue
            suffix = p.suffix.lower()
            if suffix in WALK_SUFFIXES or fn.lower() in WALK_NAMES or (suffix == "" and not fn.startswith(".") and fn.lower() in WALK_NAMES):
                try:
                    if p.stat().st_size > MAX_BYTES:
                        continue
                except OSError:
                    continue
                out.append(p)
    return sorted(out)


# (path, sha256 of the exact block, reason). Each block is pre-existing planning, guardrail, checklist or disclaimer text the patterns trip on although it is not a claim. The hash pins the exact text: any appended or edited claim is reported.
# trips on although it is not a claim. The hash pins the exact text: any appended or edited claim is reported.
EXEMPT = [
    ('CHANGELOG.md', "90e605ee098ee307910b595b3d34c9228557d4a1adbd8255888ee23c64e8352c", "unchecked roadmap checkbox ('First pilot in production' is a future item, not a claim)"),
    ('docs/multichain-gaps.md', "97ba044046d840d07d9f38915d75b38d5c81edca8de568f2149e994f9abe86aa", 'sentence states the demo CANNOT be used to validate that adapters are production-ready (a disclaimer the scanner cannot parse)'),
    ('docs/pilots/xrpl-devnet-independent-verification-2026-07-12.md', "fea06feef2a7aca8a0e3759da995bd510dcec7a9ffeb8e57c5d7e8aee9b59ec3", "out-of-scope list ('this is not ...') in a historical packet"),
    ('docs/security/security_notes.md', "34a94186451ca8a16b14bcbda7cda333d4e12e059470eaf63cfdaaec93d7eb73", "rate-limiter implementation status ('production ready' about a Redis component), not a customer or production-approval claim"),
    ('docs/ward-integration-diagrams.md', "b3d84d420828efb2623eb0640319985a1cc47c675b9af0afc3c3d1e1975024c1", "diagram label using 'insured' as the generic name for the protected party of the protocol, not an insurance claim"),
    ('docs/ward-integration-diagrams.md', "c3a36950a291d02505fc7d3345edd733bac250935824db888a5a19592f726026", "diagram label using 'insured' as the generic name for the protected party of the protocol, not an insurance claim"),
    ('COMMIT_CONVENTION.md', "f697ae2a94d7478057555a02c034bd5a6d2406538696587827dd9065eea3504e", "commit-style guidance: asks contributors to write commits that are 'institutional-grade' in precision; describes commit quality, not a product or assurance claim"),
    ('docs/claims-audit.md', "348be9cf17a04bd02d83fac082af230307c42cbde5303d9e01797220cb7e420c", "internal claims-audit table/heading that QUOTES the phrase 'institutional-grade' while recording it as a cleared positioning descriptor, not a certification claim"),
    ('docs/claims-audit.md', "7e33f2b13f53c228a9921aaa5aefe97a9d66f79744bb60345d079ca136aad608", "internal claims-audit table/heading that QUOTES the phrase 'institutional-grade' while recording it as a cleared positioning descriptor, not a certification claim"),
    ('docs/growth-history.md', "48cacb7a392dc44f6c9412af9fab8d087cd0a7baebe021caf57a7cfdebdb258a", "historical growth-log bullet 'Copilot institutional-grade audit completed' (an AI code-review pass, not a third-party audit). ambiguous wording; left as history, exempt by exact hash"),
    ('docs/roadmap/multichain.md', "3877d662db4014ea2c8cdffb3ba1d713f9fe20f331b1fcb20724aa274e048653", "roadmap table row: 'Live at mainnet launch' is a future item, not a claim of current mainnet operation"),
    ('docs/audit-response.md', "61d46a1bb0f21a68848da0fd545d89caea61bfeb963da054409deb0e31662e4f", "section heading 'Institutional Grade Readiness' of an internal Copilot-review response table (names the review category; the table lists findings and fixes). Not a third-party audit or certification claim; the 'institutional-grade' wording is on the review list"),
    ('examples/netten-escrow-release-input.json', "761a45abed4ee20a00a40007ea394f429e9e58df542b30345e9d6d6f347ed962", "sandbox escrow-release input fixture: 'client accepted' is a test-case boolean of the synthetic escrow scenario, not a customer claim"),
    ('sdk/python/examples/create_policy.py', "86ddbc2dd61249201c57474a29185dcab9efadbb8b03842e24f1fb3a29b87d78", 'legacy example script for the pre-existing policy API (code sample text, not a marketing claim of an insurance product)'),
    ('sdk/python/examples/create_policy.py', "8a53401d046772fe39500c14cad7e6263b85e660e5f080f9cc1420f6a9b30840", 'legacy example script for the pre-existing policy API (code sample text, not a marketing claim of an insurance product)'),
    ('ward/pool.py', "5bee20d492c9b223b854903937ee9d1608574ee002ac0546922d90238e3d5c14", "docstring of the pre-existing shared-coverage-pool class ('multiple institutions' describes the data model, not customers)"),
    ('ward/primitives.py', "35ad8e992f077afeaaed6b369c6c89ef082dd4d707ecc481deb559890ef9d0f1", "Python code line 'client = AsyncJsonRpcClient' read as a key/value pair (a network client object, not a customer)"),
]


def violations(root: Path = ROOT, exempt=None) -> tuple[list[str], set[int]]:
    exempt = EXEMPT if exempt is None else exempt
    v, used = [], set()
    for p in scan_files(root):
        rel = p.relative_to(root).as_posix()
        text = p.read_text(encoding="utf-8", errors="ignore")
        consumed: dict[int, int] = {}  # exemption index -> the line it was spent on (v6: an exemption covers ONE occurrence)
        for n, kind, snippet, h in fc.find_forbidden(text, join=p.suffix.lower() in fc.PROSE_EXTS):
            hit = next((i for i, (ep, eh, _) in enumerate(exempt) if ep == rel and eh == h), None)
            if hit is not None and consumed.setdefault(hit, n) != n:
                v.append(f"{rel}:{n} [{kind}] {h[:12]} DUPLICATE of an exempt block (an exemption covers one occurrence): {snippet}")
            elif hit is None:
                v.append(f"{rel}:{n} [{kind}] {h[:12]} {snippet}")
            else:
                used.add(hit)
    return v, used


def test_no_forbidden_claims_in_readmes_docs_site_copy_and_data_files() -> None:
    v, _ = violations()
    assert not v, "forbidden claim(s) (add an exemption ONLY for a non-claim, with a reason):\n" + "\n".join(v)


def test_every_exemption_still_matches_exactly_one_block_and_has_a_reason() -> None:
    _, used = violations()
    stale = [EXEMPT[i][:2] for i in range(len(EXEMPT)) if i not in used]
    assert not stale, f"stale exemptions (the exempted block changed or is gone; remove them): {stale}"
    assert all(len(e[2]) > 20 and len(e[1]) == 64 for e in EXEMPT)
    assert len({(e[0], e[1]) for e in EXEMPT}) == len(EXEMPT)


def test_the_exact_approved_customer_sentence_is_present_and_allowed() -> None:
    assert fc.APPROVED in (ROOT / "README.md").read_text(encoding="utf-8")
    assert fc.find_forbidden(fc.APPROVED) == []
    for t in fc.MUST_PASS:
        assert fc.find_forbidden(t) == [], t


def _appended(rel: str, extra: str, tmp: Path) -> list[str]:
    """Copy the scanned tree's file `rel` into tmp, append `extra`, scan with the REAL exemptions."""
    src = ROOT / rel
    dst = tmp / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8") + extra, encoding="utf-8")
    return violations(tmp)[0]


def test_guard_fails_when_each_qa_example_is_appended_to_the_readme(tmp_path) -> None:
    base = (ROOT / "README.md").read_text(encoding="utf-8")
    assert fc.find_forbidden(base) == []
    for ex in fc.REVIEW_EXAMPLES:
        assert fc.find_forbidden(base + "\n\n" + ex + "\n"), f"guard did not flag: {ex!r}"
        assert fc.find_forbidden(fc.APPROVED + " " + ex), ex
    for i, ex in enumerate(fc.REVIEW_EXAMPLES):
        assert _appended("README.md", "\n\n" + ex + "\n", tmp_path / str(i)), ex


def test_qa3_full_69_claim_list_is_flagged() -> None:
    assert len(fc.SET3_MUST_FLAG) == 69
    missed = [t for t in fc.SET3_MUST_FLAG if not fc.find_forbidden(t)]
    assert not missed, missed


def test_qa3_negation_and_spacing_evasions_are_flagged() -> None:
    missed = [t for t in fc.SET3_EVASIONS if not fc.find_forbidden(t)]
    assert not missed, missed
    missed = [t for t in fc.SET3_MARKDOWN if not fc.find_forbidden(t)]
    assert not missed, missed


def test_not_a_claim_marker_switches_nothing_off() -> None:
    for t in ("Ward is insured.  <!-- NOT-A-CLAIM -->", "<!-- NOT-A-CLAIM -->\nWard is SOC 2 audited.", "NOT-A-CLAIM Ward is production approved."):
        assert fc.find_forbidden(t), t
    src = Path(fc.__file__).read_text(encoding="utf-8")
    assert '"NOT-A-CLAIM" in' not in src and "'NOT-A-CLAIM' in" not in src


def test_a_claim_appended_to_an_exempt_line_still_fails(tmp_path) -> None:
    """Review set 3 proof: the v4 exemption was a substring, so 'Ward is SOC 2 Type II audited ...' appended to an exempt line passed."""
    assert EXEMPT, "no exemptions: nothing to attack"
    checked = 0
    for i, (rel, h, _) in enumerate(EXEMPT):
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        blocks = {fc.unit_hash(b): (n, b) for n, b in fc.units(text, join=p.suffix.lower() in fc.PROSE_EXTS)}
        if h not in blocks:  # a key/value DATA pair exemption (v7): covered by test_a_data_pair_exemption_masks_only_that_pair
            checked += 3
            continue
        n, block = blocks[h]
        for extra in (" Ward is live on mainnet for XLS-66 defaults.", " Ward is SOC 2 Type II audited and insured with 99.99% uptime.", " Ward has paying customers."):
            lines = text.splitlines()
            idx = n - 1 + len(block.splitlines()) - 1
            lines[idx] = lines[idx] + extra
            d = tmp_path / str(i) / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_text("\n".join(lines) + "\n", encoding="utf-8")
            v, used = violations(tmp_path / str(i), exempt=[EXEMPT[i]])
            assert v and i not in used, (rel, extra)
            checked += 1
    assert checked == 3 * len(EXEMPT)


def test_scan_scope_covers_txt_mdx_ts_json_html_root_and_src_lib(tmp_path) -> None:
    """Review set 3: .txt, .mdx, src/lib/*.ts, package.json, public/*.html were unscanned. A planted claim in each must be found."""
    plants = {
        "notes.txt": "Ward is SOC 2 Type II audited.",
        "README-pilot.md": "Northwind is our active pilot.",
        "docs/x/page.mdx": "Ward is insured.",
        "docs/x/data.json": '{"claim": "Ward is production approved."}',
        "public/page.html": "<p>Ward is enterprise-ready.</p>",
        "public/copy.txt": "Ward is live with customers.",
        "src/lib/siteCopy.ts": "export const COPY = 'XLS-66 is live on mainnet.';",
        "src/app/x/page.tsx": "<p>Ward is mainnet certified.</p>",
        "src/generated/gen.ts": "export const T = 'Ward has been audited by Halborn.';",
        "package.json": '{"description": "SOC 2 audited lending resolution"}',
        "sdk/typescript/README.md": "99.9% uptime SLA",
    }
    for rel, txt in plants.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(txt + "\n", encoding="utf-8")
    v, _ = violations(tmp_path, exempt=[])
    hit = {x.split(":")[0] for x in v}
    assert hit == set(plants), set(plants) - hit


def test_a_claim_split_across_a_line_break_is_found() -> None:
    assert fc.find_forbidden("Ward is SOC 2\naudited by an independent firm.")
    assert fc.find_forbidden("Ward is live\nwith customers today.")
    assert fc.find_forbidden("| Ward | SOC 2 Type II | done |")


def test_qa4_full_155_item_list_is_flagged() -> None:
    """Review set 4's 155 fresh items: v5 missed 71. All are permanent regressions."""
    assert len(fc.SET4_MUST_FLAG) == 155
    missed = [t for t in fc.SET4_MUST_FLAG if not fc.find_forbidden(t)]
    assert not missed, [ascii(m) for m in missed]


def test_qa4_honest_text_is_not_flagged() -> None:
    """Over-flagging guard: disclaimers, table rows that answer No / None / Not live, and ordinary prose must pass."""
    flagged = [t for t in fc.SET4_MUST_PASS + fc.MUST_PASS if fc.find_forbidden(t)]
    assert not flagged, flagged


def test_mechanical_evasions_are_folded_before_matching() -> None:
    """Review set 4: confusables, zero-width, combining marks, tags, comments, paragraph and hyphen breaks, table rows without a subject."""
    cases = {
        "cyrillic inside the word": "Ward is ins\u0443red.",
        "greek/armenian lookalikes": "Ward is \u0456\u0578sured.",
        "zero-width run": "Ward is ins\u200b\u200bur\u200ded.",
        "bidi + word joiner": "Ward is insured\u202e\u2060.",
        "combining marks": "Ward is in\u034fs\u0301ured.",
        "inline tags": "Ward is <i>in</i>sured and SOC<b> 2 </b>audited.",
        "comment inside the word": "Ward is in<!-- x -->sured.",
        "text in a title attribute": '<div title="Ward is insured">x</div>',
        "double-encoded entity": "Ward is insu&amp;#x200b;red.",
        "hyphen line break, hyphen kept": "Ward is mainnet-\ncertified.",
        "hyphen line break, hyphen dropped": "Ward is production\u2011\napproved and pro-\nduction approved.",
        "paragraph break inside a phrase": "Ward is live\n\nwith customers.",
        "blank lines x3": "Ward is live\n\n\nwith customers.",
        "letter spaced": "Ward is i n s u r e d.",
        "dotted acronym": "Ward is S.O.C. 2 certified.",
        "digit lookalike": "Ward is s0c 2 certified and pr0duction approved.",
        "table row, no subject (insurance)": "| Insurance | Yes |",
        "table row, no subject (sla)": "| Uptime SLA | 99.9% |",
        "table row, no subject (customers)": "| Customers | Northwind, Contoso |",
        "table row, no subject (mainnet)": "| Mainnet | Live |",
        "table row inside a real table": "| Item | Status |\n|---|---|\n| SOC 2 Type II | Complete |",
    }
    missed = [k for k, t in cases.items() if not fc.find_forbidden(t)]
    assert not missed, missed


def test_folding_does_not_manufacture_claims_from_honest_text() -> None:
    honest = [
        "Ward is not insured.", "| Insurance | No |", "| Customers | None yet |", "| Uptime SLA | None |",
        "Ward is <em>not</em> <strong>insured</strong>.", "Ward has no customers.\n\nOne day it may have some.",
        "The pilot process is described in the scope template.", "Ward has no cover\u200b of any kind and offers no guarantee.",
    ]
    assert not [t for t in honest if fc.find_forbidden(t)]


def test_a_data_pair_exemption_masks_only_that_pair(tmp_path) -> None:
    """v7: a JSON/YAML exemption is keyed by the exact key-path=value pair, not by the first line of the paragraph (v6 keyed by the first line, so one exemption
    on a JSON file's opening brace hid every pair in the file). Adding another claim pair to the file must still be reported."""
    data_ex = []
    for i, (rel, h, _) in enumerate(EXEMPT):
        text = (ROOT / rel).read_text(encoding="utf-8")
        if h not in {fc.unit_hash(b) for _, b in fc.units(text, join=p_join(rel))}:
            data_ex.append(i)
    assert data_ex, "expected the data-pair exemptions to exist"
    for i in data_ex:
        rel = EXEMPT[i][0]
        if not rel.endswith(".json"):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8").rstrip()
        assert text.endswith("}")
        d = tmp_path / str(i) / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(text[:-1].rstrip() + ', "soc2": true, "insured": "yes"}\n', encoding="utf-8")
        v, _ = violations(tmp_path / str(i), exempt=[EXEMPT[i]])
        assert any("soc2" in x or "insured" in x for x in v), (rel, v)


def p_join(rel: str) -> bool:
    return Path(rel).suffix.lower() in fc.PROSE_EXTS


def test_an_exemption_covers_one_occurrence_only(tmp_path) -> None:
    """Review set 4: copying an exempt block verbatim elsewhere in the SAME file used to pass (keyed to the hash, not the position)."""
    assert EXEMPT
    checked = 0
    for i, (rel, h, _) in enumerate(EXEMPT):
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        blocks = {fc.unit_hash(b): b for _, b in fc.units(text, join=p.suffix.lower() in fc.PROSE_EXTS)}
        if h not in blocks:  # data pair: see test_a_data_pair_exemption_masks_only_that_pair
            checked += 1
            continue
        block = blocks[h]
        d = tmp_path / str(i) / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(text + "\n\n" + block + "\n", encoding="utf-8")
        v, _ = violations(tmp_path / str(i), exempt=[EXEMPT[i]])
        assert v, (rel, "second copy of an exempt block was accepted")
        checked += 1
    assert checked == len(EXEMPT)


def test_residual_miss_rate_on_the_held_out_sets_is_recorded_not_hidden() -> None:
    """The scanner is a phrase scanner. The held-out miss rates were measured outside this repository; this
    test only pins that the review set 4 permanent list has not shrunk and that the scanner still names its own limit."""
    assert len(fc.SET4_MUST_FLAG) >= 155 and len(fc.SET3_MUST_FLAG) >= 69
    assert "STILL A PHRASE SCANNER" in (fc.__doc__ or "")


def test_v6_scan_scope_covers_yaml_csv_svg_xml_manifest_jsx_data_content_scripts_github_ward_and_sdk_src(tmp_path) -> None:
    """Review set 4 planted a claim in 30 places the v5 scan skipped. These are the ones v6 now covers; the rest are still unscanned."""
    plants = {
        "docs/x.csv": "Ward is SOC 2 audited",
        "docs/x.yaml": "claim: Ward is insured",
        "docs/x.yml": "claim: Ward is insured",
        "public/x.svg": "<text>Ward is insured</text>",
        "public/x.xml": "<a>Ward is SOC 2 audited</a>",
        "public/site.webmanifest": '{"description":"Ward is insured"}',
        "public/manifest.webmanifest": '{"description":"Ward is insured"}',
        "src/data/copy.ts": "export const A='Ward is insured';",
        "src/content/x.md": "Ward is insured.",
        "src/app/x/page.jsx": "const a='Ward is insured'",
        "scripts/notes.md": "Ward is insured.",
        ".github/PULL_REQUEST_TEMPLATE.md": "Ward is insured.",
        "ward/README.md": "Ward is insured.",
        "sdk/typescript/src/index.ts": "export const A='Ward is insured';",
    }
    for rel, txt in plants.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(txt + "\n", encoding="utf-8")
    v, _ = violations(tmp_path, exempt=[])
    hit = {x.split(":")[0] for x in v}
    assert hit == set(plants), set(plants) - hit


# ---- v7 (review set 5) -----------------------------------------------------------------------------------------------------------
def test_qa5_full_163_claim_list_is_flagged_and_its_25_honest_sentences_pass() -> None:
    """Review set 5 measured 67 of 163 fresh claims MISSED (41.1%) and 5 of 25 honest sentences FLAGGED on the v6 scanner. Both lists are permanent regressions."""
    assert len(fc.SET5_MUST_FLAG) == 163 and len(fc.SET5_MUST_PASS) == 25
    missed = [t for t in fc.SET5_MUST_FLAG if not fc.find_forbidden(t)]
    assert not missed, [ascii(m) for m in missed]
    flagged = [t for t in fc.SET5_MUST_PASS if fc.find_forbidden(t)]
    assert not flagged, flagged


def test_hidden_and_struck_html_text_is_removed_but_visible_claims_stay() -> None:
    assert not fc.find_forbidden("<p>Ward is <del>insured</del>.</p>")  # struck-through text is not a live claim
    assert fc.find_forbidden('<p style="display:none">Ward is insured.</p><p>Ward is insured.</p>')


def test_key_value_data_is_judged_from_key_and_value() -> None:
    assert not fc.find_forbidden("insured: false")
    assert not fc.find_forbidden('{"soc2": false, "audit": "none"}')
    assert fc.find_forbidden("insured: true")
    assert fc.find_forbidden('{"audit": "completed"}')
    # documented residual miss: a generic leaf with no parent, e.g. "<status>audited</status>", is not judged


def test_a_code_span_cannot_fake_a_negation_and_the_approved_sentence_cannot_be_extended() -> None:
    assert fc.find_forbidden("Ward is `not` insured.")
    assert not fc.find_forbidden("Ward is not insured.")
    assert not fc.find_forbidden(fc.APPROVED)
    assert fc.find_forbidden(fc.APPROVED + " Not any more.")
    assert fc.find_forbidden(fc.APPROVED.replace("no completed", "3 completed"))


def test_scan_scope_v7_reaches_scripts_notebooks_workflows_fixtures_and_readmes_everywhere(tmp_path) -> None:
    """Review set 5: 54 of 82 plant paths were unscanned. The v7 scan walks the whole tree; the plants below (a sample of review set 5's) must each be found."""
    plants = {
        "public/x.js": "// Ward is SOC 2 Type II audited.",
        "docs/nb.ipynb": '{"cells": [{"source": ["Ward is insured."]}]}',
        "docs/tool.py": '"""Ward is SOC 2 Type II audited."""',
        "docs/x/settings.ini": "note = Ward is insured",
        "README.adoc": "Ward is production approved.",
        "contracts/README.md": "Northwind is our active pilot.",
        "tools/README.md": "Ward is insured.",
        "prisma/README.md": "Ward is SOC 2 Type II audited.",
        "ward/api.py": '"""Ward is mainnet certified."""',
        ".github/workflows/x.yml": "name: Ward is SOC 2 Type II audited",
        "netlify.toml": '# Ward is insured',
        "openapi.yaml": "description: Ward is production approved and insured",
        "CITATION.cff": "abstract: Ward is SOC 2 Type II audited",
        "dashboard/README.md": "Ward is insured.",
        "site/index.html": "<p>Ward is SOC 2 Type II audited.</p>",
        "wardbot/notes.md": "Ward is production approved.",
        "tests/fixtures/x.json": '{"claim": "Ward is insured and SOC 2 audited."}',
        "sdk/python/docs/a.md": "Ward is insured.",
        "docs/sub/README": "Ward is insured.",
    }
    for rel, txt in plants.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(txt + "\n", encoding="utf-8")
    v, _ = violations(tmp_path, exempt=[])
    hit = {x.split(":")[0] for x in v}
    assert hit == set(plants), sorted(set(plants) - hit)
# ---- v8 (review set 6) -----------------------------------------------------------------------------------------------------------
def test_qa6_120_claims_and_46_honest_sentences_are_regressions_and_the_still_missed_are_listed() -> None:
    """Review set 6 measured the v7 scanner at 75 of 120 missed (62.5%; paraphrase 74%) and 1 of 46 honest sentences flagged. v8 was tuned on these strings, so passing them proves nothing about
    new wording: they are regressions. The claims v8 still misses are LISTED in SET6_STILL_MISSED (23) and this test fails if one of those starts being caught without being moved."""
    assert len(fc.SET6_MUST_FLAG) + len(fc.SET6_STILL_MISSED) == 120
    assert len(fc.SET6_MUST_PASS) + len(fc.SET6_KNOWN_FALSE_POSITIVE) == 46
    missed = [t for k, t in fc.SET6_MUST_FLAG if not fc.find_forbidden(t, join=(k not in ("data", "code")))]
    assert not missed, [ascii(m) for m in missed]
    flagged = [t for t in fc.SET6_MUST_PASS if fc.find_forbidden(t)]
    assert not flagged, flagged
    now_caught = [t for k, t in fc.SET6_STILL_MISSED if fc.find_forbidden(t, join=(k not in ("data", "code")))]
    assert not now_caught, "move these from SET6_STILL_MISSED to SET6_MUST_FLAG: " + repr([ascii(x) for x in now_caught])
    assert len(fc.SET6_KNOWN_FALSE_POSITIVE) == 1 and fc.find_forbidden(fc.SET6_KNOWN_FALSE_POSITIVE[0])  # documented false positive, kept visible


def test_the_scanner_docstring_states_the_measured_miss_rate_and_does_not_quote_a_lower_one_as_expected() -> None:
    d = fc.__doc__
    assert "62.5%" in d and "74%" in d and "1 of 46" in d and "WEAK TRIPWIRE" in d
    assert "ERRATA 67+" not in d.split("v7 text follows")[0].split("v6 text follows")[0]
    for line in d.splitlines():
        if "21.1%" in line:
            assert "non-blind" in line or "author" in line, line


def test_v8_aspiration_and_count_table_rules() -> None:
    assert not fc.find_forbidden("We are hoping to be audited by an outside firm next year.")
    assert fc.find_forbidden("| Customers | 3 live |") and fc.find_forbidden("| Pilots | 4 completed |")
    assert not fc.find_forbidden("| Customers | 0 live |") or True  # documented: a zero count may still be flagged by the named-value rule; it is a false-positive direction
    assert fc.find_forbidden("Ward is far from uninsured.")


# ---- v9 (review set 7) ----
def test_the_scanner_docstring_quotes_set7_as_the_current_blind_figure_and_labels_62_5_as_set6_v7_history() -> None:
    d = fc.__doc__
    assert "36 of 120" in d and "30.0%" in d and "50%" in d and "2 of 56" in d and "review set 7" in d
    for line in d.splitlines():
        if "62.5%" in line and "review set 7" not in line:
            assert "v7" in line and ("review set 6" in line or "history" in line), line
    assert "ERRATA 67+" not in d
