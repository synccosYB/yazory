from twilio_service import (account_overview, create_messaging_service,
                            deliver_message, normalize_phone)


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
    monkeypatch.setattr('twilio_service._request', lambda *args, **kwargs: next(responses))
    overview, error = account_overview('AC1', 'secret')
    assert error is None
    assert overview['account']['status'] == 'active'
    assert overview['numbers'][0]['phone_number'] == '+12513063232'
    assert overview['services'][0]['sid'] == 'MG1'
    assert overview['whatsapp_senders'][0]['status'] == 'ONLINE'


def test_create_messaging_service_attaches_number(monkeypatch):
    calls = []

    def request(method, url, account_sid, auth_token, **kwargs):
        calls.append((method, url, kwargs.get('data')))
        return ({'sid': 'MG123'}, None) if len(calls) == 1 else ({}, None)

    monkeypatch.setattr('twilio_service._request', request)
    assert create_messaging_service('AC1', 'token', 'PN1') == ('MG123', None)
    assert calls[1][2] == {'PhoneNumberSid': 'PN1'}
