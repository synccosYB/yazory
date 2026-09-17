import base64
import hashlib
import hmac

import pytest

from inbound_email import retrieve_received_email, verify_webhook


def test_received_email_requests_embedded_inline_images(monkeypatch):
    requested = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"id":"received-1","html":"<p>Hello</p>"}'

    def fake_urlopen(request, timeout):
        requested['url'] = request.full_url
        return Response()

    monkeypatch.setattr('inbound_email.urlopen', fake_urlopen)
    result = retrieve_received_email('test-key', 'received-1')
    assert result['id'] == 'received-1'
    assert requested['url'].endswith('?html_format=data_uri')


def test_verify_webhook_uses_raw_payload_and_rejects_tampering():
    payload = b'{"type":"email.received"}'
    secret_bytes = b'signing-secret'
    secret = 'whsec_' + base64.b64encode(secret_bytes).decode()
    headers = {'svix-id': 'msg_1', 'svix-timestamp': '1770000000'}
    signed = b'msg_1.1770000000.' + payload
    headers['svix-signature'] = 'v1,' + base64.b64encode(
        hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode()
    assert verify_webhook(payload, headers, secret, now=1770000000)['type'] == 'email.received'
    with pytest.raises(ValueError, match='signature'):
        verify_webhook(payload + b' ', headers, secret, now=1770000000)
