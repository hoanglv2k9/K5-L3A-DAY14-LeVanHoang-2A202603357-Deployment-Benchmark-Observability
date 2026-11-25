# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode secret trong source code (`app.py` dòng 17–18):** Ghi trực tiếp `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub sẽ lộ ngay thông tin nhạy cảm và khó xoay vòng key (secret rotation).
2. **Không quản lý cấu hình qua biến môi trường (`app.py` dòng 21–22, 51–53):** Gán cứng `DEBUG = True`, `MAX_TOKENS = 500`, `host="localhost"` (chỉ nghe loopback nội bộ, chạy trong container sẽ không nhận được traffic từ ngoài), `port=8000` (cứng cổng, không đọc biến `PORT` do Railway/Render cấp) và `reload=True` (tốn tài nguyên và gây rò rỉ/restart không kiểm soát trong production).
3. **Dùng `print()` thay cho structured logging & in lộ secret (`app.py` dòng 33–38):** Ghi log dạng text tự do `[DEBUG] ...` không thể parse tự động trên hệ thống log tập trung; đặc biệt dòng 34 còn `print` trực tiếp `OPENAI_API_KEY` ra stdout.
4. **Thiếu endpoint kiểm tra sức khỏe `/health` và `/ready` (`app.py` dòng 42–43):** Nền tảng cloud / Load Balancer không phân biệt được khi nào process crash cần restart hoặc khi nào app chưa sẵn sàng nhận traffic.
5. **Thiếu xử lý tắt an toàn (Graceful Shutdown):** Không có `lifespan` hay xử lý `SIGTERM`, khi nền tảng stop/redeploy container đột ngột sẽ làm đứt ngang request đang xử lý của người dùng.
6. **Không kiểm soát đầu vào & giao thức HTTP chuẩn (`app.py` dòng 30–31):** Nhận `question: str` qua query parameter (`POST /ask?question=...`) thay vì JSON request body có schema validation (giới hạn độ dài, báo lỗi 422 rõ ràng) và dễ lộ câu hỏi của người dùng trong URL/access log.
7. **Không cấu hình CORS (`app.py` dòng 13):** Thiếu chính sách `CORSMiddleware` giới hạn origin và phương thức cho phép khi nối với frontend thực tế.

