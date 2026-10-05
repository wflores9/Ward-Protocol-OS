"""Forbidden-claims scanner shared by the WARD and OS wording tests (v7). ward_signed = False.

CURRENT HONEST NUMBERS (v9, from independent review set 7, which had NOT seen v8's tuning): the v8 scanner missed 36 of 120 fresh claims (30.0% overall; paraphrases 30 of 60 = 50%;
mechanical disguises 1 of 20; data rows 2 of 25; negations 3 of 15) and flagged 2 of 56 honest sentences (3.6%, both substring hits on "insur*" inside honest text). On the same
items the v7 scanner missed 42 of 120 (35.0%). Those are the figures to quote for THIS file. The "62.5% / 74%" below is review set 6's measurement of the v7 scanner and is kept only as
history; it is not a v8 measurement. Treat the scanner as a weak tripwire: about half of new paraphrases will pass it.

READ THIS FIRST (v8, review set 6): THIS IS A WEAK TRIPWIRE, NOT A CONTROL. It is a list of phrase patterns plus text folding. It catches the wording its
authors already thought of and the mechanical disguises listed below; it does NOT understand meaning, and wording nobody tried will pass.
Review set 6's number for the v7 scanner (history; see the v9 paragraph above for v8): the v7 scanner missed 75 of 120 fresh claims (62.5%; paraphrase 52 of 70 = 74%) and flagged 1 of 46 honest sentences, as measured by
independent review set 6 on strings the author had not seen. The v6 scanner missed 86 of 120 on the same items and had 4 false positives. Earlier lower figures (41.1% on 163
claims by review set 5 for v6; 21.1% on the author's own set for v7; "about 10%") were either measured on other items or on the author's non-blind sets, and must never be quoted
as the expected miss rate. Expect a fresh paraphrase to be missed more often than not.
v8 adds more phrase families and review set 6's 120 claims and 46 honest sentences as regressions (SET6_MUST_FLAG / SET6_MUST_PASS; the claims v8 STILL misses are listed in
SET6_STILL_MISSED, not hidden). v8's own after-figures (review set 6's set after tuning on it: 23 of 120 missed; the author's three hash-first sets A, B, C)
are NOT blind and are NOT a prediction: set C, written after all v8 changes and before measurement, still missed 19 of 36 (52.8%)
at v8 (paraphrase 19 of 25), so the honest expectation for a new paraphrase is still a majority missed.
It must never be the only thing between a false claim and publication: human review of every public sentence is still required.

v7 (review set 5) adds: the full Unicode UTS #39 confusables table (single-character Latin lookalikes, 1,4xx characters) plus small capitals, Hangul/Braille
"blank" fillers stripped, in-word separators (middle dot, underscore, asterisk) and markdown emphasis folded, struck-through / hidden HTML text
removed before matching, table rows written as HTML cells judged like markdown rows, key/value data (JSON, YAML, TOML, INI, XML) judged from key and
value instead of as prose (so `insured: false` is not a claim and `"audit": "completed"` is), conditional ("if Ward were insured") and
"nothing/nobody" negation, more claim families (assurance reports, other standards, named-firm reviews, insurance policies, uptime figures,
customer/pilot/contract wording, "launched", "processing real settlements", MiCA, "perfect record"), and four negation shapes review set 5 found.
Review set 5's 163 claims and 25 honest sentences are permanent regressions (SET5_MUST_FLAG, SET5_MUST_PASS). Not fixed: `&nbsp;` inside a word (it is a space),
a code span used to fake a negation ("`not` insured") which reads as negated text, and any paraphrase not listed.

v6 text follows.

v6 (review set 4) adds, each proved by tests/test_forbidden_claims.py against review set 4's 155 fresh items (SET4_MUST_FLAG, permanent):
  * normalisation now also: strips every Unicode format character (Cf: zero-width, bidi controls, soft hyphen), decomposes and
    drops combining marks, folds confusables (Cyrillic/Greek/Armenian/modifier lookalikes -> Latin) and in-word digit
    lookalikes (s0c, pr0duction), removes HTML comments and tags BEFORE matching (inline tags join, block tags separate),
    and joins a hyphen line-break both ways ("mainnet-\ncertified" and "pro-\nduction").
  * a claim split across a paragraph break is found (bridge pass over adjacent blocks), and letter-spaced words
    ("i n s u r e d") are detected as their own kind.
  * a markdown table row with no subject ("| Insurance | Yes |", "| Customers | Northwind, Contoso |") is judged from its key
    and value cells (kind table-claim).
  * more claim wording (SOC II, System and Organization Controls, insurance policy/fund/cover, security audit by X, five-nines,
    24/7/365, service credits, "rely on Ward", "onboarded", "signed order form", generally available, live on the XRP Ledger
    mainnet, XLS-66d, licensed/regulated/approved by SEC, satisfies MiCA, institutional-grade, production standard/release/
    service, proven in production, mainnet-valid, certified by an independent third party, "not uninsured", FR/DE/ES).
  * an exemption covers ONE occurrence of its block: a second identical block in the same file is a violation.
STILL A PHRASE SCANNER. Wording nobody has tried will pass. There is no claim that any rate generalises.

v5 text follows.
Forbidden-claims scanner shared by the WARD and OS wording tests (v5, review set 3). ward_signed = False.

What changed from v4 (each item is a review set 3 finding, proved by tests/test_forbidden_claims.py):
  * The text is normalised before matching: NFKC, zero-width characters removed, HTML entities decoded, spaced-out
    letters tolerated ("S O C 2"), and a block of consecutive text lines is joined, so a claim split across a line
    break is still seen.
  * A negation counts only when the negator governs the claim: it sits in the same clause, within 8 words before the
    claim (or inside the matched phrase), with no positive assertion word between them, and it is not "not just/only/
    merely". A negator AFTER the claim ("insured, not merely tested"), a semicolon / dash / comma-clause break, or
    "it is false that ..." do not excuse anything. The v4 rule (any negator anywhere in the sentence) is gone.
  * The `<!-- NOT-A-CLAIM -->` whole-line switch is REMOVED. Nothing in a file can switch the scanner off.
  * An exemption is keyed to the exact SHA-256 of the exempted block (path + content hash), not a substring, so a claim
    appended to an exempt line changes the hash and fails.
  * More claim families: audited by / independently audited, four nines, live with customers/banks, design partner: X,
    XLS-65/66 live (with or without "on mainnet"), deployed / used in production, in production at X, protects customer
    funds, secures $N, ISO 27001, penetration test passed, regulator approved / licensed / MiCA, bank-grade,
    enterprise-ready, battle-tested, running on mainnet since.
  * review set 3's full 69-claim list, its 15 evasions and its markdown probes are permanent regressions (SET3_* below).
A phrase scanner is not a legal review and a novel wording will pass; that is stated here, not hidden."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata

APPROVED = "Ward has no production customer deployments and no completed customer pilots as of September 2026."

ZW = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad\u115f\u1160\u3164\uffa0\u2800\u180e\u17b4\u17b5\u034f]")  # v7: + Hangul fillers, Braille blank, Mongolian vowel separator, Khmer inherent vowels, CGJ
# confusables: characters that LOOK like Latin letters (Cyrillic, Greek, Armenian, Cherokee-free small set) folded to the Latin letter.
CONFUSABLES = {
    **{c: l for c, l in zip("\u0430\u0435\u043e\u0440\u0441\u0443\u0445\u0456\u0458\u0455\u0501\u051b\u04bb\u0461\u044c\u043d\u043a\u043c\u0442\u0432\u0433\u0438",
                            "aeopcyxijsdqhwbhkmtbrn")},
    **{c: l for c, l in zip("\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0423\u0406\u0408\u0405", "ABEKMHOPCTXYIJS")},
    **{c: l for c, l in zip("\u03b1\u03bf\u03bd\u03c1\u03b9\u03ba\u03c5\u03c7\u03c4\u03c9\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7",
                            "aovpikuxtwABEZHIKMNOPTYX")},
    "\u0131": "i", "\u0269": "i", "\u026a": "i", "\u01c0": "l", "\u0578": "n", "\u057c": "n", "\u0585": "o", "\u0581": "g", "\u0563": "q", "\u0570": "h",
    "\u0142": "l", "\u0111": "d", "\u00f8": "o", "\u00d8": "O", "\u1d00": "a", "\u1d04": "c", "\u1d07": "e", "\u1d0f": "o", "\u1d1c": "u", "\u0251": "a", "\u0261": "g",
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2212": "-", "\ufe63": "-", "\uff0d": "-",
}
UTS39_CONFUSABLES = {  # v7: generated from Unicode confusables.txt v18.0.0 (2026-08-06) single-char -> single Latin letter entries (1462), plus small capitals; lowercase targets
    'a': '\u0251\u0391\u03b1\u0410\u0430\u13aa\u15c5\u1d00\u237a\ua4ee\uab64\uff21\uff41\U000102a0\U00016f40\U0001ccd6\U0001d400\U0001d41a\U0001d434\U0001d44e\U0001d468\U0001d482\U0001d49c\U0001d4b6\U0001d4d0\U0001d4ea\U0001d504\U0001d51e\U0001d538\U0001d552\U0001d56c\U0001d586\U0001d5a0\U0001d5ba\U0001d5d4\U0001d5ee\U0001d608\U0001d622\U0001d63c\U0001d656\U0001d670\U0001d68a\U0001d6a8\U0001d6c2\U0001d6e2\U0001d6fc\U0001d71c\U0001d736\U0001d756\U0001d770\U0001d790\U0001d7aa\U0001df5a\U0001df6a',
    'b': '\u0184\u0299\u0392\u0412\u042c\u07d5\u13cf\u13f4\u1472\u15af\u15f7\u212c\u2c82\ua4d0\ua557\ua7b4\uff22\uff42\U00010282\U000102a1\U00010301\U0001031c\U00016eb6\U0001ccd7\U0001d207\U0001d401\U0001d41b\U0001d435\U0001d44f\U0001d469\U0001d483\U0001d4b7\U0001d4d1\U0001d4eb\U0001d505\U0001d51f\U0001d539\U0001d553\U0001d56d\U0001d587\U0001d5a1\U0001d5bb\U0001d5d5\U0001d5ef\U0001d609\U0001d623\U0001d63d\U0001d657\U0001d671\U0001d68b\U0001d6a9\U0001d6e3\U0001d71d\U0001d757\U0001d791',
    'c': '\u03f2\u03f9\u0421\u0441\u1004\u105a\u13df\u1c83\u1d04\u2102\u212d\u216d\u217d\u2ca4\u2ca5\ua4da\uabaf\uff23\uff43\U000102a2\U00010302\U00010415\U0001043d\U0001051b\U000118e9\U000118f2\U0001ccd8\U0001d134\U0001d402\U0001d41c\U0001d436\U0001d450\U0001d46a\U0001d484\U0001d49e\U0001d4b8\U0001d4d2\U0001d4ec\U0001d520\U0001d554\U0001d56e\U0001d588\U0001d5a2\U0001d5bc\U0001d5d6\U0001d5f0\U0001d60a\U0001d624\U0001d63e\U0001d658\U0001d672\U0001d68c\U0001f74c',
    'd': '\u0501\u13a0\u13e7\u146f\u15de\u15ea\u1d05\u2145\u2146\u216e\u217e\ua4d2\ua4d3\uff24\uff44\U0001018b\U0001ccd9\U0001d403\U0001d41d\U0001d437\U0001d451\U0001d46b\U0001d485\U0001d49f\U0001d4b9\U0001d4d3\U0001d4ed\U0001d507\U0001d521\U0001d53b\U0001d555\U0001d56f\U0001d589\U0001d5a3\U0001d5bd\U0001d5d7\U0001d5f1\U0001d60b\U0001d625\U0001d63f\U0001d659\U0001d673\U0001d68d',
    'e': '\u0395\u0415\u0435\u04bd\u13ac\u1d07\u212e\u212f\u2130\u2147\u22ff\u2d39\ua4f0\ua5cb\uab32\uff25\uff45\U00010286\U000118a6\U000118ae\U0001ccda\U0001d404\U0001d41e\U0001d438\U0001d452\U0001d46c\U0001d486\U0001d4d4\U0001d4ee\U0001d508\U0001d522\U0001d53c\U0001d556\U0001d570\U0001d58a\U0001d5a4\U0001d5be\U0001d5d8\U0001d5f2\U0001d60c\U0001d626\U0001d640\U0001d65a\U0001d674\U0001d68e\U0001d6ac\U0001d6e6\U0001d720\U0001d75a\U0001d794\U0001df81',
    'f': '\u017f\u0192\u0284\u03dc\u0584\u07d3\u15b4\u1e9d\u2131\ua4dd\ua730\ua798\ua799\uab35\uff26\uff46\U0001017e\U00010287\U000102a5\U00010525\U000118a2\U000118c2\U0001ccdb\U0001d213\U0001d405\U0001d41f\U0001d439\U0001d453\U0001d46d\U0001d487\U0001d4bb\U0001d4d5\U0001d4ef\U0001d509\U0001d523\U0001d53d\U0001d557\U0001d571\U0001d58b\U0001d5a5\U0001d5bf\U0001d5d9\U0001d5f3\U0001d60d\U0001d627\U0001d641\U0001d65b\U0001d675\U0001d68f\U0001d7ca',
    'g': '\u018d\u0261\u0262\u050c\u0581\u13c0\u13f3\u1d83\u210a\ua4d6\uff27\uff47\U0001ccdc\U0001d406\U0001d420\U0001d43a\U0001d454\U0001d46e\U0001d488\U0001d4a2\U0001d4d6\U0001d4f0\U0001d50a\U0001d524\U0001d53e\U0001d558\U0001d572\U0001d58c\U0001d5a6\U0001d5c0\U0001d5da\U0001d5f4\U0001d60e\U0001d628\U0001d642\U0001d65c\U0001d676\U0001d690',
    'h': '\u029c\u0397\u041d\u04ba\u04bb\u0570\u10b9\u13bb\u13c2\u157c\u210b\u210c\u210d\u210e\u2c8e\ua4e7\uff28\uff48\U000102cf\U0001ccdd\U0001d407\U0001d421\U0001d43b\U0001d46f\U0001d489\U0001d4bd\U0001d4d7\U0001d4f1\U0001d525\U0001d559\U0001d573\U0001d58d\U0001d5a7\U0001d5c1\U0001d5db\U0001d5f5\U0001d60f\U0001d629\U0001d643\U0001d65d\U0001d677\U0001d691\U0001d6ae\U0001d6e8\U0001d722\U0001d75c\U0001d796',
    'i': '\xa1\u0131\u0269\u026a\u03b9\u0456\u04cf\u0582\u13a5\u2139\u2148\u2160\u2170\u2373\u2c93\ua647\ua7ae\uab75\uff49\U000118c3\U0001d422\U0001d456\U0001d48a\U0001d4be\U0001d4f2\U0001d526\U0001d55a\U0001d58e\U0001d5c2\U0001d5f6\U0001d62a\U0001d65e\U0001d692\U0001d6a4\U0001d6ca\U0001d704\U0001d73e\U0001d778\U0001d7b2',
    'j': '\u0237\u037f\u03f3\u0408\u0458\u0575\u13ab\u148d\u1d0a\u2149\ua4d9\ua7b2\uff2a\uff4a\U0001ccdf\U0001d409\U0001d423\U0001d43d\U0001d457\U0001d471\U0001d48b\U0001d4a5\U0001d4bf\U0001d4d9\U0001d4f3\U0001d50d\U0001d527\U0001d541\U0001d55b\U0001d575\U0001d58f\U0001d5a9\U0001d5c3\U0001d5dd\U0001d5f7\U0001d611\U0001d62b\U0001d645\U0001d65f\U0001d679\U0001d693\U0001d6a5',
    'k': '\u039a\u041a\u13e6\u16d5\u1d0b\u2c94\ua4d7\uff2b\uff4b\U00010518\U0001cce0\U0001d40a\U0001d424\U0001d43e\U0001d458\U0001d472\U0001d48c\U0001d4a6\U0001d4c0\U0001d4da\U0001d4f4\U0001d50e\U0001d528\U0001d542\U0001d55c\U0001d576\U0001d590\U0001d5aa\U0001d5c4\U0001d5de\U0001d5f8\U0001d612\U0001d62c\U0001d646\U0001d660\U0001d67a\U0001d694\U0001d6b1\U0001d6eb\U0001d725\U0001d75f\U0001d799',
    'l': '\u0196\u01c0\u029f\u0399\u0406\u04c0\u05c0\u05d5\u05df\u0627\u0661\u06f1\u07ca\u0964\u104a\u13de\u14aa\u16c1\u16d0\u2110\u2111\u2112\u2113\u216c\u217c\u21bf\u2223\u23fd\u2502\u2503\u2c92\u2cd0\u2d4a\u2d4f\ua4e1\ua4f2\ua56f\ua781\ua7fe\ua830\ua8ce\uaa5d\ufe31\ufe8d\ufe8e\uff11\uff29\uff2c\uff4c\uff5c\uffe8\U0001028a\U00010309\U00010320\U0001041b\U0001050e\U00010526\U00010926\U00010c3e\U00010ca5\U00010cfa\U00011047\U000110c0\U00011141\U000111c5\U000113d4\U0001144b\U000115c5\U00011641\U000118a3\U000118b2\U00011c41\U00011dda\U00011de1\U00016d63\U00016eaa\U00016f16\U00016f28\U0001ccde\U0001cce1\U0001ccf1\U0001d100\U0001d22a\U0001d377\U0001d408\U0001d40b\U0001d425\U0001d43c\U0001d43f\U0001d459\U0001d470\U0001d473\U0001d48d\U0001d4c1\U0001d4d8\U0001d4db\U0001d4f5\U0001d50f\U0001d529\U0001d540\U0001d543\U0001d55d\U0001d574\U0001d577\U0001d591\U0001d5a8\U0001d5ab\U0001d5c5\U0001d5dc\U0001d5df\U0001d5f9\U0001d610\U0001d613\U0001d62d\U0001d644\U0001d647\U0001d661\U0001d678\U0001d67b\U0001d695\U0001d6b0\U0001d6ea\U0001d724\U0001d75e\U0001d798\U0001d7cf\U0001d7d9\U0001d7e3\U0001d7ed\U0001d7f7\U0001e141\U0001e8c7\U0001ed01\U0001ee00\U0001ee80\U0001fbf1',
    'm': '\u039c\u03fa\u041c\u13b7\u15f0\u16d6\u1d0d\u2133\u216f\u2c98\ua4df\uff2d\U000102b0\U00010311\U00010c21\U0001cce2\U0001d40c\U0001d440\U0001d474\U0001d4dc\U0001d510\U0001d544\U0001d578\U0001d5ac\U0001d5e0\U0001d614\U0001d648\U0001d67c\U0001d6b3\U0001d6ed\U0001d727\U0001d761\U0001d79b',
    'n': '\u0274\u039d\u0578\u057c\u2115\u2c9a\ua4e0\uff2e\uff4e\U00010513\U00011abe\U0001cce3\U0001d40d\U0001d427\U0001d441\U0001d45b\U0001d475\U0001d48f\U0001d4a9\U0001d4c3\U0001d4dd\U0001d4f7\U0001d511\U0001d52b\U0001d55f\U0001d579\U0001d593\U0001d5ad\U0001d5c7\U0001d5e1\U0001d5fb\U0001d615\U0001d62f\U0001d649\U0001d663\U0001d67d\U0001d697\U0001d6b4\U0001d6ee\U0001d728\U0001d762\U0001d79c',
    'o': '\u039f\u03bf\u03c3\u03ed\u041e\u043e\u0555\u0585\u05e1\u0647\u0665\u06be\u06c1\u06d5\u06f5\u07c0\u07cb\u0840\u0966\u09e6\u0a66\u0ae6\u0b20\u0b66\u0be6\u0c02\u0c66\u0c82\u0ce6\u0d02\u0d20\u0d66\u0d82\u0e50\u0ed0\u101d\u1040\u10ff\u110b\u11bc\u12d0\u17e0\u1a45\u1a80\u1a90\u1bea\u1c82\u1cbf\u1d0f\u1d11\u2134\u2c9e\u2c9f\u2d54\u3007\u3147\ua4f3\uab3d\ufba6\ufba7\ufba8\ufba9\ufbaa\ufbab\ufbac\ufbad\ufee9\ufeea\ufeeb\ufeec\uff10\uff2f\uff4f\uffb7\U00010292\U000102ab\U0001030f\U00010404\U0001042c\U000104c2\U000104ea\U00010516\U0001092c\U00010c17\U00010d07\U00011124\U00011302\U000114d0\U000118b5\U000118c8\U000118d7\U000118e0\U00011de0\U00016ae9\U0001cce4\U0001ccf0\U0001d40e\U0001d428\U0001d442\U0001d45c\U0001d476\U0001d490\U0001d4aa\U0001d4de\U0001d4f8\U0001d512\U0001d52c\U0001d546\U0001d560\U0001d57a\U0001d594\U0001d5ae\U0001d5c8\U0001d5e2\U0001d5fc\U0001d616\U0001d630\U0001d64a\U0001d664\U0001d67e\U0001d698\U0001d6b6\U0001d6d0\U0001d6d4\U0001d6f0\U0001d70a\U0001d70e\U0001d72a\U0001d744\U0001d748\U0001d764\U0001d77e\U0001d782\U0001d79e\U0001d7b8\U0001d7bc\U0001d7ce\U0001d7d8\U0001d7e2\U0001d7ec\U0001d7f6\U0001e140\U0001e2f0\U0001ee24\U0001ee84\U0001fbf0',
    'p': '\xfe\u01bf\u03a1\u03c1\u03f1\u03f8\u0420\u0440\u13e2\u146d\u1d18\u2119\u2374\u2ca2\u2ca3\u2cce\u2ccf\ua4d1\uff30\uff50\U00010295\U0001cce5\U0001d40f\U0001d429\U0001d443\U0001d45d\U0001d477\U0001d491\U0001d4ab\U0001d4c5\U0001d4df\U0001d4f9\U0001d513\U0001d52d\U0001d561\U0001d57b\U0001d595\U0001d5af\U0001d5c9\U0001d5e3\U0001d5fd\U0001d617\U0001d631\U0001d64b\U0001d665\U0001d67f\U0001d699\U0001d6b8\U0001d6d2\U0001d6e0\U0001d6f2\U0001d70c\U0001d71a\U0001d72c\U0001d746\U0001d754\U0001d766\U0001d780\U0001d78e\U0001d7a0\U0001d7ba\U0001d7c8',
    'q': '\u051a\u051b\u0563\u0566\u211a\u2d55\uff31\uff51\U0001cce6\U0001d410\U0001d42a\U0001d444\U0001d45e\U0001d478\U0001d492\U0001d4ac\U0001d4c6\U0001d4e0\U0001d4fa\U0001d514\U0001d52e\U0001d562\U0001d57c\U0001d596\U0001d5b0\U0001d5ca\U0001d5e4\U0001d5fe\U0001d618\U0001d632\U0001d64c\U0001d666\U0001d680\U0001d69a',
    'r': '\u01a6\u024c\u0280\u0433\u13a1\u13d2\u1587\u1d26\u211b\u211c\u211d\u2c85\ua4e3\uab47\uab48\uab81\uff32\uff52\U000104b4\U00016a19\U00016f35\U0001cce7\U0001d216\U0001d411\U0001d42b\U0001d445\U0001d45f\U0001d479\U0001d493\U0001d4c7\U0001d4e1\U0001d4fb\U0001d52f\U0001d563\U0001d57d\U0001d597\U0001d5b1\U0001d5cb\U0001d5e5\U0001d5ff\U0001d619\U0001d633\U0001d64d\U0001d667\U0001d681\U0001d69b',
    's': '\u01bd\u0405\u0455\u054f\u0d1f\u10bd\u10fd\u13d5\u13da\u1cbd\ua4e2\ua576\ua731\uabaa\uff33\uff53\U00010296\U00010420\U00010448\U000118c1\U00016ad6\U00016f3a\U0001cce8\U0001d412\U0001d42c\U0001d446\U0001d460\U0001d47a\U0001d494\U0001d4ae\U0001d4c8\U0001d4e2\U0001d4fc\U0001d516\U0001d530\U0001d54a\U0001d564\U0001d57e\U0001d598\U0001d5b2\U0001d5cc\U0001d5e6\U0001d600\U0001d61a\U0001d634\U0001d64e\U0001d668\U0001d682\U0001d69c',
    't': '\u03a4\u0422\u07e0\u13a2\u1d1b\u22a4\u27d9\u2ca6\u3112\u4e05\ua4d4\ua50b\uff34\uff54\U00010297\U000102b1\U00010315\U000118bc\U00016f0a\U0001cce9\U0001d373\U0001d413\U0001d42d\U0001d447\U0001d461\U0001d47b\U0001d495\U0001d4af\U0001d4c9\U0001d4e3\U0001d4fd\U0001d517\U0001d531\U0001d54b\U0001d565\U0001d57f\U0001d599\U0001d5b3\U0001d5cd\U0001d5e7\U0001d601\U0001d61b\U0001d635\U0001d64f\U0001d669\U0001d683\U0001d69d\U0001d6bb\U0001d6f5\U0001d72f\U0001d769\U0001d7a3\U0001f768',
    'u': '\u028b\u03c5\u054d\u057d\u1200\u144c\u1d1c\u222a\u22c3\ua4f4\ua79f\uab4e\uab52\uff35\uff55\U000104ce\U000104f6\U000118b8\U000118d8\U00016f42\U0001ccea\U0001d414\U0001d42e\U0001d448\U0001d462\U0001d47c\U0001d496\U0001d4b0\U0001d4ca\U0001d4e4\U0001d4fe\U0001d518\U0001d532\U0001d54c\U0001d566\U0001d580\U0001d59a\U0001d5b4\U0001d5ce\U0001d5e8\U0001d602\U0001d61c\U0001d636\U0001d650\U0001d66a\U0001d684\U0001d69e\U0001d6d6\U0001d710\U0001d74a\U0001d784\U0001d7be',
    'v': '\u03bd\u0474\u0475\u05d8\u0667\u06f7\u13d9\u142f\u1d20\u2164\u2174\u2228\u22c1\u2d38\ua4e6\ua6df\uaba9\uff36\uff56\U0001051d\U00010c1f\U00011706\U000118a0\U000118c0\U00016f08\U0001cceb\U0001cefc\U0001d20d\U0001d415\U0001d42f\U0001d449\U0001d463\U0001d47d\U0001d497\U0001d4b1\U0001d4cb\U0001d4e5\U0001d4ff\U0001d519\U0001d533\U0001d54d\U0001d567\U0001d581\U0001d59b\U0001d5b5\U0001d5cf\U0001d5e9\U0001d603\U0001d61d\U0001d637\U0001d651\U0001d66b\U0001d685\U0001d69f\U0001d6ce\U0001d708\U0001d742\U0001d77c\U0001d7b6\U0001e145',
    'w': '\u026f\u0448\u0461\u051c\u051d\u0561\u13b3\u13d4\u1d21\u29e2\u2cbd\ua4ea\ua7fa\uab83\uaba4\uff37\uff57\U0001170a\U0001170e\U0001170f\U000118e6\U000118ef\U0001ccec\U0001d20c\U0001d416\U0001d430\U0001d44a\U0001d464\U0001d47e\U0001d498\U0001d4b2\U0001d4cc\U0001d4e6\U0001d500\U0001d51a\U0001d534\U0001d54e\U0001d568\U0001d582\U0001d59c\U0001d5b6\U0001d5d0\U0001d5ea\U0001d604\U0001d61e\U0001d638\U0001d652\U0001d66c\U0001d686\U0001d6a0\U0001df7d',
    'x': '\xd7\u03a7\u0425\u0445\u1541\u157d\u166d\u166e\u16b7\u1763\u1bec\u1cf5\u2169\u2179\u2573\u292b\u292c\u2a2f\u2cac\u2d5d\ua4eb\ua7b3\uff38\uff58\U00010290\U000102b4\U00010317\U00010322\U00010527\U00010c13\U00010c82\U00010cc2\U00010cfc\U000118ec\U0001cced\U0001d417\U0001d431\U0001d44b\U0001d465\U0001d47f\U0001d499\U0001d4b3\U0001d4cd\U0001d4e7\U0001d501\U0001d51b\U0001d535\U0001d54f\U0001d569\U0001d583\U0001d59d\U0001d5b7\U0001d5d1\U0001d5eb\U0001d605\U0001d61f\U0001d639\U0001d653\U0001d66d\U0001d687\U0001d6a1\U0001d6be\U0001d6f8\U0001d732\U0001d76c\U0001d7a6',
    'y': '\u0263\u028f\u03a5\u03b3\u03d2\u0423\u0443\u04ae\u04af\u07cc\u10e7\u13a9\u13bd\u1d8c\u1eff\u213d\u2ca8\u2ca9\u311a\u4e2b\ua4ec\uab5a\uff39\uff59\U000102b2\U00010c20\U000118a4\U000118c4\U000118dc\U00016f43\U0001ccee\U0001d418\U0001d432\U0001d44c\U0001d466\U0001d480\U0001d49a\U0001d4b4\U0001d4ce\U0001d4e8\U0001d502\U0001d51c\U0001d536\U0001d550\U0001d56a\U0001d584\U0001d59e\U0001d5b8\U0001d5d2\U0001d5ec\U0001d606\U0001d620\U0001d63a\U0001d654\U0001d66e\U0001d688\U0001d6a2\U0001d6bc\U0001d6c4\U0001d6f6\U0001d6fe\U0001d730\U0001d738\U0001d76a\U0001d772\U0001d7a4\U0001d7ac',
    'z': '\u0396\u10cd\u13c3\u1d22\u2124\u2128\u2c6b\u2c6c\u2c8c\u2c8d\u2d2d\ua4dc\ua6c9\uab93\uff3a\uff5a\U000102f5\U00010507\U000118a9\U000118e5\U00011abc\U0001ccef\U0001d419\U0001d433\U0001d44d\U0001d467\U0001d481\U0001d49b\U0001d4b5\U0001d4cf\U0001d4e9\U0001d503\U0001d537\U0001d56b\U0001d585\U0001d59f\U0001d5b9\U0001d5d3\U0001d5ed\U0001d607\U0001d621\U0001d63b\U0001d655\U0001d66f\U0001d689\U0001d6a3\U0001d6ad\U0001d6e7\U0001d721\U0001d75b\U0001d795',
}
_CONF_TABLE = {ord(k): v for k, v in CONFUSABLES.items()}
for _t, _chars in UTS39_CONFUSABLES.items():
    for _c in _chars:
        _CONF_TABLE.setdefault(ord(_c), _t)
_CONF_TABLE.update({ord(k): v for k, v in CONFUSABLES.items() if k in "\u2010\u2011\u2012\u2212\ufe63\uff0d"})  # hyphen look-alikes keep priority
DIGIT_LOOK = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s"}
HARD_NEG = re.compile(r"\b(no|not|never|none|without|cannot|can't|isn't|aren't|doesn't|does not|do not|don't|won't|neither|nor|lack(?:s|ing)?|absent|unaudited|hasn't|haven't|wasn't|weren't|nothing|nobody|no one|nowhere)\b", re.I)
SOFT_NEG = re.compile(r"\b(until|when|once|if|unless|before|pending|awaiting|await(?:s)?|requires?|required|must|should|would|could|planned|goal|target|future|roadmap|draft|placeholder|hypothetical|illustrative|synthetic|will|how|seek(?:s|ing)?|pursue|pursuing|intend(?:s|ed)?|need(?:s|ed)?|invite|commission(?:ed)?|scope|scoped|open to)\b", re.I)
SOFT_KINDS = {"v8b-usage", "v8b-cover", "v8b-review", "v8-review", "v8-cert", "v8-insurance", "v8-usage", "v8-regulator", "xls-active", "mainnet-certified", "production-approved", "pilot-implied", "deployed", "v7-review", "v7-customers", "v7-contract", "v7-live", "v7-standards", "v7-graduated"}
SUBJECT_NEG = {"nothing", "nobody", "no one", "nowhere", "none"}  # v7: "Nothing here is audited" negates although "is" follows
COND_PREFIX = re.compile(r"\b(?:if|unless|whether|suppose|supposing|imagine|were)\b[^.;,:\n]{0,40}$", re.I)  # v7: "If Ward were insured we would say so"
NEG_EXEMPT_KINDS = {"v8b-record", "v8-record", "track-record", "double-negation", "denied-negation", "v7-record", "v7-findings"}  # "no incidents in production" is itself the claim; "not uninsured" says insured
CANCEL_AFTER_NEG = re.compile(r"^\W*(just|only|merely|simply|even|so much as)\b", re.I)
ASSERT_CUE = re.compile(r"\b(is|are|was|were|but|yet|however|it's)\b", re.I)
FALSE_THAT = re.compile(r"\b(false|untrue|not true|not the case|incorrect|wrong)\s+that\b", re.I)
CLAUSE_SPLIT = re.compile(r"[.;:!?\n]|\s[—–-]{1,2}\s|[—–]|[()]|,\s+(?:and |but |yet |though |although |while |however |it |we |they |which |ward )", re.I)

SOC = r"S\s?O\s?C\s?[- ]?(?:2|II\b|two\b)"
FORBIDDEN = [
    ("soc2", re.compile(rf"\b{SOC}\b[^.\n]{{0,40}}\b(audit\w*|certified|certification|complian(?:t|ce)|attest\w*|report|type (?:i|ii|1|2)|passed|achieved|complete[d]?|examination|certificad[oa]|zertifiziert|certifi[eé]e?)\b|\b(audited|certified|compliant|attested|complet\w+)\b[^.\n]{{0,25}}\b{SOC}\b", re.I)),
    ("insured", re.compile(r"(?<!un)(?<!un-)\b(fully |are |is |be |and )?(insured|insurance[- ]backed|underwritten|covered by insurance|bonded|FDIC[- ]insured)\b|\b(?:cyber|liability|crime|custody|professional|D&O|E&O)\s+(?:insurance|indemnity|cover(?:age)?)\b|\b(?:backed|protected|covered|secured|guaranteed|underwritten) by (?:an? |the |our )?(?:insurance (?:fund|pool|polic(?:y|ies))|insurers?)\b|\binsurance polic(?:y|ies) (?:with|from|issued|underwritten|by)\b|\bindemnity cover\b|\b(?:carries|carry|holds?|has|have|maintains?|purchased|bought)\s+(?:\w+ ){0,4}(?:insurance|indemnity)\b(?! (?:policy )?(?:is|are) (?:not|planned))|\b(?:covered|backed|protected|underwritten) by (?:an? |the |our )?(?:\w+ ){0,3}(?:insurance|liability|indemnity|underwrit\w+|insurer)\b|\bunderwriter\b|\b(?:errors and omissions|professional liability|liability) (?:insurance|policy|cover\w*)\b|\b(?:est|sont|is|ist|sind|est[aá]|es|è)\s+(?:enti[eè]rement |vollst[aä]ndig |totalmente |completamente )?(?:assur[eé]e?s?|versichert|asegurad[oa]s?|assicurat[oa])\b", re.I)),
    ("double-negation", re.compile(r"\b(?:not|never|isn't|aren't)\s+(?:un-?insured|un-?audited|un-?certified|un-?attested)\b", re.I)),
    ("track-record", re.compile(r"\b(?:zero|no|without any)\s+(?:\w+ )?(?:incidents?|outages?|downtime|breaches?|exploits?|losses)\s+in production\b|\bzero downtime\b|\b100\s?%\s*uptime\b|\bproven (?:in production|at scale)\b|\bbattle[- ]proven\b", re.I)),
    ("audited", re.compile(r"\b(?:has been|have been|was|were|is|are|been|independently|externally|fully|third[- ]party|professionally|formally)\s+audited\b|\baudited\s+(?:by|independently|externally)\b|\bindependently audited\b|\baudited by\b|\bhas passed (?:an? )?(?:independent |external |security )?audit\b|\b(?:security|code|smart[- ]contract|third[- ]party|external|independent|formal)\s+(?:audit|review|assessment)\s+(?:by|from|was|completed|passed)\b|\b(?:underwent|completed|passed|received|finished|obtained)\s+(?:its |an? |the |a full )?(?:[\w-]+ ){0,3}(?:security )?(?:audit|penetration test|pen test)\b|\b(?:is|are|was|and|be|been)\s+audit[- ](?:ready|complete|passed|cleared)\b|\bformally verified\b|\b(?:audit\w*|firms?|reviewers?)\b[^.\n]{0,30}\bsigned[- ]off\b|\bsigned[- ]off (?:on|by) (?:the )?(?:code\w*|protocol|contracts?|audit\w*)\b|\bvalidated by an? (?:outside|external|independent|third[- ]party) audit\w*|\b(?:is|are|was|were|been)\s+(?:audit[ée]e?|auditiert|auditad[oa]s?)\b|\b(?:clean|unqualified|favou?rable|positive)\s+(?:audit )?opinion\b|\b(?:external|third[- ]party|outside|independent)\s+(?:firm|assessor|auditor|reviewer)s?\b[^.\n]{0,40}\b(?:reviewed|assessed|found|signed|validated|verified|opinion|attest\w*)\b|\b(?:passed|completed|received|obtained|been through|underwent)\s+(?:an? |the |its )?(?:full |formal |external |independent |third[- ]party )*(?:security )?(?:review|assessment|certification|accreditation)\b(?! (?:is|will|would|to|process))|\b(?:external|independent)\s+code (?:audit|review)\b", re.I)),
    ("sla-figure", re.compile(r"\b(\d{2,3}(\.\d+)?\s?%\s*(uptime|availability|SLA)|SLA\s*(of|:|=|is|guarantees?)\s*\d|(?:\d+|two|three|four|five|six|seven)(\.\d+)?[\s-]*(nines)|(uptime|availability)(?: SLA)?\s*(of|:|=)\s*\d|\d{2,3}(?:\.\d+)?\s?(?:%|percent)\s*(?:\w+ ){0,2}(?:uptime|availability|SLA)|\d+[- ]?(?:hours?|hrs?|minutes?|mins?)\s+(?:\w+ ){0,2}(?:response|support|SLA|resolution)|\b24\s?[x/]\s?7\s?/\s?365\b|\b24\s?[x/]\s?7\s+(?:support|coverage|monitoring|on-call|availability)|(?:contractual )?service credits?\s+(?:apply|are|will)|\b(?:uptime|availability)\s+(?:guarantee|commitment|promise|target|SLA)\b[^.\n]{0,15}\d|\b(?:guarantees?|commits? to|promises?|offers?|provides?)\s+(?:a |an )?\d{2,3}(?:\.\d+)?\s?(?:%|percent)|\b24\s?[x/]\s?7\b(?![^.\n]{0,12}(?:support|coverage|monitoring)\s+(?:is|are) (?:not|no))|respon(d|se)\s+(within|in)\s+\d+\s*(hours?|hrs?|minutes?|business days?)|\d+\s*[- ]?(hour|hr|minute)\s+(response|support|SLA)|\b24\s?[x/]\s?7\s+support)", re.I)),
    ("sla-offer", re.compile(r"\b(Mainnet API with SLA|SLA[- ]backed|backed by (an )?SLA|guaranteed (uptime|availability|response)|enterprise SLA|our SLA)\b", re.I)),
    ("pilot-implied", re.compile(r"\b(active pilots?|live pilots?|pilot (customers?|is live|is running|is underway|in production)|completed (customer )?pilots?|running (a |the )?(customer )?pilots?|design[- ]partners? (is|are) (live|active|onboarded|running|signed)|design[- ]partner (live|active)|(our|first|current|existing|paying|signed|onboarded|one) (design[- ]partners?|customers?)\b|our (first |current |active )?pilots?\b|customers? (are|is|went) (live|using|in production|running|onboarded)|went live|trusted by|used by (customers|institutions|banks|lenders)|Northwind\b[^.\n()]{0,40}\b(is|are|was|were)\b[^.\n()]{0,30}\b(pilot|customer|live)\b|(completed|successful|live) customer (pilot|deployment|integration)|production customers?|in production with|live with (?:\w+ ){0,3}(customers?|banks?|institutions?|lenders?|clients?)|design[- ]partners?\s*[:\-–]\s*(?-i:[A-Z])|design[- ]partners? (include|includes|including|such as)|design[- ]partners? (in|at) production|(?:work|works|working) with (?:our |the )?design[- ]partners|(?:ward'?s|our) design[- ]partners?|\b\w+,? our design[- ]partner\b|(?:has|have|had) (?:paying|signed|onboarded) customers?|signed (?:our|its) first customer|first customer\b|\b(?:is|are|became|becomes|as) (?:a|an|our) design[- ]partners?\b(?![- ]+(?:pilots?|briefs?|outreach|packets?|playbooks?|programs?|qualification|proof|evidence))|\b(?:banks|lenders|customers|institutions|clients|users|exchanges)\b(?: \w+){0,2} (?:(?:rely|relies|depend|depends|count|run|runs) on Ward\b|(?:already |currently |now )(?:rely|relies|depend|depends|count|run|runs) on (?:Ward|it|us)\b|(?:rely|relies|depend|depends|count|run|runs) on (?:it|us) (?:every ?day|daily|today|now)\b)|onboarded (?:its |our |the )?(?:first |\d+ |\w+ )?(?:institutions?|customers?|banks?|lenders?|clients?)|\b(?:is|are|was|were|became|as) (?:a|an|our|one of our) (?:Ward |paying |pilot |production )?(?:customers?|clients?)\b(?! of)|\bpilots?\s+(?:with\s+[\w ]{1,30}?\s+)?(?:has |have |was |were )?(?:completed|concluded|finished|succeeded|passed)\b|\b(?:has|have|had|got|received|closed|holds?)\s+(?:now\s+)?(?:a |an |its |our |the )?signed (?:order form|contract|agreement|MSA|LOI|SOW)\b|\bWard customers?\b|\b(?:our )?customers?\s*[:\-–]\s*(?-i:[A-Z])|\b(?:currently )?processing (?:live|real|production) (?:\w+ ){0,3}(?:for|with)\b|\b(?:\d+|several|many|multiple|dozens of) (?:enterprise |paying |production |live )?(?:customers|clients|institutions|banks|lenders|deployments|integrations)\b(?! (?:can|could|may|might|would|will|should))|\b(?:has|have|got) (?:an? |one |another )?(?:live |real |paying |production |enterprise |active )+(?:customers?|clients?|deployments?|institutional clients?)\b|\b(?:paying|institutional|live) (?:customers?|clients?|lending desks?) (?:include|includes|such as|like)\b|\b(?:with|for|to) (?:its |our |the |a |real )?(?:paying|live|real) (?:customers?|clients?|lending desks?)\b(?! (?:data|funds? are not))|\b(?:institutions?|lenders?|banks?|customers?|users?) (?:depend|rely)\s+on\s+Ward\b|\brelied (?:up)?on by\b|\btrusted (?:choice|partner|standard|platform) of\b|\b(?:institutions?|lenders?|banks?) (?:choose|chose|trust|use|adopt(?:ed)?) Ward\b|\bWard (?:is|has been) (?:already )?(?:used|adopted|chosen|relied (?:up)?on) by\b|\bready for (?:institutional|customer) use\b(?! (?:once|when|after|until))|\bhas (?:had )?no (?:security )?(?:incidents?|breaches?|losses)\b|\bnever (?:had|suffered|experienced) (?:an? )?(?:incident|breach|exploit|loss)\b|\b(?:serves?|serving|handles?|handling|runs?|operates?|operating) (?:\w+ ){0,3}(?:real|live|production|critical|mission-critical) (?:\w+ ){0,2}(?:lenders?|banks?|desks?|customers?|institutions?|workflows?|infrastructure|loans?)\b)", re.I)),
    ("deployed", re.compile(r"\b(?:deployed|running|live|operating|operational|used|in use)\s+(?:in|on)\s+(?:production|(?:the )?(?:xrpl )?mainnet)\b|\bin production (?:at|with|by|for)\b|\bused in production\b|\brunning on (?:xrpl )?mainnet since\b|\bdeployed to (?:xrpl )?mainnet\b|\bdeployed to production\b|\bprotects?\s+(?:real |actual )?(?:customer|user|client|depositor|institutional)s?'?\s*(?:funds|assets|deposits|capital|money)|\bsecures? \$\s?\d|\b(?:runs?|running|operates?|operating|provides?|providing) (?:an? )?(?:live |production )?(?:production )?service (?:for|to) (?:banks|lenders|customers|institutions|clients)|\b(?:using|uses|used) (?:\w+ ){0,2}in production\b|\bin production since\b|\bgenerally available\b|\bopen for business\b|\bfull(?:y)? (?:mainnet )?launch(?:ed)?\b|\b(?:completed|had) (?:a |the )?(?:full |formal )?(?:mainnet )?launch\b|\bgone live\b|\bhas launched\b|\bnow serves?\b|\bgeneral availability\b|\ben producci[oó]n\b|\bin Produktion\b|\bin use by (?:banks|lenders|customers|institutions)|\bused by real\b|\bthe production (?:release|standard)\b|\bproduction (?:release|standard)\b[^.\n]{0,40}\b(?:shipped|released|available|launched)\b", re.I)),
    ("assurance-claims", re.compile(r"\bISO[ /-]?27001\b|\b(?:passed|completed|underwent|cleared|clean)\b[^.\n]{0,25}\b(?:penetration[- ]tests?|pen[- ]?tests?)\b|\bregulator[- ](?:approved|cleared|authori[sz]ed|licensed)\b|\bWard\b[^.\n]{0,30}\b(?:is|are|been|being) (?:an? )?(?:fully |duly )?(?:licensed|regulated|registered|authori[sz]ed)\b|\b(?:fully )?compliant with (?:MiCA|GDPR|FATF|SEC|MAS|FCA)\b|\bMiCA[- ](?:compliant|licensed|authori[sz]ed)\b|\b(?:bank|institutional)[- ]grade\b|\benterprise[- ]ready\b|\bbattle[- ]tested\b|\bISO[ /-]?(?:9001|certified|compliant)\b|\b(?:GDPR|SOC|HIPAA|PCI|FATF|MiCA|ISO)[- ](?:compliant|certified)\b|\bpenetration[- ]tested\b|\bpen[- ]tested\b|\b(?:approved|cleared|authori[sz]ed|licensed|blessed) by (?:the )?(?:SEC|CFTC|FCA|MAS|FINMA|OCC|FinCEN|NYDFS|ESMA|regulators?)\b|\bpre-?approved\b|\b(?:satisf(?:y|ies|ied)|meets?|met|fulfil\w*) (?:the )?(?:MiCA|GDPR|FATF|regulatory)\b|\bcleared (?:a |the )?(?:compliance|regulatory|legal) review\b|\bSystem (?:and|&) Organi[sz]ation Controls?\s*(?:2|II|two)?[^.\n]{0,30}(?:attest\w*|report|complian\w*|certif\w*|audit\w*|examination|type)\b|\b(?:officially|fully|formally|independently|externally) (?:certified|accredited|approved)\b|\bregulated entity\b|\b(?:SOC|assurance|audit|attestation|compliance)\s+report\s+(?:is|are)\s+(?:available|public|published|on request)\b|\b(?:SOC|assurance|audit|attestation)\s+reports?\s+(?:available|on request|under NDA)\b|\b(?:approved|accredited|cleared) (?:for use )?by (?:institutions|banks|lenders|customers|regulators?|the regulator)\b|\b(?:authori[sz]ed|supervised|approved)\s+(?:and|&)\s+(?:supervised|authori[sz]ed|approved)\s+by\b|\bformally approved\b|\bis (?:formally |officially |independently |externally )(?:approved|accredited|certified)\b(?! (?:by Ward|for Ward))", re.I)),
    ("golden-regen", re.compile(r"\b(current(ly)?|today'?s?|this|latest)\b[^.\n]{0,40}\b(WARD|engine|source|code|build|release)\b[^.\n]{0,40}\b(regenerat\w*|reproduc\w*|re-?creat\w*|re-?deriv\w*|rebuild\w*)\b[^.\n]{0,60}\bgolden\b|\bgolden (receipts?|fixtures?)\b[^.\n]{0,60}\b(regenerat\w*|reproduc\w*|re-?creat\w*)\b[^.\n]{0,40}\b(exact\w*|byte[- ]?(for[- ]byte|identical\w*)|identical\w*)\b|\bregenerat\w*\b[^.\n]{0,40}\bhistorical golden", re.I)),
    ("mainnet-certified", re.compile(r"\b(mainnet[- ](certified|approved|ready|live|launched|deployed)|(certified|approved|ready|live|launched|deployed) (for|on) (xrpl )?mainnet|Ward[- ]certified|conformance[- ]certified|certified (by|for) Ward|certified on mainnet|certified by (?:an? )?(?:independent |third[- ]party|external|outside)\b|mainnet[- ](?:valid|proven|grade)|(?:live|launched|deployed|operational|running|available) (?:for|on|in) (?:the )?(?:xrpl |xrp ledger |xrp |main ?)(?:mainnet|main[- ]?network|network|ledger)(?!\s*(?:dev|test)net)|(?:open|available|operating|operational|running) (?:for business )?(?:on|in|at) (?:the )?(?:xrp ledger |xrpl )?main(?:net|[- ]?network)(?! (?:is|are) (?:not|planned)))\b", re.I)),
    ("production-approved", re.compile(r"\b(production[- ](approved|ready|grade|certified|cleared)|(approved|cleared|ready|certified) for production|approved for (mainnet|production)( use)?|cleared for production)\b", re.I)),
    ("xls-active", re.compile(r"\bXLS-?(?:65|66)d?\b(?![- ]?(?:dependent|enabled|gated|capable|ready))(?:\s*(?:and|&|/|,)\s*(?:XLS-?)?(?:65|66)\b)?(?:[^.;\n]{0,40}?(?<![-\w])(?:live|active|enabled|activated)\b|[^.;\n]{0,45}?\bavailable (?:on|in) (?:xrpl )?mainnet)|(?<![-\w])\b(?:active|enabled|live|activated)\b[^.;\n]{0,25}XLS-?(?:65|66)\b|\b(?:lending (?:protocol|amendment)|single[- ]asset[- ]vaults?)\b[^.;\n]{0,15}\b(?:is|are|has been|has|now) (?:now )?(?:live|active|enabled|activated)\b|\bXLS-?(?:65|66)d?\b[^.;\n]{0,40}\b(?:enabled|live|active) on (?:the )?(?:xrp ledger|xrpl|mainnet)\b", re.I)),
    # ---- v7 (review set 5): wording families found missing. Each is a phrase pattern; none understands meaning. ----
    ("v7-review", re.compile(r"\b(?:reviewed|assessed|examined|inspected|vetted|tested)\b[^.;\n]{0,25}\bby (?:an? |the )?(?:external|independent|outside|third[- ]party)\b|\b(?:completed|passed|underwent|received|obtained|has|have|had|with|after|through|cleared)\s+(?:an? |the |its |our )?(?:\w+ )?(?:external|independent|third[- ]party|outside)\s+security\s+(?:assessment|review|examination)\b(?![^.\n]{0,25}\b(?:is|are|will be|would be|to be) (?:planned|pending|scheduled|not|future))|\b(?:gone|went|passed|been|goes) through (?:an? )?(?:external|independent|third[- ]party|outside)\b|\b(?:unqualified|clean|favou?rable)\s+(?:attestation|opinion|report)\b|\battestation over\b|\bAICPA\b|\bSOC\s?[123]?\s+reports?\b|\breviewed line by line\b|\b(?:Zellic|Halborn|CertiK|Trail of Bits|OpenZeppelin|Quantstamp|Least Authority|NCC Group|Cure53|Spearbit|Code4rena|Sherlock|Hacken|Peckshield|Consensys Diligence|Deloitte|PwC|KPMG|EY|Ernst & Young|Schellman|A-LIGN|Prescient Assurance)\b[^.;\n]{0,40}\b(?:review\w*|audit\w*|assess\w*|report|clean|passed|signed|attest\w*|verified)\b", re.I)),
    ("v7-standards", re.compile(r"\bISO(?:/IEC)?[ -]?2700[12]\b|\b(?:PCI[- ]DSS|HIPAA|FedRAMP|CCPA|SOX|NIST[- ]800-53|CSA STAR|SOC ?[123])\b[^.\n]{0,25}\b(?:compliant|certified|complian\w+|attested|authori[sz]ed)\b|\b(?:compliant|certified|compliance)\s+(?:with|to)\s+(?:the )?(?:PCI|HIPAA|FedRAMP|CCPA|SOX|NIST|GDPR|MiCA)\b|\bcompl(?:y|ies|ied) with\b[^.\n]{0,30}\b(?:MiCA|GDPR|PCI|HIPAA|FATF|SEC|MAS|FCA|EU|regime|regulations?)\b", re.I)),
    ("v7-findings", re.compile(r"\bcame back clean\b|\bno (?:critical|high|major|material|significant) (?:findings|issues|vulnerabilities)\b(?! (?:were|was|have been) (?:found|reported) (?:yet|so far))(?![^.\n]{0,30}\b(?:expected|hoped|aim|goal|target))", re.I)),
    ("v7-insurance", re.compile(r"\breimburs\w+\b[^.\n]{0,40}\b(?:by|from)\s+(?:our |the |an? )?(?:underwriters?|insurers?|insurance)\b|\b(?:our|the) underwriters?\b|\b(?:cyber|liability|crime|D&O|E&O|professional)\s+polic(?:y|ies)\b|\bunderwritten by\b", re.I)),
    ("v7-uptime", re.compile(r"\b(?:uptime|availability)\b[^.\n]{0,50}\b\d{2,3}(?:\.\d+)?\s?(?:%|percent)|\b(?:financially[- ]backed|contractual|guaranteed|committed|formal) service[- ]level\b|\bbacked by (?:an? )?(?:[\w-]+ ){0,3}(?:service[- ]level agreement|SLA)\b|\bguaranteed to be available\b|\bavailable 24\s?[/x]\s?7\b|\b24\s?[/x]\s?7\s?(?:availability|uptime)\b", re.I)),
    ("v7-customers", re.compile(r"\b(?:lenders?|banks?|customers?|clients?|institutions?|funds?)\b[^.;,\n]{0,30}\b(?:have|has|are|is|now)?\s*(?:already |now |all )?(?:integrated|adopted|deployed|onboarded|rel(?:y|ies) (?:on|upon)|trust(?:s|ed)?|use[sd]?|using)\s+(?:\w+ ){0,2}Ward\b|\b(?:banks?|lenders?|funds?|customers?|clients?|institutions?)\s+(?:\w+ ){0,3}use\s+Ward\b|\bintegrated Ward\b|\bprotect(?:s|ing|ed)?\s+(?:real |actual |live )?(?:customer|user|client|depositor|institutional)s?'?\s*(?:\w+\s)?(?:funds|assets|deposits|capital|money|positions)\b|\b(?:our|its|ward'?s)\s+(?:early|first|initial|existing|current|paying|pilot|enterprise|institutional)\s+(?:customers?|users|clients|adopters)\b|\bclosed (?:our |its )?(?:first )?(?:\w+ )?(?:deal|pilot|customer|contract)\b", re.I)),
    ("v7-contract", re.compile(r"\b(?:has|have|had|holds?|with|got|received|obtained|closed|secured)\s+(?:an? |our |its |the )?(?:signed|executed|countersigned)\s+(?:\w+ ){0,2}(?:master services agreement|MSA|order form|customer (?:contract|agreement)|LOI|letter of intent|contract|agreement)\b(?!\s+(?:template|draft|sample|example|placeholder))", re.I)),
    ("v7-live", re.compile(r"\blaunched (?:publicly|on|in|at)\b|\b(?:ward(?: protocol)?|it|we|the protocol|the platform|the service) (?:is|are) (?:now |already |fully |currently )?in production\b|\b(?:now|already|fully) operational\b|\bnow live\b(?!\s+(?:elsewhere|here|there)\b)|\bgoes live\b|\bWard(?: Protocol)?\b[^.\n]{0,20}\b(?:is|are) (?:now |already |fully |currently )?live\b(?!\s+(?:on|in|against) (?:the )?(?:dev|test|sandbox))|\b(?:runs|running|operates|works|lives|settles|processes)\b[^.\n]{0,20}\b(?:on|in) (?:the )?(?:XRPL |XRP Ledger )?mainnet\b|\b(?:on|in) mainnet today\b|\b(?:processing|processes|processed|settl(?:es|ing|ed)|handl(?:es|ing|ed)|moves?|moving|moved)\s+(?:\w+ ){0,2}(?:real|live|actual|customer)\s+(?:\w+ ){0,2}(?:settlements?|funds|money|payments?|transactions?|loans?|claims?|escrows?|volume)\b", re.I)),
    ("v7-record", re.compile(r"\bperfect (?:security|safety|uptime|track) record\b|\bno funds? (?:have|has) (?:ever )?been (?:lost|stolen|at risk)\b|\b(?:security|Ward|protocol|platform|code|contracts?)\b[^.\n]{0,30}\b(?:has|have|been|was|were|is|are) independently (?:confirmed|validated|reviewed|assessed|attested|tested)\b|\blegal opinion\b[^.\n]{0,40}\b(?:confirms?|concludes?|states?|says|finds?)\b", re.I)),
    ("v7-graduated", re.compile(r"\bno longer (?:experimental|a prototype|testnet[- ]only|pre-?production|in beta|pre-?launch)\b|\bthe audited\b|\bour audited\b|\baudited (?:XRPL|lending|resolution|protocol|platform)\b", re.I)),
    ("denied-negation", re.compile(r"\b(?:no denying|can(?:'|no)t deny|nobody can (?:say|deny|claim)|undeniabl\w+|far from (?:being )?(?:un-?\w+|without|lacking)|anything but (?:un-?\w+|without|lacking)|(?:wrong|untrue|false|misleading|incorrect|inaccurate) (?:to|that)(?: \w+){0,3} (?:say|claim|state|suggest|describe|call|think)[^.;\n]{0,60}\b(?:no|not|never|without|lacks?|pre-?\w+)\b|it(?: i|')s (?:simply |just |plainly )?(?:not |un)true that\b[^.;\n]{0,40}\b(?:lack|no|not|without|hasn'?t|pre-?\w+)|no truth to the (?:idea|claim|suggestion) that\b[^.;\n]{0,40}\b(?:no|not|never|without|lacks?)|never said\b[^.;\n]{0,40}\bnot\b|not the case that\b[^.;\n]{0,40}\b(?:no|not|never|without|lacks?))\b", re.I)),
    ("v7-golden", re.compile(r"\b(?:build|engine|ward|code|source|release|implementation)\b[^.\n]{0,30}\b(?:regenerat\w*|reproduc\w*|re-?creat\w*)\b[^.\n]{0,30}\b(?:every|all|each|the)\b[^.\n]{0,25}\b(?:golden|historical|receipts?)\b(?!(?:[^.\n]|\.\d){0,140}?\b(?:not|no longer|never)\b)|\b(?:golden|historical) (?:receipts?|fixtures?)\b[^.\n]{0,40}\bare (?:all )?(?:regenerat\w*|reproduc\w*)\b[^.\n]{0,25}\b(?:by|from|with)\b[^.\n]{0,20}\b(?:engine|build|code|source|ward)\b(?!(?:[^.\n]|\.\d){0,140}?\b(?:not|no longer|never)\b)|\bregenerat\w*\b[^.\n]{0,25}\b(?:every|all)\b[^.\n]{0,20}\bgoldens?\b(?![^.\n]{0,80}\b(?:not|no longer|never)\b)", re.I)),
    # ---- v8 (review set 6): paraphrase families. Review set 6 measured 74% of paraphrased claims missed by v7. These are MORE PHRASE PATTERNS, written after the author saw the v8 held-out
    # misses and then review set 6's misses, so they are tuned to those shapes and the after-figures are NOT blind. A paraphrase nobody listed still passes. ----
    ("v8-review", re.compile(r"\bclean bill of health\b|\b(?:signed off|sign-off|sign off) (?:on|by|from)\b[^.\n]{0,40}\b(?:audit\w*|firm|reviewer|regulators?|agenc\w+|experts?|testers?)\b|\b(?:audit\w*|firms?|reviewers?|regulators?|agenc\w+|experts?|testers?|watchdogs?)\b[^.\n]{0,25}\bsigned off\b|\b(?:cleared|passed|completed|survived)\s+(?:an? |the |its |our |their )?(?:\w+ ){0,3}(?:security |external |independent |outside )+(?:examination|review|exercise|assessment|inspection|penetration \w+)\b|\bpassed the (?:outside|external|independent|third[- ]party) \w+(?:'s)? (?:examination|review|exercise|audit)\b|\b(?:independent |external |outside |third[- ]party )(?:testers?|reviewers?|auditors?|experts?|researchers?) (?:found|have found|reported) (?:nothing|no (?:issues|problems|flaws|vulnerabilities))\b|\bfound nothing wrong\b|\b(?:auditors?|reviewers?|examiners?)\b[^.\n]{0,25}\b(?:reviewed and approved|approved)\b[^.\n]{0,40}\b(?:logic|contracts?|code|protocol|escrow|system)\b|\b(?:reviewed|examined|checked|inspected)\b[^.\n]{0,30}\b(?:line by line|end[- ]to[- ]end)\b[^.\n]{0,20}\bby (?:an? |the )?(?:well-known |leading |top |outside |external |independent )*(?:security|audit\w*|accounting|consult\w*)[ \w-]{0,20}(?:firm|company|team|experts?)\b|\battested to (?:our|its|ward's|the) (?:controls|security|processes)\b|\b(?:top[- ](?:four|4|tier)|big[- ](?:four|4)) (?:accounting |audit\w* )?firm\b|\bgone through\b[^.\n]{0,30}\bcode\b[^.\n]{0,40}\b(?:clean|approved|passed|health)\b|\b(?:external|independent|outside|third[- ]party) (?:firm|experts?|reviewers?|auditors?|examiners?) (?:has|have) (?:gone through|reviewed|examined|checked)\b[^.\n]{0,60}\b(?:clean|approved|passed|health|nothing wrong)\b", re.I)),
    ("v8-cert", re.compile(r"\bcertificate (?:proving|showing|confirming|attesting)\b[^.\n]{0,30}\b(?:controls?|security|complian\w+|examin\w+)\b|\b(?:official |formal )?compliance (?:stamp|seal|badge|mark)\b|\b(?:certification|accreditation|attestation) (?:from|by) (?:an? |the )?(?:recogni[sz]ed|accredited|official|independent|external)\b[^.\n]{0,30}\b(?:is|are|was|has been) (?:current|valid|active|held)\b|\bformal (?:assurance|attestation|certification) engagement\b|\bsatisf\w+ the requirements of\b[^.\n]{0,30}\b(?:assurance|attestation|certification|audit)\b", re.I)),
    ("v8-insurance", re.compile(r"\b(?:an? |the )?insurer (?:stands|is standing) behind\b|\binsurance (?:cover(?:age)?|policy) (?:applies|extends|protects|covers)\b|\b(?:fully|completely) covered (?:if|when|against)\b|\b(?:would be|will be|are|is) (?:reimbursed|compensated|made whole) (?:under|by|through) (?:our |the |an? )?(?:cover(?:age)?|polic(?:y|ies)|insur\w+|backstop|carrier)\b|\b(?:third[- ]party|external|independent) (?:backstop|guarantor|guarantee|carrier)\b[^.\n]{0,30}\b(?:protect\w*|cover\w*|backs?|backing)\b|\bprotected (?:against|from) loss by\b|\bbacked by an? (?:insurance )?(?:insurer|carrier|insurance carrier)\b|\bunderwritten by an? (?:carrier|insurer)\b|\b(?:policy|cover(?:age)?) underwritten by\b|\bmoney (?:sits |is )?behind\b[^.\n]{0,40}\b(?:polic(?:y|ies)|insur\w+|carrier)\b", re.I)),
    ("v8-usage", re.compile(r"\b(?:real|actual|live|paying|client|customer)\s+(?:customers?|clients?|businesses|firms|institutions|funds|money|balances|assets|payments|volume|users)\b[^.\n]{0,40}\b(?:use[sd]?|using|run(?:s|ning)?|settl\w+|process\w*|handl\w+|hold\w*|trust\w*|rel(?:y|ies|ied))\b[^.\n]{0,20}\bWard\b|\bWard\b[^.\n]{0,40}\b(?:is |are |has been |have been |was )?(?:used|running|operating|settling|processing|handling|trusted with|holding)\b[^.\n]{0,40}\b(?:real|actual|live|client|customer|paying)\s+(?:customers?|clients?|businesses|firms|institutions|funds|money|balances|assets|payments|volume|users|transactions)\b|\bprocessing (?:transactions|payments|settlements) for real\b|\b(?:financial|banking|lending|fintech) (?:companies|firms|institutions|houses) (?:use|are using|rely on|run)\b[^.\n]{0,30}\bWard\b|\bWard\b[^.\n]{0,30}\b(?:in|for) commercial (?:use|service)\b|\b(?:operating|running|live|working) in the wild\b|\bin the wild with (?:real )?(?:money|funds|users)\b|\b(?:has|have) been (?:deployed|adopted|integrated) by (?:banks?|lenders?|funds?|institutions?|firms?|customers?)\b|\bused in anger\b|\b(?:partners?|institutions?|firms?|lenders?|banks?)\b[^.\n]{0,25}\b(?:are |is )?(?:operating|transacting|settling) (?:on|with) Ward\b|\bWard is (?:now )?(?:a |the )?production (?:system|service|platform)\b|\b(?:our|the|a)\s+production (?:deployment|system|service) (?:has been|is|was) running\b|\b(?:live|monthly|daily) (?:volume|throughput) on Ward\b|\bliv(?:e|ing) (?:with|alongside) (?:two |three |four |five |several |\d+ )?(?:lenders?|banks?|customers?|clients?|institutions?)\b|\b(?:already |now )?live with (?:two |three |four |five |several |\d+ |a |an |our first )?(?:lenders?|banks?|customers?|clients?|institutions?)\b|\b(?:first|second|third) (?:paying |institutional |enterprise |commercial )+(?:client|customer|user)\b[^.\n]{0,30}\b(?:came|signed|joined|went|onboard\w*|live)\b|\b(?:completed|finished) onboarding\b[^.\n]{0,40}\b(?:client|customer|institution)\b|\bwent live (?:for|with) (?:customers|clients|users)\b|\bprocessing (?:real |live )?(?:transactions|payments|settlements)\b[^.\n]{0,30}\bfor (?:real |paying |live )(?:businesses|customers|clients|firms|users)\b", re.I)),
    ("v8-record", re.compile(r"\b(?:never|not once|has never) (?:lost|leaked|exposed|mishandled|lost track of)\b[^.\n]{0,25}\b(?:funds?|money|assets?|balances?)\b|\b(?:flawless|perfect|spotless|unblemished)\b[^.\n]{0,20}\b(?:uptime|record|history|availability|track record)\b|\buptime\b[^.\n]{0,25}\b(?:flawless|perfect|spotless|unblemished)\b|\bno downtime\b(?:[^.\n]{0,20}\b(?:to date|so far|ever|since)\b)|\bzero downtime\b|\bsafely handl\w+\b[^.\n]{0,20}\b(?:customer|client|user) (?:money|funds|assets)\b|\btrack record of (?:safely |securely )?(?:handling|holding|protecting)\b", re.I)),
    ("v8-regulator", re.compile(r"\bregulators?\b[^.\n]{0,25}\b(?:have |has )?(?:cleared|approved|authori[sz]ed|licen[cs]ed|signed off on)\b[^.\n]{0,40}\b(?:Ward|to operate|the protocol|the platform|coverage model|our)\b|\b(?:checked|reviewed) and (?:approved|cleared) by (?:the |a |an )?(?:regulator|regulators|authority|SEC|FCA|MAS|FINMA)\b|\b(?:Ward|the protocol|the platform) (?:is|are) (?:now |already )?(?:fully |duly )?(?:licen[cs]ed|regulated|registered)\b(?![^.\n]{0,20}\b(?:not|never|no)\b)|\bwatchdog agenc\w+\b[^.\n]{0,25}\b(?:signed off|approved|cleared)\b", re.I)),
    # ---- v8b: shapes from review set 6's 120 fresh claims, added AFTER I read its misses. These are regression patterns for THOSE shapes, not a measurement of anything. ----
    ("v8b-usage", re.compile(r"\b(?:running|operating|working|live|settling|serving|processing)\b[^.\n]{0,25}\b(?:against|with|on|for|to|on top of)\s+(?:real|live|actual|paying)\s+(?:customer |client |user )?(?:money|funds|assets|balances|institutions|customers|clients|users)\b|\breal (?:payouts?|claims?|settlements?) (?:have been|were|are) (?:executed|paid|settled|processed|made)\b|\b(?:completed|processed|paid out|settled|executed)\s+(?:its |our |the )?(?:first |real |live |production |\d+ )*(?:production |real |live )?(?:claims?|payouts?|settlements?|policyholder claims?)\b[^.\n]{0,30}\b(?:production|mainnet|policyholders?|for months|on time|in full|real)\b|\b(?:mainnet|production) (?:deployment|system|service) has (?:processed|settled|paid|handled)\b|\bpaid out claims\b|\b(?:already |now )?invoicing (?:paying )?(?:customers|clients)\b|\b(?:signed up|signed on|joined|came on board|onboarded) as (?:paying|commercial|enterprise|institutional) (?:clients?|customers?)\b|\b(?:paying|commercial|enterprise) (?:clients?|customers?|institutions?) (?:right now|today|already)\b|\bserving paying\b|\b(?:our|its|ward's) (?:clients|customers|users) include\b|\broute[sd]? (?:their |its )?(?:\w+ ){0,2}risk through Ward\b|\brel(?:y|ies|ied) on Ward (?:receipts?|certificates?|attestations?)\b[^.\n]{0,30}\b(?:books|accounts|reporting|reserves|audit\w*)\b|\brolled out to production\b|\b(?:everything|all)\b[^.\n]{0,30}\b(?:is |are )?live and working\b|\bcommercially available\b|\bout of (?:beta|alpha|preview)\b|\bno longer (?:a )?(?:prototype|experimental|beta)\b[^.\n]{0,40}\b(?:live|carries?|production|customers?|balances)\b|\bcarries live (?:balances|funds|money)\b|\bmajor (?:exchanges?|banks?|custodians?|funds?|issuers?) (?:route|use|rely|run|trust)\b|\b(?:well-known|leading|major|top) (?:custodian|exchange|bank|fund|issuer|asset manager)s? (?:relies?|uses?|trust\w*)\b|\basset managers? signed up\b|\bdeployed today into a live\b|\bcan be deployed today\b|\bready for (?:live )?(?:treasury|production|institutional) (?:use|deployment)\b|\b(?:chosen|selected|adopted) by (?:leading|major|top) (?:issuers?|banks?|exchanges?|institutions?)\b|\bmarket standard\b", re.I)),
    ("v8b-cover", re.compile(r"\b(?:investors?|depositors?|lenders?|users?|holders?)\b[^.\n]{0,40}\b(?:are |is |get |will get |would get )(?:protected|covered|reimbursed|made whole|paid back|repaid)\b[^.\n]{0,30}\b(?:if|when|in case|should)\b|\bget (?:their|the) money back\b|\b(?:carrier|insurer|underwriter|reinsurer)s? (?:stands? behind|backs?|have priced|has priced|bound|have bound)\b|\bpriced and bound cover\b|\bbacking of an? (?:top[- ]tier |leading |major )?(?:reinsurer|insurer|carrier|underwriter)\b|\b(?:losses|shortfalls?)\b[^.\n]{0,70}\b(?:are |is )?(?:made whole|reimbursed|covered)\b|\breimburses (?:lenders|depositors|investors|users|holders)\b|\bstands? behind (?:vault |every |all )?(?:vault )?(?:deposits?|vaults?|policies|positions)\b|\bfunded reserve\b|\b(?:capital|reserve) pool of real assets\b|\breserve fund (?:is |are )?(?:fully )?funded\b|\breserve (?:fully )?covers\b|\bbacked by a (?:capital |reserve )(?:fund|pool)\b|\bcoverage is active\b|\bcoverage limit\b[^.\n]{0,10}\$|\$[\d,.]+\s?(?:m|k|million|thousand)?\s+(?:per vault|per policy|of coverage)\b|\bfully (?:funded|reserved|collateri[sz]ed) (?:reserve|pool|fund)\b", re.I)),
    ("v8b-review", re.compile(r"\b(?:formal|full|complete|rigorous|external|independent|third[- ]party) (?:third[- ]party |external |independent )?(?:penetration|pen[- ]?test|security|code) (?:exercise|test|review|audit|assessment)\b[^.\n]{0,30}\b(?:came out clean|clean|passed|completed|no findings)\b|\bcame out clean\b|\b(?:validated|verified|confirmed|checked|attested|endorsed|certified|approved|notari[sz]ed)\b[^.\n]{0,25}\bby (?:an? |the )?(?:major |accredited |leading |independent |top |licensed |well-known |outside )*(?:accounting firm|audit firm|auditors?|lab(?:oratory)?|notary|law firm|counsel|accredited \w+|assessors?)\b|\bpassed (?:a |the |its )?(?:compliance|regulatory|legal|security) review\b|\blegal counsel (?:has |have )?(?:confirmed|concluded|advised|opined)\b|\b(?:SEC|CFTC|FCA|FINMA|MAS|regulators?) (?:has |have )?(?:looked at|reviewed|examined)\b[^.\n]{0,30}\b(?:no objections?|raised no|no concerns?|comfortable|fine with)\b|\bmoney[- ]transmitter licen[cs]e\b|\bregulatory sandbox approval\b|\bunder a formal regulatory\b|\bmeets? bank[- ](?:level|grade)\b|\bcertified product\b|\bseal of approval\b|\b(?:has |have )?signed off on the design\b|\bcleared a formal\b[^.\n]{0,30}\b(?:compliance|review|audit)\b|\baccepted by (?:auditors|regulators|banks|exchanges)\b|\bproof of reserves\b[^.\n]{0,30}\b(?:accepted|used by|recogni[sz]ed)\b|\b(?:accepted|recogni[sz]ed) (?:by \w+ )?as proof of reserves\b|\bendorsed by (?:leading|major|top|well-known)\b|\breproduced all of our results\b|\bindependently reproduced\b[^.\n]{0,40}\b(?:production|all)\b", re.I)),
    ("v8b-record", re.compile(r"\b(?:stayed|remained|been|kept) (?:online|up|available|running)\b[^.\n]{0,25}\b(?:without (?:interruption|a single|any)|for the (?:last|past) (?:year|\w+ months))\b|\bnever (?:had|suffered|experienced|seen) (?:a |an |any )?(?:single )?(?:outage|incident|breach|failure|downtime)s?\b|\bbattle[- ]hardened\b|\bcontinuous(?:ly)? green\b|\b(?:no|zero) (?:outages?|incidents?|breaches?)\b[^.\n]{0,30}\b(?:no|zero) (?:incidents?|outages?|breaches?)\b|\bno customer (?:has |have )?ever lost\b|\bnever fails? to pay\b|\b(?:uptime|availability)[\w ]{0,30}[:=]\s*100\s?%|\bthousands of (?:live |real |production )?transactions\b", re.I)),
]

# a negation must precede the claim closely; these kinds also accept conditional / future framing
NEG_CLAIM = re.compile(r"\b(?:no|not|never|cannot|can't|without|don't|do not|does not|must not|should not|avoid|nor|neither)\b[^.;\n]{0,25}\b(?:claim\w*|statement|state|say|imply|implies|represent\w*|suggest\w*|assert\w*|present\w*)\b|\b(?:over-?claim\w*|any (?:claim|statement)s?|claims? (?:that|of)|must not be (?:represented|described|presented))\b", re.I)


NOT_A_NEGATION = re.compile(r"^\W*(?:prevent\w*\b|stop\w*\b|keep\w*\b|hinder\w*\b|to (?:stop|prevent)\b|before\b|only\b|doubt\b|question\b|wonder\b|one\b|body\b|less than\b|surprisingly\b|coincidence\b|to mention\b)", re.I)


ASPIRATION = re.compile(r"\b(?:hop(?:e|es|ed|ing)|wish(?:es|ed|ing)?|aim(?:s|ed|ing)?|want(?:s|ed|ing)?|would like|looking|trying|going|plan(?:s|ned|ning)?|intend(?:s|ed|ing)?|seek(?:s|ing)?|expect(?:s|ed|ing)?)\s+(?:to|for)\s+(?:be|get|obtain|have|receive|undergo|pursue|achieve|earn)\b[^.;\n]{0,12}$", re.I)  # v8: "we are hoping to be audited" is not a claim. Narrow on purpose: only a wish verb + to + be/get/obtain, immediately before the claim (a broad "hope" window also silenced real hits in the seed data)


def _negated(kind: str, clause: str, m: re.Match) -> bool:
    if kind in NEG_EXEMPT_KINDS or FALSE_THAT.search(clause):
        return False
    if ASPIRATION.search(clause[max(0, m.start() - 40): m.start()]):
        return True
    if NEG_CLAIM.search(clause[: m.start()]):
        return True
    if COND_PREFIX.search(clause[max(0, m.start() - 60): m.start()]) and kind not in NEG_EXEMPT_KINDS:
        return True
    inside = m.group(0)
    for neg in HARD_NEG.finditer(inside):
        if not CANCEL_AFTER_NEG.match(inside[neg.end():]) and not NOT_A_NEGATION.match(inside[neg.end():]):
            return True
    prefix = clause[: m.start()]
    toks = list(re.finditer(r"[\w'’-]+", prefix))
    for pat, span in ((HARD_NEG, 12), (SOFT_NEG if kind in SOFT_KINDS else None, 8)):
        if pat is None:
            continue
        window_start = toks[-span].start() if len(toks) >= span else 0
        for neg in pat.finditer(prefix, window_start):
            between = prefix[neg.end():] + " " + m.group(0)
            if CANCEL_AFTER_NEG.match(between) or NOT_A_NEGATION.match(prefix[neg.end():]):
                continue
            if pat is HARD_NEG and ASSERT_CUE.search(between) and neg.group(0).lower() not in SUBJECT_NEG:
                continue
            return True
    return False


BLOCK_TAGS = r"(?:p|div|li|ul|ol|table|thead|tbody|tr|td|th|h[1-6]|section|article|header|footer|main|nav|pre|blockquote|hr|br|dl|dt|dd|figure|figcaption|title|option|label)"
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
HTML_BLOCK_TAG = re.compile(rf"</?{BLOCK_TAGS}\b[^>]*>", re.I)
HTML_ANY_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
HYPHEN_BREAK = re.compile(r"(\w)-[ \t]*\n[ \t]*(?=\w)")


def _fold_char_class(t: str) -> str:
    t = unicodedata.normalize("NFKC", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")           # zero-width, bidi controls, soft hyphen, tags
    t = ZW.sub("", t)                                                            # v7: Hangul fillers, Braille blank, etc. (category Lo/So, not Cf)
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) not in ("Mn", "Me"))  # combining marks (incl. U+034F)
    t = t.translate(_CONF_TABLE)
    return unicodedata.normalize("NFC", t)


def _fold_digit_lookalikes(t: str) -> str:
    return re.sub(r"(?<=[A-Za-z])[01345](?=[A-Za-z])", lambda m: DIGIT_LOOK[m.group(0)], t)


ATTR_TEXT = re.compile(r"""\b(?:title|alt|aria-label|aria-description|content|placeholder|data-[\w-]+|value|label)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)


