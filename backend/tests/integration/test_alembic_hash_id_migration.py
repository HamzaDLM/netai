from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "9f1c2a6d4b7e_use_hash_ids_for_conversation.py"
)


def test_hash_id_migration_file_exists() -> None:
    assert MIGRATION_PATH.exists()


def test_hash_id_migration_contains_expected_conversion_steps() -> None:
    content = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "conversation_id_map" in content
    assert "CREATE TABLE conversation_new" in content
    assert "CREATE TABLE message_new" in content
    assert "CREATE TABLE conversation_summaries_new" in content
    assert "PRAGMA foreign_keys=OFF" in content
    assert "PRAGMA foreign_keys=ON" in content