### Exercise 1.2: Kết quả chạy thử bản `develop` (trong WSL2)
Lệnh test:
```bash
curl -sS -i -X POST "http://127.0.0.1:8000/ask?question=Hello"
```
Output nhận được:
```text
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 07:42:12 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Feature (`01-localhost-vs-production`) | Develop (`develop/app.py`) | Production (`production/app.py` & `config.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG = True`, `port = 8000` (dòng 17–22, 51–53) | Đọc toàn bộ từ biến môi trường qua `Settings` (`config.py` dòng 17–35) và `validate()` fail-fast khi thiếu `AGENT_API_KEY` ở `production` (dòng 37–46) | Không lộ secret lên Git; dùng chung một codebase qua dev/staging/production chỉ bằng đổi env vars. |
| **Network binding & Port** | `host="localhost"`, `port=8000`, `reload=True` (dòng 50–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (`PORT` env), `reload=settings.debug` (`false`) (dòng 194–198) | Bắt buộc lắng nghe `0.0.0.0` và đọc `PORT` động thì container/cloud mới định tuyến được traffic vào app. |
| **Health & Readiness** | Không có `/health`, `/ready` (dòng 42) | Có `GET /health` trả uptime/version/env (dòng 135–149) và `GET /ready` trả `200` hoặc `503` theo `is_ready` (dòng 152–161) | Giúp Load Balancer / cloud tách biệt *liveness* (còn sống) và *readiness* (đủ điều kiện nhận request). |
| **Logging** | `print("[DEBUG] Using key: ...")` (dòng 33–38) | Structured JSON logging với `format='{"time":...}'` + `json.dumps(...)`, tuyệt đối không log secret (`app.py` dòng 28–31, 111–122) | Hệ thống observability (Loki, Datadog) tìm kiếm/cảnh báo theo trường JSON nhanh và bảo mật. |
| **CORS & Input** | Không cấu hình CORS; nhận `?question=` trên URL (dòng 30–31) | `CORSMiddleware` giới hạn `allowed_origins` và `["GET", "POST"]` (dòng 77–82); nhận JSON body và trả `422` nếu rỗng (dòng 103–108) | Ngăn truy cập cross-origin trái phép và tránh lộ dữ liệu câu hỏi trên URL log. |
| **Shutdown (Graceful)** | Dừng đột ngột khi tắt process | Dùng `@asynccontextmanager lifespan` đặt `is_ready = False` trước khi tắt (dòng 39–67) và bắt `SIGTERM` (dòng 180–189) | Tránh mất request đang xử lý khi redeploy. *(Lưu ý thực nghiệm: khi ghi đè `signal.signal(SIGTERM, ...)` ở dòng 189 mà không gọi lại handler gốc của uvicorn sẽ khiến process không tắt khi nhận `SIGTERM` — cần chú ý tránh lỗi này ở Part 6.)* |

**Kết quả tự kiểm tra bản `production` (trong WSL2):**
- `GET /health` → `{"status":"ok","uptime_seconds":1.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T07:42:15.358160+00:00"}`
- `GET /ready` → `{"ready":true}`
- `POST /ask` (`{"question":"Hello"}`) → `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}`

---

## Part 2: Docker

### Exercise 2.1: Phân tích `02-docker/develop/Dockerfile`
1. **Base image:** `python:3.11` (`FROM python:3.11`, dòng 8) — bản phân phối Python đầy đủ trên Debian kèm compiler, công cụ build và nhiều thư viện hệ thống nên kích thước rất lớn.
2. **Working directory:** `/app` (`WORKDIR /app`, dòng 11) — thư mục làm việc hiện hành bên trong container; mọi lệnh `COPY`, `RUN`, `CMD` sau đó thực thi từ đây.
3. **Tại sao `COPY 02-docker/develop/requirements.txt .` trước khi `COPY` code (`app.py`, dòng 14–20):** Để tận dụng **Docker layer cache**. Thư viện ít thay đổi hơn mã nguồn; đặt `COPY requirements.txt` + `RUN pip install --no-cache-dir` trước giúp khi sửa `app.py`, Docker tái sử dụng cache layer đã cài sẵn thư viện thay vì tải và cài lại từ đầu *(lưu ý: `--no-cache-dir` chỉ tắt cache file `.whl` của `pip` để giảm size layer, không tắt Docker layer cache)*.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào:** `CMD ["python", "app.py"]` (dòng 30) là câu lệnh mặc định khi khởi chạy container và **có thể bị ghi đè hoàn toàn** bởi tham số truyền sau tên image trong `docker run <image> <lệnh khác>`. Ngược lại, `ENTRYPOINT` cố định executable chính chạy trong container (khi dùng chung, `CMD` trở thành đối số mặc định truyền vào `ENTRYPOINT`).

### Exercise 2.2: Build và chạy container bản `develop`
Chạy build từ **thư mục gốc repo** để build context khớp các lệnh `COPY` (`.dockerignore` loại bỏ `.env`, `venv/`, `__pycache__/` giúp không lọt secret vào image và build nhanh hơn):
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name part2-dev -p 8000:8000 my-agent:develop
curl -sS http://127.0.0.1:8000/health
curl -sS -X POST "http://127.0.0.1:8000/ask?question=What%20is%20Docker%3F"
```
Kết quả chạy thực tế trong WSL2:
- `GET /health` → `{"status":"ok","uptime_seconds":0.7,"container":true}`
- `POST /ask?question=What%20is%20Docker%3F` → `{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}`

### Exercise 2.3: Multi-stage build & So sánh kích thước image
- **Stage 1 (`builder` — `02-docker/production/Dockerfile` dòng 16–29):** Dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` và `pip install --no-cache-dir --user` vào `/root/.local`. Image này chỉ phục vụ biên dịch và cài đặt dependencies.
- **Stage 2 (`runtime` — dòng 36–72):** Khởi tạo sạch từ `python:3.11-slim`, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local`, chép `main.py` & `utils/mock_llm.py`, bổ sung `HEALTHCHECK` và `USER appuser`. Do **loại bỏ hoàn toàn** `gcc`, header files và công cụ build khỏi image cuối, dung lượng giảm mạnh và giảm bề mặt tấn công bảo mật.
- **Output thực tế `docker images my-agent` (trên máy trong WSL2):**
  ```text
  IMAGE               ID             DISK USAGE   CONTENT SIZE
  my-agent:develop    1d2986ede2a6       1.67GB          426MB
  my-agent:advanced   5fa8d9099e04        240MB         57.4MB
  ```
- **Chênh lệch đo bằng `docker image inspect`:**
  - `my-agent:develop`: **`1.667.771.714` bytes** (`1.667,8 MB` / `1.67 GB` hệ thập phân).
  - `my-agent:advanced`: **`239.811.258` bytes** (`239,8 MB` / `240 MB` hệ thập phân).
  - **Mức giảm dung lượng:** giảm **`1.428,0 MB`** (`-85,6%` theo disk usage; `-86,5%` theo content size từ `426 MB` xuống `57,4 MB`), đạt yêu cầu `< 500 MB`.

### Exercise 2.4: Kiến trúc Docker Compose stack (`02-docker/production/`)
```text
Client ──(HTTP :80 / HTTPS :443)──▶ Nginx (nginx:alpine, rate limit 10r/s, proxy_pass)
                                        │ (bridge network: internal)
                                        ▼
                                   Agent (:8000, non-root, target=runtime)
                                    ├──▶ Redis (redis:7-alpine :6379 + volume redis_data)
                                    └──▶ Qdrant (qdrant/qdrant:v1.9.0 :6333 + volume qdrant_data)
```
- **Các service được start & cách giao tiếp (`docker compose -p k5-day14-docker ps`):**
  - Tạo `.env.local` (bị `.gitignore` bỏ qua) và chạy với `-p k5-day14-docker` để cô lập project name khỏi thư mục `production/` ở Part 5 & Part 7.
  - Bốn container chạy cùng mạng bridge `internal`: `nginx` mở cổng `:80/:443` ra host và `proxy_pass http://agent_backend` (tới DNS nội bộ `agent:8000`, áp rate-limit `10r/s` trừ `/health`); `agent` không mở port trực tiếp ra ngoài, dùng `depends_on` chờ `redis` (`healthy`) & `qdrant` (`healthy`) trước khi khởi chạy và giao tiếp qua DNS tên service (`REDIS_URL=redis://redis:6379/0`, `QDRANT_URL=http://qdrant:6333`); `redis` & `qdrant` gắn named volumes (`redis_data`, `qdrant_data`) để bền vững dữ liệu.
- **Kết quả test thật qua Nginx (trên cổng `80`):**
  - `curl -sS http://127.0.0.1/health` → `{"status":"ok","uptime_seconds":1.0,"version":"2.0.0","timestamp":"2026-11-25T07:55:56.548178"}`
  - `curl -sS -X POST http://127.0.0.1/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'` → `{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}`
- Sau khi kiểm thử xong đã tắt sạch stack (`docker compose -p k5-day14-docker down -v`).

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Cloud Deployment (`06-lab-complete/` lên Render)
- **Public URL:** `https://k5-l3a-day14-levanhoang-2a202603357.onrender.com` (Render Web Service `Docker`, Root Directory `06-lab-complete`, nối tới Render Key Value/Redis `k5-day14-redis` cùng region `Singapore`).
- **Kết quả kiểm tra thật trên URL public:**
  - `GET /health` → `HTTP 200` (`{"status":"healthy","environment":"production"}`)
  - `GET /ready` → `HTTP 200` (`{"status":"ready","redis":"connected"}`)
  - `POST /ask` (không có `X-API-Key`) → `HTTP 401` (`{"detail":"Invalid or missing X-API-Key header"}`)
  - `POST /ask` (có `X-API-Key` hợp lệ) → `HTTP 200`
  - `check_production_ready.py --public-url https://k5-l3a-day14-levanhoang-2a202603357.onrender.com` → **`Result: 12/12 tiêu chí đạt · 44/44 checks passed`** (`🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!`).
- **Deliverables đính kèm:** [DEPLOYMENT.md](DEPLOYMENT.md) và ảnh chụp tại `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`.

### So sánh `railway.toml` vs `render.yaml`
Khi cấu hình deploy container Docker cho `06-lab-complete/`:

| Tiêu chí | `railway.toml` (Railway Config-as-Code) | `render.yaml` (Render Blueprint IaC) |
|---|---|---|
| **Định dạng & vai trò** | TOML (`[build]`, `[deploy]`), cấu hình cho **1 service** hiện tại (Build + Deploy policy). | YAML (`services:` list), chuẩn **Infrastructure as Code (IaC) đa service** — có thể khai báo cả web service lẫn managed Redis (`type: redis` ở `03-cloud-deployment/render/render.yaml`) trong cùng một file. |
| **Cách build & runtime** | Đặt `[build] builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` (hoặc `"NIXPACKS"` nếu không dùng Docker). | Khai báo trực tiếp từng service: `type: web`, `runtime: docker`, `plan: free`, `region` (`singapore` trong mẫu). |
| **Health check & Restart** | `healthcheckPath = "/health"`, `healthcheckTimeout = 100`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3`. | `healthCheckPath: /health`, `autoDeploy: true` khi push GitHub. |
| **Quản lý Env vars & Secrets** | Không khai báo env vars/secrets trong `railway.toml`; đặt riêng trên Railway Dashboard hoặc `railway variables set ...` (Railway tự cấp `$PORT` và cho phép tạo Redis plugin riêng). | Khai báo sẵn danh sách `envVars` ngay trong YAML mà không lộ secret: biến thường ghi `value: ...`, secret dùng `generateValue: true` (Render tự sinh key) hoặc `sync: false` (nhập tay trên dashboard như `REDIS_URL`). |

**Vì sao khác nhau?** Railway tối ưu trải nghiệm *zero-config cho từng service* (TOML gọn nhẹ chỉ mô tả cách build/restart, hạ tầng phụ như Redis & env vars quản lý trực quan qua Dashboard/CLI), trong khi Render Blueprint định nghĩa *toàn bộ topology hệ thống trong một file YAML* gắn với Git nên dễ tái tạo nguyên stack qua nhiều môi trường nhưng cấu trúc dài và chặt chẽ hơn.

### Exercise 3.3: Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)
Qua `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD trên Google Cloud Build + Cloud Run thực hiện tuần tự 4 bước sau mỗi lần push lên `main`:
1. **`test` (`python:3.11-slim`):** Cài dependencies và chạy `pytest tests/ -v --tb=short`; nếu test fail thì dừng ngay pipeline.
2. **`build` (`gcr.io/cloud-builders/docker`):** Build Docker image gắn tag theo `$COMMIT_SHA` và `:latest`, tận dụng `--cache-from` từ image `:latest` để tăng tốc build.
3. **`push`:** Đẩy image với đủ cả 2 tag lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcloud run deploy`):** Triển khai image `$COMMIT_SHA` lên Cloud Run khu vực `asia-southeast1` với cấu hình sản xuất (chi tiết IaC tương ứng trong `service.yaml`: `minScale: 1` tránh cold start, `maxScale: 10`, `containerConcurrency: 80`, tài nguyên `512Mi` RAM / `1` vCPU, lấy secret qua GCP Secret Manager không hardcode, và gắn `livenessProbe /health` + `startupProbe /ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)
Bật server với `AGENT_API_KEY=secret-key-123` và test lần lượt 3 trường hợp với `curl -i`:
```text
--- Không gửi X-API-Key -> 401 ---
HTTP/1.1 401 Unauthorized
content-type: application/json
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

--- Gửi sai X-API-Key (wrong-key) -> 403 ---
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

--- Gửi đúng X-API-Key: secret-key-123 -> 200 ---
HTTP/1.1 200 OK
{"question":"hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```
- **Nhận xét (Exercise 4.1):**
  - *Check API key ở đâu?* Tại hàm `verify_api_key` (`develop/app.py` dòng 39–54, dùng `APIKeyHeader(name="X-API-Key", auto_error=False)`), gắn vào `/ask` qua `Depends(verify_api_key)` (dòng 70), trong khi `/` và `/health` mở công khai.
  - *Sai/thiếu key thì sao?* Thiếu header `X-API-Key` → **`401 Unauthorized`**; gửi sai key → **`403 Forbidden`**.
  - *Làm sao rotate key?* Cập nhật biến môi trường `AGENT_API_KEY` trên server/nền tảng cloud (khuyên hỗ trợ đồng thời `key_cũ,key_mới` trong thời gian chuyển tiếp để không đứt kết nối client rồi mới thu hồi key cũ) mà **không cần sửa code**.

