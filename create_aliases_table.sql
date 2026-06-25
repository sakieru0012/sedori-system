-- product_aliases テーブル作成（Supabase SQL Editor で実行）

CREATE TABLE IF NOT EXISTS product_aliases (
    id              BIGSERIAL PRIMARY KEY,
    alias           TEXT NOT NULL,
    canonical_name  TEXT NOT NULL,
    platform        TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- alias での検索を高速化
CREATE INDEX IF NOT EXISTS idx_product_aliases_alias ON product_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_product_aliases_canonical ON product_aliases(canonical_name);

-- alias は一意制約（同じ別名が重複登録されないように）
CREATE UNIQUE INDEX IF NOT EXISTS idx_product_aliases_alias_unique ON product_aliases(alias);
