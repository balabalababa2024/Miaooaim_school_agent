CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE static_rule (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(512)
);

CREATE TABLE dynamic_plan_experience (
    id SERIAL PRIMARY KEY,
    request TEXT NOT NULL,
    full_game TEXT NOT NULL,
    final_plan TEXT NOT NULL,
    embedding vector(512)
);

-- 建议顺便把索引也建了
CREATE INDEX IF NOT EXISTS idx_static_rule_embedding
ON static_rule USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_dynamic_plan_embedding
ON dynamic_plan_experience USING hnsw (embedding vector_cosine_ops);