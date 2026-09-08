"""Small Stripe boundary so payment code is testable without network access."""

import stripe


def create_checkout_session(secret_key, params, idempotency_key):
    client = stripe.StripeClient(secret_key, max_network_retries=2)
    return client.v1.checkout.sessions.create(
        params=params,
        options={'idempotency_key': idempotency_key},
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
