# Deployment Information

## Public URL
https://k5-l3a-day14-levanhoang-2a202603357.onrender.com

## Platform
Render (Web Service `Docker` với Root Directory `06-lab-complete` + Render Key Value / Redis miễn phí, region `Singapore`)

## Test Commands

### Health & Readiness Check
```bash
curl -i https://k5-l3a-day14-levanhoang-2a202603357.onrender.com/health
# Expected: HTTP 200 — {"status":"healthy","environment":"production"}

curl -i https://k5-l3a-day14-levanhoang-2a202603357.onrender.com/ready
# Expected: HTTP 200 — {"status":"ready","redis":"connected"}
```

### API Test (Authentication & Inference)
```bash
# Thiếu X-API-Key -> 401 Unauthorized
curl -i -X POST https://k5-l3a-day14-levanhoang-2a202603357.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: HTTP 401 — {"detail":"Invalid or missing X-API-Key header"}

# Có X-API-Key hợp lệ -> 200 OK
curl -i -X POST https://k5-l3a-day14-levanhoang-2a202603357.onrender.com/ask \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

### Production Readiness Validation
```bash
python check_production_ready.py --public-url https://k5-l3a-day14-levanhoang-2a202603357.onrender.com
# Result: 12/12 tiêu chí đạt · 44/44 checks passed
```

## Environment Variables Set (trên Render Dashboard — không commit giá trị thật)
- `ENVIRONMENT` (`production`)
- `AGENT_API_KEY` (secret)
- `REDIS_URL` (Internal Key Value URL của `k5-day14-redis`)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `MONTHLY_BUDGET_USD` (`20.0`)
- `PORT` (do Render tự cấp lúc runtime)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
