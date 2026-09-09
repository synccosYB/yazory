"""Small Stripe boundary so payment code is testable without network access."""

import stripe


def _interactive_client(secret_key):
    return stripe.StripeClient(
        secret_key,
        max_network_retries=0,
        http_client=stripe.RequestsClient(timeout=(3, 10)),
    )


def create_checkout_session(secret_key, params, idempotency_key):
    # Retained for legacy records/tests. New donor entry uses native Yazory UI.
    client = _interactive_client(secret_key)
    return client.v1.checkout.sessions.create(
        params=params,
        options={'idempotency_key': idempotency_key},
    )


def create_payment_intent(secret_key, params, idempotency_key):
    client = _interactive_client(secret_key)
    return client.v1.payment_intents.create(
        params=params,
        options={'idempotency_key': idempotency_key},
    )


def retrieve_payment_intent(secret_key, payment_intent_id):
    client = _interactive_client(secret_key)
    return client.v1.payment_intents.retrieve(
        payment_intent_id,
        params={'expand': ['latest_charge.balance_transaction']},
    )


def create_customer(secret_key, params, idempotency_key):
    client = _interactive_client(secret_key)
    return client.v1.customers.create(
        params=params,
        options={'idempotency_key': idempotency_key},
    )


def create_subscription(secret_key, params, idempotency_key):
    client = _interactive_client(secret_key)
    return client.v1.subscriptions.create(
        params=params,
        options={'idempotency_key': idempotency_key},
    )


def retrieve_charge(secret_key, charge_id):
    client = _interactive_client(secret_key)
    return client.v1.charges.retrieve(
        charge_id,
        params={'expand': ['balance_transaction']},
    )


def construct_webhook_event(payload, signature, webhook_secret):
    return stripe.Webhook.construct_event(payload, signature, webhook_secret)


def create_connected_account(secret_key, params, idempotency_key):
    client = stripe.StripeClient(secret_key, max_network_retries=2)
    return client.v1.accounts.create(params=params, options={'idempotency_key': idempotency_key})


def create_account_link(secret_key, params):
    client = stripe.StripeClient(secret_key, max_network_retries=2)
    return client.v1.account_links.create(params=params)


def retrieve_connected_account(secret_key, account_id):
    client = stripe.StripeClient(secret_key, max_network_retries=2)
    return client.v1.accounts.retrieve(account_id)


def create_transfer(secret_key, params, idempotency_key):
    client = stripe.StripeClient(secret_key, max_network_retries=2)
    return client.v1.transfers.create(params=params, options={'idempotency_key': idempotency_key})


def create_billing_portal_session(secret_key, customer_id, return_url):
    client = _interactive_client(secret_key)
    return client.v1.billing_portal.sessions.create(params={
        'customer': customer_id, 'return_url': return_url})
