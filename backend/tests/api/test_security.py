from autoeval_ops.api.security import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    verify_api_key,
)


def test_generated_key_has_expected_prefix():
    assert generate_api_key().startswith(API_KEY_PREFIX)


def test_generated_keys_are_unique():
    assert generate_api_key() != generate_api_key()


def test_hash_then_verify_roundtrip():
    key = generate_api_key()
    assert verify_api_key(key, hash_api_key(key)) is True


def test_verify_rejects_wrong_key():
    stored = hash_api_key(generate_api_key())
    assert verify_api_key(generate_api_key(), stored) is False


def test_verify_rejects_malformed_hash():
    assert verify_api_key("some-key", "not-a-bcrypt-hash") is False


def test_hash_is_salted_so_same_key_hashes_differently():
    key = generate_api_key()
    assert hash_api_key(key) != hash_api_key(key)