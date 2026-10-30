# Phase3E-A offline odds and post-match evaluation handoff

## Authority and verified baseline

Executed the owner's explicit implementation instruction and all eight verified
handoff-manifest documents. Their earlier planning-only status is superseded only
for this scope. Read AGENTS, README, prior handoffs, settlement/payout, Poisson,
prospective recorder, shadow adapter, real model and existing scoring tests.
Remote/local main matched152ad62a6d4f7d7ba3cae1b47933582db20f3254 and tree
ab1c3a0274d178cd0216cbe087fd990ee323c956. Branch
codex/phase3ea-offline-odds-evaluation starts there. Baseline563 tests passed
in8.076s on Windows CPython3.12.14. Budget฿0, stdlib only, no subagents.

All prior Python modules, tests, fixtures and Trial1 remain untouched. Trial1
commitment39d137da033ef661682f0d162d259d8074bdb7b131eea35cf467f6bd0e494131
was not loaded, replaced, graded or claimed independently published. No real
odds, result, private image, copyrighted bookmaker extract, independent review
or historical timestamp was invented. The only new example is the clearly
invented factory in tests/odds_evaluation_cases.py and its parameter mutations.
No paid API, network code, scraping, credentials, publication, bet execution,
odds integration, fitting, deployment, merge or3E-B work.

## Research before coding and rights audit

