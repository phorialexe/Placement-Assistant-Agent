-- The database, not your Python code, refuses to rewrite history.

CREATE TRIGGER IF NOT EXISTS message_no_update
BEFORE UPDATE ON message
BEGIN
    SELECT RAISE(ABORT, 'message table is append-only: updates are not allowed');
END;

CREATE TRIGGER IF NOT EXISTS message_no_delete
BEFORE DELETE ON message
BEGIN
    SELECT RAISE(ABORT, 'message table is append-only: deletes are not allowed');
END;
