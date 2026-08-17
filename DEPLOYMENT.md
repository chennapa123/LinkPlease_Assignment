# Deployment Guide

This guide covers deploying LinkPlease in different environments.

## Development Deployment

### Using Docker Compose (Recommended for Local Development)

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f app

# Run migrations
docker-compose exec app alembic upgrade head

# Stop services
docker-compose down
```

The application will be available at `http://localhost:8000`

## Production Deployment

### Prerequisites

- Docker & Docker Compose installed
- Environment variables configured
- PostgreSQL credentials secured
- PseudoGram API key obtained

### Using Docker Compose Production File

1. **Create `.env.prod` with production values:**

```bash
cp .env.example .env.prod
```

Edit `.env.prod`:
```
DB_PASSWORD=<secure-password>
PSEUDOGRAM_API_KEY=<your-api-key>
PSEUDOGRAM_BASE_URL=https://pseudogram-api.onrender.com/
MAX_RETRY_ATTEMPTS=5
LOG_LEVEL=INFO
```

**IMPORTANT**: Do not commit `.env.prod` to version control. Use a secrets management system instead.

2. **Build and start services:**

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

3. **Run database migrations:**

```bash
docker-compose -f docker-compose.prod.yml run app alembic upgrade head
```

4. **Verify the application is running:**

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "linkplease"
}
```

### Differences Between Development and Production

| Aspect | Development | Production |
|--------|-------------|-----------|
| File | `docker-compose.yml` | `docker-compose.prod.yml` |
| Code Reload | Enabled (--reload) | Disabled |
| Volumes | Mounted (live code changes) | None (immutable image) |
| Logging | Console | JSON file (10 MB max, 10 files retained) |
| Health Check | None | HTTP check every 30s |
| Restart Policy | No | Unless-stopped |
| Database Container | Standard | Same (consider external DB) |
| Resource Limits | None | (Can be added) |

### Advanced Production Setup

#### Using External PostgreSQL

Edit `.env.prod` to use external PostgreSQL:

```
DATABASE_URL=postgresql+psycopg://user:password@rds.example.com:5432/linkplease
```

Then run just the app container:

```bash
docker run -d \
  --name linkplease-app \
  --env-file .env.prod \
  -p 8000:8000 \
  linkplease
```

Or with docker-compose, remove the `db` service from the file.

#### Using Kubernetes

Example Kubernetes deployment manifest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: linkplease
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: linkplease
  template:
    metadata:
      labels:
        app: linkplease
    spec:
      containers:
      - name: linkplease
        image: linkplease:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: linkplease-secrets
              key: database-url
        - name: PSEUDOGRAM_API_KEY
          valueFrom:
            secretKeyRef:
              name: linkplease-secrets
              key: api-key
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: linkplease-service
  namespace: production
spec:
  selector:
    app: linkplease
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

#### Using Render or Similar PaaS

1. Push code to GitHub
2. Connect repository to Render
3. Set environment variables in Render dashboard
4. Configure to run: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Health Checks and Monitoring

#### Application Health

```bash
# Check application health
curl http://localhost:8000/health

# Check database connectivity
curl http://localhost:8000/stats
```

#### PostgreSQL Health (if using Docker)

```bash
docker-compose -f docker-compose.prod.yml exec db pg_isready -U postgres -d linkplease
```

#### View Application Logs

```bash
# Docker Compose
docker-compose -f docker-compose.prod.yml logs -f app

# Kubernetes
kubectl logs -f deployment/linkplease -n production
```

### Database Migrations in Production

Always test migrations in a staging environment first.

```bash
# Apply migrations
docker-compose -f docker-compose.prod.yml run app alembic upgrade head

# Verify migration status
docker-compose -f docker-compose.prod.yml run app alembic current

# Rollback if needed
docker-compose -f docker-compose.prod.yml run app alembic downgrade -1
```

### Backup and Disaster Recovery

#### PostgreSQL Backup

```bash
# Backup database
docker-compose -f docker-compose.prod.yml exec db pg_dump -U postgres linkplease > backup.sql

# Restore database
docker-compose -f docker-compose.prod.yml exec db psql -U postgres linkplease < backup.sql
```

#### Automated Backup (with cron)

```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/backups/linkplease_${DATE}.sql"

docker-compose -f docker-compose.prod.yml exec db pg_dump -U postgres linkplease > "$BACKUP_FILE"
gzip "$BACKUP_FILE"

