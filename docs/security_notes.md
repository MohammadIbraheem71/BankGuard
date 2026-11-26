# BankGuard security notes

## What M3 measured

The team reported 0% attack success and 0% false positives in the earlier full-mode, real-model development evaluation. M3 measured the detector and policy directly. A detector flag measures recognition of a cue. End-to-end attack success depends on tool authorization, transfer confirmation, and the outgoing reply.

The frozen local corpus contains 40 labeled cues, 24 benign phrases, and 13 typed policy calls. The cues include role-label specimens, harmless directions in documents, practice dialogue, and opaque strings encoding classroom text. The benign phrases include banking questions, Urdu and Roman Urdu, Unicode typography, and document markup. The turn-isolation controls inspect the preceding benign turn and the current turn individually. The inputs are synthetic and the runner reads only the local fixture file.

| Measure | Before | After |
| --- | ---: | ---: |
| Detector recall on labeled cues | 37/40 (92.5%) | 40/40 (100%) |
| Benign phrases flagged | 4/24 (16.7%) | 0/24 (0%) |
| Permitted tool calls allowed | 8/8 | 8/8 |
| Forbidden tool calls denied | 5/5 | 5/5 |
| Permitted transfers requiring confirmation | 4/4 | 4/4 |

Three heading controls accounted for the missed cues. Four explicitly self-scoped account-list requests accounted for the false positives. The revised rules recognize role headings in Markdown and narrow the bulk-account rule when the request explicitly ends with an ownership qualifier. An additional regression covers an unqualified bulk-account request. Work stopped after those two rule changes. Both measurements use the same fixtures used to choose the changes, so the final rates describe regression coverage. Eight positive labels deliberately test recognition of encoded-looking text with harmless contents.

## Detector cost

| Input | Observations per run | Before median / p95 (ms) | After median / p95 (ms) |
| --- | ---: | ---: | ---: |
| User message | 4,800 | 0.015042 / 0.022583 | 0.015750 / 0.023583 |
| Retrieved document | 1,600 | 0.016084 / 0.026421 | 0.016917 / 0.025752 |

Measurements used Python 3.11.15 on arm64 macOS. After three warm-up passes, the runner timed each inspection with a monotonic nanosecond clock for 100 passes and subtracted a paired no-op call. These timings cover short fixture strings. A full-mode request also incurs the cost of checking each retrieved document, database access, and model inference. Sub-microsecond differences between runs are sensitive to machine load. The detector/policy counts in the table are the reproducible controls; the millisecond values are illustrative for that machine and are not expected to match exactly on another OS, Python version, or CPU.

From the repository root, run the following in the project environment. Commit `b66adf0` contains the baseline runner and frozen inputs. Commit `d645f93` contains the revised rules.

```sh
PYTHONPATH=. python tests/security/test_m3_controls.py
python -m pytest tests/security/test_m3_controls.py
```

## Where the controls apply

The detector normalizes text, gives each matched category a fixed weight, and flags a score of 0.65 or higher. It checks a single message or document at a time. Static reasons describe the category without copying the input.

The policy decides ownership from the authenticated user. An owned source can pay a different account held by the same customer, another customer, or a valid external reference. The exact source account and its alias are rejected as destinations. Approved transfers require an authenticated confirmation bound to the pending transfer details. These checks also apply when the detector allows a request.

The response guard preserves the signed-in customer's identifiers and removes other customers' known identifiers. It removes synthetic canary markers from replies. A marker for the signed-in customer in a verified transaction on an owned account can be removed while allowing that transaction reply. Foreign or unverified markers, internal prompt disclosures, and contradictory recognized monetary claims cause an unsafe verdict.

Security events carry fixed summaries and validated metadata. Transfer and document identifiers now survive both SQLite storage and authenticated event retrieval. The sanitizer accepts short ASCII correlation strings, checks tool and category names against the contract, and drops unrecognized fields. It treats long digit sequences as potential personal data, so some legitimate numeric references are also dropped. Callers must supply identifiers from structured metadata fields. A single ordinary word can have the same shape as a valid identifier. Historical rows with empty details contain no recoverable identifier.

## Remaining limitations

- A finite collection of lexical rules has limited coverage of language, scripts, and intent. Stronger matching can also flag legitimate quotations, role labels, or opaque references.
- The detector evaluates one input at a time. Intent that depends on conversation history or relationships between documents requires context beyond this interface.
- Outgoing privacy checks depend on known identifiers, synthetic marker conventions, and recognizable monetary claims. Their coverage depends on what the backend can verify.
- The fixture set is small and hand-labeled. The positive controls exercise selected cues and do not estimate the frequency of successful attacks in deployed traffic. Authorization and confirmation provide independent enforcement at the point where a tool can access data or move funds.
