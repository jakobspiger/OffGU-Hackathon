import os

import pytest
from langgraph.graph import END, START, StateGraph
from streamlit.testing.v1 import AppTest

from src.config import PROJECT_ROOT, Settings
from src.engine.service import analyze
from src.errors import ComponentNotReadyError, RetrievalError
from src.knowledge.retrieval import reset_cache, retrieve
from src.state import PipelineState


def _retrieve_against_empty_index(tmp_path, monkeypatch):
    """Point retrieve() at an empty temp index and drop any cached index."""

    empty = tmp_path / "index"
    empty.mkdir()
    reset_cache()
    settings = Settings(_env_file=None, afs_index_dir=empty)
    monkeypatch.setattr("src.config.Settings", lambda *a, **kw: settings)
    return empty, settings


def test_public_stubs_do_not_fabricate_results(tmp_path, monkeypatch):
    with pytest.raises(ComponentNotReadyError, match="T06-T11"):
        analyze("Synthetic new request")
    # T04 is implemented: a retrieve() against a missing index raises
    # RetrievalError. The configured dir is empty; a gitignored
    # data/index/evidence.jsonl must not count as that index.
    _retrieve_against_empty_index(tmp_path, monkeypatch)
    with pytest.raises(RetrievalError):
        retrieve("Synthetic retrieval query")


def test_retrieve_raises_when_configured_index_is_empty_even_if_workspace_index_exists(
    tmp_path, monkeypatch
):
    workspace = PROJECT_ROOT / "data" / "index" / "evidence.jsonl"
    stamp = workspace.stat().st_mtime_ns if workspace.is_file() else None
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "evidence.jsonl").write_text('{"not": "read"}\n', encoding="utf-8")

    _empty, settings = _retrieve_against_empty_index(tmp_path, monkeypatch)
    with pytest.raises(RetrievalError, match="not found") as exc:
        retrieve("Synthetic retrieval query")

    message = str(exc.value)
    expected = os.path.join(str(settings.afs_index_dir), "evidence.jsonl")
    assert repr(expected) in message
    assert "decoy" not in message
    if stamp is not None:
        assert workspace.stat().st_mtime_ns == stamp


@pytest.mark.parametrize("query", ["", "   ", None])
def test_invalid_inputs_fail_before_component_calls(query):
    with pytest.raises(ValueError):
        analyze(query)
    with pytest.raises(ValueError):
        retrieve(query)


@pytest.mark.parametrize("k", [0, -1, 51, True, "8"])
def test_retrieval_limit_is_bounded(k):
    with pytest.raises(ValueError):
        retrieve("Synthetic query", k)


def test_state_supports_actual_langgraph_partial_updates():
    graph = StateGraph(PipelineState)
    graph.add_node("initialize", lambda state: {"revision_count": 0})
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", END)
    result = graph.compile().invoke({"query": "Synthetic input"})
    assert result["query"] == "Synthetic input"
    assert result["revision_count"] == 0
    assert "result" not in result


def test_foundation_ui_boots_without_credentials():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    assert not app.exception
    assert "Projektfundament" in app.info[0].value
