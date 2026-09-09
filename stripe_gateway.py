"""Small Stripe boundary so payment code is testable without network access."""

import stripe


def create_checkout_session(secret_key, params, idempotency_key):
    # A Checkout click is an interactive request. Stripe's SDK defaults to an
    # 80-second timeout and retries network failures, which can leave the user
    # staring at "Opening Stripe…" for several minutes. Fail promptly instead;
    # the idempotency key makes a safe retry possible from the form.
    client = stripe.StripeClient(
        secret_key,
        max_network_retries=0,
        http_client=stripe.RequestsClient(timeout=(3, 10)),
    )
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


def create_billing_portal_session(secret_key, customer_id, return_url):
    client = stripe.StripeClient(
        secret_key, max_network_retries=0,
        http_client=stripe.RequestsClient(timeout=(3, 10)))
    return client.v1.billing_portal.sessions.create(params={
        'customer': customer_id, 'return_url': return_url})
