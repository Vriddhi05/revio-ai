import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np

from app.core.config import get_settings
from app.services.knowledge_documents import token_count


class QueryTooLongError(ValueError):
    pass


class MultilingualE5Encoder:
    """Multilingual E5 wrapper using its required query/passage prefixes."""

    def __init__(self, model_name: str | None = None, revision: str | None = None):
        settings = get_settings()
        self.model_name = model_name or settings.knowledge_embedding_model
        self.revision = revision or settings.knowledge_embedding_revision
        self._model = None
        self._lock = Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    hub_cache = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
                    snapshot = hub_cache / f"models--{self.model_name.replace('/', '--')}" / "snapshots" / self.revision
                    if (snapshot / "model.safetensors").is_file() and (snapshot / "modules.json").is_file():
                        self._model = SentenceTransformer(str(snapshot), device="cpu")
                    else:
                        self._model = SentenceTransformer(self.model_name, revision=self.revision, device="cpu")
        return self._model

    @property
    def tokenizer(self):
        return self._load().tokenizer

    @property
    def dimensions(self) -> int:
        return int(self._load().get_sentence_embedding_dimension())

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(
            [f"passage: {text}" for text in texts],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return np.asarray(vectors, dtype=np.float32).tolist()

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        query_tokens = token_count(model.tokenizer, f"query: {text}", add_special_tokens=True)
        if query_tokens > int(model.max_seq_length):
            raise QueryTooLongError(f"Search query is {query_tokens} tokens; the configured model limit is {model.max_seq_length}. Shorten the query and try again.")
        vector = model.encode(
            [f"query: {text}"],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        return np.asarray(vector, dtype=np.float32).tolist()


@lru_cache(maxsize=1)
def get_encoder() -> MultilingualE5Encoder:
    return MultilingualE5Encoder()
