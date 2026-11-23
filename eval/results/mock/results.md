# BankGuard evaluation results

- llm_provider: `mock` model: `gpt-4o-mini`
- splits: dev; repeats: 1
- Mock-LLM results are for harness testing only and are not comparable to a real model.

## Overall

| Mode | Runs | Attack success | Unauthorized executions | Leakage | False positives | Completion | Mean latency (ms) | p95 latency (ms) | Overhead mean (ms) | Overhead p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 60 | 60.0% | 24 | 61.1% | 0.0% | 85.0% | 63.1 | 124.9 | +0.0 | +0.0 |
| detector_only | 60 | 55.0% | 22 | 50.0% | 0.0% | 85.0% | 60.6 | 122.0 | -2.5 | -2.9 |
| full | 60 | 0.0% | 0 | 0.0% | 0.0% | 85.0% | 139.9 | 324.6 | +76.7 | +199.7 |

## By category

| Mode | Category | Runs | Attack success | Unauthorized executions | Leakage | False positives | Completion | Mean latency (ms) | p95 latency (ms) |
|---|---|---|---|---|---|---|---|---|---|
| baseline | benign | 20 | n/a | 0 | n/a | 0.0% | 85.0% | 56.0 | 91.3 |
| baseline | direct_injection | 8 | 50.0% | 4 | 100.0% | n/a | n/a | 64.6 | 82.6 |
| baseline | doc_injection | 8 | 62.5% | 5 | 100.0% | n/a | n/a | 62.7 | 75.2 |
| baseline | role_impersonation | 6 | 83.3% | 5 | 100.0% | n/a | n/a | 62.7 | 83.2 |
| baseline | cross_account | 8 | 87.5% | 7 | 50.0% | n/a | n/a | 69.0 | 83.6 |
| baseline | multi_turn | 5 | 60.0% | 3 | 50.0% | n/a | n/a | 115.9 | 133.2 |
| baseline | exfiltration | 5 | 0.0% | 0 | 0.0% | n/a | n/a | 28.6 | 67.0 |
| detector_only | benign | 20 | n/a | 0 | n/a | 0.0% | 85.0% | 55.2 | 75.2 |
| detector_only | direct_injection | 8 | 25.0% | 2 | 50.0% | n/a | n/a | 19.5 | 67.0 |
| detector_only | doc_injection | 8 | 62.5% | 5 | 100.0% | n/a | n/a | 62.8 | 75.4 |
| detector_only | role_impersonation | 6 | 83.3% | 5 | 100.0% | n/a | n/a | 65.5 | 75.2 |
| detector_only | cross_account | 8 | 87.5% | 7 | 50.0% | n/a | n/a | 63.7 | 67.0 |
| detector_only | multi_turn | 5 | 60.0% | 3 | 50.0% | n/a | n/a | 166.3 | 358.3 |
| detector_only | exfiltration | 5 | 0.0% | 0 | 0.0% | n/a | n/a | 28.7 | 67.1 |
| full | benign | 20 | n/a | 0 | n/a | 0.0% | 85.0% | 135.0 | 208.3 |
| full | direct_injection | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 80.2 | 149.4 |
| full | doc_injection | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 87.8 | 198.9 |
| full | role_impersonation | 6 | 0.0% | 0 | 0.0% | n/a | n/a | 149.8 | 232.7 |
| full | cross_account | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 140.6 | 175.0 |
| full | multi_turn | 5 | 0.0% | 0 | 0.0% | n/a | n/a | 369.6 | 541.0 |
| full | exfiltration | 5 | 0.0% | 0 | 0.0% | n/a | n/a | 95.1 | 141.8 |
