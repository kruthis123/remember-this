CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS messages (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    raw_text text NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL,
    message_id bigint NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    fact_text text NOT NULL,
    embedding vector(1024),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usages (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS hnsw_embeddings
ON memories
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS user_memory_index
ON memories (user_id);

CREATE INDEX IF NOT EXISTS usage_index
ON usages (user_id, created_at);
