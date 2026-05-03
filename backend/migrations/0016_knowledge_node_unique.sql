-- Prevent duplicate KnowledgeNode rows from concurrent Canvas ingestions.
--
-- Two constraints are needed because PostgreSQL treats NULL as distinct from
-- every other NULL in unique indexes:
--   • uq_kn_dataset_doc_title  — covers rows where document_id IS NOT NULL
--     (all Canvas-ingested nodes always have a document_id)
--   • ux_kn_dataset_null_title — partial index covers document_id IS NULL
--     (manually analysed text without a canvas document)

-- Step 1: remove duplicates keeping the row with the highest id (latest write).

-- 1a. Non-NULL document_id duplicates
DELETE FROM knowledge_nodes
WHERE id NOT IN (
    SELECT MAX(id)
    FROM knowledge_nodes
    WHERE document_id IS NOT NULL
    GROUP BY dataset_id, document_id, title
)
AND document_id IS NOT NULL;

-- 1b. NULL document_id duplicates (title uniqueness per dataset)
DELETE FROM knowledge_nodes
WHERE id NOT IN (
    SELECT MAX(id)
    FROM knowledge_nodes
    WHERE document_id IS NULL
    GROUP BY dataset_id, title
)
AND document_id IS NULL;

-- Step 2: add unique constraint for non-NULL document_id rows.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_kn_dataset_doc_title'
          AND conrelid = 'knowledge_nodes'::regclass
    ) THEN
        ALTER TABLE knowledge_nodes
            ADD CONSTRAINT uq_kn_dataset_doc_title
            UNIQUE (dataset_id, document_id, title);
    END IF;
END$$;

-- Step 3: partial unique index for rows where document_id IS NULL.
CREATE UNIQUE INDEX IF NOT EXISTS ux_kn_dataset_null_title
    ON knowledge_nodes (dataset_id, title)
    WHERE document_id IS NULL;