### Exercise 4.2 & 4.3: JWT Authentication, RBAC & Rate Limiting (`04-api-gateway/production/`)
1. **Lấy JWT token (`POST /auth/token` với `student` / `demo123`, giữ token đã che):**
   - `create_token` (`auth.py` dòng 35–43) ký JWT bằng `HS256` gồm `sub`, `role="user"`, `iat`, `exp` (`60` phút) — stateless, server không cần truy vấn DB mỗi request.
   - Output sau khi che phần chữ ký JWT: `Token received (masked): eyJhbGciOiJIUzI1Ni...<REDACTED>`.
2. **Kiểm tra xác thực, phân quyền RBAC & vòng lặp 12 request (`student` giới hạn `10 req/phút`):**
   ```text
   --- Không gửi Bearer token -> 401 ---
   HTTP/1.1 401 Unauthorized
   www-authenticate: Bearer
   x-content-type-options: nosniff
   x-frame-options: DENY
   x-xss-protection: 1; mode=block
   referrer-policy: strict-origin-when-cross-origin
   {"detail":"Authentication required. Include: Authorization: Bearer <token>"}

   --- Request #1 (Authorization: Bearer eyJhbGciOiJIUzI1Ni...<REDACTED>) -> 200 ---
   HTTP/1.1 200 OK
   {"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

   --- Vòng lặp Request #2..#12 ---
   Request #2 -> HTTP 200 ... Request #10 -> HTTP 200
   --- Request #11 -> 429 ---
   HTTP/1.1 429 Too Many Requests
   x-ratelimit-limit: 10
   x-ratelimit-remaining: 0
   x-ratelimit-reset: 1795594677
   retry-after: 59
   {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
   Request #12 -> HTTP 429

   --- RBAC check: GET /admin/stats với token student -> 403 ---
   HTTP/1.1 403 Forbidden
   {"detail":"Admin only"}
   ```
