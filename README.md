# LinkPlease

A resilient comment-to-DM automation service that integrates with PseudoGram to detect keywords in comments and send direct messages to users.

## Overview

LinkPlease is a FastAPI-based service that:

1. **Accepts webhook events** from PseudoGram (comment created, comment deleted)
2. **Matches comments** against a set of keywords stored in the database
3. **Sends DMs** to users whose comments match a rule
4. **Handles delivery failures** with retry logic and exponential backoff
5. **Reconciles delivery status** against PseudoGram API responses
6. **Provides stats** on total sent, queued, failed, and duplicate-blocked deliveries

## Architecture

### Technology Stack

- **Framework**: FastAPI (Python 3.12+)
- **Database**: PostgreSQL + SQLAlchemy 2.x ORM
- **Migrations**: Alembic
- **HTTP Client**: httpx
- **Containerization**: Docker & Docker Compose
- **Testing**: pytest + pytest-cov

### Core Concepts

#### Durable Delivery Queue

Deliveries are persisted in the database with an explicit state machine:
- `queued`: Ready to send
- `sending`: Currently being sent to PseudoGram
- `accepted`: PseudoGram acknowledged the DM request
- `delivered`: PseudoGram confirmed the DM was sent
- `failed`: Delivery exhausted retry attempts
- `cancelled`: Cancelled because the comment was deleted

#### Duplicate Prevention

A unique constraint on `(rule_id, user_id)` prevents the same rule from generating multiple deliveries to the same user per webhook batch.

#### Background Worker

A configurable delivery worker:
- Claims due deliveries from the queue
- Sends DM requests to PseudoGram
- Handles transient errors (rate limits, timeouts) with retry scheduling
- Handles permanent errors (auth, malformed data) by marking as failed

#### Reconciliation

A reconciliation service periodically:
- Queries PseudoGram for delivery status updates
- Transitions accepted deliveries to delivered when confirmed

#### Rate Limiting

A sliding-window rate limiter enforces **10 requests per rolling 60 seconds** to the PseudoGram API.

### Project Structure

```
LinkPlease_Assignment/
├── app/
│   ├── __init__.py
│   ├── main.py              # API endpoints, webhook handler, simulator
│   ├── config.py            # Environment and settings
│   ├── database.py          # SQLAlchemy engine & session factory
│   ├── models.py            # Rule, Event, Delivery ORM models
│   ├── schemas.py           # Request/response Pydantic schemas
│   └── services/
│       ├── pseudogram_client.py      # HTTP client for PseudoGram API
│       ├── delivery_worker.py        # Background task for sending DMs
│       ├── rate_limiter.py           # Sliding-window rate limiter
│       └── reconciliation_service.py # Status reconciliation
├── migrations/              # Alembic migration scripts
├── tests/                   # pytest test suite
├── scripts/
│   └── compare_simulator_truth.py   # Simulation comparison utility
├── docker-compose.yml       # Local development environment
├── Dockerfile               # Container image definition
├── requirements.txt         # Python dependencies
├── pytest.ini              # pytest configuration
├── .env.example            # Environment variables template
├── alembic.ini             # Alembic configuration
└── README.md               # This file
```

## Getting Started

### Prerequisites

- Python 3.12+
- Docker & Docker Compose (for local PostgreSQL)
- PseudoGram API key

### Local Setup

1. **Clone the repository**
   ```bash
   cd LinkPlease_Assignment
   ```

2. **Create a Python virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your PseudoGram API key and other settings
   ```

5. **Start PostgreSQL with Docker Compose**
   ```bash
   docker-compose up -d
   ```

6. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

7. **Start the application**
   ```bash
   uvicorn app.main:app --reload
   ```

   The API will be available at `http://localhost:8000`

### Testing

Run the full test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app tests/
```

Run specific test file:
```bash
pytest tests/test_health.py -v
```

## API Endpoints

### Health Check

**GET** `/health`

Returns service health status.

**Response (200)**
```json
{
  "status": "ok",
  "service": "linkplease"
}
```

### Create Rule

**POST** `/rules`

Create a new keyword rule for automatic DM dispatch.

**Request Body**
```json
{
  "keyword": "PRICE",
  "dm_message": "Check our pricing page at example.com/pricing"
}
```

**Response (201)**
```json
{
  "rule_id": 1,
  "keyword": "PRICE",
  "dm_message": "Check our pricing page at example.com/pricing"
}
```

### Get Statistics

**GET** `/stats`

Get delivery statistics.

**Response (200)**
```json
{
  "sent": 42,
  "failed": 2,
  "queued": 5,
  "duplicates_blocked": 3
}
```

- `sent`: Deliveries confirmed as sent by PseudoGram
- `failed`: Deliveries that failed after max retries
- `queued`: Deliveries waiting to be sent or currently sending
- `duplicates_blocked`: Deliveries blocked by the (rule_id, user_id) unique constraint

### Webhook

**POST** `/webhook`

Receive events from PseudoGram. Requests must include an `X-PseudoGram-Signature` header with HMAC-SHA256 verification.

**Supported Event Types**
- `comment.created`: Triggers rule matching and delivery creation
- `comment.deleted`: Cancels queued deliveries for that comment

**Example Event Payload**
```json
{
  "event_id": "evt_12345",
  "event_type": "comment.created",
  "data": {
    "comment_id": "cmt_67890",
    "text": "I want to know about PRICE options",
    "from": {
      "user_id": "user_abc123"
    }
  }
}
```

### Simulator Lifecycle (Phase 11)

**POST** `/v1/simulate/start`

Start a simulation run for load testing.

**Request Body**
```json
{
  "webhook_url": "https://example.com/webhook",
  "count": 500,
  "duration_seconds": 60
}
```

**Response (200)**
```json
{
  "run_id": "sim_abc123def456",
  "status": "started"
}
```

**GET** `/v1/simulate/{run_id}/truth`

Get the expected delivery state for a simulation run.

**Response (200)**
```json
{
  "run_id": "sim_abc123def456",
  "expected": {
    "sent": 125,
    "failed": 0,
    "queued": 0,
    "duplicates_blocked": 25
  }
}
```

## Configuration

Edit `.env` to configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/linkplease` | PostgreSQL connection string |
| `PSEUDOGRAM_API_KEY` | (empty) | API key for PseudoGram authentication |
| `PSEUDOGRAM_BASE_URL` | `https://pseudogram-api.onrender.com/` | Base URL for PseudoGram API |
| `MAX_RETRY_ATTEMPTS` | `5` | Maximum retry attempts for failed deliveries |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Deployment

