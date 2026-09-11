from twilio_service import deliver_message, normalize_phone


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