- **Giải thích Exercise 4.3:**
  - **Thuật toán & Ngưỡng:** `RateLimiter` (`rate_limiter.py` dòng 17–87) dùng **Sliding Window Counter** lưu timestamps trong `deque` 60 giây (tránh lỗi cho phép burst gấp đôi ở mép phút của Fixed Window). User thường (`student`, `role="user"`) giới hạn **`10 req/phút`** (request `#1..#10` hợp lệ, `#11` trả **`429`** kèm `Retry-After: 59`); admin (`teacher`, `role="admin"`) được tách nhánh sang `rate_limiter_admin` (`100 req/phút` tại `app.py` dòng 141, hoặc có thể bỏ qua bước `limiter.check()` nếu cần bypass hoàn toàn).
  - **Thứ tự các lớp bảo vệ:** `Auth (401/403)` → `Input Validation (422)` → `Rate Limit (429)` → `Cost Guard (402)` → `Gọi LLM (200)`, giúp chặn sớm request trái phép hoặc quá tải trước khi tiêu tốn chi phí gọi mô hình. Middleware `security_headers` (`app.py` dòng 75–86) tự gắn `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` và xóa header `server`.

### Exercise 4.4: Cơ chế Cost Guard & Tại sao cần cả Rate Limit lẫn Cost Guard
- **Cách triển khai trong `cost_guard.py`:**
  1. **Pre-check trước khi gọi LLM (`check_budget`, dòng 60–91):** Kiểm tra ngân sách toàn hệ thống (`global_daily_budget_usd = $10.0/ngày`, vượt → `503`), sau đó kiểm tra ngân sách từng user (`daily_budget_usd = $1.0/ngày`, vượt → `402 Payment Required`), và ghi log `WARNING` khi đạt ngưỡng `80%` (`warn_at_pct = 0.8`).
  2. **Ghi nhận chi phí sau khi LLM trả lời (`record_usage`, dòng 93–110):** Tính tiền theo giá token đầu vào (`$0.00015/1K`) và đầu ra (`$0.0006/1K`), cộng dồn vào `UsageRecord` theo ngày và `_global_cost`. Kết quả `GET /me/usage` sau 10 request là `input_tokens=24, output_tokens=292, cost_usd=0.000179, budget_remaining_usd=0.999821`.
  3. **Thiết kế chuẩn Redis khi lên production (CP5):** Vì `RateLimiter._windows` và `CostGuard._records` trong Part 4 lưu ở RAM (`dict`) nên mất khi restart và không đồng bộ khi scale nhiều worker; ở Part 6 cần chuyển sang **Redis** (`key = f"budget:{user_id}:{month_key}"` dùng `INCRBYFLOAT` + `EXPIRE` ~32 ngày để tự reset theo chu kỳ) và sửa lỗi ở `app.py` dòng 160 đang trả `usage.total_cost_usd` thay vì `budget - total_cost_usd`.
