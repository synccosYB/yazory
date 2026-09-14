"""Verified Resend inbound-email helpers."""
import base64
import hashlib
import hmac
import json
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ('br', 'p', 'div', 'li', 'tr'):
            self.parts.append('\n')


def html_to_text(value):
    parser = _TextExtractor()
    parser.feed(value or '')
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines()
                     if line.strip())


def verify_webhook(payload, headers, secret, tolerance=300, now=None):
    """Verify a Resend/Svix signature against the untouched request body."""
    if not secret:
        raise ValueError('Webhook verification is not configured.')
    message_id = headers.get('svix-id', '')
    timestamp = headers.get('svix-timestamp', '')
    signatures = headers.get('svix-signature', '')
    if not message_id or not timestamp or not signatures:
        raise ValueError('Missing webhook signature headers.')
    try:
        timestamp_number = int(timestamp)
    except ValueError as exc:
        raise ValueError('Invalid webhook timestamp.') from exc
    if abs((time.time() if now is None else now) - timestamp_number) > tolerance:
        raise ValueError('Webhook timestamp is outside the allowed window.')
    encoded_secret = secret[6:] if secret.startswith('whsec_') else secret
    try:
        key = base64.b64decode(encoded_secret, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid webhook signing secret.') from exc
    signed = message_id.encode() + b'.' + timestamp.encode() + b'.' + payload
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    candidates = [item.split(',', 1)[1] for item in signatures.split(' ')
                  if item.startswith('v1,')]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise ValueError('Invalid webhook signature.')
    try:
        return json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid webhook JSON.') from exc


def retrieve_received_email(api_key, email_id, timeout=10):
    if not api_key or not email_id:
        raise ValueError('Inbound email retrieval is not configured.')
    request = Request(
        f'https://api.resend.com/emails/receiving/{email_id}?html_format=cid',
        headers={'Authorization': f'Bearer {api_key}', 'User-Agent': 'Yazory/1.0'})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get('message')
        except (ValueError, AttributeError):
            detail = None
        raise ValueError(detail or f'Resend returned HTTP {exc.code}.') from None
    except (URLError, TimeoutError) as exc:
        raise ValueError(
            f'Resend could not be reached: {exc.reason if hasattr(exc, "reason") else exc}') from None
