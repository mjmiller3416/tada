"""One-off script: generates a VAPID keypair for Web Push (SPEC §2).

Run once locally:  python -m scripts.generate_vapid_keys

Copy VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY into the backend and cron
Railway services' env vars, and copy VAPID_PUBLIC_KEY into the frontend
service as NEXT_PUBLIC_VAPID_PUBLIC_KEY. Only needed again if rotating keys.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_value = private_key.private_numbers().private_value
    private_b64 = _b64url(private_value.to_bytes(32, "big"))

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = _b64url(public_bytes)

    print("VAPID_PUBLIC_KEY=" + public_b64)
    print("VAPID_PRIVATE_KEY=" + private_b64)


if __name__ == "__main__":
    main()