- **Vì sao cần cả Rate Limit và Cost Guard:** **Rate limit (`429`)** bảo vệ **tốc độ & khả năng chịu tải** (chống spam nhiều request/giây), còn **Cost Guard (`402`)** bảo vệ **ngân sách tiền** — một user dùng dưới 10 req/phút vẫn có thể gửi prompt rất dài gây cháy ngân sách token nếu thiếu Cost Guard.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health Check vs Readiness Check (`05-scaling-reliability/develop/app.py` & `production/app.py`)
| Endpoint | Mục đích & Hành vi | Output chạy thật / Mã HTTP |
|---|---|---|
| `GET /health` (**Liveness**) | Kiểm tra *process còn sống không*; đo `uptime_seconds` và `% RAM` qua `psutil` (`< 90%` → `"ok"`, ngược lại `"degraded"`). Trong `production/app.py` (dòng 187–205), nếu mất Redis vẫn trả HTTP **`200`** (`"status": "degraded"`, `"redis_connected": false`) để orchestrator không kill/restart oan container khi lỗi nằm ở Redis. | `200 OK` — `{"status":"ok","uptime_seconds":0.6,"version":"1.0.0","environment":"development","checks":{"memory":{"status":"ok","used_percent":11.1}}}` |
| `GET /ready` (**Readiness**) | Kiểm tra *instance sẵn sàng nhận traffic mới chưa*; trả **`503 Service Unavailable`** khi đang startup, khi `_is_ready = False` lúc shutdown, hoặc khi `_redis.ping()` thất bại (ở `production/app.py` dòng 208–215) để Load Balancer ngừng gửi request mới tới instance đó. | `200 OK` — `{"ready":true,"in_flight_requests":1}` (và `503` nếu chưa sẵn sàng / mất Redis) |

### Exercise 5.2: Graceful Shutdown khi nhận `SIGTERM` (`05-scaling-reliability/develop/app.py`)
- **Cơ chế 4 bước:** Middleware `track_requests` (dòng 72–81) đếm `_in_flight_requests`. Khi orchestrator gửi **`SIGTERM`** (khác với `SIGKILL` không thể bắt và làm đứt ngang socket):
  1. Server ngừng nhận kết nối mới và `/ready` chuyển sang `503` (`_is_ready = False`).
  2. Khối shutdown của `lifespan` (dòng 54–66) chờ `_in_flight_requests == 0` tối đa `timeout_graceful_shutdown=30` giây.
  3. Hoàn thành nốt các request đang chạy và đóng tài nguyên sạch sẽ.
  4. Thoát process với exit code `0`.
  *(Lưu ý kỹ thuật: trong `develop/app.py` dòng 186 đăng ký `signal.signal(...)` trước `uvicorn.run()` nên uvicorn vẫn cài được signal handler của chính nó khi vào event loop; khi tự cài `SIGTERM` handler ở Part 6 phải gọi tiếp handler cũ của uvicorn để không làm treo shutdown.)*
- **Test thực tế trong WSL2** (gửi 2 request `POST /ask` song song rồi gửi `kill -SIGTERM` tới PID `2710` sau `0.8s`):
  ```text
  {"answer":"Đây là câu trả lời từ AI agent (mock)..."} [req1_http=200]
  {"answer":"Tôi là AI agent được deploy lên cloud..."} [req2_http=200]
  INFO:     Shutting down
  INFO:     127.0.0.1:48572 - "POST /ask?question=hello1 HTTP/1.1" 200 OK
  INFO:     127.0.0.1:48570 - "POST /ask?question=hello2 HTTP/1.1" 200 OK
  INFO:     Waiting for application shutdown.
  2026-11-25 08:27:11,730 INFO 🔄 Graceful shutdown initiated...
  2026-11-25 08:27:10,150 INFO ✅ Shutdown complete
  INFO:     Application shutdown complete.
  INFO:     Finished server process [2710]
  2026-11-25 08:27:10,151 INFO Received signal 15 — uvicorn will handle graceful shutdown
  ```
- **Kết luận:** Cả hai request đang xử lý đều trả trọn vẹn `200 OK` trước khi server thoát an toàn.

### Exercise 5.3: Thiết kế Stateless thay thế State trong RAM (`05-scaling-reliability/production/app.py`)
- **Vấn đề của Stateful (`dict` in-memory):** Khi chạy nhiều replica phía sau Load Balancer, Turn 1 gửi vào `Instance 1` (lưu trong RAM của `Instance 1`), Turn 2 được cân bằng sang `Instance 2` → mất sạch lịch sử hội thoại.
- **Giải pháp Stateless trong `production/app.py` (dòng 59–90):** Toàn bộ session được serialize JSON và lưu tập trung trong **Redis** tại key `session:{session_id}` bằng `setex(..., ttl_seconds=3600, ...)` (giới hạn `20` tin nhắn / `10` turns gần nhất). Mọi instance đều bình đẳng, có thể scale hoặc thay thế bất kỳ lúc nào (bài học áp dụng sang Part 6 cho `rate_limiter` và `cost_guard`).

### Exercise 5.4: Chạy Stack Load Balanced với Nginx + 3 Agent Instances
```text
Client ──(:8080)──▶ Nginx (round-robin + proxy_next_upstream error timeout http_503)
                      ├──▶ k5-day14-scaling-agent-1 (:8000) ──┐
                      ├──▶ k5-day14-scaling-agent-2 (:8000) ──┼──▶ Redis (:6379)
                      └──▶ k5-day14-scaling-agent-3 (:8000) ──┘
```
- **Cơ chế Nginx (`nginx.conf`):** Dùng Docker DNS resolver `127.0.0.11`, gắn header `X-Served-By $upstream_addr`, `upstream agent_cluster` trỏ `agent:8000` (Docker Compose tự round-robin qua 3 container), và bật `proxy_next_upstream error timeout http_503; proxy_next_upstream_tries 3;` để tự động chuyển sang instance khác nếu một instance đang tắt hoặc bị lỗi.
- **Lệnh chạy theo chuẩn K5 (dùng `.env.local` và `-p k5-day14-scaling` để tách biệt tên project `production`):**
  `docker compose -p k5-day14-scaling up -d --build --scale agent=3` → chạy đủ 3 container `agent` (port nội bộ `8000`), `redis` (`6379`) và `nginx` (`0.0.0.0:8080->80`).

