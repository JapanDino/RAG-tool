-- Migration 02: HNSW index + missing UniqueConstraints
-- Run after 01_enable_pgvector.sql

-- HNSW index for fast cosine similarity search on knowledge_nodes.vec
-- Requires pgvector >= 0.5 (available in pgvector/pgvector:pg16 image)
CREATE INDEX IF NOT EXISTS ix_knode_vec_hnsw
    ON knowledge_nodes
    USING hnsw (vec vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- UniqueConstraints that tasks.py relies on via ON CONFLICT
CREATE UNIQUE INDEX IF NOT EXISTS uq_embeddings_chunk_id
    ON embeddings (chunk_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_bloom_chunk_level
    ON bloom_annotations (chunk_id, level);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kedge_ds_from_to_method
    ON knowledge_edges (dataset_id, from_node_id, to_node_id, method);
