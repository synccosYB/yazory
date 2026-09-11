from twilio_service import (account_overview, create_messaging_service,
                            deliver_message, find_messaging_service_for_number,
                            message_status, normalize_phone)


def test_normalize_us_phone_numbers():
    assert normalize_phone('(845) 555-1212') == '+18455551212'
    assert normalize_phone('1-845-555-1212') == '+18455551212'
    assert normalize_phone('+44 20 7946 0958') == '+442079460958'


def test_sms_uses_messaging_service(monkeypatch):
    captured = {}

    class Response:
        ok = True

        @staticmethod
        def json():
            return {'sid': 'SM123'}

    def post(url, data, auth, timeout):
        captured.update(url=url, data=data, auth=auth, timeout=timeout)
        return Response()

    monkeypatch.setattr('twilio_service.requests.post', post)
    provider_id, error = deliver_message(
        'AC123', 'token', '8455551212', 'Hello', channel='sms',
        messaging_service_sid='MG123')
    assert (provider_id, error) == ('SM123', None)
    assert captured['data'] == {
        'Body': 'Hello', 'To': '+18455551212', 'MessagingServiceSid': 'MG123'}


def test_whatsapp_adds_twilio_channel_prefix(monkeypatch):
    captured = {}

    class Response:
        ok = True

        @staticmethod
        def json():
            return {'sid': 'SM456'}

    monkeypatch.setattr('twilio_service.requests.post', lambda **kwargs: None)

    def post(url, data, auth, timeout):
        captured.update(data)
        return Response()

    monkeypatch.setattr('twilio_service.requests.post', post)
    assert deliver_message(
        'AC123', 'token', '+18455551212', 'Hello', channel='whatsapp',
        whatsapp_from='whatsapp:+14155238886') == ('SM456', None)
    assert captured['To'] == 'whatsapp:+18455551212'
    assert captured['From'] == 'whatsapp:+14155238886'


def test_account_overview_returns_only_safe_metadata(monkeypatch):
    responses = iter([
        ({'friendly_name': 'Yazory', 'status': 'active', 'type': 'Full'}, None),
        ({'incoming_phone_numbers': [{'sid': 'PN1', 'phone_number': '+12513063232',
          'friendly_name': 'Yazory', 'capabilities': {'sms': True}}]}, None),
        ({'services': [{'sid': 'MG1', 'friendly_name': 'Yazory Messaging'}]}, None),
        ({'senders': [{'sid': 'XE1', 'sender_id': '+12513063232',
          'status': 'ONLINE'}]}, None),
    ])
    calls = []

    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return next(responses)

    monkeypatch.setattr('twilio_service._request', request)
    overview, error = account_overview('AC1', 'secret')
    assert error is None
    assert overview['account']['status'] == 'active'
    assert overview['numbers'][0]['phone_number'] == '+12513063232'
    assert overview['services'][0]['sid'] == 'MG1'
    assert overview['whatsapp_senders'][0]['status'] == 'ONLINE'
    assert calls[-1][1]['params']['Channel'] == 'whatsapp'


def test_create_messaging_service_attaches_number(monkeypatch):
    calls = []

    def request(method, url, account_sid, auth_token, **kwargs):
        calls.append((method, url, kwargs.get('data')))
        return ({'sid': 'MG123'}, None) if len(calls) == 1 else ({}, None)

    monkeypatch.setattr('twilio_service._request', request)
    assert create_messaging_service('AC1', 'token', 'PN1') == ('MG123', None)
    assert calls[1][2] == {'PhoneNumberSid': 'PN1'}


def test_finds_service_that_already_owns_number(monkeypatch):
    def request(method, url, *args, **kwargs):
        rows = ([{'sid': 'PNwanted'}] if url.endswith('MGexisting/PhoneNumbers')
                else [])
        return {'phone_numbers': rows}, None

    monkeypatch.setattr('twilio_service._request', request)
    result = find_messaging_service_for_number(
        'AC1', 'token', [{'sid': 'MGempty'}, {'sid': 'MGexisting'}], 'PNwanted')
    assert result == 'MGexisting'


def test_message_status_returns_delivery_error_without_secrets(monkeypatch):
    sid = 'SM' + 'a' * 32
    monkeypatch.setattr('twilio_service._request', lambda *args, **kwargs: ({
        'sid': sid, 'status': 'undelivered', 'error_code': 30034,
        'error_message': 'US A2P registration required', 'to': '+18455551212',
        'from': '+12513063232', 'body': 'secret message body'}, None))
    result, error = message_status('AC1', 'token', sid)
    assert error is None
    assert result['status'] == 'undelivered'
    assert result['error_code'] == 30034
    assert 'body' not in result


def test_message_status_rejects_invalid_reference():
    assert message_status('AC1', 'token', 'not-a-message') == (
        None, 'Enter a valid Twilio message reference.')