### Exercise 5.5: Kiểm chứng Stateless khi Scale & Hạ 1 Instance
1. **Kết quả chạy `python test_stateless.py` (5 request liên tiếp tới `http://localhost:8080/chat`):**
   ```text
   Session ID: 95701202-0268-4985-bb3f-15961745d238
   Request 1: [instance-d728a3]
   Request 2: [instance-f1a7fb]
   Request 3: [instance-d728a3]
   Request 4: [instance-1ffd80]
   Request 5: [instance-f1a7fb]
   Total requests: 5
   Instances used: {'instance-1ffd80', 'instance-d728a3', 'instance-f1a7fb'}
   ✅ All requests served despite different instances!
   Total messages: 10
   ✅ Session history preserved across all instances via Redis!
   ```
2. **Thử nghiệm `docker kill e2f312cf8b78` (hạ đột ngột 1 trong 3 container `agent` khi đang chạy):**
   - Gọi `GET /chat/95701202-0268-4985-bb3f-15961745d238/history` → vẫn còn đủ `count: 10` message từ Turn 1–5.
   - Gửi tiếp `POST /chat` (`{"question":"Still alive?","session_id":"95701202-0268-4985-bb3f-15961745d238"}`) → trả `200 OK` (`"served_by":"instance-d728a3","storage":"redis"`), chứng minh Nginx + Redis duy trì hội thoại liên tục ngay cả khi mất instance.
3. Đã tắt và dọn sạch stack (`docker compose -p k5-day14-scaling down -v`).

---

## Part 6: Final Project (`06-lab-complete/`)

### 1. Kiến trúc & các module đã hoàn thiện
- `app/config.py`: Đọc toàn bộ cấu hình theo chuẩn 12-Factor (`PORT`, `ENVIRONMENT`, `DEBUG`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD`) qua `load_dotenv(override=False)` + `os.getenv(...)`, không hard-code secret.
- `app/redis_client.py`: Khởi tạo client `redis.from_url(..., decode_responses=True, socket_connect_timeout=2.0, socket_timeout=2.0)` an toàn khi `REDIS_URL` rỗng/lỗi; hàm `redis_healthy()` dùng `ping()` cho `GET /ready` (không crash lúc khởi động nếu Redis chưa lên).
- `app/auth.py`: Sử dụng `APIKeyHeader(name="X-API-Key", auto_error=False)` và `secrets.compare_digest`; trả `HTTP 401` khi thiếu hoặc sai `X-API-Key` (và fail-closed nếu `AGENT_API_KEY` chưa cấu hình).
- `app/rate_limiter.py`: Sliding-window 60 giây trên Redis Sorted Set (`ZREMRANGEBYSCORE` -> `ZCARD` -> `ZADD` với member duy nhất `f"{now}:{uuid4}"` -> `EXPIRE 60`) theo SHA-256 prefix của API key; trả `HTTP 429` kèm header `Retry-After` động, chia sẻ state giữa `--workers 2` và sau khi restart.
- `app/cost_guard.py`: `check_budget()` kiểm tra cả ngân sách ngày (`cost:daily:YYYY-MM-DD` vs `DAILY_BUDGET_USD`) và tháng (`cost:monthly:YYYY-MM` vs `MONTHLY_BUDGET_USD`) trước khi gọi LLM (trả `HTTP 402` khi vượt); `record_cost()` tính chi phí theo `PRICE_INPUT_PER_1K` / `PRICE_OUTPUT_PER_1K` và cộng dồn bằng `INCRBYFLOAT` + `EXPIRE`.
- `app/main.py`:
  - `GET /health` -> `200` (liveness, độc lập Redis); `GET /ready` -> `200` khi Redis `ping` thành công hoặc `503` khi Redis mất kết nối.
  - `POST /ask`: nhận `{"question": "...", "user_id": "..."}` (tùy chọn `user_id`), nối tuần tự `Depends(verify_api_key)` -> `check_rate_limit` -> `check_budget` -> `llm_ask` -> `record_cost`.
  - `JsonFormatter` định dạng mọi dòng log app thành single-line JSON trên `stdout` (không log secret/key).
  - Bắt `SIGTERM` ghi log JSON rồi gọi lại handler trước đó của `uvicorn` (`_previous_sigterm`), kết hợp `lifespan` đóng kết nối Redis sạch sẽ để hoàn tất in-flight request và thoát `exit code 0`.
- Container & deploy:
  - `Dockerfile`: Multi-stage (`FROM python:3.11-slim AS builder` cài dependencies vào `/install`, `FROM python:3.11-slim AS runtime`), chạy user non-root `appuser`, `HEALTHCHECK` gọi `/health` theo `$PORT`, `CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]` giữ `uvicorn` làm PID 1.
  - `.dockerignore`: Loại trừ `.env`, `.env.*` (giữ `.env.example`), `__pycache__/`, `*.py[cod]`, `venv/`, `.venv/`, `.git/`, `*.md`, `benchmark-observability/`, giúp build context gọn chỉ ~6.9 KB.
  - `.env.example`: Liệt kê đủ biến cấu hình (giá trị placeholder, không chứa secret thật).
  - `docker-compose.yml`: Chạy `agent` + `redis:7-alpine` (`healthcheck` `redis-cli ping`, `depends_on: service_healthy`, `env_file` với `required: false`, `REDIS_URL=redis://redis:6379/0`).
  - `railway.toml` & `render.yaml`: Cấu hình Docker deploy với healthcheck `/health`, secret `AGENT_API_KEY` (`generateValue: true`) và `REDIS_URL` (`sync: false`) không hard-code.

