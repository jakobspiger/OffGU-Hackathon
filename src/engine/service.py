"""Public entry point. UI (T12) und Batch (T14) rufen diese eine Funktion auf.

``analyze(query)`` baut den typisierten Initialzustand, laesst den kompilierten
LangGraph laufen (Extraktion -> Regeln -> Retrieval -> Luecken -> Synthese ->
Versuchsplan-Seam -> Gate inkl. begrenzter Korrekturschleife) und liefert das
freigegebene Ergebnis. Erwartete Fehler aus :mod:`src.errors` (ConfigurationError,
ProviderError, ExtractionError, SynthesisError, RetrievalError) propagieren
unveraendert; es werden nie Provider-Antworten oder Credentials geleakt.
"""

from src.config import Settings
from src.engine.graph import compiled_graph, set_max_revisions
from src.models import AnalysisResult
from src.state import PipelineState


def analyze(query: str) -> AnalysisResult:
    """Fuehre die vollstaendige Analyse-Pipeline fuer ``query`` aus.

    * Validiert die Query mit dem bestehenden Guard.
    * ``Settings().require_llm()`` fruehzeitig, um bei fehlendem
      OPENAI_API_KEY/OPENAI_MODEL sofort mit einer klaren ConfigurationError zu
      scheitern, bevor ein Provider aufgerufen wird.
    * Baut den Initialzustand ``{"query": query, "revision_count": 0}`` und
      invokiert den kompilierten Graphen.
    * Liefert ``state['result']`` (Gate-Ergebnis) bzw. faellt auf
      ``state['draft']`` zurueck, falls (noch) kein Gate ein Ergebnis gesetzt hat.
    """

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")

    settings = Settings()
    settings.require_llm()

    # Korrekturschleifen-Obergrenze an die aktive Konfiguration koppeln
    # (dokumentierte Wiederverwendung von afs_max_retries).
    set_max_revisions(settings.afs_max_retries)

    initial: PipelineState = {"query": query, "revision_count": 0}
    final = compiled_graph().invoke(initial)

    result = final.get("result")
    if result is None:
        result = final["draft"]
    return result