- [surebet](https://github.com/HintikkaKimmo/surebet/tree/f17f0c93b506f9bcfa085be08bda3a1735daf05a),
  masterf17f0c93b506f9bcfa085be08bda3a1735daf05a, last commit2018-04-06.
  Read MIT LICENSE, surebet/converter.py and tests/test_converter.py. Useful
  explicit per-format functions and positive/negative test vectors. Rejected
  floating intermediates, automatic2-decimal rounding, permissive domains and
  its arbitrage/execution ecosystem. Old project, not an adopted dependency.
- [odds.converter](https://github.com/marcoblume/odds.converter/tree/f9252cbdb39efc889b5519bf4973a0cfc9b57245),
  masterf9252cbdb39efc889b5519bf4973a0cfc9b57245,2018-07-09, version1.4.9.
  Read DESCRIPTION(GPL3), R/odds.malay2dec.R and R/odds.indo2dec.R. Confirmed
  different domains and sign formulas; independently implemented elementary
  mathematics. No GPL source copied or dependency imported. No upstream code
  executed. No current maintenance/security guarantee inferred from old code.
- [Pinnacle odds formats](https://support.pinnacle.bet/hc/en-us/articles/46734345399313-What-are-the-different-odds-formats-available)
  explains decimal gross return and American risk/profit conventions.
- [Pinnacle AH](https://support.pinnacle.bet/hc/en-us/articles/45192829163921-What-is-an-Asian-Handicap-in-soccer-betting)
  and [Virgin Bet rules](https://help.virginbet.com/hc/en-gb/articles/29726972639506-Understanding-Handicap-Bets)
  confirm quarter-stake splitting, pushes and half outcomes. In-play reset
  semantics are explicitly rejected; this code handles pre-match REGULATION_90.
  Provider-specific void rules, extra time and three-way handicap are excluded.

Bookmaker pages are factual research references, not redistribution permissions,
current price feeds, result verification or evidence of the owner's UI notation.
No extracts or genuine market data are packaged. Code licenses grant no data
rights. Record rights remain explicit and evaluation requires CLEARED plus
out-of-band approved hashes and matching supplied source bytes. Local hashes
never certify source truth, reviewer identity or first-publication time.

## Minimal design and schema refinements

Two new pure modules: odds_observations.py and result_evaluation.py. Immutable
FrozenRecord contains protocol, canonical_bytes and domain-separated SHA256.
Evaluation contains status, canonical_bytes and SHA256. No I/O or clock calls.
Existing strict JSON loader rejects duplicate keys, floats, NaN, bad UTF8 and
records>64KiB; URLs/identifiers/UTC validation reuse recorder primitives. Missing
or unknown fields fail. Type/identity/time validation fails closed by ValueError;
unverified/nonregulation results return PENDING, not zero or a loss.

Odds required fields follow the handoff plus snapshot_id. Source/capture/claimed/
independent-observation times are distinct; provenance_assurance is always
LOCAL_ONLY. source_kind is MANUAL_TRANSCRIPTION or RETAINED_SNAPSHOT. Rights
are CLEARED/UNKNOWN/BLOCKED. Exact fields are visible in the small invented
factory and freeze_odds required set. Late observations are retained with
LATE_UNSUITABLE_FOR_PREMATCH rather than silently backdated/discarded.

price(raw_text, explicit_format)->Fraction is authoritative. Plain ASCII
decimal text: optional sign, integer part, optional1..18 fractional digits,
length<=32. Magnitude1e-12..1e12 bounds work. No floats, Unicode signs, commas,
exponents, bare decimal point, NaN or inferred format. Domains:
DECIMAL>1; HK>0; American explicit signed integer magnitude>=100;
Malay0<abs(x)<=1; Indonesian abs(x)>=1. Sign formulas follow the supplied math.
Explicit AMERICAN -100 means2, never AH -1/-0.5. AH requires integer quarter
units[-80,80] on HOME/AWAY; 1X2 requires null handicap and HOME/DRAW/AWAY.

Refinement: recurring conversions cannot be represented by a finite decimal
string exactly. decimal_price is a deterministic30-place display string;
decimal_price_exact is a canonical Fraction string and is authoritative for
no-vig/net arithmetic. price_display_policy states this explicitly. Supplied
calculated fields must match recomputation. Raw quote text is preserved.
No context-dependent Decimal arithmetic in conversion or display formatting.

freeze_odds(payload,source_bytes=None) and freeze_result(payload,source_bytes=None)
hash bytes only when provided, validate any matching declared hash, otherwise
retain null or an explicitly unverified caller hash. A serialized hash alone is
not evidence of retained bytes. Comparison/scoring REHASH actual source bytes
again and fail/PENDING if missing/mismatched, even for an approved record hash.
Source-byte input bounded4MiB at freezing. External audit must establish rights
and source authenticity; no automatic trust upgrade exists.

checked(record) reparses/recomputes canonical record and hash. append_record
returns a NEW tuple; validate_chain requires the complete root(None predecessor),
exact links and no duplicate hash. An optional independently anchored expected
head detects re-sealed replacement histories. Hash chains are not physical
write protection, signatures or trusted timestamps; external head anchors and
retained bytes are needed to detect wholesale rewriting.

## Evaluation and mathematical behavior

compare_1x2 requires exactly three distinct H/D/A selections, same exact fixture,
bookmaker, snapshot_id, source URL/hash and capture/claim/review time. Only1X2
REGULATION_90. Source bytes and separately approved record pins are mandatory.
Rights cleared, timestamps known and no later than BOTH forecast capture and
cutoff. This conservative policy excludes later closing prices even when before
kickoff; they must not be retroactively treated as forecast-time inputs.
It preserves forecast probabilities, reports exact overround=sum(1/D)-1,
q=(1/D)/sum(1/D), and model-minus-no-vig. Negative margins are reported rather
than treated as profitable opportunities. Proportional no-vig is a benchmark
method, not objective outcome chances. AH never uses naive1/D side normalization.

freeze_result requires separate result protocol, exact identity/REGULATION_90,
integer goals0..99 only for FINISHED_REGULATION. UNKNOWN,POSTPONED,ABANDONED,
AWARDED,EXTRA_TIME records retain no goals and cannot be graded. Recorded time
must follow kickoff, and a finished result must be at least90min after kickoff
(necessary lower bound, not proof of final whistle). Verified time cannot
predate capture. Result bytes, CLEARED rights, approved result digest, review
time<=evaluation and reviewer distinct from operator are required for scoring.
Claims alone never constitute independent review. Caller supplies known_results
history; any conflicting regulation score prevents grading. Undisclosed external
conflicts cannot be discovered offline; the caller must provide complete history.

score_1x2 validates original FrozenEvidence by exact recorder replay, preserving
original bytes/digest. NO_FORECAST->EXCLUDED_NO_FORECAST; unverified/unknown/
conflicting result->PENDING. A verified outcome yields n=1, unscaled Brier
sum(p-onehot)^2 in[0,2] as exact Fraction, and natural log loss. Zero actual
probability is explicitly POSITIVE_INFINITY, never silently clipped/NaN.
One match is not calibration/accuracy evidence. summarize returns n,pending,
excluded and means only for n>0, rejects duplicate forecasts and altered output
checksums; no zero-score fill-in or overall profitability metric.

settle_ah validates the same fixture/quote/result guards and delegates all five
outcomes to settle_handicap. Existing calculate_payout also reports the exact
payout AT THE DISPLAY DECIMAL price. Authoritative hypothetical net uses the
existing settlement win/loss Fractions with the exact converted price; recurring
price display rounding never silently affects authoritative net. All outputs
say hypothetical unit net, not actual betting ROI or proof a wager occurred.

ah_model_value is explicitly hypothetical model analysis, not the frozen1X2
packet reinterpreted as an AH forecast. It verifies the supplied immutable
Poisson distribution by reconstruction with existing explicit-cap API, reuses
asian_handicap buckets, and computes (FW+HW/2)*(D-1)-(HL/2+FL). Push=0.
No renormalization. Raw retained/omitted mass and geometric upper bound remain.
Lower/upper unit net add worst-case omitted loss(-1) or gain(D-1). These bounds
address truncation only, not parameter/model uncertainty or profitability.

## API example (invented only, not external approval)

```python
from tests.odds_evaluation_cases import packet, trio, scoring, RAW
from premfootballbot.result_evaluation import compare_1x2, score_1x2

frozen = packet()  # Explicitly invented fixture/forecast, not Trial1.
quotes = trio()
# Test-only pins below stand in for a SEPARATELY provisioned external-review
# registry. Never self-pin genuine incoming records to manufacture approval.
demo_pins = tuple(q.sha256 for q in quotes)
comparison = compare_1x2(frozen, quotes, source_bytes=RAW,
                         approved_odds_sha256=demo_pins)
final, demo_review = scoring()
evaluation = score_1x2(frozen, final, **demo_review)
assert comparison.status == "COMPARABLE" and evaluation.status == "SCORED"
```

Production integration must supply actual retained bytes and independent review
registries, not the invented helper. No real price/result is accepted by this
delivery and no original forecast is rewritten.

## Actual tests, changed files and review gate

Baseline563 passed8.076s. Initial targeted50 passed0.077s. After source-byte/
conflict tests, full suite620 passed8.647s on Windows CPython3.12.14:563 unchanged
plus57 new tests (16 individual format vectors, domain/JSON/ledger defenses,
snapshot matching, exact scores/infinite loss, conflicting/unverified results,
AH named cases and110 side/quarter/score subcases, enumeration/tail checks,
no I/O, unchanged forecast bytes and resealed evidence rejection).
Commands: python -B -m unittest tests.test_odds_evaluation -v;
python -B -m unittest discover -s tests -v.
Final committed-export reruns and counts/timings are in review evidence. No Linux,
Python3.13, remote CI or external linter/type checker execution claimed here.

Changed files: README.md; premfootballbot/odds_observations.py;
premfootballbot/result_evaluation.py; tests/odds_evaluation_cases.py;
tests/test_odds_evaluation.py; this handoff. All earlier source/tests/fixtures
are byte-identical. Review ZIP includes exact complete Git source, patch,
manifest, baseline/final verbose logs, design checkpoint and source audit.

No unresolved local test failures. Review external-pin provisioning, complete
conflict/history handling, actual rights/timing and provider-specific rules before
any real use. Independent review and separate owner merge approval are required;
draft PR only. No3E-B or operational pilot authorization is implied.