### 2. Kết quả chạy `check_production_ready.py` (chế độ đầy đủ, có Docker)
Chạy trong WSL2 Ubuntu (`DOCKER_BUILDKIT=0 ~/day14-venv/bin/python check_production_ready.py`):
- Image size thực tế: **`238 MB`** (`< 500 MB`, build trong `42s`).
- `docker stop`: **`exit code 0, 0.9s`** (`< 10s`), in-flight request khi gửi `SIGTERM` trả `200 OK` và process tự thoát `exit code 0`.
- Rate limit với `RATE_LIMIT_PER_MINUTE=5`: chặn `429` sau `5` request thành công và **sau khi restart agent vẫn trả `429`** (state lưu trong Redis).
- Cost guard (`budget=0.000001 USD`): trả `402` ngay request đầu tiên; structured logging ghi `17 dòng JSON` hợp lệ.

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

### 3. Kiểm tra thêm `docker compose` end-to-end
- Chạy `DOCKER_BUILDKIT=0 docker compose -p k5-day14-part6 up -d --build` (không có `.env`):
  - `redis` đạt `healthy`, `agent` khởi động thành công.
  - `GET /health` -> `200` (`{"status":"healthy","environment":"development"}`).
  - `GET /ready` -> `200` (`{"status":"ready","redis":"connected"}`).
  - `POST /ask` thiếu `X-API-Key` -> `401` (fail-closed đúng thiết kế).
- Đã dọn stack sạch bằng `docker compose -p k5-day14-part6 down -v`.

---

## AI Log
- **Part 1 (CP1):**
  - *Hỏi gì:* Nhờ AI rà soát và phân tích các anti-patterns trong `01-localhost-vs-production/develop/app.py` đối chiếu với `production/app.py` và `production/config.py`.
  - *Nhận gì:* Danh sách 7 vấn đề kèm số dòng code cụ thể và bảng so sánh theo tiêu chuẩn 12-Factor App.
  - *Tự sửa & tự kiểm tra:* Tự dựng venv WSL2 (`~/day14-venv`), chạy trực tiếp cả 2 server, gọi `curl -i` kiểm tra `/ask` (query param ở `develop` và JSON ở `production`), `/health`, `/ready`, và tự ghi nhận thêm hiện tượng thực tế khi gửi `SIGTERM` tới `production/app.py` dòng 189.
- **Part 2 (CP2):**
  - *Hỏi gì:* Nhờ AI rà soát cấu trúc `02-docker/develop/Dockerfile`, multi-stage `02-docker/production/Dockerfile`, `docker-compose.yml` và `nginx.conf`.
  - *Nhận gì:* Giải thích cơ chế layer cache, phân biệt `CMD`/`ENTRYPOINT`, sơ đồ luồng Nginx -> Agent -> Redis/Qdrant và quy trình chạy dùng `-p k5-day14-docker` + `.env.local`.
  - *Tự sửa & tự kiểm tra:* Tự build thật từ gốc repo cả hai image `my-agent:develop` (`1.67 GB`) và `my-agent:advanced` (`240 MB`), chạy container và Docker Compose stack trong WSL2, đo size trực tiếp bằng `docker images` + `docker image inspect` và gọi thật `/health`, `/ask` qua Nginx trước khi dọn stack (`down -v`).
- **Part 4 (CP3):**
  - *Hỏi gì:* Nhờ AI rà soát luồng xác thực trong `04-api-gateway/develop/app.py` và bộ 3 module bảo mật (`auth.py`, `rate_limiter.py`, `cost_guard.py`) trong `04-api-gateway/production/`.
  - *Nhận gì:* Phân tích mã HTTP (`401`/`403`/`200`/`429`/`402`), thuật toán Sliding Window Counter và cơ chế chặn trước/ghi nhận sau của Cost Guard.
  - *Tự sửa & tự kiểm tra:* Tự chạy cả 2 server trên cổng `8000` trong WSL2, lấy JWT bằng tài khoản `student`/`demo123`, chạy vòng lặp 12 request chứng minh chuyển từ `200` sang `429` kèm `Retry-After`, test `/me/usage`, `/admin/stats` (`403`), che toàn bộ token JWT trước khi dán vào báo cáo, và tự phát hiện bug nhỏ ở dòng 160 `production/app.py` (`budget_remaining_usd` in nhầm `total_cost_usd`).
- **Part 5 (CP4):**
  - *Hỏi gì:* Nhờ AI đối chiếu `05-scaling-reliability/develop/app.py` và `production/app.py` về cơ chế liveness/readiness, graceful shutdown và lưu session stateless trên Redis.
  - *Nhận gì:* Sơ đồ luồng `SIGTERM` (`track_requests` + `lifespan` + `timeout_graceful_shutdown=30`) và kịch bản test scale 3 instance qua Nginx cổng `8080`.
  - *Tự sửa & tự kiểm tra:* Tự chạy bản `develop` gửi 2 request song song rồi bắn `kill -SIGTERM` để xác nhận cả 2 request trả `200 OK` trước khi thoát; tạo `.env.local`, chạy `k5-day14-scaling` scale 3 agent (`mirror.gcr.io/library/python:3.11-slim` để tránh 429 Docker Hub khi build), chạy `test_stateless.py` thấy đủ 3 `instance-*` và `10` messages, tự `docker kill` 1 container rồi test lại `/history` & `/chat` vẫn hoạt động bình thường trước khi `down -v`.
