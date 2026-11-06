"""The shared password hashing used by the admin and singer locks."""

from pikaraoke.lib.password_hashing import hash_password, verify_password


def test_a_password_verifies_against_its_own_hash():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)


def test_a_wrong_password_does_not_verify():
    stored = hash_password("correct horse")
    assert not verify_password("battery staple", stored)


def test_each_hash_is_salted_so_two_hashes_of_one_password_differ():
    assert hash_password("same") != hash_password("same")


def test_an_empty_or_malformed_stored_value_is_false_not_an_error():
    assert not verify_password("anything", "")
    assert not verify_password("anything", "no-colon")