### Docker Compose (Development)

```bash
docker-compose up
```

This starts:
- PostgreSQL on port 5432
- FastAPI application on port 8000

### Production Deployment

For production, consider:

1. **Use environment-specific `.env` files**
   ```bash
   cp .env.example .env.production
   # Update with production secrets
   ```

2. **Configure external PostgreSQL** (managed database service)

3. **Set up a reverse proxy** (nginx, traefik) with TLS

4. **Enable health checks** in orchestration platform (Kubernetes, ECS, etc.)

5. **Run background services separately**
   - Use process supervisor or orchestration to run delivery worker
   - Run reconciliation service on a schedule

6. **Monitor and log**
   - Send application logs to centralized logging
   - Set up alerts for failed deliveries

## Background Services

### Delivery Worker

The delivery worker is not yet integrated as a background task in this phase. When implemented, it will:

```python
# Pseudocode for future implementation
async def delivery_worker():
    while True:
        deliveries = get_due_deliveries()
        for delivery in deliveries:
            try:
                send_to_pseudogram(delivery)
            except RetryableError:
                schedule_retry(delivery)
            except PermanentError:
                mark_failed(delivery)
        await asyncio.sleep(WORKER_POLL_INTERVAL)
```

### Reconciliation Service

The reconciliation service is not yet integrated as a background task in this phase. When implemented, it will:

```python
# Pseudocode for future implementation
async def reconciliation_service():
    while True:
        deliveries = get_accepted_deliveries()
        for delivery in deliveries:
            status = get_status_from_pseudogram(delivery.dm_id)
            if status == "sent":
                mark_delivered(delivery)
        await asyncio.sleep(RECONCILIATION_POLL_INTERVAL)
```

## Development Workflow

### Creating a New Feature

1. Create a feature branch
2. Add tests in `tests/`
3. Implement the feature
4. Run tests: `pytest -v`
5. Commit and push

### Running Migrations

After modifying `app/models.py`:

```bash
# Auto-generate migration
alembic revision --autogenerate -m "Add new column"

# Review the migration in migrations/versions/

# Apply migration
alembic upgrade head
```

## Troubleshooting

### Database Connection Issues

```
Error: could not translate host name "db" to address
```

- Ensure Docker Compose is running: `docker-compose up -d`
- Check PostgreSQL is healthy: `docker-compose ps`

### Webhook Signature Verification Fails

```
401 Unauthorized: invalid webhook signature
```

- Verify `PSEUDOGRAM_API_KEY` is correctly set in `.env`
- Ensure the webhook payload body is not modified before verification

### Rate Limit Errors

The service enforces a 10 requests/60 seconds limit. If you see:

```
429 Too Many Requests
```

Adjust `MAX_RETRY_ATTEMPTS` or implement request queueing.

## Testing Coverage

The test suite covers:

- ✅ Health check endpoint
- ✅ Rule creation with validation
- ✅ Webhook signature verification
- ✅ Event deduplication
- ✅ Comment matching and delivery creation
- ✅ Unique constraint enforcement
- ✅ PseudoGram client (mocked)
- ✅ Delivery worker state transitions
- ✅ Rate limiter sliding window
- ✅ Reconciliation logic
- ✅ Comment deletion handling
- ✅ Stats aggregation
- ✅ Simulator lifecycle and truth comparison

Run `pytest --cov=app` to see detailed coverage.

## Known Limitations

See [FAILURES.md](FAILURES.md) for a complete list of known issues and limitations.

## Future Phases

- **Phase 12**: Documentation & deployment (current)
- **Phase 13**: Real deployment verification from public URL
- **Phase 14**: Final submission to PseudoGram assignment endpoint

## Support

For issues or questions, please refer to [FAILURES.md](FAILURES.md) or check the test suite for usage examples.

## License

This project is part of the PseudoGram assignment.
