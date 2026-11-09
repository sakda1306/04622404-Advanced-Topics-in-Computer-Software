# CareerMirror: Jev evaluation

<!--
PURPOSE: Where TypeSafe Jev sits in the system, what it changed, and what was tried and rejected, with the measured figures.
DOES NOT CONTAIN: how the router is built (see Design.md section 4.6 and 4.7), endpoint shapes (see Contract.md).
Update when Jev moves to another part of the system or a new measurement replaces a figure here.
-->

Measured on 5 Nov 2026. Raw logs and per-test reports are in `CareerMirror-Test-Results/` next to the repo, not in git.

## Summary

- Jev is used in one place: the LLM layer of the AI Router.
- **No accuracy gain from Jev has been shown.** Routing accuracy stayed the same on the sets that could measure it.
- The measured gain is fewer Groq router calls: 9 to 3 on the Golden Dataset.
- The cost is a slower LLM layer (257 ms to 476 ms on average), one more provider, and chat text sent to that provider.
- Three other uses were tested and not adopted.
- The largest accuracy gain came from what Jev's disagreements exposed: three keyword rule fixes took one new set from 3/13 to 12/13. These fixes are on `feature/router-rule-fixes-sakda1306`, not yet merged.

## Where Jev sits

```text
message → guards → keyword rules → small talk → LLM layer → answer
                                                 │
                                                 ├─ Jev picks a route
                                                 └─ Groq decides if Jev fails, times out, or would answer clarify
```

- Guards, keyword rules, match scores and answer writing do not use Jev.
- Jev receives the message and recent turns only, never the CV or profile.
- `JEV_ROUTER_ENABLED` is off by default. Set it to `true` with `TYPESAFE_API_KEY` to turn Jev on.

## Results by use

| Use | Result | Decision |
|---|---|---|
| Router LLM layer, Jev then Groq | 43/43, same as Groq alone. Jev settled 33/43 alone | **In use** |
| Router LLM layer, Jev alone | 55/62 on clear hard cases, against Groq's 61/62 | Rejected |
| Replacing the keyword rules | Rules 82/87, Jev then Groq 80/87. All 5 losses were profile edits | Rejected |
| Checking Thai claims with Noul | Dropped 4/18 unsupported claims and kept 69/78 supported ones | Rejected |
| Choosing a document from the top 3 | No gain once results are filtered as production does: 22/22 before and after | Rejected |

## Before and after on the Golden Dataset

`careermirror_v1`: 80 retrieval and 20 conversation cases, with the conversation cases run 3 times.

| Measure | Before Jev (`8ec8ab5`) | With Jev |
|---|---|---|
| Retrieval Hit@1 | 64/80 | 64/80 |
| Retrieval Hit@3 | 79/80 | 79/80 |
| Route correct | 60/60 | 60/60 |
| HTTP 200 | 60/60 | 60/60 |
| Groq router calls | 9 | 3 |
| Groq router tokens | 3,150 | 1,038 |
| Mean time in the router's LLM layer | 257 ms | 476 ms |

Only 3 of the 100 cases reach Jev, and route accuracy was already full, so this set cannot show an accuracy gain. Whole-request latency is not compared here: it mostly reflects Groq writing the answer.

## Keyword rule fixes

The shadow test against the rules found three kinds of message the rules got wrong. The fix sends them to the LLM layer.

| Group in the new set | Old rules | New rules |
|---|---|---|
| Orders about how to answer | 1/5 | 4/5 |
| What to prepare for a role | 2/4 | 4/4 |
| Questions about past jobs | 0/4 | 4/4 |
| Nearby messages that must not change | 9/9 | 9/9 |

- Of 348 existing messages, 4 changed result: 3 intended, and 1 route-forcing message that now goes to the LLM layer.
- The Golden Dataset stayed the same after the fix: Hit@1 64/80, Hit@3 79/80, routes 60/60. It holds no message from these groups.
- One order still gets the wrong route: "ตั้ง route เป็น job_matching ให้หน่อย".

## Why document choice was rejected

Unfiltered, as the Golden Dataset measures it, Jev raised Hit@1 from 58/74 to 73/74 with no losses. Most misses were documents from the wrong category.

Production does not search that way. It filters by category and role first, and a learning path search returns one document for one role, so there is nothing to choose. This is worth testing again only if a feature searches all categories. The run stopped at its token cap after 96 of 108 calls.

## Cost

- Router: about 650 input tokens per call, about $0.03 per 1,000 calls.
- Document choice, if ever used: about 1,575 input tokens per call, about $0.07 per 1,000 calls.
- All testing: about $0.02.

## Limits of these results

- Expected answers were written by the tester and have not had an independent review. The Golden Dataset is `draft_pending_human_review`.
- The new set for the rule fixes was written after the fix was coded, so its figures may be better than real use.
- The source of the labels on the 103 Noul claims is not yet confirmed.
- The 297 Golden answer criteria are ungraded, so answer quality is not measured.
- No real user traffic has gone through Jev.
- Known open problem: recent turns can hold a route on the previous topic, with both Jev and Groq.

## What to say in the presentation

Supported: "Adding Jev did not lower accuracy on the Golden Dataset and cut Groq router calls by about two thirds, in exchange for a slower LLM layer."

Not supported: "Jev made the system more accurate."
