"""Offline defensive controls and a repeatable detector microbenchmark."""
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter_ns

import pytest

from app.models import ToolCall
from app.security import detector, policy

CASES = [json.loads(line) for line in Path(__file__).with_name("redteam_cases.jsonl").read_text().splitlines()]
TEXT = [case for case in CASES if case["kind"] != "policy"]
CALLS = [case for case in CASES if case["kind"] == "policy"]


def test_corpus_integrity():
    assert len({case["id"] for case in CASES}) == len(CASES)
    assert len({case["text"] for case in TEXT}) == len(TEXT)
    counts = Counter(case["kind"] for case in TEXT)
    assert counts["cue"] >= 40 and counts["benign"] >= 20


@pytest.mark.parametrize("case", CALLS, ids=lambda case: case["id"])
def test_policy_control(case, seeded_bank, alice):
    decision = policy.authorize(alice, ToolCall(name=case["tool"], args=case["args"]))
    assert (decision.allowed, decision.requires_confirmation) == (case["allowed"], case["confirm"])


def measure():
    counts = Counter()
    timings = defaultdict(list)
    def noop(text, source):
        return None

    for case in TEXT:
        source, text = case["source"], case["text"]
        if "previous_turn" in case:
            assert not detector.inspect(case["previous_turn"]).flagged
        result = detector.inspect(text, source)
        counts[case["kind"], result.flagged] += 1

    for _ in range(3):
        for case in TEXT:
            detector.inspect(case["text"], case["source"])
    for _ in range(100):
        for case in TEXT:
            text, source = case["text"], case["source"]
            start = perf_counter_ns()
            noop(text, source)
            overhead = perf_counter_ns() - start
            start = perf_counter_ns()
            detector.inspect(text, source)
            timings[source].append(perf_counter_ns() - start - overhead)
    print(dict(counts))
    for source, samples in timings.items():
        print(f"{source} n={len(samples)} median={median(samples)/1e6:.6f} ms "
              f"p95={quantiles(samples, n=100, method='inclusive')[94]/1e6:.6f} ms")


if __name__ == "__main__":
    measure()


@pytest.mark.parametrize("case", TEXT, ids=lambda case: case["id"])
def test_detector_control(case):
    if "previous_turn" in case:
        assert not detector.inspect(case["previous_turn"]).flagged
    result = detector.inspect(case["text"], case["source"])
    assert result.flagged == (case["kind"] == "cue")
