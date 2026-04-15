-- ORB Platform Migration v5
-- Commander durable memory file per owner

ALTER TABLE IF EXISTS business_profiles
ADD COLUMN IF NOT EXISTS commander_memory_file TEXT DEFAULT '';

COMMENT ON COLUMN business_profiles.commander_memory_file IS
'Durable per-owner Commander context file editable from side dock and setup workflows.';
