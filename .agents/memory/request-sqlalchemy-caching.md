---
name: Request-level SQLAlchemy caching
description: Transaction boundaries and in-transaction write coherence for request caches
---

When caching workflow permissions for one request, invalidate the cache when the underlying transaction changes; an in-request commit or rollback can otherwise leave decisions based on stale grants or assignments. Flask-SQLAlchemy exposes a scoped session, so use its current session instance when comparing transaction identity.

**Why:** Repeated authorization checks once drove page query counts upward, but a naive request-only cache risked stale decisions after a transaction boundary; using transaction methods on the scoped-session proxy itself also caused runtime errors.

**How to apply:** For future authorization-query batching or caching, make the cache request-local and transaction-aware, and cover both ordinary GETs and requests that commit partway through.

For mutable person data, transaction identity alone is not enough: negative results, alias targets, and identity keys can change without a commit. Limit automatic caching to explicitly controlled import/preload operations unless every writer maintains cache coherence. Raw SQL mapper writes also require expiring or refreshing retained ORM rows, not just removing dictionary entries.

**Why:** Broad request caching returned stale missing addresses and old canonical identities after same-transaction writes. Mapper-written bilingual names remained stale when an ORM instance was still referenced. Batched imports also reuse newly created people across different book sources, so an owner absent at the start need not remain absent later in the upload.

**How to apply:** Test absent→created, alias changes, identity rekeying, retained ORM instances, commit/rollback, and multiple source rows sharing one newly created owner. Separate SELECT growth from necessary inserts when measuring import batching.