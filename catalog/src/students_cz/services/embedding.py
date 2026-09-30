"""Turning text into a vector, and nothing else.

The last of the three mechanisms that find what somebody meant, and the only
one that reads meaning rather than letters: "объяснить пределы и производные" is
about calculus and contains none of its names. It is asked last and only when
the other two found nothing — see `services/parser` for the rule and
`docs/data-model.md` for why.

The model is an ONNX build of EmbeddingGemma-300m, quantised to q4, and it lives
inside the image; `docs/architecture.md` says why it is not fetched at runtime.
Two dependencies carry it, `onnxruntime` and `tokenizers`, and neither pulls a
deep-learning framework in behind it.

The protocol is here so everything above it — the confidence rule, the rebuild,
the search — is testable without loading 200 MB. `tests/conftest.py` has the
fake.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

# EmbeddingGemma was trained with these, and the two sides say different things:
# a query announces what it is looking for, a passage what it is. Embedding
# either with the other's prefix lands it somewhere else in the space.
QUERY_PREFIX = "task: search result | query: "
DOCUMENT_PREFIX = "title: none | text: "

# Where the image puts the model, and where a developer can point at a local
# copy instead. Not a URL: nothing downloads anything at runtime.
MODEL_DIR = Path(os.environ.get("EMBEDDING_MODEL_DIR", "/app/model"))

# The name the ONNX repository publishes, kept as it is: the graph refers to its
# own weight file by name from inside itself, so a tidier one breaks the pair.
MODEL_FILE = "model_q4.onnx"

# The revision the image is built from. Here as well as in the Dockerfile, and
# `tests/test_embedding.py` fails when the two disagree: the name below is what
# every row is written and read under, so a new model under an old name would
# embed queries with new weights against vectors made by the old ones — and
# nothing would fail, it would just answer worse.
MODEL_REVISION = "5090578d9565bb06545b4552f76e6bc2c93e4a66"

# Written into every row it produces, so a rollback finds its own vectors and a
# change of model is a rebuild rather than a silent reinterpretation.
MODEL_NAME = f"embeddinggemma-300m-q4@{MODEL_REVISION[:7]}"

# The vector's width, fixed by the model. Changing the model changes this, and
# changing this means recomputing every row — which is why the column type says
# it out loud.
DIMENSIONS = 768

# The box is shared with another project's bot, and onnxruntime helps itself to
# every core it can see.
THREADS = int(os.environ.get("EMBEDDING_THREADS", "2"))


def as_query(text: str) -> str:
    return f"{QUERY_PREFIX}{text}"


def as_document(text: str) -> str:
    return f"{DOCUMENT_PREFIX}{text}"


class Embedder(Protocol):
    """Text in, unit vectors out, in the order given.

    `name` goes into every row the embedder produces and is what every read
    filters on, so two of them never mix: a rollback finds the vectors its own
    image made, a change of model writes its own alongside, and a fake in a test
    cannot be mistaken for either.
    """

    name: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class OnnxEmbedder:
    """The real one. Loads once; `encode` is called on the request path.

    Normalised on the way out, so every comparison downstream is a dot product
    and no caller has to remember to divide.
    """

    name = MODEL_NAME

    def __init__(self, model_dir: Path | None = None) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        directory = model_dir or MODEL_DIR
        options = ort.SessionOptions()
        options.intra_op_num_threads = THREADS
        options.inter_op_num_threads = 1

        self._np = np
        self._tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self._session = ort.InferenceSession(
            str(directory / MODEL_FILE),
            options,
            providers=["CPUExecutionProvider"],
        )

    def encode(self, texts: list[str], batch: int = 16) -> list[list[float]]:
        np = self._np
        out: list = []
        for start in range(0, len(texts), batch):
            encoded = [
                self._tokenizer.encode(text) for text in texts[start : start + batch]
            ]
            width = max(len(item.ids) for item in encoded)
            ids = np.array(
                [item.ids + [0] * (width - len(item.ids)) for item in encoded],
                dtype="int64",
            )
            mask = np.array(
                [[1] * len(item.ids) + [0] * (width - len(item.ids)) for item in encoded],
                dtype="int64",
            )
            vectors = self._session.run(
                ["sentence_embedding"], {"input_ids": ids, "attention_mask": mask}
            )[0]
            out.append(vectors)

        matrix = np.concatenate(tuple(out)).astype("float32")
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix.tolist()


_embedder: Embedder | None = None
_looked = False


def get_embedder() -> Embedder | None:
    """One session per process, created on first use and kept.

    `None` when the model is not on disk, and that is a supported state rather
    than a failure: the vector is the third mechanism and the first two work
    without it. A development checkout, a test run and an image built without
    the model stage all search perfectly well — they just cannot answer the
    queries only meaning can reach. Warmed by the lifespan hook rather than by
    the first person to search.
    """
    global _embedder, _looked
    if _embedder is None and not _looked:
        _looked = True
        if (MODEL_DIR / MODEL_FILE).exists():
            _embedder = OnnxEmbedder()
        else:
            log.info("no embedding model at %s — semantic search is off", MODEL_DIR)
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """For tests, and for the one-shot rebuild that builds its own."""
    global _embedder, _looked
    _embedder = embedder
    _looked = embedder is not None