def _strip_markup(t: str) -> str:
    """Comments go; text-bearing attributes (title, alt, aria-label, content, data-*) are KEPT as text; tags go (inline tags join words)."""
    t = HTML_COMMENT.sub("", t)
    t = HIDDEN_HTML.sub(" ", t)          # v7: display:none / hidden text is not read by a human, and may be a fake negation ("<span hidden>not</span>")
    t = STRUCK_HTML.sub(" ", t)          # v7: <del>not</del> insured reads "insured" to a person
    t = HTML_ANY_TAG.sub(lambda m: " " + " ".join(a or b for a, b in ATTR_TEXT.findall(m.group(0))) + " " if ATTR_TEXT.search(m.group(0)) else m.group(0), t)
    t = HTML_BLOCK_TAG.sub(" ", t)
    return HTML_ANY_TAG.sub("", t)


def normalise(text: str, hyphen: str = "keep") -> str:
    """hyphen='keep': 'mainnet-\\ncertified' -> 'mainnet-certified'; 'drop': 'pro-\\nduction' -> 'production'."""
    t = html.unescape(html.unescape(text))               # twice: &amp;#x200b; style double encoding
    t = _strip_markup(t)
    t = HYPHEN_BREAK.sub(lambda m: m.group(1) + ("-" if hyphen == "keep" else ""), t)
    t = _fold_char_class(t)
    t = _fold_digit_lookalikes(t)
    t = re.sub(r"NOT-A-CLAIM", " ", t)  # the old whole-line marker carries no meaning and must not read as a negation
    return re.sub(r"[ \t\r\f\v]+", " ", t)


