import email_service
import json


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


def test_delivery_sets_reply_to_when_configured(monkeypatch):
    captured = {}

    class Accepted(ResponseWithoutId):
        def read(self):
            return b'{"id":"sent_1"}'

    def accept(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return Accepted()

    monkeypatch.setattr(email_service, 'urlopen', accept)
    provider_id, error = email_service.deliver(
        'key', 'from@example.test', 'to@example.test', 'Subject', '<p>Body</p>',
        'Body', reply_to='reply+secure@reply.example.test')
    assert provider_id == 'sent_1' and error is None
    assert captured['reply_to'] == 'reply+secure@reply.example.test'


def test_branded_sender_adds_yaazory_display_name_to_bare_address():
    assert email_service.branded_sender('notifications@synccos.live') == (
        'Yaazory Notifications <notifications@synccos.live>')


def test_branded_sender_replaces_old_display_name_but_keeps_address():
    assert email_service.branded_sender(
        'Old Name <notifications@synccos.live>') == (
        'Yaazory Notifications <notifications@synccos.live>')
