# BankGuard evaluation results

- llm_provider: `openai` model: `gpt-4o-mini`
- splits: heldout; repeats: 1
- Mock-LLM results are for harness testing only and are not comparable to a real model.

## Overall

| Mode | Runs | Attack success | Unauthorized executions | Leakage | False positives | Completion | Mean latency (ms) | p95 latency (ms) | Overhead mean (ms) | Overhead p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 60 | 10.0% | 3 | 5.0% | 0.0% | 100.0% | 2743.8 | 7408.6 | +0.0 | +0.0 |
| detector_only | 60 | 7.5% | 2 | 5.0% | 0.0% | 100.0% | 2555.7 | 6856.9 | -188.1 | -551.8 |
| full | 60 | 0.0% | 0 | 0.0% | 0.0% | 100.0% | 2612.1 | 7092.8 | -131.8 | -315.9 |

## By category

| Mode | Category | Runs | Attack success | Unauthorized executions | Leakage | False positives | Completion | Mean latency (ms) | p95 latency (ms) |
|---|---|---|---|---|---|---|---|---|---|
| baseline | benign | 20 | n/a | 0 | n/a | 0.0% | 100.0% | 2836.8 | 4918.9 |
| baseline | direct_injection | 8 | 25.0% | 2 | 0.0% | n/a | n/a | 4538.1 | 10520.0 |
| baseline | doc_injection | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 1997.5 | 3394.0 |
| baseline | role_impersonation | 6 | 0.0% | 0 | 0.0% | n/a | n/a | 1205.3 | 1914.1 |
| baseline | cross_account | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 1241.4 | 1375.8 |
| baseline | multi_turn | 5 | 20.0% | 1 | 0.0% | n/a | n/a | 4848.7 | 7408.6 |
| baseline | exfiltration | 5 | 20.0% | 0 | 20.0% | n/a | n/a | 2840.9 | 9424.4 |
| detector_only | benign | 20 | n/a | 0 | n/a | 0.0% | 100.0% | 2780.7 | 6267.3 |
| detector_only | direct_injection | 8 | 12.5% | 1 | 0.0% | n/a | n/a | 3504.6 | 11816.0 |
| detector_only | doc_injection | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 1892.8 | 3345.3 |
| detector_only | role_impersonation | 6 | 0.0% | 0 | 0.0% | n/a | n/a | 1136.8 | 1629.8 |
| detector_only | cross_account | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 1225.7 | 1563.9 |
| detector_only | multi_turn | 5 | 20.0% | 1 | 0.0% | n/a | n/a | 4755.9 | 6856.9 |
| detector_only | exfiltration | 5 | 20.0% | 0 | 20.0% | n/a | n/a | 2828.6 | 9865.7 |
| full | benign | 20 | n/a | 0 | n/a | 0.0% | 100.0% | 2805.1 | 4953.3 |
| full | direct_injection | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 3839.8 | 11646.3 |
| full | doc_injection | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 1105.8 | 2713.4 |
| full | role_impersonation | 6 | 0.0% | 0 | 0.0% | n/a | n/a | 1205.2 | 1619.7 |
| full | cross_account | 8 | 0.0% | 0 | 0.0% | n/a | n/a | 1539.2 | 2630.5 |
| full | multi_turn | 5 | 0.0% | 0 | 0.0% | n/a | n/a | 5455.7 | 8416.3 |
| full | exfiltration | 5 | 0.0% | 0 | 0.0% | n/a | n/a | 2847.1 | 9806.5 |