PROSE_EXTS = (".md", ".mdx", ".markdown", ".txt", ".rst", ".tsx", ".html", ".htm")
MAX_BLOCK_LINES = 6


def units(text: str, join: bool = True) -> list[tuple[int, str]]:
    """(first line number, raw block text). A block is one line, or a line plus its continuation lines: a continuation is a
    non-blank line that does not open a list item, heading, table row, quote or fence."""
    out: list[tuple[int, list[str]]] = []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            out.append((n, []))
            continue
        starts = bool(re.match(r"^(?:[-*+•]\s|#|\||>|\d+[.)]\s|```|<)", s))
        quote_cont = bool(s.startswith(">") and out and out[-1][1] and not out[-1][1][0].strip().startswith((">", "|", "#", "```", "<")))  # v7: "We hold\n> SOC 2\n> Type II"
        if join and out and out[-1][1] and (not starts or quote_cont) and len(out[-1][1]) < MAX_BLOCK_LINES:
            out[-1][1].append(line)
        else:
            out.append((n, [line]))
    return [(n, "\n".join(ls)) for n, ls in out if ls]


def unit_hash(block: str) -> str:
    return hashlib.sha256(block.strip().encode("utf-8")).hexdigest()


ALT_CONFUSABLES = {ord(k): v for k, v in {"\u0443": "u", "\u043d": "n", "\u0432": "v", "\u0438": "u", "\u0433": "r", "\u044c": "b", "\u0442": "t", "\u043c": "m", "\u03bd": "n", "\u03c5": "u"}.items()}
LETTER_RUN = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z0-9] ){3,}[A-Za-z0-9](?![A-Za-z0-9])")
SPACED_STEMS = re.compile(r"(?<!un)(insured|audited|soc2|socii|certified|production|uptime|customers|mainnet|approved|compliant|regulated|licensed|attested|livewith|paying)", re.I)
SOC_DOTS = re.compile(r"\bS[.\s-]{0,2}O[.\s-]{0,2}C\.?[\s-]*(?=(?:2|II|two)\b)", re.I)


