import lancedb
import pyarrow as pa
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent / "lancedb_data"
TABLE_NAME = "documents"
VECTOR_DIM = 768


def _get_table():
    db = lancedb.connect(str(DB_PATH))
    if TABLE_NAME in db.table_names():
        return db.open_table(TABLE_NAME)
    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("doc_id", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
        pa.field("chunk_index", pa.int32()),
    ])
    return db.create_table(TABLE_NAME, schema=schema)


def add_chunks(doc_id: str, chunks: list[str], vectors: list[list[float]]):
    table = _get_table()
    rows = [
        {"id": f"{doc_id}_{i}", "doc_id": doc_id, "text": chunk,
         "vector": np.array(vec, dtype=np.float32).tolist(), "chunk_index": i}
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]
    table.add(rows)


def search(
    query_vector: list[float],
    top_k: int = 4,
    doc_id: str | None = None,
    doc_ids: list[str] | None = None,
) -> list[dict]:
    """Semantic search with optional single or multi-doc filter.
    We fetch a larger pool first, then post-filter by doc_id — more
    reliable than LanceDB's .where() on vector search results.
    """
    table = _get_table()
    # If filtering, fetch a bigger pool so we still get top_k after filtering
    fetch_limit = top_k if not (doc_id or doc_ids) else top_k * 10
    results = (
        table.search(np.array(query_vector, dtype=np.float32))
        .limit(fetch_limit)
        .to_list()
    )

    # Post-filter by document
    if doc_id:
        results = [r for r in results if r["doc_id"] == doc_id]
    elif doc_ids:
        doc_ids_set = set(doc_ids)
        results = [r for r in results if r["doc_id"] in doc_ids_set]

    return [{"text": r["text"], "doc_id": r["doc_id"]} for r in results[:top_k]]


def get_all_chunks(doc_id: str) -> list[str]:
    """Return all text chunks for a document (used for summarization)."""
    table = _get_table()
    rows = table.to_arrow()
    if rows.num_rows == 0:
        return []
    doc_ids_col = rows.column("doc_id").to_pylist()
    texts_col   = rows.column("text").to_pylist()
    chunks_col  = rows.column("chunk_index").to_pylist()
    combined = [(t, c) for d, t, c in zip(doc_ids_col, texts_col, chunks_col) if d == doc_id]
    combined.sort(key=lambda x: x[1])
    return [t for t, _ in combined]


def delete_document(doc_id: str):
    table = _get_table()
    table.delete(f"doc_id = '{doc_id}'")


def list_documents() -> list[str]:
    table = _get_table()
    rows = table.to_arrow()
    if rows.num_rows == 0:
        return []
    return list(dict.fromkeys(rows.column("doc_id").to_pylist()))
