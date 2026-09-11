import email_service


class ResponseWithoutId:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{}'


def test_delivery_requires_provider_id(monkeypatch):
    monkeypatch.setattr(email_service, 'urlopen',
                        lambda request, timeout: ResponseWithoutId())
    provider_id, error = email_service.deliver(
        'key', 'from@example.test', 'to@example.test', 'Subject', '<p>Body</p>', 'Body')
    assert provider_id is None
    assert 'without returning a delivery ID' in error
