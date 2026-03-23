from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class TemplateEvidence:
    source: str
    content: str
    score: float


class QdrantTemplateRetriever:
    def __init__(self, base_url: str, collection: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection

    async def retrieve(self, query: str, top_k: int = 5) -> list[TemplateEvidence]:
        # Temporary lexical fallback over scrolled templates.
        # Replace with vector search once query embeddings are wired in app.
        url = f"{self.base_url}/collections/{self.collection}/points/scroll"
        payload = {
            "limit": 500,
            "with_payload": True,
            "with_vector": False,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            body = resp.json()

        points = body.get("result", {}).get("points", [])
        tokens = {t for t in query.lower().split() if t}

        scored: list[TemplateEvidence] = []
        for point in points:
            template = point.get("payload", {}).get("template")
            if not isinstance(template, str) or not template:
                continue

            words = set(template.lower().split())
            overlap = len(tokens.intersection(words))
            score = float(overlap)
            if score > 0:
                scored.append(
                    TemplateEvidence(
                        source="qdrant_template",
                        content=template,
                        score=score,
                    )
                )

        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:top_k]
