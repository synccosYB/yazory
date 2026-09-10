import io
import json

import pytest

from ai_email import (draft_initial_email, fallback_initial_email,
                      initial_email_subject)


def test_ai_email_extracts_output_without_case_details(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            return json.dumps({'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': 'Dear {supporter_name}, hello.'}]}]}).encode()
    def fake_urlopen(request, timeout):
        captured['body'] = json.loads(request.data)
        return Response()
    monkeypatch.setattr('ai_email.urlopen', fake_urlopen)
    assert draft_initial_email('secret') == 'Dear {supporter_name}, hello.'
    prompt = captured['body']['input']
    assert 'private case details' in prompt
    assert captured['body']['store'] is False


def test_ai_email_requests_heimish_yiddish(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            return json.dumps({'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': 'לכבוד {supporter_name}'}]}]}).encode()
    def fake_urlopen(request, timeout):
        captured['body'] = json.loads(request.data)
        return Response()
    monkeypatch.setattr('ai_email.urlopen', fake_urlopen)
    assert draft_initial_email('secret', language='yi').startswith('לכבוד')
    assert 'heimish Yiddish' in captured['body']['input']


def test_ai_email_requires_configuration():
    with pytest.raises(ValueError, match='not configured'):
        draft_initial_email('')


def test_localized_fallback_draft_and_subject():
    assert fallback_initial_email('yi').startswith('לכבוד {supporter_name}')
    assert '{staff_name}' in fallback_initial_email('he')
    assert initial_email_subject('yi') == 'ווען איז א גוטע צייט צו רעדן?'
