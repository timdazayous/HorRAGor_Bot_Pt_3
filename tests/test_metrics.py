"""Tests unitaires — src/metrics.py (instrumentation Prometheus par agent)."""
from types import SimpleNamespace

from src.metrics import AGENT_CALLS, AGENT_LATENCY, AGENT_TOKENS, record_llm_usage, track_node


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def _histogram_observation_count(histogram, **labels) -> float:
    # Chaque bucket ne compte que les observations tombées dans SA tranche
    # (pas cumulatif en mémoire, seulement au scrape) : la somme de tous les
    # buckets donne donc le nombre total d'observations.
    return sum(b.get() for b in histogram.labels(**labels)._buckets)


def test_track_node_increments_calls_and_latency():
    @track_node("test_agent_calls")
    def fake_node(state):
        return {"ok": True}

    before_calls = _counter_value(AGENT_CALLS, agent="test_agent_calls")
    before_count = _histogram_observation_count(AGENT_LATENCY, agent="test_agent_calls")

    result = fake_node({})

    assert result == {"ok": True}
    assert _counter_value(AGENT_CALLS, agent="test_agent_calls") == before_calls + 1
    assert _histogram_observation_count(AGENT_LATENCY, agent="test_agent_calls") == before_count + 1


def test_record_llm_usage_increments_tokens():
    response = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14})

    before_in = _counter_value(AGENT_TOKENS, agent="test_agent_tokens", direction="input")
    before_out = _counter_value(AGENT_TOKENS, agent="test_agent_tokens", direction="output")

    record_llm_usage("test_agent_tokens", response)

    assert _counter_value(AGENT_TOKENS, agent="test_agent_tokens", direction="input") == before_in + 10
    assert _counter_value(AGENT_TOKENS, agent="test_agent_tokens", direction="output") == before_out + 4


def test_record_llm_usage_no_usage_metadata_is_a_noop():
    response = SimpleNamespace(usage_metadata=None)
    before = _counter_value(AGENT_TOKENS, agent="test_agent_noop", direction="input")

    record_llm_usage("test_agent_noop", response)

    assert _counter_value(AGENT_TOKENS, agent="test_agent_noop", direction="input") == before


def test_record_llm_usage_missing_attribute_is_a_noop():
    response = object()  # pas d'attribut usage_metadata du tout
    record_llm_usage("test_agent_missing_attr", response)  # ne doit pas lever d'exception
