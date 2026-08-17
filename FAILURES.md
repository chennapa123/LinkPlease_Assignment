# Known Limitations and Failures

This document describes known issues, limitations, and design trade-offs in LinkPlease.

## Critical Path Items Not Yet Implemented

### Phase 13: Public Deployment Verification

The application has not been deployed to a publicly accessible URL yet. The following functionality depends on this:
- Real webhook delivery from PseudoGram to a public endpoint
- End-to-end testing with actual PseudoGram events
- Load testing via the simulator against a production instance

### Phase 14: Final Assignment Submission

The final submission endpoint to POST results back to the PseudoGram assignment API is not yet implemented. This includes:
- Generating the final submission payload with all statistics
- Authenticating to the assignment submission endpoint
- Handling submission errors and retries

## Design Limitations

### Background Services Not Integrated

The following background services exist as standalone modules but are not yet integrated into the FastAPI application lifecycle:

1. **Delivery Worker** (`app/services/delivery_worker.py`)
   - Currently only tested in isolation
   - Not scheduled to run continuously on application startup
   - Must be invoked manually or via external job scheduler

2. **Reconciliation Service** (`app/services/reconciliation_service.py`)
   - Currently only tested in isolation
   - Not scheduled to run periodically
   - Accepted deliveries may stay in that state indefinitely without reconciliation

**Impact**: In production, these services must be run as separate processes or integrated via an event loop. The current implementation provides the logic but not the orchestration.

### Simulator Not Connected to Real Load Generation

The simulator endpoints (`POST /v1/simulate/start`, `GET /v1/simulate/{run_id}/truth`) exist but:
- Do not actually generate webhook events
- Do not drive the delivery pipeline
- Serve only as a contract for comparison

**Impact**: Real load testing requires either:
- External simulation tool sending actual webhook events
- Integration with PseudoGram's test simulator API

### Unique Constraint Silently Ignores Duplicates

When a duplicate delivery is detected (same rule_id and user_id), the unique constraint silently rolls back the insert:

```python
try:
    db.add(delivery)
    db.commit()
except IntegrityError:
    db.rollback()
```

**Impact**: The duplicate is not logged or counted separately from "duplicates_blocked" stats. There is no audit trail of which duplicate inserts were attempted.

## Operational Limitations

### Database Migrations Must Be Manual

Before running the application on a new environment:
```bash
alembic upgrade head
```

There is no automatic migration on startup. If migrations are not run, the application will fail when creating tables.

**Mitigation**: Add `Base.metadata.create_all()` on startup (already implemented).

### No Request Logging or Tracing

The application does not implement:
- Request/response logging (other than error cases)
- Distributed tracing
- Audit trail of rule changes or delivery events

**Impact**: Debugging production issues requires examining database state directly.

### Rate Limiter Not Persistent Across Restarts

The sliding-window rate limiter stores state in memory:
```python
class SlidingWindowRateLimiter:
    def __init__(self):
        self.requests: list[float] = []
```

**Impact**: 
- Rate limit state is lost when the application restarts
- Multiple instances of the application do not share rate limit state
- A coordinated attack could bypass the limiter by targeting multiple instances

### PSEUDOGRAM_API_KEY Stored as Plain Text in Environment

The API key is not encrypted or hashed:
```python
pseudogram_api_key: str = ""
```

**Impact**: The key is visible in environment files, logs, and process listings. Implement:
- Secure vault integration (Kubernetes Secrets, AWS Secrets Manager, HashiCorp Vault)
- Key rotation mechanism
- Audit logging of key usage

### No Timeout on Long-Running Requests

PseudoGram requests use httpx with a default timeout, but webhook processing has no timeout:

```python
async def receive_webhook(request: Request):
    raw_body = await request.body()
    # If the request body is extremely large, this could block indefinitely
```

**Impact**: Malicious or misconfigured clients could send huge payloads causing memory exhaustion.

**Mitigation**: Set a max body size limit in FastAPI or middleware.

## Data Consistency Issues

### Comment Text Not Stored

When a comment is deleted, we only have the comment_id but not the original comment text:

```python
elif event_type == "comment.deleted":
    comment_id = (payload.get("data") or {}).get("comment_id")
    handle_comment_deleted(str(comment_id))
```

**Impact**: Cannot verify that the deleted comment actually matched a rule. Cannot generate detailed audit reports.

