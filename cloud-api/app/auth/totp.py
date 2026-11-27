"""TOTP (RFC 6238) for the owner. The secret is shown once, at enrollment."""

import pyotp

ISSUER = "PharmaCare"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(email: str, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def code_matches(secret: str, code: str) -> bool:
    cleaned = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(cleaned) != 6:
        return False
    return bool(pyotp.TOTP(secret).verify(cleaned, valid_window=1))
