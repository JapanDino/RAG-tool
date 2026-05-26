-- Migration 0018: add is_expert flag to node_labels
-- Marks annotations made in blind expert mode (model predictions hidden).
-- Used for pedagogical validation metrics (Cohen's κ).

ALTER TABLE node_labels
    ADD COLUMN IF NOT EXISTS is_expert BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS ix_node_labels_is_expert
    ON node_labels (is_expert);
