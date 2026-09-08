import stripe_gateway


def test_checkout_uses_an_interactive_timeout(monkeypatch):
    captured = {}

    class Sessions:
        def create(self, params, options):
            captured['params'] = params
            captured['options'] = options
            return {'id': 'cs_test', 'url': 'https://checkout.stripe.test/cs_test'}

    class Client:
        def __init__(self, secret_key, **kwargs):
            captured['secret_key'] = secret_key
            captured.update(kwargs)
            self.v1 = type('V1', (), {'checkout': type('Checkout', (), {'sessions': Sessions()})()})()

    monkeypatch.setattr(stripe_gateway.stripe, 'StripeClient', Client)
    monkeypatch.setattr(stripe_gateway.stripe, 'RequestsClient',
                        lambda timeout: ('http-client', timeout))

    result = stripe_gateway.create_checkout_session(
        'sk_test_key', {'mode': 'payment'}, 'checkout-1')

    assert result['id'] == 'cs_test'
    assert captured['max_network_retries'] == 0
    assert captured['http_client'] == ('http-client', (3, 10))
    assert captured['options']['idempotency_key'] == 'checkout-1'
