---
name: Request-level SQLAlchemy caching
description: Why permission caches in Flask-SQLAlchemy should be tied to a transaction
---

When caching workflow permissions for one request, invalidate the cache when the underlying transaction changes; an in-request commit or rollback can otherwise leave decisions based on stale grants or assignments. Flask-SQLAlchemy exposes a scoped session, so use its current session instance when comparing transaction identity.

**Why:** Repeated authorization checks once drove page query counts upward, but a naive request-only cache risked stale decisions after a transaction boundary; using transaction methods on the scoped-session proxy itself also caused runtime errors.

**How to apply:** For future authorization-query batching or caching, make the cache request-local and transaction-aware, and cover both ordinary GETs and requests that commit partway through.