# Cleanup old backups (keep 30 days)
find /backups -name "*.gz" -mtime +30 -delete
```

Schedule with cron:
```bash
0 2 * * * /path/to/backup.sh
```

### Scaling Considerations

#### Multiple Application Instances

Use a load balancer (nginx, HAProxy, cloud provider) to distribute traffic:

```
Client → Load Balancer → App Instance 1
                      ├→ App Instance 2
                      └→ App Instance 3
                           ↓
                      PostgreSQL (shared)
```

**Important**: The in-memory rate limiter is not shared between instances. Consider:
1. Moving rate limiter to Redis
2. Implementing request queueing per instance
3. Using load balancer-level rate limiting

#### Database Connection Pooling

Add pgBouncer for production deployments:

```yaml
pgbouncer:
  image: edoburu/pgbouncer
  environment:
    DATABASE_URL: postgres://postgres:password@db:5432/linkplease
    POOL_MODE: transaction
    MAX_CLIENT_CONN: 1000
    DEFAULT_POOL_SIZE: 25
  ports:
    - "6432:6432"
```

Update `DATABASE_URL` to connect to pgBouncer:
```
postgresql+psycopg://postgres:password@pgbouncer:6432/linkplease
```

### Security Checklist

- [ ] Environment variables stored in secure secrets manager (not `.env` files in production)
- [ ] HTTPS/TLS enabled via reverse proxy
- [ ] Firewall rules restrict database access to app container
- [ ] API keys rotated regularly
- [ ] Logs collected centrally (CloudWatch, Datadog, ELK, etc.)
- [ ] Database backups automated and tested
- [ ] Intrusion detection/monitoring enabled
- [ ] Rate limiting enforced (application + load balancer levels)
- [ ] SQL injection tested (using SQLAlchemy ORM prevents this)
- [ ] CSRF protection verified (FastAPI provides by default)

### Monitoring and Alerts

#### Application Metrics to Monitor

- Response time (p50, p95, p99)
- Error rate (5xx responses)
- Delivery success rate
- Delivery queue size
- Database query performance
- Container memory/CPU usage

#### Example Prometheus Alerts

```yaml
groups:
  - name: linkplease
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{job="linkplease", status=~"5.."}[5m]) > 0.05
        annotations:
          summary: "High error rate on LinkPlease"

      - alert: AppDown
        expr: up{job="linkplease"} == 0
        annotations:
          summary: "LinkPlease app is down"

      - alert: LargeQueueSize
        expr: linkplease_queue_size > 10000
        annotations:
          summary: "Delivery queue size is large"
```

### Rollback Procedure

If a deployment has issues:

1. **Identify the issue** from logs
2. **Stop the problematic version** (or keep it running if safe)
3. **Revert to previous image version**:

```bash
# Keep current version image ID
CURRENT_IMAGE=$(docker images linkplease --format "{{.ID}}" | head -1)

# Pull and start previous version
docker-compose -f docker-compose.prod.yml down
# Update compose file to use previous tag
docker-compose -f docker-compose.prod.yml up -d
```

4. **Verify health checks pass**
5. **Run any necessary migrations**
6. **Investigate what went wrong**

### Cost Optimization

- Use cloud provider's managed PostgreSQL (AWS RDS, Azure Database)
- Configure auto-scaling based on CPU/memory
- Use spot instances for non-critical workloads
- Implement request caching where appropriate
- Monitor and optimize database query performance

---

## Troubleshooting

### Application won't start

```
Error: could not translate host name "db"
```

**Solution**: Ensure `docker-compose up -d` completes before checking logs. Database takes 30-40 seconds to be ready.

### Migrations fail

```
sqlalchemy.exc.ProgrammingError: (psycopg.ProgrammingError) relation "rules" already exists
```

**Solution**: Database already has tables. If this is a fresh deployment, the `Base.metadata.create_all()` in app startup has already created tables. Migrations are only needed for schema changes.

### High memory usage

**Solution**: 
- Monitor with `docker stats`
- Increase container memory limit
- Check for memory leaks in application
- Consider connection pooling

### Database locked

```
ERROR: database is locked
```

**Solution**: 
- Check for long-running queries: `SELECT * FROM pg_stat_activity;`
- Kill if necessary: `SELECT pg_terminate_backend(pid);`
- For SQLite in tests, use `PRAGMA journal_mode=WAL;`

---

**Last Updated**: 2026-08-17