- **Part 6 (CP5):**
  - *Hỏi gì:* Nhờ AI đối chiếu các TODO trong `06-lab-complete/` (`app/*.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) với tiêu chí của `check_production_ready.py` (mà không chỉnh sửa `check_production_ready.py`).
  - *Nhận gì:* Thiết kế các module production (`Settings` qua `os.getenv`, Redis client có timeout + non-blocking startup, `APIKeyHeader` trả `401` dùng `secrets.compare_digest`, sliding-window ZSET dùng UUID tránh trùng member ở tốc độ cao, Cost Guard `DAILY_BUDGET_USD`/`MONTHLY_BUDGET_USD` trả `402`, `JsonFormatter`, nối `SIGTERM` + `exec uvicorn` làm PID 1).
  - *Tự sửa & tự kiểm tra:* Chạy `check_production_ready.py` lần lượt ở chế độ `--static-only` (`28/28` checks) rồi chế độ đầy đủ trong WSL2 Docker (`12/12 tiêu chí · 43/43 checks passed`, image `238 MB`, `docker stop` `0.9s`), tự test thêm `docker compose -p k5-day14-part6 up -d --build` xác nhận `/health` `200`, `/ready` `200`, `/ask` không key `401`, và kiểm tra `git diff` bảo đảm `check_production_ready.py` & `utils/mock_llm.py` còn nguyên vẹn.
- **Part 3 (CP6 — Render Cloud Deployment):**
  - *Hỏi gì:* Nhờ AI hướng dẫn từng bước cấu hình Render (`Key Value` Redis + `Web Service` Docker với Root Directory `06-lab-complete`), đối chiếu `06-lab-complete/railway.toml`, `render.yaml`, `03-cloud-deployment/render/render.yaml` và phân tích `03-cloud-deployment/production-cloud-run/`.
  - *Nhận gì:* Bộ 6 biến môi trường chuẩn cho Render Dashboard (không lộ secret trong repo), bảng so sánh TOML single-service vs YAML Blueprint đa service và tóm tắt 4 bước CI/CD Cloud Run.
  - *Tự sửa & tự kiểm tra:* Tự tạo `k5-day14-redis` + Web Service `Docker` trên Render đạt trạng thái `Live` tại `https://k5-l3a-day14-levanhoang-2a202603357.onrender.com`; tự kiểm chứng `/health` (`200`), `/ready` (`200`, `redis: connected`), `/ask` không key (`401`), `/ask` có key (`200`), và chạy `check_production_ready.py --public-url ...` đạt `12/12 tiêu chí · 44/44 checks passed` trước khi lưu ảnh và hoàn tất `DEPLOYMENT.md`.
- **Part 7 Bước 1 (CP7):**
  - *Hỏi gì:* Nhờ AI hướng dẫn chạy bộ benchmark local (`develop/`), viết Histogram `agent_question_length_chars` (Exercise 7.1) và xác định nguyên nhân `scaling-03`, `security-02` bị fail ở `eval_v2`.
  - *Nhận gì:* Đoạn code `Histogram` đúng chuẩn cardinality thấp, lệnh chạy `load_test.py` ở 4 mức concurrency & 3 mức `MOCK_SLOW_RATE`, và cách bổ sung `KNOWLEDGE_BASE` trong `mock_llm.py` + workflow `.github/workflows/eval.yml`.
  - *Tự sửa & tự kiểm tra:* Tự cài `prometheus-client==0.26.0` vào `~/day14-venv`, tự chạy v1 (`8001`) và v2 (`8002`) kiểm tra `/metrics`, chạy đầy đủ 7 bài `load_test.py` + 3 bài `eval/run_eval.py` (kể cả kiểm thử quality gate v1 vs v2 trả `exit code 1`), kiểm tra `eval_v2.json` trước khi sửa `KNOWLEDGE_BASE` cho cả `develop` và `production`, rồi chạy lại đạt `23/23 (100.0%)` không regression và đối chiếu từng con số từ `reports/*.json` sang `BENCHMARK_REPORT.md`.
- **Part 7 Bước 2 (CP8):**
  - *Hỏi gì:* Nhờ AI rà soát cấu trúc Docker Compose observability stack (`prometheus`, `grafana`, `jaeger`, `locust`, `nginx`), hướng dẫn unit test alert rules và kịch bản chaos 5 thí nghiệm (A–E).
  - *Nhận gì:* Cách gán cờ `--no-deps` khi chạy `locust` để Docker Compose không tự thu hồi `--scale agent=3` về `2` theo `deploy.replicas`, cú pháp API Jaeger v2 (`/api/v3/traces`), và phương án kích hoạt ≥ 2 alert firing đồng thời.
  - *Tự sửa & tự kiểm tra:* Tự phát hiện và sửa bug thiếu `ENV PYTHONUSERBASE=/home/agent/.local` trong `production/Dockerfile` khiến container non-root `agent` lỗi `No module named 'uvicorn'`; kéo các image qua `mirror.gcr.io` tránh 429 Docker Hub; chạy `promtool test rules` đạt `SUCCESS`; chạy Locust headless 2 phút cho `scale_1` và `scale_3` xuất CSV; tự đối chiếu `trace_id` giữa Jaeger v3 và `docker compose logs`; thực hiện đủ 5 bài phá hệ thống (E, C, B, A, D), chụp đủ 4 screenshot và dọn sạch stack (`down -v`) sau khi kiểm tra ảnh thật.