def variants(block: str) -> list[str]:
    """Distinct normalisations of one block: hyphen line-break kept / dropped x confusable primary / alternate fold."""
    seen: list[str] = []
    for hy in ("keep", "drop"):
        base = normalise(block, hy)
        cands = [base]
        raw = _fold_char_class_alt(block, hy)
        if raw is not None:
            cands.append(raw)
        for c in list(cands):
            cands.extend(_v7_extra(c))
        for c in cands:
            c = SOC_DOTS.sub("SOC ", c).replace("\n", " ")
            if c not in seen:
                seen.append(c)
    return seen


# ---- v7 (review set 5): further mechanical folds, applied as EXTRA candidates (the plain text is still scanned) ----------------------------
INWORD_SEP = re.compile(r"(?<=[A-Za-z])[\u00b7\u2022\u2027\u22c5_*~`\\](?=[A-Za-z])")
LEADING_LOOK = re.compile(r"(?<![A-Za-z0-9])([1$@5430])(?=[A-Za-z]{3,})")
LEAD_MAP = {"1": "i", "$": "s", "@": "a", "5": "s", "4": "a", "3": "e", "0": "o"}
EMPH = re.compile(r"(\*\*|__|\*|_|~~|`)")
HIDDEN_HTML = re.compile(r"<(?:span|div|p|font|b|i|em|strong|u|small|sup|sub)\b[^>]*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|color\s*:\s*(?:transparent|white|#fff\b|#ffffff\b)|hidden\b)[^>]*>.*?</(?:span|div|p|font|b|i|em|strong|u|small|sup|sub)>", re.I | re.S)
STRUCK_HTML = re.compile(r"<(del|s|strike)\b[^>]*>.*?</\1>", re.I | re.S)


