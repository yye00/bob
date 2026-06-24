-- Migration: add spec_slot column to features table.
--
-- spec_slot is a stable cross-generation identifier derived from the YAML spec
-- key (e.g. "F-R6-200").  It lets the convergence detector compare feature sets
-- across generations without being confused by freshly-minted UUIDs that are
-- assigned on every `bob init`.
--
-- This statement is idempotent when run via the Python migration helper
-- (add_spec_slot.upgrade), which checks PRAGMA table_info before executing.
-- Running this SQL directly on a database that already has the column will
-- raise an "duplicate column name" error from SQLite; use the Python helper
-- for idempotent execution.

ALTER TABLE features ADD COLUMN spec_slot TEXT DEFAULT NULL;
