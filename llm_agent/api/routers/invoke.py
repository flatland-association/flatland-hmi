# TODO: still work in process!

import logging

from fastapi import APIRouter, HTTPException

from flatland_agent.agents.coordinator_agent import CoordinatorAgent
from flatland_agent.models import InvokeRequest

router = APIRouter(tags=["invoke"])

logger = logging.getLogger("flatland")
logger.setLevel(logging.INFO)


@router.post("/invoke")
async def invoke(request: InvokeRequest) -> dict:
    """Invoke the coordinator agent with a prompt and optional responses.

    Parameters
    ----------
    request : InvokeRequest
        The request object containing the prompt string, optional responses, and context.

    Returns:
    -------
    dict: A dictionary containing the response from the coordinator agent.

    Raises:
    ------
    HTTPException: If the prompt is empty (400) or if an internal error occurs (500).
    """
    coordinator = CoordinatorAgent()
    # TODO: parse actual prompt data from request
    try:
        prompt = """
            Als Disponent musst du die Fahrplanvarianten bei Abweichungen vergleichen und die beste Lösungsvariante
            finden. Als Input liefert dir das System für n Zugfahrten die Fahrstrecke als Codepunktabfolge mit
            Durchfahrtszeiten und Ankunftszeiten. Zudem wird pro Zugfahrt die späteste Ankunftszeit angegeben,
            die nicht überschritten werden darf. Falls der Zug später als der späteste Ankunftszeitpunkt ankommt, ist
            das nicht gut. Zu früh ist ebenfalls nicht akzeptabel. Zu früh ist alles, was vor der späteste Ankunft
            ankommt. Das Ziel muss sein, möglichst genau anzukommen. Zu spät ist keine Lösung und sehr ungünstig.
            Kommt der Zug nie am Target an - muss die Lösung als nicht lösbar markiert werden und darf nicht verwendet
            werden.

            Folgende Zugfahrten gibt es:
            A, B, C

            Es gibt drei Lösungsvarianten:
            V1, V2 und V3

            Hier die Daten für V1:

            A: [ (Ort C1, Zeit: 10), (Ort C2, Zeit: 11), (Ort C2, Zeit: 12), Target: C2, späteste Ankunft: 14]
            B: [ (Ort C0, Zeit: 8), (Ort C2, Zeit: 9), (Ort C2, Zeit: 10), Target: C2, späteste Ankunft: 10]
            C: [ (Ort C0, Zeit: 10), (Ort C0, Zeit: 11), (Ort C0, Zeit: 12), (Ort C0, Zeit: 13), (Ort C3, Zeit: 14), Target: C3, späteste Ankunft: 13]

            Hier die Daten für V2:

            A: [ (Ort C1, Zeit: 10), (Ort C2, Zeit: 11), (Ort C2, Zeit: 12), Target: C2, späteste Ankunft: 14]
            B: [ (Ort C0, Zeit: 8), (Ort C1, Zeit: 9), (Ort C2, Zeit: 10), Target: C2, späteste Ankunft: 10]
            C: [ (Ort C0, Zeit: 10), (Ort C3, Zeit: 11), (Ort C4, Zeit: 12), (Ort C3, Zeit: 13), Target: C3, späteste Ankunft: 13]

            Hier die Daten für V3:

            A: [ (Ort C1, Zeit: 10), (Ort C3, Zeit: 11), (Ort C3, Zeit: 12), Target: C2, späteste Ankunft: 14]
            B: [ (Ort C0, Zeit: 8), (Ort C1, Zeit: 9), (Ort C2, Zeit: 10), Target: C2, späteste Ankunft: 10]
            C: [ (Ort C0, Zeit: 10), (Ort C3, Zeit: 11), (Ort C4, Zeit: 12), (Ort C3, Zeit: 13), Target: C3, späteste Ankunft: 13]

            Die Zahlen sind als Minute zu interpretieren

            ich will nur nachfolgender OUTPUT von dir. 

            Variante { } -> {   die Varianten bei welcher mindestens ein Zug nicht ankommt mit ❌ | Markiere die beste Variante mit ✔️ |  restliche Varianten mit ➤  } - das Icon muss vor dem  Variante angezeigt werden.

            Zug -> bewertung { zu früh als icon ⇠ mit gerechneten minuten abweichung | pünklich als icon ✔ | zu spät als ⚠️ mit gerechneten abweichung minuten | nicht angekommen mit ❌ } 

            Stelle sicher, dass Zwischen den Varianten und den Zügen jeweils eine leere Zeile ist.

            Zusammenfassung der Varianten - welche besser bewertet ist - mit kurzer begründung.

            Leite diese Anfrage in jedem Fall an den Language Agenten weiter.
        """
        return await coordinator.process(prompt)
    except Exception as err:
        logger.exception("Error occurred while processing the request.")
        raise HTTPException(status_code=500, detail="An internal error occurred") from err