def _v7_extra(c: str) -> list[str]:
    out = []
    a = INWORD_SEP.sub("", c)
    a = LEADING_LOOK.sub(lambda m: LEAD_MAP[m.group(1)], a)
    a = re.sub(r"\bSOC\b", "SOC", a.replace("$OC", "SOC"))
    if a != c:
        out.append(a)
    cs = re.sub(r"`\s*(?:no|not|never|none|without|isn't|aren't|hasn't|haven't|cannot|can't)\s*`", " ", c, flags=re.I)  # a code span faking a negation: "`not` insured" reads "insured"
    if cs != c:
        out.append(cs)
    b = EMPH.sub("", c)                       # markdown emphasis inside a word: _in_**sured**, ins*ured
    b = re.sub(r"(?<=[A-Za-z])[ \xa0](?=(?:s?ured|dited|tified|duction|tomers|ainnet)\b)", "", b)
    if b != c and b != a:
        out.append(b)
    return out


def _fold_char_class_alt(block: str, hy: str):
    if not any(ord(ch) in ALT_CONFUSABLES for ch in block):
        return None
    t = html.unescape(html.unescape(block))
    t = _strip_markup(t)
    t = HYPHEN_BREAK.sub(lambda m: m.group(1) + ("-" if hy == "keep" else ""), t)
    t = unicodedata.normalize("NFKC", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    t = t.translate(ALT_CONFUSABLES)
    t = _fold_char_class(t)
    t = _fold_digit_lookalikes(t)
    return re.sub(r"[ \t\r\f\v]+", " ", t)


# ---- table rows with no subject: "| Insurance | Yes |", "| Uptime SLA | 99.9% |", "| Customers | Northwind |", "| Mainnet | Live |"
NEG_VALUE = re.compile(r"^\W*(?:no|none|n/?a|not|never|nil|null|false|0|zero|tbd|tba|planned|pending|future|roadmap|target|goal|draft|example|template|synthetic|illustrative|placeholder|unknown|open|todo|requires?|required|must|after|until|when|once|if|-+|\u2014|\u2013|\u274c|\u2717|\u2718|\u00d7)\W*$|^\W*(?:not|no|none|n/a|nil|never|pending|planned|future|roadmap|target|goal|requires?|must|after|until|when|once|if)\b|\b(?:not yet|no customers?|none yet|not available|not offered|not provided|not applicable|coming soon|to be defined|to be decided)\b", re.I)
POS_VALUE = re.compile(r"^\W*(?:yes|true|y|live|licen[cs]ed|regulated|registered|authori[sz]ed|launched|insured|audited|covered|compliant|completed?|passed|active|enabled|complete[d]?|done|passed|certified|approved|available|achieved|ready|running|deployed|in production|operational|on|granted|included|provided|offered|\u2705|\u2714\ufe0f?|\u2713|\u2611\ufe0f?)\b|[\u2705\u2714\u2713\u2611]|\b\d{2,3}(?:\.\d+)?\s?%", re.I)
TABLE_TOPICS = [
    ("insured", re.compile(r"\b(?:insur\w*|indemnity|liability cover\w*)\b", re.I), "pos"),
    ("soc2", re.compile(r"\bSOC\s?[- ]?(?:2|II|two)\b|\bSystem (?:and|&) Organi[sz]ation Controls\b|\bISO[ /-]?27001\b", re.I), "pos"),
    ("audited", re.compile(r"\b(?:audit\w*|penetration test\w*|pen[- ]?test\w*|security review)\b", re.I), "pos"),
    ("sla-figure", re.compile(r"\b(?:uptime|availability|SLA|service level|response time|support hours?)\b", re.I), "pct"),
    ("pilot-implied", re.compile(r"^(?:our |current |active |paying |named |signed |first |pilot )?(?:customers?|clients?|design[- ]partners?|pilots?|users?|adopters?|logos?|institutions?|banks?|lenders?)(?: list| names?)?$", re.I), "named"),
    ("mainnet-certified", re.compile(r"\b(?:mainnet|production|xrpl mainnet|general availability|GA)\b", re.I), "pos"),
    ("pilot-implied", re.compile(r"\b(?:pilots?|design[- ]partners?)(?: status)?\b", re.I), "pos"),
    ("xls-active", re.compile(r"\bXLS-?(?:65|66)d?\b|\blending protocol\b|\bsingle[- ]asset vaults?\b", re.I), "pos"),
    ("assurance-claims", re.compile(r"\b(?:regulat\w*|licen[cs]\w*|compliance|GDPR|MiCA|certification)\b", re.I), "pos"),
]


def table_topic_key(line: str) -> bool:
    """True when a markdown row's first cell names a topic (Insured, Audit, Customers...): such a row is judged as key/value only."""
    st = line.strip()
    if not st.startswith("|") or re.fullmatch(r"[|\s:\-]+", st):
        return False
    cells = [c.strip() for c in st.strip("|").split("|")]
    if len(cells) < 2:
        return False
    keyc = re.sub(r"[`*_]", "", cells[0]).strip()
    return len(keyc.split()) <= 5 and any(t.search(keyc) for _, t, _ in TABLE_TOPICS)


def table_claims(line: str) -> list[tuple[str, str]]:
    s = line.strip()
    if not s.startswith("|") or re.fullmatch(r"[|\s:\-]+", s):
        return []
    cells = [c.strip() for c in s.strip("|").split("|")]
    if len(cells) < 2:
        return []
    out = []
    key, vals = cells[0], cells[1:]
    keyc = re.sub(r"[`*_]", "", key).strip()
    if len(keyc.split()) > 5:
        return []
    for kind, topic, mode in TABLE_TOPICS:
        if not topic.search(keyc):
            continue
        for v in vals:
            if not v or NEG_VALUE.search(v):
                continue
            vv = re.sub(r"[`*_]", "", v).strip()
            ok = bool(POS_VALUE.search(v)) if mode in ("pos", "pct") else bool(re.fullmatch(r"[A-Z0-9][\w.&'-]*(?:[ ,/&]+[A-Z0-9][\w.&'-]*){0,7}(?:\s*\([^)]{1,30}\))?", vv)) and not re.fullmatch(r"(?:Customers?|Status|Value|Details?|Notes?|Name|Role|Who|What)", vv)
            if mode == "named" and not ok:  # v8: "3 live", "4 completed", "2 signed": a count with a status word
                ok = bool(re.fullmatch(r"[1-9]\d*\+?\s+(?:live|active|completed|signed|paying|onboarded|in production|running|deployed)(?:\s+\w+){0,2}", vv, re.I))
            if mode == "pct":
                ok = bool(re.search(r"\d", v)) and not NEG_VALUE.search(v)
            if ok:
                out.append((kind, s))
                break
    return out


# ---- v7: key/value data (JSON, YAML, TOML, INI, XML-ish) judged from KEY and VALUE, not as prose ------------------------------------------
DATA_TOPICS = [
    ("insured", re.compile(r"\b(?:insur\w*|indemn\w*|underwrit\w*)\b", re.I), "pos"),
    ("audited", re.compile(r"\b(?:audit\w*|pen ?test\w*|penetration\w*|security review|external review)\b", re.I), "pos"),
    ("soc2", re.compile(r"\b(?:soc ?[123]|soc2|iso ?27001|pci|hipaa|certif\w*|complian\w*|attest\w*)\b", re.I), "pos"),
    ("sla-figure", re.compile(r"\b(?:sla|uptime|availability|nines)\b", re.I), "num"),
    ("pilot-implied", re.compile(r"\b(?:customers?|clients?|pilots?|design partners?|adopters?|users?|lenders?|banks?)\b", re.I), "named"),
    ("mainnet-certified", re.compile(r"\b(?:mainnet|production|generally available|ga)\b", re.I), "pos"),
    ("assurance-claims", re.compile(r"\b(?:regulat\w*|licen[cs]\w*|mica|gdpr)\b", re.I), "pos"),
]
DATA_POS = re.compile(r"^(?:true|yes|y|on|active|live|enabled|complete[d]?|done|passed|pass|certified|approved|achieved|granted|licen[cs]ed|regulated|launched|insured|audited|covered|compliant|clean|third[- ]party|external|independent|in[- ]production|production|operational|ga)$", re.I)
DATA_NEG = re.compile(r"^(?:[A-Za-z0-9]{30,}|false|no|n|off|none|null|nil|n/?a|0|0\.0|\[\]|\{\}|\"\"|''|planned|pending|tbd|tba|todo|unknown|not[- ].*|no[- ].*|never|disabled|inactive|open|draft|example|synthetic|placeholder|roadmap|future|target|goal|requires?.*|must.*)$", re.I)
KV_LINE = re.compile(r"""^\s*(?:[-*]\s+)?(?:<[\w:-]+>\s*)?["']?([A-Za-z_][\w .-]{0,48}?)["']?\s*(?::|=)\s*(.*?)\s*,?\s*$""")
XML_LINE = re.compile(r"^\s*<([A-Za-z_][\w:-]*)>\s*(.*?)\s*</\1>\s*$")


def _words_of_key(k: str) -> str:
    k = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", k)
    return re.sub(r"[_.\-/]+", " ", k).strip()


def _flatten_json(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten_json(v, path + (str(k),))
    elif isinstance(obj, list):
        if not obj:
            yield (path, "[]")
        for v in obj:
            yield from _flatten_json(v, path + ("[]",))
    else:
        yield (path, "null" if obj is None else str(obj).lower() if isinstance(obj, bool) else str(obj))


GENERIC_LEAF = {"status", "state", "value", "enabled", "active", "live", "ok", "covered", "complete", "completed", "passed", "result", "name", "names", "list", "items", "level", "type", "count", "total", "[]"}


def _topic_words(path_words: str) -> str:
    """Judge a pair by its LEAF key ("stale" in dimensions.LIVE_SOURCE.stale); a generic leaf ("status", "live") borrows its parent key."""
    ws = path_words.split()
    if not ws:
        return path_words
    leaf = ws[-1].lower()
    if leaf in GENERIC_LEAF and len(ws) >= 2:
        return " ".join(ws[-2:])
    return " ".join(ws[-2:])


def _judge_pair(path_words: str, value: str) -> list[tuple[str, str]]:
    v = value.strip().strip('"\'').strip()
    out = []
    if not v or DATA_NEG.match(v):
        return out
    topic_text = _topic_words(path_words)
    for kind, topic, mode in DATA_TOPICS:
        if not topic.search(topic_text):
            continue
        listy = "[]" in path_words.split()
        if mode == "pos":
            ok = bool(DATA_POS.match(v)) or bool(re.search(r"\b(?:complete[d]?|passed|active|approved|certified|licen[cs]ed|live|launched)\b", v, re.I))
        elif mode == "num":
            ok = bool(re.fullmatch(r"\d{2,3}(?:\.\d+)?\s?%?", v)) or bool(re.fullmatch(r"\d+(?:\.\d+)?", v) and float(v) > 0)
        else:  # named
            ok = bool(re.fullmatch(r"[A-Z0-9][\w.&'-]*(?:[ ,/&]+[A-Z0-9][\w.&'-]*){0,5}", v)) or (v.replace(",", "").isdigit() and int(v.replace(",", "")) > 0) or bool(DATA_POS.match(v))
            if not listy and not re.search(r"customers?|clients?|pilots?|partners?", path_words, re.I):
                ok = False
        if ok:
            out.append((kind, f"{path_words} = {v}"))
    return out


def data_claims(block: str, values: list[str] | None = None) -> tuple[list[tuple[str, str]], bool]:
    """(claims, handled). handled=True when every non-blank line of the block is a short key/value pair (or JSON that parses), so the prose scan
    is skipped for it: `insured: false` is not a claim, `\"audit\": \"completed\"` is."""
    txt = block.strip()
    if not txt:
        return [], False
    if txt[:1] in "{[" and txt[-1:] in "}]":
        try:
            import json as _json
            obj = _json.loads(txt)
        except Exception:
            obj = None
        if obj is not None:
            out = []
            for path, val in _flatten_json(obj):
                out += _judge_pair(" ".join(_words_of_key(p) if p != "[]" else "[]" for p in path), val)
                if values is not None:
                    values.append(val)
            return out, True
    out, last_key, handled_all, any_kv = [], "", True, False
    for line in txt.splitlines():
        if not line.strip() or line.strip().startswith(("#", "//", ";")):
            continue
        m = XML_LINE.match(line)
        if m:
            any_kv = True
            out += _judge_pair(_words_of_key(m.group(1)), m.group(2))
            if values is not None:
                values.append(m.group(2))
            continue
        m = KV_LINE.match(line)
        if m and len(m.group(2).split()) <= 4:
            key, val = m.group(1).strip(), m.group(2).strip()
            if val == "" or val in ("[", "{", "|", ">"):
                last_key = key
                any_kv = True
                continue
            any_kv = True
            out += _judge_pair(_words_of_key(key), val)
            if values is not None:
                values.append(val)
            last_key = key
            continue
        li = re.match(r"^\s*-\s+(.*?)\s*$", line)
        if li and last_key:
            any_kv = True
            out += _judge_pair(_words_of_key(last_key) + " []", li.group(1))
            if values is not None:
                values.append(li.group(1))
            continue
        handled_all = False
    return out, bool(any_kv and handled_all)


HTML_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
HTML_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)


def html_rows_as_pipes(text: str) -> str:
    def row(m):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in HTML_CELL.findall(m.group(1))]
        return ("| " + " | ".join(cells) + " |") if len(cells) >= 2 else m.group(0)
    t = HTML_ROW.sub(lambda m: "\n" + row(m) + "\n", text)
    # bare adjacent cells without a <tr>: <td>Uptime</td><td>99.99%</td>
    t = re.sub(r"<t[dh]\b[^>]*>([^<]{1,60})</t[dh]>\s*<t[dh]\b[^>]*>([^<]{1,60})</t[dh]>", lambda m: "\n| %s | %s |\n" % (m.group(1).strip(), m.group(2).strip()), t, flags=re.I)
    return t



