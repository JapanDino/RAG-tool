"""Generate tool registration keys without overwriting existing keys."""

import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "secrets")
    target.mkdir(parents=True, exist_ok=True)
    private_path, public_path = target / "lti-private.pem", target / "lti-public.json"
    if private_path.exists() or public_path.exists():
        raise SystemExit("Keys already exist; refusing to overwrite")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid=secrets.token_hex(16), use="sig", alg="RS256")
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with os.fdopen(
        os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as output:
        output.write(pem)
    public_path.write_text(json.dumps({"keys": [public]}, indent=2), encoding="utf-8")
    print(
        "Registration keys generated. Private key remains local; do not commit secrets/."
    )


if __name__ == "__main__":
    main()
