"""Sign a webhook body, because the signature covers bytes and not a document.

`verify_webhook_signature` runs HMAC-SHA256 over the raw request body, so a
signature belongs to one exact byte sequence: re-indent the JSON, reorder the
keys or change a single character of the `chat_id` and it stops matching. That
is what makes a stored Insomnia request with a baked-in signature so brittle —
and why a chat identifier, which the service generates, cannot be templated
into one.

Give it the body on stdin and it prints the two lines to paste back:

    echo '{"company_id": "...", "chat_id": "...", "body": "oi"}' \\
        | uv run python -m scripts.sign_webhook

It re-serialises compactly and prints what it actually signed, so the body you
paste and the body it signed cannot differ.
"""

import hashlib
import hmac
import json
import sys

from app.core.config import settings


def signature_over(body: bytes) -> str:
    return hmac.new(settings.webhook_hmac_secret.encode(), body, hashlib.sha256).hexdigest()


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit("nothing on stdin: pipe the JSON body in")

    try:
        # Re-serialised rather than passed through, so that what is printed and
        # what was signed are the same bytes by construction. Unicode is left
        # unescaped because the signature is over UTF-8 and an escaped body
        # would sign different bytes than the one a person pastes back.
        body = json.dumps(json.loads(raw), ensure_ascii=False, separators=(", ", ": ")).encode()
    except json.JSONDecodeError as broken:
        sys.exit(f"not JSON: {broken}")

    print(body.decode())
    print(signature_over(body))


if __name__ == "__main__":
    main()