_APPROVED_STANDALONE = re.compile(re.escape(APPROVED) + r"(?=[ \t*_]*(?:$|\|)|\s+(?:There is no|See \[)\b)", re.M)  # exact sentence followed only by end of line, a table pipe, or a following sentence that starts 'There is no' / 'See [' (the README pattern)


def _scan_text(t: str) -> list[tuple[str, str]]:
    """[(kind, snippet)] for one already-normalised text (no line numbers, no exemptions)."""
    hits: list[tuple[str, str]] = []
    t = _APPROVED_STANDALONE.sub("", t)  # v7: only the approved sentence ALONE on its line/paragraph is removed; extended forms ("... and 3 completed customer pilots", "... Not any more.") are scanned
    if re.search(r"no production customer deployments and\b", t, re.I):  # what is left of the approved wording after the standalone removal was edited, extended or embedded: never trusted
        hits.append(("approved-sentence-altered", t[max(0, t.lower().find("no production customer deployments and") - 20): t.lower().find("no production customer deployments and") + 110]))
    for kind, pat in FORBIDDEN:
        for m in pat.finditer(t):
            bounds = [0] + [c.end() for c in CLAUSE_SPLIT.finditer(t, 0, m.start())]
            cs = bounds[-1]
            ce_m = CLAUSE_SPLIT.search(t, m.end())
            clause = t[cs: ce_m.start() if ce_m else len(t)]
            shifted = re.compile(pat.pattern, pat.flags).search(clause)
            mm = next((x for x in pat.finditer(clause) if x.start() <= m.start() - cs <= x.end()), shifted)
            if mm is None or _negated(kind, clause, mm):
                continue
            hits.append((kind, t.strip()[:160]))
            break
    for run in LETTER_RUN.finditer(t):
        joined = run.group(0).replace(" ", "")
        if SPACED_STEMS.search(joined):
            hits.append(("letter-spaced", run.group(0)))
            break
    return hits


BRIDGE_STARTS = re.compile(r"^(?:[-*+\u2022]\s|#|\||>|\d+[.)]\s|```|<)")


def find_forbidden(text: str, join: bool = True) -> list[tuple[int, str, str, str]]:
    """[(line, kind, snippet, sha256-of-block)]. The approved sentence is removed first; nothing else can switch a hit off.
    Passes: (1) each block under every normalisation variant; (2) markdown table rows judged as key/value; (3) adjacent blocks
    joined across a paragraph break when the first does not end a sentence ("live" / blank / "with customers")."""
    out: list[tuple[int, str, str, str]] = []
    blocks = units(text, join)
    # v7: key/value data is judged per PARAGRAPH (a YAML list is several one-line blocks). handled_lines: lines whose KEY text is not prose-scanned.
    data_hits: dict[int, list[tuple[str, str]]] = {}
    handled_lines: set[int] = set()
    value_texts: dict[int, list[str]] = {}
    para: list[tuple[int, str]] = []
    for n, line in list(enumerate(text.splitlines(), 1)) + [(0, "")]:
        if line.strip() and not line.lstrip().startswith(("|", ">", "#")):
            para.append((n, line))
            continue
        if para:
            vals: list[str] = []
            claims, handled = data_claims(normalise("\n".join(l for _, l in para), "keep"), vals)
            if handled:
                data_hits.setdefault(para[0][0], []).extend(claims)
                handled_lines.update(k for k, _ in para)
                value_texts[para[0][0]] = vals
            para = []
    for n, block in blocks:
        raw_hash = unit_hash(block)
        got: list[tuple[str, str]] = []
        block_p = html_rows_as_pipes(block) if "<t" in block.lower() else block
        blk_lines = set(range(n, n + len(block.splitlines())))
        for dk, dsn in data_hits.get(n, []):  # v7: a data claim is keyed by its OWN text (key path = value), not by the paragraph's first line, so an exemption cannot mask a second pair
            out.append((n, dk, dsn, unit_hash(dk + "|" + dsn)))
        pipe_rows = [ln for ln in block_p.splitlines() if ln.strip().startswith("|")]
        keyed_rows = [ln for ln in pipe_rows if table_topic_key(ln)]
        if blk_lines <= handled_lines:
            for v in value_texts.get(n, []):
                if re.search(r"[A-Za-z]{3}", v):
                    for tv in (v, v.replace("-", " ")):
                        for t in variants(tv):
                            got += _scan_text(t)
        else:
            prose = block_p if not keyed_rows else "\n".join(ln for ln in block_p.splitlines() if ln not in keyed_rows)
            for t in variants(prose):
                got += _scan_text(t)
        for line in block_p.splitlines():
            got += table_claims(normalise(line))
        seen = set()
        for kind, snip in got:
            if kind not in seen:
                seen.add(kind)
                out.append((n, kind, snip, raw_hash))
    if join:
        for (n1, b1), (n2, b2) in zip(blocks, blocks[1:]):
            s1, s2 = b1.strip(), b2.strip()
            if not s1 or not s2 or BRIDGE_STARTS.match(s1) or BRIDGE_STARTS.match(s2) or re.search(r"[.!?:;|>)\]`]$", s1) or len(b1.splitlines()) >= MAX_BLOCK_LINES:
                continue
            already = {k for (ln, k, _, _) in out if ln in (n1, n2)}
            joined = b1.rstrip() + " " + b2.lstrip()
            got = []
            for t in variants(joined):
                got += _scan_text(t)
            for kind, snip in got:
                if kind not in already:
                    already.add(kind)
                    out.append((n1, kind, snip, unit_hash(joined)))
    return out


# ---------------------------------------------------------------------------------------------------------------
# What a reviewer may append to a README to test the guard.
REVIEW_EXAMPLES = [
    "One design partner is live.",
    "Northwind is our active pilot.",
    "SOC 2 audited, insured, 99.9% SLA.",
    "XLS-66 active on Mainnet.",
    "Mainnet certified and production approved.",
    "Trusted by customers in production.",
    "The Northwind Devnet demo is a completed customer pilot.",
    "Ward is SOC 2 Type II compliant.",
    "Ward is insured.",
    "We guarantee 99.95% uptime.",
    "We respond within 4 hours.",
    "XLS-65 is enabled on XRPL Mainnet.",
    "Ward is production ready.",
    "Our first customer went live in September.",
    "Ward is Mainnet approved.",
    "Current WARD regenerates the historical golden receipts exactly.",
    "Today's engine reproduces the golden receipts byte-for-byte.",
    "The latest release rebuilds the historical golden receipts.",
]

# Review set 3's 69 new claims. Every one must be flagged.
SET3_MUST_FLAG = [
    "Ward is SOC 2 compliant.", "Ward has completed SOC2 Type II.", "We hold a SOC 2 Type II report.", "SOC2 Type II certified.", "Our platform is SOC 2 Type II.",
    "Ward is insured.", "All deposits are insured.", "Coverage is insured by Lloyd's.", "Assets are covered by insurance.",
    "Ward was audited by Trail of Bits.", "Independently audited by CertiK.", "audited by a Big Four firm", "The protocol has been audited by Halborn.",
    "We offer 99.99% uptime.", "99.9% SLA", "Guaranteed 99.5% availability.", "Uptime: 99.9%", "four nines of availability", "Our SLA guarantees 24/7 support.", "We provide 24x7 support with a 1 hour response time.",
    "Ward is live with customers.", "We are live with customers today.", "Live with institutional customers.", "Ward is now live with three banks.",
    "Our pilot customer, Northwind, uses Ward daily.", "Pilot customer: Northwind.", "Northwind is a pilot customer.", "Our pilot customers include Contoso.",
    "Our design partner Northwind is live.", "Design partner: Contoso", "Ward's design partners include Northwind and Contoso.", "Northwind, our design partner, has signed.", "We work with design partners in production.",
    "Ward is mainnet certified.", "Mainnet-certified by Ward.", "Certified for XRPL Mainnet.", "This certificate is certified on mainnet.", "Ward is approved for mainnet.",
    "Ward is production approved.", "Production-approved by the founders.", "Approved for production.", "Cleared for production use.",
    "XLS-66 live.", "XLS-66 is live on mainnet.", "Lending on XLS-66 is live on XRPL mainnet.", "XLS-66 live on Mainnet", "XLS-66 is live now.", "The XLS-66 amendment is active on mainnet.", "XLS-65 and XLS-66 are enabled on mainnet.",
    "Ward protects real customer funds.", "Ward is deployed in production.", "Ward is in production at Northwind.", "Ward secures $10M of customer assets.", "Ward is trusted by lenders.",
    "Ward has paying customers.", "We have signed our first customer.", "Ward is used in production by Contoso.", "Contoso went live with Ward.", "Ward is FDIC insured.",
    "Ward is ISO 27001 certified.", "Ward passed a penetration test with zero findings.", "Ward is regulator approved.", "Ward is licensed.", "Ward is fully compliant with MiCA.",
    "Ward is bank-grade.", "Ward is enterprise-ready.", "Ward is battle-tested in production.", "Ward has been running on mainnet since 2025.", "Ward is deployed on XRPL Mainnet.",
]
# Review set 3 negation / spacing evasions: every one must be flagged.
SET3_EVASIONS = [
    "Ward is insured, not merely tested.", "Ward is SOC 2 audited; there is no doubt.", "No one doubts Ward is insured.", "Ward is not just audited, it is SOC 2 certified.",
    "We are live with customers — not a demo.", "Ward is Ward-certified.", "Northwind is a design partner (not a customer).", "Ward is SOC 2 Type II compliant without any gaps.",
    "It is false that Ward lacks SOC 2 compliance.", "Ward SOC 2 attested\u200b.", "Ward is S O C 2 certified", "W\u0430rd is insured.", "ward is INSURED",
    "Ward is insured\nagainst loss", "Ward is un-insured? no: insured.",
]
SET3_MARKDOWN = [
    "> Ward is insured.", "**Ward is SOC 2 certified**", "| Ward | SOC 2 Type II | done |", "- [x] SOC 2 Type II audit complete", "<!-- x -->\nWard is insured.",
    "```\nWard is insured.\n```", "Ward is insured.  <!-- NOT-A-CLAIM -->", "<p>Ward is SOC&nbsp;2 certified</p>", "Ward is SOC 2\ncertified",
]
# honest disclaimers that must keep passing (proves the negation rule is not simply switched off)
MUST_PASS = [
    APPROVED,
    "Ward is not insured. There is no SLA and no SOC 2 report. XLS-66 is not active on Mainnet.",
    "Ward has not been audited by any third party.",
    "Ward is not SOC 2 audited, insured, or certified.",
    "Ward does not have SOC 2 Type II compliance.",
    "XLS-66 is not live on mainnet until the amendment activates.",
    "Ward does not claim mainnet certification.",
]

# Review set 4's 155 fresh items (verbatim). Every one must be flagged: permanent regression (v6).
SET4_MUST_FLAG = [
    'Ward has successfully completed a SOC 2 Type 2 examination.',
    'Our SOC-2 report is available on request.',
    'We are SOC II compliant.',
    'Ward holds a System and Organization Controls 2 attestation.',
    "Ward's controls were independently attested (SOC 2).",
    'Ward carries $50M of cyber insurance.',
    "Deposits are protected by an insurance policy with Lloyd's.",
    'Customer assets are backed by an insurance fund.',
    'The smart contracts underwent a full security audit by OpenZeppelin.',
    'Ward completed its third-party security audit in August.',
    'A leading firm has reviewed and signed off on the codebase.',
    'Our code was formally verified.',
    'We deliver 99.95% monthly availability.',
    'Ward offers a five-nines service level.',
    'Ward guarantees a 15 minute incident response.',
    'Support: 24/7/365 with a dedicated account manager.',
    'Contractual service credits apply if uptime drops below 99.9 percent.',
    'Ward runs a production service for banks.',
    'Several lenders rely on Ward every day.',
    'Ward is currently processing live loan resolutions for a customer.',
    'Ward has onboarded its first institution.',
    'Ward has three paying design partners.',
    'Our customers include Northwind and Contoso.',
    'Northwind has been using Ward in production since July.',
    'Tailspin Vault Technologies is a Ward customer.',
    "Ward's first pilot completed successfully with Northwind.",
    'The pilot with Northwind concluded and Ward passed.',
    'Ward now has a signed order form with a customer.',
    'Ward customers: Northwind, Contoso, Tailspin Vault.',
    'Ward is running in production today.',
    'Ward is generally available.',
    'Ward has launched on XRPL mainnet.',
    'Ward is live on the XRP Ledger mainnet.',
    'Ward went live on mainnet in September 2026.',
    'Ward is certified for production use on XRPL.',
    'XLS-66 lending is now enabled on mainnet.',
    'XLS-66d is live on the XRP Ledger.',
    'Lending Protocol (XLS-66) has activated on mainnet.',
    'The XLS-65 vault amendment passed and is live.',
    'Single Asset Vaults are live on mainnet and Ward covers them.',
    'Ward is fully regulated.',
    'Ward is a licensed money transmitter.',
    'Ward is GDPR compliant and ISO certified.',
    'Ward has been penetration tested by NCC Group.',
    "Ward's approach was approved by the SEC.",
    'Ward is regulator-friendly and pre-approved by regulators.',
    'Ward satisfies MiCA requirements today.',
    'Institutional-grade custody and resolution, ready today.',
    'Trusted by the largest XRPL lenders.',
    'The production release of Ward v1.0 shipped.',
    'Ward is the production standard for lending resolution.',
    'Ward is proven in production.',
    'Ward has zero incidents in production.',
    'Ward is audit-ready and audit-complete.',
    'Ward is certified by an independent third party.',
    "Ward's conformance certificates are mainnet-valid.",
    'Ward is not only insured but also SOC 2 certified.',
    'No doubt: Ward is SOC 2 Type II audited.',
    'Nobody can deny that Ward is insured.',
    'Never before has a protocol been so thoroughly insured as Ward.',
    'Ward is not uninsured.',
    'We do not hide that Ward is SOC 2 certified.',
    'There is no question Ward is live with customers.',
    'Not only is Ward audited by Halborn, it is also insured.',
    'Ward has no gaps: it is SOC 2 Type II audited.',
    'Without exaggeration, Ward is production approved.',
    'Ward cannot be described as anything but mainnet certified.',
    'Ward is insured (no, really).',
    'Contrary to rumor, Ward is insured.',
    'Ward is insured. Not a joke.',
    'Do not believe the critics: Ward is SOC 2 audited.',
    'Ward, which has no competitors, is insured.',
    'Ward is insured and never had a claim.',
    'Ward is not a demo; it is live with customers.',
    "Ward isn't just a prototype. It's deployed in production.",
    'Ward is no longer a pilot: it is production ready.',
    'Ward is\nSOC 2\nType II\ncertified.',
    'Ward is live\n\nwith customers.',
    "Ward is fully\ninsured\nby Lloyd's.",
    'XLS-66\nis live\non mainnet.',
    'Ward has\npaying\ncustomers.',
    'Ward is SOC\n2 audited.',
    'Ward is mainnet-\ncertified.',
    'Ward is production-\napproved.',
    'Ward is in\nproduction at Northwind.',
    'Ward\nis\ninsured',
    '| Feature | Status |\n|---|---|\n| SOC 2 Type II | Complete |',
    '| Insurance | Yes |',
    '| Uptime SLA | 99.9% |',
    '| Customers | Northwind, Contoso |',
    '| Mainnet | Live |',
    '- **Insured**: yes',
    '* SOC 2 Type II \u2705',
    '1. Ward is SOC 2 audited',
    '### Ward is insured',
    '[Ward is insured](https://example.com)',
    '![Ward is insured](x.png)',
    '<li>Ward is SOC&#32;2 certified</li>',
    '<span>Ward is <b>insured</b></span>',
    '<div title="Ward is insured">x</div>',
    '<td>99.99% uptime</td>',
    '<p>Ward is <em>live</em> with <em>customers</em></p>',
    '{"status": "SOC 2 Type II audited"}',
    '{"description": "Ward is insured and live with customers"}',
    '{"claims": ["insured", "SOC 2 certified"]}',
    '{"soc2": true, "insured": true}',
    '"badge": "SOC 2 Type II certified"',
    "const copy = 'Ward is insured';",
    "const badge = `SOC 2 ${'Type II'} audited`;",
    '  // Ward is production approved',
    'Ward is insured\\n',
    '`Ward is insured`',
    '~~not~~ Ward is insured',
    '<!-- not --> Ward is insured',
    '<s>not</s> Ward is insured',
    'Ward is ins\u0443red.',
    'Ward is \u0456nsured.',
    'Ward is S\u041eC 2 certified.',
    'Ward is SOC 2 audited.',
    'Ward is \uff33\uff2f\uff23 2 certified.',
    'Ward is \u24d8nsured.',
    'Ward is in\u200bsured.',
    'Ward is in\xadsured.',
    'Ward is insu\u200cred.',
    'Ward is insured\u2060.',
    'Ward is \u1d35nsured.',
    'Ward is INSURED',
    'Ward is iNsUrEd',
    'W A R D  i s  i n s u r e d',
    'Ward is i n s u r e d.',
    'Ward is S.O.C. 2 certified.',
    'Ward is S-O-C 2 certified.',
    'Ward is SOC\xa02 certified.',
    'Ward is SOC\u20022 certified.',
    'Ward is SOC\t2 certified.',
    'Ward is s0c 2 certified.',
    'Ward is soc2-certified.',
    'Ward is SOC 2 (Type II) certified.',
    'Ward is insured\u061c.',
    'Ward is insured\u202e.',
    'Ward is in\u034fsured.',
    'Ward is ins\u0301ured.',
    'Ward is live w\u0456th customers.',
    'Ward has paying cust\u043emers.',
    'Ward is pr\u043eduction approved.',
    'Ward is \u217cive with customers.',
    'Ward est assur\xe9.',
    'Ward ist versichert.',
    'Ward est\xe1 asegurado y certificado SOC 2.',
    'Ward is SOC<b> 2 </b>audited.',
    'Ward is <i>in</i>sured.',
    'Ward is in<!-- x -->sured.',
    'Ward is in&shy;sured.',
    'Ward is insu&#x200b;red.',
    'Ward is SOC&#x20;2 certified.',
]
# Honest text that must keep passing (review set 4's three plus disclaimers and ordinary engineering prose). Guards against over-flagging.
SET4_MUST_PASS = [
    "Ward is not insured, not SOC 2 audited, and has no customers.",
    "There is no SLA.",
    "Ward has no insurance policy, no insurance fund and no SOC II report.",
    "We do not offer 24/7/365 support, service credits or a five-nines target.",
    "Institutions and developers read the log to judge engineering discipline.",
    "The signed order form template is a draft and has not been used.",
    "The checker treats warnings as failures in production builds of the site.",
    "| Insurance | No |", "| Uptime SLA | None |", "| Customers | None yet |", "| Mainnet | Not live |", "| SOC 2 | Not started |",
    "| Feature | Status |", "| Design partners | Planned |",
    "Ward is pre-mainnet; XLS-66 is not live on mainnet.",
    "<p>Ward is <em>not</em> <strong>insured</strong>.</p>",
    "Ward has no customers, and no one relies on Ward today.",
    "A design-partner pilot is a scoped, non-production engagement.",
]

