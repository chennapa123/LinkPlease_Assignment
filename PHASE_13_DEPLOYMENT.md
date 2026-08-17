# Phase 13: Real Deployment Verification

This guide walks through deploying LinkPlease to Render and validating it works end-to-end with real PseudoGram integration.

## Prerequisites

- Render account (free tier available at https://render.com)
- GitHub repository with LinkPlease code pushed
- PseudoGram API key
- PseudoGram webhook simulator access (or test account)

## Step 1: Deploy to Render

### 1.1 Connect GitHub Repository

1. Go to https://render.com and sign up/log in
2. Click "New +" → "Web Service"
3. Connect your GitHub account and select the LinkPlease repository
4. Configure the service:

   | Setting | Value |
   |---------|-------|
   | Name | `linkplease-api` |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt && alembic upgrade head` |
   | Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

5. Click "Create Web Service"

### 1.2 Provision PostgreSQL Database

1. In Render dashboard, click "New +" → "PostgreSQL"
2. Configure the database:

   | Setting | Value |
   |---------|-------|
   | Name | `linkplease-db` |
   | Database | `linkplease` |
   | User | `postgres` |
   | Region | Same as API (for latency) |

3. Create the database (takes ~5 minutes)

### 1.3 Link Database to API Service

1. In the API service settings, scroll to "Environment"
2. Add environment variable:
   - Key: `DATABASE_URL`
   - Value: Copy the connection string from the PostgreSQL service dashboard
   - **Change the database URL from the defaults to use the new PostgreSQL instance**

3. Add the PseudoGram API key:
   - Key: `PSEUDOGRAM_API_KEY`
   - Value: Your actual PseudoGram API key

4. Verify other environment variables are set:
   - `PSEUDOGRAM_BASE_URL`: `https://pseudogram-api.onrender.com/`
   - `MAX_RETRY_ATTEMPTS`: `5`
   - `LOG_LEVEL`: `INFO`

5. Click "Save Changes"
6. The service will auto-redeploy

### 1.4 Verify Deployment

```bash
# Get your Render service URL from the dashboard (looks like https://linkplease-api-xxxxx.onrender.com)
# Store it in a variable
export SERVICE_URL="https://linkplease-api-xxxxx.onrender.com"

# Check health endpoint
curl $SERVICE_URL/health

# Expected response:
# {"status":"ok","service":"linkplease"}
```

## Step 2: Initial Validation

Run the validation script to ensure the deployed service is working:

```bash
python scripts/validate_deployment.py --url $SERVICE_URL
```

This will verify:
- ✅ Health endpoint is responsive
- ✅ Database connectivity is working
- ✅ API endpoints are accessible
- ✅ Webhook signature verification is configured

## Step 3: Create Test Rules

Before running the simulator, create some test rules on the deployed instance:

```bash
curl -X POST $SERVICE_URL/rules \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "PRICE",
    "dm_message": "Check our pricing at example.com/pricing"
  }'

curl -X POST $SERVICE_URL/rules \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "BUDGET",
    "dm_message": "Learn about our budget options"
  }'

curl -X POST $SERVICE_URL/rules \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "HELP",
    "dm_message": "Support available at support@example.com"
  }'
```

Verify they were created:

```bash
curl $SERVICE_URL/stats

# Should show: {"sent": 0, "failed": 0, "queued": 0, "duplicates_blocked": 0}
```

## Step 4: Load Testing with Simulator

Run the load testing script against the deployed instance:

```bash
python scripts/load_test_deployed.py \
  --url $SERVICE_URL \
  --webhook-count 100 \
  --duration-seconds 30 \
  --api-key "your-pseudogram-api-key"
```

This will:
1. Send 100 simulated webhook events to the deployed instance
2. Spread them over 30 seconds
3. Track delivery success rate
4. Measure response times
5. Report final stats

### Expected Results

After the load test:

```bash
curl $SERVICE_URL/stats
```

You should see:
- `sent` > 0 (depends on worker integration, may show 0)
- `queued` > 0 (events waiting to be sent)
- `failed` = 0
- `duplicates_blocked` > 0 (if same comment/rule matched multiple times)

## Step 5: Truth Comparison

Compare the actual stats against expected values:

```bash
python scripts/compare_truth.py \
  --deployed-url $SERVICE_URL \
  --expected-sent 100 \
  --expected-failed 0 \
  --expected-queued 50 \
  --expected-duplicates 25
```

This validates that the deployment matches the expected behavior.

## Step 6: Webhook Verification

If PseudoGram provides a test mode or webhook forwarding:

1. Configure PseudoGram to send webhooks to: `$SERVICE_URL/webhook`
2. Send a test webhook with your API key signature
3. Verify the webhook is accepted:

```bash
# Should see status 200 and response: {"status":"accepted","event_id":"..."}
```

## Step 7: Monitor Logs

View application logs in Render dashboard:

1. Go to your service → Logs
2. Filter for errors: `level:error`
3. Check for any issues with:
   - Database connectivity
   - PseudoGram API calls
   - Signature verification

To tail logs in real-time:

```bash
# Using Render CLI (if installed)
render logs linkplease-api
```

## Step 8: Performance Baseline

Record baseline performance metrics:

```bash
python scripts/benchmark_deployed.py --url $SERVICE_URL
```

This will measure and report:
- Response time for GET /health
- Response time for GET /stats
- Response time for POST /rules
- Response time for POST /webhook
- Throughput (requests/second)
- P50, P95, P99 latencies

## Troubleshooting Deployment

### Build Failed

Check the build logs in Render:
1. Go to "Events" tab
2. Look for error messages
3. Common issues:
   - Missing environment variables
   - Invalid Python dependencies
   - Alembic migration failures

**Solution**: Fix the issue, push to GitHub, Render will rebuild automatically.

### Database Connection Error

```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Causes**:
- DATABASE_URL not set or incorrect
- PostgreSQL service not ready yet
- IP whitelist issue

**Solution**:
1. Verify DATABASE_URL is set correctly in Environment
2. Wait 5-10 minutes for PostgreSQL to fully initialize
3. In PostgreSQL service, disable IP whitelist for testing (not recommended for production)

### Timeout Errors

```
TimeoutError: Timed out connecting to PostgreSQL
```

**Causes**:
- PostgreSQL is still starting up
- Network latency is high
- Connection pool is exhausted

**Solution**:
1. Wait for PostgreSQL startup to complete
2. Check service resource usage in Render dashboard
3. Increase connection pool size if needed

### Migration Errors

```
alembic.util.exc.CommandError: No such revision
```

**Causes**:
- Database schema doesn't match migrations
- Migrations not run properly

**Solution**:
1. SSH into the service (Render provides this)
2. Run manually: `alembic upgrade head`
3. Check migration status: `alembic current`

## Performance Tuning

### Monitor Resource Usage

In Render dashboard:
- Check CPU usage (should be <50% for light load)
- Check memory usage (should be <200MB)
- Check database connections

### Scaling

For higher load:
1. Upgrade to higher plan (more CPU/memory)
2. Add multiple instances (horizontal scaling)
3. Enable caching for repeated requests

### Database Optimization

If queries are slow:
1. Check slow query log in PostgreSQL
2. Add indexes (modify migrations, redeploy)
3. Consider read replicas for scaled-out scenarios

## Rollback Procedure

If deployment has issues:

1. In Render dashboard, go to "Deploys"
2. Find the previous successful deployment
3. Click "Redeploy"
4. Confirm the action

The service will revert to the previous version within 1-2 minutes.

## Cost Estimation

Render free tier includes:
- **Web Service**: One free instance, auto-pauses after 15 minutes of inactivity
- **PostgreSQL**: Requires paid plan (starts at ~$7/month)

Typical cost for Phase 13 testing:
- Web Service: Free (auto-pauses) or ~$12/month (always-on)
- PostgreSQL: ~$7-15/month
- **Total**: ~$19-27/month for a small instance

For production, budget $30-100/month depending on load.

## Next Steps

After successful Phase 13 deployment and validation:

1. ✅ Document any deployment issues encountered
2. ✅ Record performance metrics
3. ✅ Test integration with PseudoGram webhooks
4. ✅ Proceed to Phase 14: Final submission

---

**Phase 13 Completion Checklist**

- [ ] GitHub repository connected to Render
- [ ] PostgreSQL database provisioned
- [ ] Environment variables configured
- [ ] Service deployed and health check passing
- [ ] Test rules created
- [ ] Load test completed
- [ ] Stats validated against expected values
- [ ] Logs reviewed for errors
- [ ] Performance baseline recorded
- [ ] PseudoGram webhook integration verified (if available)
- [ ] Ready to proceed to Phase 14

---

**Last Updated**: 2026-08-17
