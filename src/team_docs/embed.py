"""Embeddings with Amazon Titan Text Embeddings V2, in the same region as the rest of the stack."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

MODEL_ID = "amazon.titan-embed-text-v2:0"
DIMENSIONS = 1024


class Embedder:
    """Normalized vectors, so a dot product is the cosine similarity. Counts the input tokens it used."""

    def __init__(self, client: Any, workers: int = 8):
        self._client = client
        self._workers = workers
        self.tokens = 0

    def one(self, text: str) -> np.ndarray:
        vector, tokens = self._call(text)
        self.tokens += tokens
        return vector

    def many(self, texts: list[str]) -> np.ndarray:
        """One request per text, which is what Titan takes, with several requests at a time."""
        if not texts:
            return np.zeros((0, DIMENSIONS), dtype=np.float32)
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            answers = list(pool.map(self._call, texts))
        self.tokens += sum(tokens for _, tokens in answers)
        return np.vstack([vector for vector, _ in answers])

    def _call(self, text: str) -> tuple[np.ndarray, int]:
        response = self._client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": DIMENSIONS, "normalize": True}),
        )
        answer = json.loads(response["body"].read())
        return np.asarray(answer["embedding"], dtype=np.float32), int(answer.get("inputTextTokenCount", 0))