# Review set 5's 163 fresh claims (verbatim, v7). Every one must be flagged: permanent regression. Review set 5 measured 67 of these (41.1%) as MISSED by the v6 scanner.
SET5_MUST_FLAG = [
    "Ward's smart contracts were reviewed line by line by Zellic and came back clean.",  # para
    'Our contracts have gone through an external security assessment with no critical findings.',  # para
    "A Big Four accounting firm issued an unqualified attestation over Ward's controls.",  # para
    'We are covered by a $20M cyber liability policy.',  # para
    'Losses from a resolver failure would be reimbursed by our underwriters.',  # para
    'Every deposit is backed by an insurer.',  # para
    'Ward maintains a crime policy and a professional liability policy.',  # para
    'Ward achieved SOC 2 Type I in Q2.',  # para
    'The Ward control environment holds an AICPA SOC report.',  # para
    'We are ISO/IEC 27001:2022 certified.',  # para
    'Ward is PCI DSS compliant.',  # para
    'Ward is HIPAA compliant.',  # para
    'Uptime over the last twelve months was 99.98%.',  # para
    'We commit to a 30-minute response for Sev-1 incidents.',  # para
    'Ward is backed by a financially-backed service level agreement.',  # para
    'Ward is covered by a 99.9% availability commitment.',  # para
    'Banks use Ward to settle loan defaults every week.',  # para
    'Three lenders have integrated Ward into their servicing stack.',  # para
    'Ward is already protecting customer positions on mainnet.',  # para
    'We closed our first paid pilot in August.',  # para
    'Ward has a signed master services agreement with a bank.',  # para
    'Our early customers are seeing measurable reductions in resolution time.',  # para
    'Ward is now processing real settlements on the XRP Ledger.',  # para
    'Ward launched publicly on the XRP Ledger last month.',  # para
    'Ward Protocol is production-grade.',  # para
    'Ward is a fully operational lending-resolution network.',  # para
    'Vault resolution runs on XRPL mainnet today.',  # para
    'Lending Protocol vaults are live on the main XRPL network and Ward resolves them.',  # para
    'The XLS-66 lending amendment went live on mainnet and Ward supports it.',  # para
    'Ward has been approved by the SEC as a compliant settlement layer.',  # para
    'Ward is registered with FinCEN as a money services business.',  # para
    "Ward complies with the EU's MiCA regime.",  # para
    'Our legal opinion confirms Ward is not a security.',  # para
    'Ward carries no counterparty risk because it is fully collateralised and insured.',  # para
    'The security of Ward has been independently confirmed.',  # para
    "Ward has been stress-tested with real customers' funds.",  # para
    "Today's release regenerates the golden receipts bit-for-bit.",  # para
    'The build reproduces every historical golden receipt exactly.',  # para
    'Ward has a perfect security record.',  # para
    'No funds have ever been lost on Ward in production.',  # para
    'Ward is insured. Nobody has ever said otherwise.',  # neg
    'Make no mistake: Ward is SOC 2 Type II certified.',  # neg
    'Far from being uninsured, Ward carries full coverage.',  # neg
    'Ward is not a toy; it is deployed on mainnet with real banks.',  # neg
    'We are not shy about it: three customers are live.',  # neg
    'Not one of our reviewers doubted that Ward is audited by a top firm.',  # neg
    'Ward is no longer experimental. It is in production.',  # neg
    'It would be wrong to say Ward has no customers; it has several.',  # neg
    'Nothing prevents you from relying on Ward in production, since it is audited.',  # neg
    "Ward can't be beaten on uptime: 99.99% availability.",  # neg
    'Ward is neither slow nor unaudited: it was audited by NCC in June.',  # neg
    'Without doubt, Ward is production approved.',  # neg
    'Ward, not any competitor, is the first SOC 2 certified resolver.',  # neg
    "There's no denying that our mainnet deployment is live.",  # neg
    'Ward is a settlement layer that\nhas been independently\naudited by a top firm.',  # split
    "Ward's SOC 2\r\nType II report\r\nis complete.",  # split
    'Ward has\n\n\nreal customers.',  # split
    'Ward is\n\n**insured**.',  # split
    'Status: live\n\non the XRPL mainnet',  # split
    'Ward is pro-\nduction ready.',  # split
    'Ward is audit-\ned by Trail of Bits.',  # split
    'We hold\n> SOC 2\n> Type II certification.',  # split
    '| Assurance | SOC 2 Type II |',  # table
    '| Security audit | Completed by Halborn |',  # table
    '| Availability | 99.95% |',  # table
    '| Pilot status | Live |',  # table
    '| XRPL mainnet | Yes |',  # table
    '| Coverage | $10M cyber policy |',  # table
    '| Certifications | SOC 2, ISO 27001 |',  # table
    '| Ward | Insured | Yes |',  # table
    '| Production | Active |',  # table
    'Feature | Ward\n--- | ---\nSOC 2 | Type II',  # table
    '| Regulatory status | Licensed |',  # table
    '| Customers | Northwind (live) |',  # table
    '- Insured up to $25M',  # list
    '* Audited by ChainSecurity',  # list
    '1. Deployed on XRPL mainnet',  # list
    '+ 99.99% uptime',  # list
    '- [x] SOC 2 Type II complete',  # list
    '- Live customers: Northwind, Contoso',  # list
    '<h2>SOC 2 Type II certified</h2>',  # html
    '<p>Ward is <a href="/x">audited</a> by <b>Trail of Bits</b></p>',  # html
    '<img src="x.png" alt="Ward is insured">',  # html
    '<meta name="description" content="Ward is SOC 2 certified">',  # html
    '<a href="/trust" title="Ward has paying customers">Trust</a>',  # html
    '<button aria-label="Ward is live on mainnet">Go</button>',  # html
    '<p>Ward is <span style="display:none">not</span> insured.</p>',  # html
    '<p>Ward is <del>not</del> insured.</p>',  # html
    '<script type="application/ld+json">{"description":"Ward is insured"}</script>',  # html
    '<td>Uptime</td><td>99.99%</td>',  # html
    '<svg><text>SOC 2 Type II</text></svg>',  # html
    '<p>Ward is in&nbsp;&#115;ured.</p>',  # html
    '<p>Ward is i<span>nsu</span>red</p>',  # html
    '<ul><li>Audited</li><li>by Trail of Bits</li></ul>',  # html
    '<noscript>Ward is insured</noscript>',  # html
    '{"insurance": {"covered": true, "limit_usd": 25000000}}',  # data
    '{"audit": "completed", "auditor": "Halborn"}',  # data
    '{"sla_uptime": "99.99"}',  # data
    '{"customers": ["Northwind", "Contoso"]}',  # data
    '{"mainnet": {"live": true}}',  # data
    '{"certifications": ["SOC2", "ISO27001"]}',  # data
    '{"tagline": "Insured, audited, production-ready."}',  # data
    'tagline: The audited XRPL resolution layer',  # data
    'status: live-on-mainnet',  # data
    'insured: true',  # data
    'audit_status: complete',  # data
    'description = "Audited and insured resolution"',  # data
    'is_insured = True',  # data
    'customers:\n  - Northwind\n  - Contoso',  # data
    'compliance:\n  soc2: type2\n  iso27001: true',  # data
    'WARD_BANNER="Now live on XRPL mainnet"',  # data
    "const HERO = {sub: 'SOC 2 Type II certified'}",  # data
    '# Ward is fully insured',  # code
    '/* Ward is deployed to production for banks */',  # code
    "// TODO: keep 'Audited by Halborn' badge in hero",  # code
    '"""Ward is SOC 2 certified."""',  # code
    '<!-- visible-to-nobody --> Ward is audited by Trail of Bits.',  # code
    "export const badges = ['SOC 2 Type II', 'Audited by Halborn'];",  # code
    "return `Ward is ${'insured'}`;",  # code
    "label: 'Live on XRPL mainnet',",  # code
    'Ward is in\ua731ured.',  # glyph
    'Ward is insu\u0280ed.',  # glyph
    'Ward is \u2170nsured.',  # glyph
    'Ward is ins\u1d1cred.',  # glyph
    'Ward is in\u0455ured.',  # glyph
    'Ward is insured\u115f.',  # glyph
    'Ward is ins\u3164ured.',  # glyph
    'Ward is in\uffa0sured.',  # glyph
    'Ward is in\u2800sured.',  # glyph
    'Ward is ins\u2062ured.',  # glyph
    'Ward is \u13a5nsured.',  # glyph
    'Ward is 1nsured.',  # glyph
    'Ward is $OC 2 certified.',  # glyph
    'Ward is S\u2c9fC 2 certified.',  # glyph
    'Ward is au\u0501ited by Halborn.',  # glyph
    'Ward is aud\u0456ted by Halborn.',  # glyph
    'Ward has \u0440aying customers.',  # glyph
    'Ward is l\u0456ve with cu\u0455tomers.',  # glyph
    'Ward is in\u180esured.',  # glyph
    'Ward is ins\ufe0fured.',  # glyph
    'Ward is in\U0001d422sured.',  # glyph
    'Ward is in\u200f\u200esured.',  # glyph
    'W\u0430rd is S\u041eC 2 cert\u0456fied.',  # glyph
    "Ward is insured\xa0by\xa0Lloyd's.",  # glyph
    'Ward is in\xb7sured.',  # glyph
    'Ward is in_sured.',  # glyph
    'Ward is ins*ured.',  # glyph
    'Ward is production\u2011ready.',  # glyph
    'Ward is \ua7aeNSURED.',  # glyph
    'Ward is au\u1d05ited by Halborn.',  # glyph
    '[SOC 2 Type II certified](https://example.com/report)',  # md
    '[![Audited by Halborn](https://img.shields.io/badge/audit-halborn-green)](x)',  # md
    '![SOC 2 Type II badge](soc2.svg)',  # md
    '[Ward is insured]: https://example.com/policy',  # md
    '[link](https://example.com "Ward is insured")',  # md
    '**Audited** by *Halborn*',  # md
    'Ward is _in_**sured**.',  # md
    'Ward is `not` insured.',  # md
    '[//]: # (hidden) Ward is audited by Halborn.',  # md
    '<https://example.com/soc2> Ward is SOC 2 certified',  # md
    'Ward is ~~un~~insured.',  # md
    '| a | b |\n|---|---|\n| Ward | \u2705 SOC 2 Type II |',  # md
    'Footnote[^1] Ward is insured.\n\n[^1]: yes',  # md
]
# Review set 5's 25 honest sentences (verbatim, v7). None may be flagged. Review set 5 measured 5 of them as FALSE POSITIVES under v6.
SET5_MUST_PASS = [
    'Ward has no insurance, no SOC 2 report and no paying customers.',
    'Nothing here is audited by a third party yet.',
    'XLS-66 is not active on mainnet; Ward works on devnet only.',
    'We have not signed any customers.',
    'The uptime target is undefined and no SLA is offered.',
    "Ward's tests run on GitHub Actions.",
    'Please do not describe Ward as insured, audited or SOC 2 certified.',
    'Insurance is out of scope for this repository.',
    'An independent audit is planned but not scheduled.',
    'There are no production deployments.',
    'Customers are not onboarded; this is a devnet demonstration.',
    "The word 'audited' must not appear in marketing copy until an audit exists.",
    'Ward is a research prototype; do not use it with real funds.',
    'Mainnet deployment has not happened.',
    '| Insured | No |',
    '| Customers | None |',
    '| SOC 2 | Not started |',
    '| Mainnet | Not live |',
    '<p>Ward is not insured.</p>',
    '{"insured": false, "audited": false}',
    'insured: false',
    '# TODO: get an audit before making any audit claim',
    'Ward has never been audited.',
    'If Ward were insured we would say so; it is not.',
    'Users should verify receipts independently.',
]

