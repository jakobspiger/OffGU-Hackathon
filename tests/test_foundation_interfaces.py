import pytest
from langgraph.graph import END, START, StateGraph
from streamlit.testing.v1 import AppTest

from src.config import PROJECT_ROOT
from src.engine.service import analyze
from src.errors import ComponentNotReadyError, RetrievalError
from src.knowledge.retrieval import retrieve
from src.state import PipelineState


def test_public_stubs_do_not_fabricate_results(tmp_path, monkeypatch):
    with pytest.raises(ComponentNotReadyError, match="T06-T11"):
        analyze("Synthetic new request")
    # T04 is implemented: a retrieve() against a missing index raises
    # RetrievalError. Point at an empty directory so a local data/index
    # built for qwen3-embedding-4b cannot satisfy the call.
    from src.config import Settings
    from src.knowledge.retrieval import reset_cache

    missing = tmp_path / "no-index"
    missing.mkdir()
    isolated = Settings(_env_file=None, afs_index_dir=missing)
    monkeypatch.setattr("src.config.Settings", lambda *a, **kw: isolated)
    reset_cache()
    with pytest.raises(RetrievalError):
        retrieve("Synthetic retrieval query")


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