### Event Processing Not Atomic

Event insertion and delivery creation happen in the same transaction, but if the transaction rolls back, the event is lost:

```python
try:
    event = Event(...)
    db.add(event)
    db.commit()  # Event is now persisted

    if event_type == "comment.created":
        # ... create deliveries
        db.commit()
except Exception:
    db.rollback()
```

**Impact**: A webhook event might be processed multiple times if the client retries after a partial failure.

### No Cleanup of Old Events

Events accumulate in the database indefinitely. There is no archival or deletion strategy.

**Impact**: Over time, the events table will grow unbounded and queries will slow down.

### Delivery Status Not Updated When Comment Deleted

When a comment is deleted, we only cancel deliveries that are `queued` or `sending`. Deliveries already in `accepted` or `delivered` state remain unchanged.

**Impact**: Stats may report a delivery as "sent" even though the original comment was deleted.

## Testing Limitations

### Database Tests Use In-Memory SQLite

Tests use SQLite, which has different concurrency and behavior from PostgreSQL:
- AUTOINCREMENT semantics differ
- Constraint enforcement may differ
- Transaction isolation levels differ

**Impact**: Tests pass against SQLite but may fail against PostgreSQL in production.

### No Concurrent Delivery Testing

Tests do not verify behavior when multiple delivery workers attempt to claim the same job.

**Impact**: Race conditions in the delivery worker are not caught.

### Simulator Truth Test Does Not Verify Actual Behavior

The simulator truth endpoint returns stats, but the test does not verify that:
- The stats are correct for the current database state
- The stats match what the delivery worker actually sent

**Impact**: A broken stats calculation could pass the simulator test.

## API Contract Issues

### No API Versioning

All endpoints are at the root `/` or `/v1/simulate`. No versioning strategy is in place for breaking changes.

**Impact**: Future changes to the API will require careful coordination or multiple versions.

### No Rate Limit Headers

HTTP responses do not include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, or `X-RateLimit-Reset` headers.

**Impact**: Clients cannot gracefully back off or warn users of approaching limits.

### Error Responses Inconsistent

Some errors return status 400, others return 401 or 404. No standardized error response format.

**Impact**: Client error handling must account for multiple response formats.

## Performance Considerations

### No Database Indexes on Comment ID

Deliveries are queried by comment_id in `handle_comment_deleted`, but there is no index:

```python
matches = db.query(Delivery).filter(Delivery.comment_id == str(comment_id)).all()
```

**Impact**: As deliveries scale, comment deletion queries become slow.

### Duplicate Detection is O(n)

Rule matching iterates through all rules and checks string containment:

```python
return [
    rule
    for rule in db.query(Rule).all()
    if rule.normalized_keyword and rule.normalized_keyword in normalized_comment
]
```

**Impact**: With thousands of rules, comment matching becomes slow.

## Security Considerations

### Webhook Signature Verification Uses Constant-Time Comparison

This is correctly implemented with `hmac.compare_digest()`, but:
- No rate limiting on webhook endpoint
- No request size limits
- No input sanitization

**Impact**: Potential for DoS or injection attacks.

### No SQL Injection Protection

The application uses SQLAlchemy ORM correctly, which prevents SQL injection. However, any raw SQL queries would be vulnerable.

## Recommended Improvements

1. **Integrate background services into FastAPI startup event** (Python 3.9+ lifespan context managers)
2. **Add persistent rate limiting** using Redis or database
3. **Implement proper structured logging** with context propagation
4. **Add request/response tracing** for debugging
5. **Implement event archival** for old events
6. **Add index on `comment_id` in deliveries table**
7. **Use full-text search or trie for rule matching** when scaling
8. **Store API keys in secure vault**, not plain text
9. **Set request body size limits** in FastAPI middleware
10. **Add versioning strategy** to the API design
11. **Implement comprehensive error response format**
12. **Run integration tests against PostgreSQL** not just SQLite

## Phase Blockers

### Cannot Complete Phase 13 Without:
- Public URL to host the application
- PseudoGram test simulator or webhook forwarding service

### Cannot Complete Phase 14 Without:
- Phase 13 completed and validated
- Assignment submission endpoint details from PseudoGram

---

**Last Updated**: 2026-08-17  
**Status**: Under Active Development