# Review set 5's 163 fresh claims (verbatim, v7). Every one must be flagged: permanent regression. Review set 5 measured 67 of these (41.1%) as MISSED by the v6 scanner.
SET5_MUST_FLAG = [
    "Ward's smart contracts were reviewed line by line by Zellic and came back clean.",  # para
    'Our contracts have gone through an external security assessment with no critical findings.',  # para
    "A Big Four accounting firm issued an unqualified attestation over Ward's controls.",  # para
    'We are covered by a $20M cyber liability policy.',  # para
    'Losses from a resolver failure would be reimbursed by our underwriters.',  # para
    'Every deposit is backed by an insurer.',  # para
    'Ward maintains a crime policy and a professional liability policy.',  # para
    'Ward achieved SOC 2 Type I in Q2.',  # para
    'The Ward control environment holds an AICPA SOC report.',  # para
    'We are ISO/IEC 27001:2022 certified.',  # para
    'Ward is PCI DSS compliant.',  # para
    'Ward is HIPAA compliant.',  # para
    'Uptime over the last twelve months was 99.98%.',  # para
    'We commit to a 30-minute response for Sev-1 incidents.',  # para
    'Ward is backed by a financially-backed service level agreement.',  # para
    'Ward is covered by a 99.9% availability commitment.',  # para
    'Banks use Ward to settle loan defaults every week.',  # para
    'Three lenders have integrated Ward into their servicing stack.',  # para
    'Ward is already protecting customer positions on mainnet.',  # para
    'We closed our first paid pilot in August.',  # para
    'Ward has a signed master services agreement with a bank.',  # para
    'Our early customers are seeing measurable reductions in resolution time.',  # para
    'Ward is now processing real settlements on the XRP Ledger.',  # para
    'Ward launched publicly on the XRP Ledger last month.',  # para
    'Ward Protocol is production-grade.',  # para
    'Ward is a fully operational lending-resolution network.',  # para
    'Vault resolution runs on XRPL mainnet today.',  # para
    'Lending Protocol vaults are live on the main XRPL network and Ward resolves them.',  # para
    'The XLS-66 lending amendment went live on mainnet and Ward supports it.',  # para
    'Ward has been approved by the SEC as a compliant settlement layer.',  # para
    'Ward is registered with FinCEN as a money services business.',  # para
    "Ward complies with the EU's MiCA regime.",  # para
    'Our legal opinion confirms Ward is not a security.',  # para
    'Ward carries no counterparty risk because it is fully collateralised and insured.',  # para
    'The security of Ward has been independently confirmed.',  # para
    "Ward has been stress-tested with real customers' funds.",  # para
    "Today's release regenerates the golden receipts bit-for-bit.",  # para
    'The build reproduces every historical golden receipt exactly.',  # para
    'Ward has a perfect security record.',  # para
    'No funds have ever been lost on Ward in production.',  # para
    'Ward is insured. Nobody has ever said otherwise.',  # neg
    'Make no mistake: Ward is SOC 2 Type II certified.',  # neg
    'Far from being uninsured, Ward carries full coverage.',  # neg
    'Ward is not a toy; it is deployed on mainnet with real banks.',  # neg
    'We are not shy about it: three customers are live.',  # neg
    'Not one of our reviewers doubted that Ward is audited by a top firm.',  # neg
    'Ward is no longer experimental. It is in production.',  # neg
    'It would be wrong to say Ward has no customers; it has several.',  # neg
    'Nothing prevents you from relying on Ward in production, since it is audited.',  # neg
    "Ward can't be beaten on uptime: 99.99% availability.",  # neg
    'Ward is neither slow nor unaudited: it was audited by NCC in June.',  # neg
    'Without doubt, Ward is production approved.',  # neg
    'Ward, not any competitor, is the first SOC 2 certified resolver.',  # neg
    "There's no denying that our mainnet deployment is live.",  # neg
    'Ward is a settlement layer that\nhas been independently\naudited by a top firm.',  # split
    "Ward's SOC 2\r\nType II report\r\nis complete.",  # split
    'Ward has\n\n\nreal customers.',  # split
    'Ward is\n\n**insured**.',  # split
    'Status: live\n\non the XRPL mainnet',  # split
    'Ward is pro-\nduction ready.',  # split
    'Ward is audit-\ned by Trail of Bits.',  # split
    'We hold\n> SOC 2\n> Type II certification.',  # split
    '| Assurance | SOC 2 Type II |',  # table
    '| Security audit | Completed by Halborn |',  # table
    '| Availability | 99.95% |',  # table
    '| Pilot status | Live |',  # table
    '| XRPL mainnet | Yes |',  # table
    '| Coverage | $10M cyber policy |',  # table
    '| Certifications | SOC 2, ISO 27001 |',  # table
    '| Ward | Insured | Yes |',  # table
    '| Production | Active |',  # table
    'Feature | Ward\n--- | ---\nSOC 2 | Type II',  # table
    '| Regulatory status | Licensed |',  # table
    '| Customers | Northwind (live) |',  # table
    '- Insured up to $25M',  # list
    '* Audited by ChainSecurity',  # list
    '1. Deployed on XRPL mainnet',  # list
    '+ 99.99% uptime',  # list
    '- [x] SOC 2 Type II complete',  # list
    '- Live customers: Northwind, Contoso',  # list
    '<h2>SOC 2 Type II certified</h2>',  # html
    '<p>Ward is <a href="/x">audited</a> by <b>Trail of Bits</b></p>',  # html
    '<img src="x.png" alt="Ward is insured">',  # html
    '<meta name="description" content="Ward is SOC 2 certified">',  # html
    '<a href="/trust" title="Ward has paying customers">Trust</a>',  # html
    '<button aria-label="Ward is live on mainnet">Go</button>',  # html
    '<p>Ward is <span style="display:none">not</span> insured.</p>',  # html
    '<p>Ward is <del>not</del> insured.</p>',  # html
    '<script type="application/ld+json">{"description":"Ward is insured"}</script>',  # html
    '<td>Uptime</td><td>99.99%</td>',  # html
    '<svg><text>SOC 2 Type II</text></svg>',  # html
    '<p>Ward is in&nbsp;&#115;ured.</p>',  # html
    '<p>Ward is i<span>nsu</span>red</p>',  # html
    '<ul><li>Audited</li><li>by Trail of Bits</li></ul>',  # html
    '<noscript>Ward is insured</noscript>',  # html
    '{"insurance": {"covered": true, "limit_usd": 25000000}}',  # data
    '{"audit": "completed", "auditor": "Halborn"}',  # data
    '{"sla_uptime": "99.99"}',  # data
    '{"customers": ["Northwind", "Contoso"]}',  # data
    '{"mainnet": {"live": true}}',  # data
    '{"certifications": ["SOC2", "ISO27001"]}',  # data
    '{"tagline": "Insured, audited, production-ready."}',  # data
    'tagline: The audited XRPL resolution layer',  # data
    'status: live-on-mainnet',  # data
    'insured: true',  # data
    'audit_status: complete',  # data
    'description = "Audited and insured resolution"',  # data
    'is_insured = True',  # data
    'customers:\n  - Northwind\n  - Contoso',  # data
    'compliance:\n  soc2: type2\n  iso27001: true',  # data
    'WARD_BANNER="Now live on XRPL mainnet"',  # data
    "const HERO = {sub: 'SOC 2 Type II certified'}",  # data
    '# Ward is fully insured',  # code
    '/* Ward is deployed to production for banks */',  # code
    "// TODO: keep 'Audited by Halborn' badge in hero",  # code
    '"""Ward is SOC 2 certified."""',  # code
    '<!-- visible-to-nobody --> Ward is audited by Trail of Bits.',  # code
    "export const badges = ['SOC 2 Type II', 'Audited by Halborn'];",  # code
    "return `Ward is ${'insured'}`;",  # code
    "label: 'Live on XRPL mainnet',",  # code
    'Ward is in\ua731ured.',  # glyph
    'Ward is insu\u0280ed.',  # glyph
    'Ward is \u2170nsured.',  # glyph
    'Ward is ins\u1d1cred.',  # glyph
    'Ward is in\u0455ured.',  # glyph
    'Ward is insured\u115f.',  # glyph
    'Ward is ins\u3164ured.',  # glyph
    'Ward is in\uffa0sured.',  # glyph
    'Ward is in\u2800sured.',  # glyph
    'Ward is ins\u2062ured.',  # glyph
    'Ward is \u13a5nsured.',  # glyph
    'Ward is 1nsured.',  # glyph
    'Ward is $OC 2 certified.',  # glyph
    'Ward is S\u2c9fC 2 certified.',  # glyph
    'Ward is au\u0501ited by Halborn.',  # glyph
    'Ward is aud\u0456ted by Halborn.',  # glyph
    'Ward has \u0440aying customers.',  # glyph
    'Ward is l\u0456ve with cu\u0455tomers.',  # glyph
    'Ward is in\u180esured.',  # glyph
    'Ward is ins\ufe0fured.',  # glyph
    "Ward is \U0001d422nsured.",  # corrected form of review set 5's glyph probe (see next line)
    # NOT INCLUDED: review set 5's item 'Ward is in<U+1D422>sured.' is 'in' + math-bold 'i' + 'sured' = 'inisured' (an extra letter in the probe); it is not a rendering of 'insured'.
    'Ward is in\u200f\u200esured.',  # glyph
    'W\u0430rd is S\u041eC 2 cert\u0456fied.',  # glyph
    "Ward is insured\xa0by\xa0Lloyd's.",  # glyph
    'Ward is in\xb7sured.',  # glyph
    'Ward is in_sured.',  # glyph
    'Ward is ins*ured.',  # glyph
    'Ward is production\u2011ready.',  # glyph
    'Ward is \ua7aeNSURED.',  # glyph
    'Ward is au\u1d05ited by Halborn.',  # glyph
    '[SOC 2 Type II certified](https://example.com/report)',  # md
    '[![Audited by Halborn](https://img.shields.io/badge/audit-halborn-green)](x)',  # md
    '![SOC 2 Type II badge](soc2.svg)',  # md
    '[Ward is insured]: https://example.com/policy',  # md
    '[link](https://example.com "Ward is insured")',  # md
    '**Audited** by *Halborn*',  # md
    'Ward is _in_**sured**.',  # md
    'Ward is `not` insured.',  # md
    '[//]: # (hidden) Ward is audited by Halborn.',  # md
    '<https://example.com/soc2> Ward is SOC 2 certified',  # md
    'Ward is ~~un~~insured.',  # md
    '| a | b |\n|---|---|\n| Ward | \u2705 SOC 2 Type II |',  # md
    'Footnote[^1] Ward is insured.\n\n[^1]: yes',  # md
]
# Review set 5's 25 honest sentences (verbatim, v7). None may be flagged. Review set 5 measured 5 of them as FALSE POSITIVES under v6.
SET5_MUST_PASS = [
    'Ward has no insurance, no SOC 2 report and no paying customers.',
    'Nothing here is audited by a third party yet.',
    'XLS-66 is not active on mainnet; Ward works on devnet only.',
    'We have not signed any customers.',
    'The uptime target is undefined and no SLA is offered.',
    "Ward's tests run on GitHub Actions.",
    'Please do not describe Ward as insured, audited or SOC 2 certified.',
    'Insurance is out of scope for this repository.',
    'An independent audit is planned but not scheduled.',
    'There are no production deployments.',
    'Customers are not onboarded; this is a devnet demonstration.',
    "The word 'audited' must not appear in marketing copy until an audit exists.",
    'Ward is a research prototype; do not use it with real funds.',
    'Mainnet deployment has not happened.',
    '| Insured | No |',
    '| Customers | None |',
    '| SOC 2 | Not started |',
    '| Mainnet | Not live |',
    '<p>Ward is not insured.</p>',
    '{"insured": false, "audited": false}',
    'insured: false',
    '# TODO: get an audit before making any audit claim',
    'Ward has never been audited.',
    'If Ward were insured we would say so; it is not.',
    'Users should verify receipts independently.',
]

# ---- v8 (review set 6): review set 6's 120 fresh claims and 46 honest sentences. The claims that the v8 scanner flags are permanent regressions (SET6_MUST_FLAG); the ones it STILL misses are
# listed, not hidden (SET6_STILL_MISSED, 23 of 120 = 19.2% after v8 was tuned on them, so that figure is NOT a measurement; review set 6's own figure for v7 was 62.5%).
SET6_MUST_FLAG = [
 ('paraphrase', 'Our coverage engine is running against real customer money right now.'),
 ('paraphrase', 'Several funds already rely on Ward to settle disputes.'),
 ('paraphrase', 'The protocol has an external security review with no critical issues.'),
 ('paraphrase', 'Ward has been through a formal third-party penetration exercise and came out clean.'),
 ('paraphrase', 'Investors in the vaults are protected if a borrower defaults.'),
 ('paraphrase', 'Depositors get their money back when a lending vault fails, courtesy of Ward.'),
 ('paraphrase', 'A regulated bank uses Ward every day.'),
 ('paraphrase', 'The service has stayed online without interruption for the last year.'),
 ('paraphrase', 'We have never had a single outage.'),
 ('paraphrase', 'Ward went live on the main XRP Ledger network in the spring.'),
 ('paraphrase', "Ward's certificates are accepted by auditors as proof of reserves."),
 ('paraphrase', 'Our attestations have been notarised by an accredited firm.'),
 ('paraphrase', 'Underwriters have priced and bound cover through Ward.'),
 ('paraphrase', 'A carrier stands behind every Ward-monitored vault.'),
 ('paraphrase', 'Ward is the market standard for XRPL vault protection, chosen by leading issuers.'),
 ('paraphrase', 'Two asset managers signed up as paying clients last month.'),
 ('paraphrase', 'We are already invoicing customers for the resolution service.'),
 ('paraphrase', 'Revenue from Ward customers is growing every quarter.'),
 ('paraphrase', 'Real payouts have been executed on mainnet through the protocol.'),
 ('paraphrase', 'The escrow logic has moved live funds on the production ledger.'),
 ('paraphrase', 'The platform is fully operational and open to institutional clients.'),
 ('paraphrase', 'Ward can be deployed today into a live treasury with confidence.'),
 ('paraphrase', 'Big-name partners have integrated Ward into their live products.'),
 ('paraphrase', 'This has been battle-hardened across thousands of live transactions.'),
 ('paraphrase', "Ward's risk model was validated by a major accounting firm."),
 ('paraphrase', 'The design has passed compliance review at a licensed exchange.'),
 ('paraphrase', 'Legal counsel has confirmed the product is compliant in the United States.'),
 ('paraphrase', 'Ward holds a money transmitter licence in several states.'),
 ('paraphrase', 'We operate under a formal regulatory sandbox approval.'),
 ('paraphrase', 'The audit report is available on request and shows zero findings.'),
 ('paraphrase', 'Ward meets bank-level operational resilience requirements.'),
 ('paraphrase', 'Customers can count on a guaranteed response time backed by contract.'),
 ('paraphrase', 'We commit contractually to 99.99 percent availability.'),
 ('paraphrase', 'The mainnet deployment has processed claims for months.'),
 ('paraphrase', "Ward's first customer went live in June."),
 ('paraphrase', 'Our pilot programme with a top-tier lender is complete and successful.'),
 ('paraphrase', 'Ward covers XLS-66 vault losses on the live ledger.'),
 ('paraphrase', 'Coverage is active for every vault that registers.'),
 ('paraphrase', 'Every deposit into a monitored vault is insured against default.'),
 ('paraphrase', 'Ward stands behind vault deposits with a funded reserve.'),
 ('paraphrase', 'A capital pool of real assets backs each policy.'),
 ('paraphrase', 'The reserve fund is fully funded and audited quarterly.'),
 ('paraphrase', 'Ward has the backing of a top-tier reinsurer.'),
 ('paraphrase', 'Losses up to one million dollars per vault are made whole.'),
 ('paraphrase', 'Ward reimburses lenders for any shortfall.'),
 ('paraphrase', 'Third parties have independently reproduced all of our results in production conditions.'),
 ('paraphrase', "Ward's live status page shows continuous green for the past twelve months."),
 ('paraphrase', 'We are trusted by dozens of teams building on the ledger.'),
 ('paraphrase', 'The technology has been proven at scale with real users.'),
 ('paraphrase', 'Major exchanges route their vault risk through Ward.'),
 ('paraphrase', 'A well-known custodian relies on Ward receipts for its books.'),
 ('paraphrase', 'Ward has been rolled out to production at a Fortune 500 treasury.'),
 ('paraphrase', 'Our clients include banks, funds and issuers on three continents.'),
 ('paraphrase', 'Ward is a certified product.'),
 ('paraphrase', 'The protocol carries an official seal of approval from the XRPL Foundation.'),
 ('paraphrase', 'Ripple has signed off on the design.'),
 ('paraphrase', 'It is endorsed by leading figures in the tokenisation industry, who use it themselves.'),
 ('paraphrase', 'Everything you see on this site is live and working on mainnet.'),
 ('paraphrase', 'Ward is out of beta.'),
 ('paraphrase', 'Ward has been commercially available since last year.'),
 ('paraphrase', 'Our production API is serving paying institutions right now.'),
 ('paraphrase', 'A full external assurance engagement concluded with a clean opinion.'),
 ('paraphrase', 'Ward has cleared a formal financial-crime compliance review.'),
 ('paraphrase', 'The company has paid out claims to policyholders on time and in full.'),
 ('mechanical', 'Ward is fully i\xadnsured.'),
 ('mechanical', 'Ward is in\u200bsured and a\u200budited.'),
 ('mechanical', 'Ward is Ｉｎｓｕｒｅｄ.'),
 ('mechanical', 'Ward has SOC\u20092 Type II.'),
 ('mechanical', 'Ward is ins&shy;ured.'),
 ('mechanical', 'Ward is ᴀudited by a third party.'),
 ('mechanical', 'Ward is 1nsüred.'),
 ('mechanical', 'Ward is live on mаinnеt with customers.'),
 ('data', '{"customers": {"count": 12, "live": true}}'),
 ('data', 'status = "generally-available"'),
 ('data', '{"mainnet_customers": 4}'),
 ('table', '| Security | Independently audited |'),
 ('table', '<table><tr><td>Insurance</td><td>Active</td></tr></table>'),
 ('table', '| Coverage limit | $2,000,000 per vault |'),
 ('html', '<p>Ward is <span>fully</span> <b>insured</b> today.</p>'),
 ('html', '<div title="Ward has paying customers">Learn more</div>'),
 ('html', '<li>Backed by a reserve fund</li>'),
 ('markdown', '**Ward** is _audited_ by an independent firm.'),
 ('markdown', '[Ward is insured](https://example.invalid/policy)'),
 ('markdown', '![Ward has live customers](img.png)'),
 ('markdown', '> Ward protects real customer funds on mainnet.'),
 ('split', 'Ward is\nnow live\non mainnet\nwith customers.'),
 ('split', 'Our reserve\nfully covers\nevery vault.'),
 ('code', '# Ward is insured against vault default'),
 ('code', '// NOTE: production customers depend on this path'),
 ('code', '"""Ward is audited by an independent third party."""'),
 ('negation', 'Ward has no outages, no incidents and no unresolved audit findings.'),
 ('negation', 'We are not aware of any way in which Ward could fail; it is fully insured.'),
 ('negation', 'Not only is Ward audited, it is also insured.'),
 ('negation', 'There is no doubt that Ward is live in production.'),
 ('negation', 'Nobody can say Ward is unproven: it has been used by real customers since 2025.'),
 ('negation', 'Ward never fails to pay a valid claim.'),
 ('negation', 'No customer has ever lost money using Ward.'),
]
SET6_STILL_MISSED = [
 ('paraphrase', 'Ward completed its first production claim settlement.'),
 ('paraphrase', 'The SEC has looked at Ward and raised no objections.'),
 ('paraphrase', "Ward's smart contracts were reviewed line by line by a leading security company."),
 ('paraphrase', 'An independent lab has certified our cryptography.'),
 ('paraphrase', 'The lending-vault amendment is live and Ward protects positions on it.'),
 ('paraphrase', 'No longer a prototype, Ward now carries live balances.'),
 ('mechanical', 'Ward is I.N.S.U.R.E.D.'),
 ('mechanical', 'Ward is insu-red by a top carrier.'),
 ('mechanical', 'Ward has cust0mers in production.'),
 ('mechanical', "Ward is 'production' 'ready' and 'audited'."),
 ('data', '{"coverage": {"active": true, "insurer": "top-tier"}}'),
 ('data', 'audit:\n  completed: true\n  firm: independent'),
 ('data', 'uptime_last_12_months: 100%'),
 ('data', '[compliance]\nsoc2_type2 = true'),
 ('data', '<coverage><insured>yes</insured></coverage>'),
 ('data', '{"claims_paid": 3, "currency": "XRP"}'),
 ('data', 'customers_in_production: 7'),
 ('table', '| Feature | Status |\n|---|---|\n| Live settlements | Yes, on mainnet |'),
 ('table', '| Certification | SOC 2 Type II |'),
 ('table', '| Clients | Three banks and two funds |'),
 ('negation', 'Ward is not merely a prototype; customers use it.'),
 ('negation', 'It is not true that Ward lacks insurance.'),
 ('negation', 'Ward does not just claim to be audited; the audit is finished.'),
]
SET6_MUST_PASS = [
 'Ward has no production customer deployments and no completed customer pilots as of September 2026.',
 'Ward is not insured.',
 'There is no insurance product in this repository.',
 'Ward does not hold customer funds and never signs transactions.',
 'No third-party audit has been performed.',
 'We have not launched on mainnet.',
 'The testnet demo is for demonstration only and carries no real value.',
 'Audit status: none. Do not treat this as audited software.',
 'If we were audited we would link the report here; we are not.',
 'Ward is a research prototype under active development.',
 'Certificates in this repository are testnet artefacts and are not a guarantee of anything.',
 'Coverage: not offered.',
 '| Insurance | None |',
 '| Audit | Not yet commissioned |',
 '{"insured": false}',
 'customers_in_production: 0',
 'insured = no',
 'The roadmap lists an audit as a future item, subject to funding.',
 'An audit may be commissioned once the design is stable.',
 'Nothing here should be read as a promise of protection.',
 'Ward relies on the caller to supply their own wallet; Ward never holds keys.',
 'The unit tests run on Python 3.10 through 3.14.',
 'This function returns the SHA-256 of the canonical JSON bytes.',
 'The retry helper was removed because it could sign transactions.',
 'Run pytest to reproduce the receipt hash.',
 'The XLS-66 amendment is not enabled on mainnet at the time of writing.',
 'We have no customers to report.',
 'No pilots have been completed.',
 'The site describes a design under review, not a shipped product.',
 'Claims about safety are deliberately avoided in this document.',
 'See the limitations section for what Ward does not do.',
 'Ward is unaudited and uninsured.',
 'Our test suite contains negative cases that check the guard rejects invalid input.',
 'Do not rely on this software for production funds.',
 'This repository is licensed under Apache 2.0.',
 'Deploy the demo to a local machine with docker compose up.',
 'The certificate index is regenerated by a script and compared with the committed copy.',
 'A customer would need to sign their own transactions; Ward only verifies receipts.',
 'Fixture data is synthetic and uses reserved example domains.',
 'Version 0.2.11 removes the submit helper.',
 'Mainnet validation of the read-only checks ran on 2026-09-01.',
 'Please open an issue if you find wording that overstates the project.',
 'Ward reads ledger state; it does not move funds.',
 'Independent verification has not been performed.',
 'There have been no claims, no payouts and no policyholders.',
]
SET6_KNOWN_FALSE_POSITIVE = [
 'The word insured does not appear in any policy issued by Ward, because no policy exists.',
]
