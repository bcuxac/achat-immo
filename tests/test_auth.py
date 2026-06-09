from achat_immo.auth import hash_password, verify_password


def test_hash_password_verifie_mot_de_passe() -> None:
    hashed = hash_password("secret-test", salt=b"1234567890123456", iterations=10_000)

    assert verify_password("secret-test", hashed)
    assert not verify_password("mauvais-secret", hashed)


def test_verify_password_accepte_secret_en_clair_pour_bootstrap() -> None:
    assert verify_password("secret-test", "secret-test")
    assert not verify_password("mauvais-secret", "secret-test")
