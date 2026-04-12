from app.api.models.chat import _generate_conversation_hash_id


def test_generated_conversation_hash_id_is_string_and_not_numeric() -> None:
    value = _generate_conversation_hash_id()

    assert isinstance(value, str)
    assert len(value) >= 12
    assert not value.isdigit()


def test_generated_conversation_hash_ids_are_unique_in_small_sample() -> None:
    values = {_generate_conversation_hash_id() for _ in range(50)}

    assert len(values) == 50
