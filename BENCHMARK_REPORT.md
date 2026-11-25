# Benchmark & Observability Report — Day 14

> Số liệu trong báo cáo được trích xuất trực tiếp từ các file report JSON trong `reports/` (`06-lab-complete/benchmark-observability/develop/reports/`), file CSV Locust trong `benchmark-results/` và số liệu đo/ảnh chụp thực tế từ stack Observability (`screenshots/`).

**Họ tên:** Lê Văn Hoàng (`K5-L3A · 2A202603357`)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 Ubuntu (`Python 3.12.3`, `~/day14-venv`), Docker Desktop `4.100.1` (`Docker 29.9.3`)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Ngưỡng SLO mặc định của `load_test.py` (`--slo-p95-ms 500`), đảm bảo 95% request (kể cả khi `v2` có thêm bước retrieval ~20ms) trả về dưới 0,5 giây. |
| Error rate `/ask` | `< 2.0 %` | Ngưỡng mặc định của `load_test.py` (`--slo-error-rate 0.02`), chừa biên độ nhỏ cho lỗi upstream ngẫu nhiên của mock LLM (`MOCK_ERROR_RATE=0.01`). |
| Accuracy trên golden dataset | `>= 85 %` (quality gate cuối `100 %`) | Dùng `>= 85%` để chặn regression trên CI/PR (`.github/workflows/eval.yml`), và yêu cầu `--min-accuracy 1.0` (`23/23`) cho bản agent v2 hoàn chỉnh sau khi vá knowledge base. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py` + Exercise 7.1 Metrics)

### 2.0 Exercise 7.1 — Metrics & Cardinality (`develop/app.py`)
- Đã thêm Histogram `agent_question_length_chars` (`buckets=(20, 50, 100, 200, 500, 1000, 2000)`) trong `06-lab-complete/benchmark-observability/develop/app.py` và gọi `QUESTION_LENGTH.observe(len(body.question))` trước bước gọi LLM.
- Kết quả thực tế đọc từ `GET http://127.0.0.1:8002/metrics` sau câu hỏi `"Prometheus thu thập metrics như thế nào?"` (40 ký tự):
  - **Counter:** `http_requests_total{method="POST",route="/ask",status="200"} 1.0` (chỉ tăng, đếm tổng số request hoặc token `llm_tokens_total`, chi phí `llm_cost_usd_total`).
  - **Gauge:** `agent_in_flight_requests 0.0` (tăng/giảm theo số request đang xử lý đồng thời) và `agent_info{model="mock-llm-small",version="v2"} 1.0`.
  - **Histogram:** `http_request_duration_seconds_bucket{le="0.3",method="POST",route="/ask"} 1.0` và `agent_question_length_chars_bucket{le="50.0"} 1.0` (`_count 1.0`, `_sum 40.0`).
- **Vì sao label `route` dùng `route.path` thay vì `request.url.path`:** Nếu dùng URL thô (`request.url.path`), khi bot quét gọi hàng nghìn đường dẫn rác như `/wp-admin`, `/.env`, `/a1b2c3`..., mỗi chuỗi tạo ra một time series mới làm **bùng nổ cardinality**, khiến Prometheus tốn RAM quá mức, chậm truy vấn hoặc OOM. Gán tất cả URL lạ về `route="unmatched"` giữ số lượng label cố định.

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức)

Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
| 1 | 4.37 | 200.2 | 232.4 | 1692.6 | 1.00% (`3/300` 503) | PASS |
| 10 | 35.71 | 201.0 | 234.5 | 1712.3 | 1.33% (`4/300` 503) | PASS |
| 50 | 55.37 | 280.2 | 2260.2 | 3325.0 | 0.67% (`2/300` 503) | FAIL (`p95 > 500ms`) |
| 100 | 45.71 | 1172.5 | 4275.3 | 5235.1 | 0.67% (`2/300` 503) | FAIL (`p95 > 500ms`) |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency. Từ `concurrency=1` lên `10`, RPS tăng gần tuyến tính từ `4.37` lên `35.71 req/s` (`~8.2x`) trong khi `p95` hầu như không đổi (`232.4 ms -> 234.5 ms`) vì 1 process uvicorn vẫn còn dư sức xử lý I/O async. Nhưng tới `concurrency=50`, agent bắt đầu chạm ngưỡng bão hòa nên RPS chỉ tăng thêm lên `55.37 req/s` còn `p95` nhảy vọt gấp ~9.6 lần lên `2260.2 ms`; sang `concurrency=100`, nghẽn hàng đợi và tranh chấp CPU event loop trên 1 process làm RPS **tụt ngược xuống `45.71 req/s`** và `p95` vọt lên `4275.3 ms`.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) | Ghi chú SLO |
|---|---:|---:|---:|---|
| 0 | 201.0 | 252.9 | 282.9 | PASS (`error_rate=1.33%`) |
| 0.03 (mặc định) | 262.0 | 254.3 | 1723.2 | p95 PASS; lần chạy này `error_rate=2.33%` (`7/300` ngẫu nhiên) nên SLO tổng FAIL |
| 0.1 | 361.5 | 1703.2 | 1721.6 | FAIL (`p95 > 500ms`, `error_rate=0.67%`) |

**Nhận xét:** Chỉ số nhạy nhất với request chậm là **p99** (và **p95** khi tỷ lệ request chậm vượt quá `5%`). Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request chậm thêm ~1.5s), `avg` chỉ tăng nhẹ `+61.0 ms` (`201.0 -> 262.0 ms`) và `p95` vẫn `254.3 ms`, nhưng **`p99` nhảy vọt gấp 6.1 lần từ `282.9 ms` lên `1723.2 ms`**. Khi tăng lên `0.1` (`10% > 5%`), cả **`p95` cũng bật lên `1703.2 ms`** trong khi `avg` mới ở `361.5 ms` (vẫn thấp hơn ngưỡng `500 ms` nếu nhìn nhầm average!). Do đó **không bao giờ đặt SLO theo average** vì số trung bình bị làm mượt bởi 90–97% request nhanh và che giấu hoàn toàn nhóm người dùng đang phải chờ gần 2 giây; SLO phải đặt theo **p95 hoặc p99**.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---:|---:|---:|
| Accuracy | 4.3% (`1/23`) | 91.3% (`21/23`) | 100.0% (`23/23`) |
| Avg tokens / câu | 56.8 | 109.1 | 113.7 |
| Tổng cost (USD) | $0.000400 (`0.0004`) | $0.000762 | $0.000790 (`0.00079`) |
| Cost / câu đúng (USD) | $0.00039975 | $0.00003627 | $0.00003436 |
| Latency p50 / p95 (ms) | 163.1 / 195.1 | 197.1 / 215.4 | 192.5 / 226.8 |
| Quality gate | FAIL (`4.3% < 80%`) | PASS (`>= 80%`, `0` regression) | PASS (`>= 100%`, `0` regression) |

**Những câu v2 trả lời sai ban đầu và cách sửa (lấy từ `reports/eval_v2.json`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `["token", "hết hạn", "chữ ký"]` | Thêm entry `(["jwt"], ...)` giải thích khác biệt giữa API key cố định và JWT token có chữ ký số & thời điểm hết hạn vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`). |
| `scaling-03` | `["cpu", "memory", "custom metrics"]` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` giải thích Kubernetes HPA scale pod theo CPU, memory hoặc custom metrics (RPS, độ dài hàng đợi) vào `KNOWLEDGE_BASE`. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng:** v2 bổ sung bước retrieval (RAG) từ `KNOWLEDGE_BASE`, nâng accuracy từ `4.3%` (`1/23`) lên `91.3%` (`21/23`) ở bản gốc (+`87.0` điểm %, cải thiện `20` câu, `0` regression) và đạt `100.0%` (`23/23`) sau khi vá 2 tài liệu thiếu.
- **Chi phí:** Vì phải chèn ngữ cảnh vào prompt, `avg_tokens` của v2 tăng gần gấp đôi (`56.8 -> 109.1 -> 113.7` tokens/câu) và tổng cost tăng khoảng `~1.9x` (`$0.000400 -> $0.000762 -> $0.000790`). Tuy nhiên, xét theo **`cost / câu đúng`**, v2 lại **rẻ hơn ~11.0 lần** so với v1 ban đầu (`$0.00003627` vs `$0.00039975`), và giảm còn `$0.00003436` sau khi đạt `23/23` — vì ở v1 gần như toàn bộ chi phí đều bị đốt cho câu trả lời sai.
- **Latency:** Retrieval bổ sung làm `p95` của v2 tăng thêm ~`20–32 ms` (`195.1 ms` ở v1 lên `215.4 ms` / `226.8 ms` ở v2), mức đánh đổi hoàn toàn chấp nhận được để có câu trả lời đúng và vẫn thấp hơn nhiều so với SLO `500 ms`.

**Quality gate trong CI:**
- Đã thử chạy kiểm chứng quality gate với `v1` đối chiếu `--baseline reports/eval_v2.json`: `run_eval.py` phát hiện `20` câu bị regression (`4.3%` vs `91.3%`), in `Quality gate ... ❌ FAIL` và trả về **`exit code 1`**.
- Đã thiết lập workflow CI tại `.github/workflows/eval.yml`: tự động bật agent v2 trên mỗi Pull Request / Push lên `main`, chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85 --baseline reports/eval_v2.json`; nếu `accuracy < 85%` hoặc có regression thì `run_eval.py` trả `exit code 1` làm job fail và chặn merge PR.

---

## 4. Observability stack (production)

### 4.1 Screenshot & quan sát Exercise 7.4
- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png`)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png`)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png`)
- [x] Trang Alerts của Prometheus với `>= 2` alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

**Trả lời Exercise 7.4 (quan sát từ stack `--scale agent=3`):**
1. **`p95` và `avg`:** Khi `scale_3` kết thúc, Prometheus đo được `p95 = 293.1 ms` (hiển thị trên card Grafana là `293.76 ms`), còn `avg = 231.4 ms`. Khoảng cách ~`62 ms` (và vọt lên `p99 ~1.7s` trên biểu đồ theo thời gian) cho thấy phần lớn request ổn định quanh `200 ms`, nhưng một tỷ lệ nhỏ (~3%) bị kẹt ở tail latency.
2. **Chia đều tải giữa các instance:** Nginx dùng `server agent:8000 resolve` kết hợp Docker DNS, chia tải rất cân bằng cho cả 3 instance: `172.18.0.4:8000` (`20.48 req/s`), `172.18.0.8:8000` (`20.96 req/s`) và `172.18.0.9:8000` (`20.06 req/s`).
3. **Vì sao `input tokens/s` > `output tokens/s`:** Prometheus ghi nhận `input = 4714.6 tokens/s` vs `output = 2463.3 tokens/s` (gấp ~1.9 lần) vì `agent v2` phải đính kèm `SYSTEM_PROMPT` và ngữ cảnh tài liệu tìm từ RAG vào input prompt gửi cho LLM.
4. **`curl http://localhost:8080/metrics` trả về gì và vì sao:** Trả về **`404 Not Found`** vì trong `nginx/nginx.conf` (`location = /metrics { return 404; }`) đã chủ động chặn endpoint metrics ở tầng reverse proxy nhằm không lộ lưu lượng/cấu trúc nội bộ ra Internet; Prometheus trong mạng nội bộ `obs_net` mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Unit test alert & thí nghiệm "phá hệ thống" (`Exercise 7.6`)
- Unit test bằng `promtool`: chạy `docker run --rm -v "$PWD/prometheus:/p" --entrypoint promtool prom/prometheus:v3.16.0 test rules /p/alert_rules_test.yml` → **`SUCCESS`**.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`) | `pending` tại `17s` → **`firing` sau `81s`** (`20.95% > 5%`) | *Error rate* & *LLM calls theo kết quả* |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`) | `pending` tại `12s` → **`firing` sau `133s`** (`p95 = 1917.2 ms > 1s`) | *Latency /ask — p50 / p95 / p99* |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`for: 2m`) | Đang `firing` ở mức **`$2.73/giờ`** (`> $2/giờ`, kế thừa cửa sổ `[5m]` đang nóng + model large) | *Cost burn rate (USD/giờ)* & *LLM latency p95 theo model* |
| D | `docker pause k5-day14-observability-agent-1` (giữ `MOCK_ERROR_RATE=0.2`) | `AgentInstanceDown` (`for: 30s`, cùng lúc `AgentHighErrorRate` vẫn firing) | `pending` tại `12s` → **`firing` sau `41s`** (`up{instance="172.18.0.4:8000"} = 0`) | *Instances* (`1/2`) & *Requests/s theo instance* |
| E | `AGENT_VERSION=v1` | **Không có** alert nào sinh ra do giảm chất lượng | Không firing (`0` alert từ suy giảm chất lượng) | *Retrieval hit ratio* biến mất, *Tokens/s* tụt (`4714/2463` → `697/379 tok/s`), bảng *Phiên bản đang chạy* |

**Giải thích thêm bài D (`docker pause` & lỗi `504`):** `docker pause` làm container treo nhưng vẫn giữ IP trong Docker DNS, nên Prometheus scrape lỗi và đánh dấu `up == 0` (nếu dùng `docker stop`, DNS sẽ xoá container nên Prometheus bỏ qua target). Ngoài ra, khi `proxy_read_timeout 10s` ở Nginx sinh ra `504 Gateway Timeout`, request không hoàn tất bên trong agent nên metric của agent không đếm lỗi này — hệ thống thật cần theo dõi thêm access log/metric ở tầng Load Balancer và synthetic check bên ngoài.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**
- Hạ tầng (latency, HTTP status `200`, uptime) vẫn hoàn toàn xanh khi agent rơi về `v1` (accuracy tụt từ `100%` xuống `4.3%`). Trong production phải phát hiện bằng: (1) chạy **`eval/run_eval.py` làm quality gate tự động trong CI/CD** trước mọi lần deploy, (2) theo dõi metric chất lượng/RAG riêng (tỷ lệ `agent_retrieval_total{result="miss"}`, version `agent_info{version=...}`) và (3) chấm điểm mẫu traffic thật theo chu kỳ (LLM-as-judge / feedback người dùng).

### 4.3 Debug bằng trace
Chọn trace chậm nhất tìm được trong Jaeger (`screenshots/jaeger-slow-trace.png`):

- `trace_id`: `3779cd4afe9d08c0f13cc02f2f192dee`
- Tổng thời gian: **`1692.5 ms`** (`POST /ask`, hiển thị `1.7s` trên Jaeger UI)
- Breakdown các span:
  - `POST /ask`: `1692.5 ms` (`100.0%`)
  - `agent.run`: `1689.9 ms` (`99.8%`)
  - `agent.retrieve_context`: `22.6 ms` (`1.3%`)
  - **Span chiếm nhiều thời gian nhất:** **`chat mock-llm-small` (`1667.0 ms`, `98.5%`)** → nguyên nhân chậm nằm ở lời gọi LLM upstream, không phải FastAPI hay bước retrieval.
- Dòng log tương ứng (trích xuất bằng `docker compose -p k5-day14-observability logs agent | grep 3779cd4afe9d08c0f13cc02f2f192dee`):

```json
{"ts": "2026-11-25T10:00:17.689215+00:00", "level": "INFO", "service": "observable-agent", "instance": "a1f9e8da7e1c", "event": "llm_call", "trace_id": "3779cd4afe9d08c0f13cc02f2f192dee", "span_id": "36952b7dd9436c74", "request_id": "c999269deec7", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1666.9}
```

- **Trace lỗi đi kèm (`screenshots/jaeger-error-trace.png`):** `trace_id = c20867f523872856b20c5714a809c1cb` (`108.7 ms`, HTTP `503`), span `agent.run` / `chat mock-llm-small` ghi event `exception: Upstream LLM error: 503 Service Unavailable (mock)`, khớp với log JSON:

```json
{"ts": "2026-11-25T10:00:13.498915+00:00", "level": "INFO", "service": "observable-agent", "instance": "a1f9e8da7e1c", "event": "llm_error", "trace_id": "c20867f523872856b20c5714a809c1cb", "span_id": "e46aea53508b35d7", "request_id": "7833f7fe18f9", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn dữ liệu: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`.

| Số instance | Chỉ số (CSV) | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---:|---|---:|---:|---:|---:|---|
| 1 | `POST /ask` | 62.87 | 200 | 270 | 1700 | `71 / 7067` (`1.00%`) |
| 1 | `Aggregated` (`/ask` + `/health`) | 69.01 | 190 | 260 | 1700 | `71 / 7757` (`0.92%`) |
| 3 | `POST /ask` | 63.32 | 190 | 230 | 1700 | `76 / 7168` (`1.06%`) |
| 3 | `Aggregated` (`/ask` + `/health`) | 69.36 | 190 | 230 | 1700 | `76 / 7851` (`0.97%`) |

**Giải thích kết quả:** Khi scale từ 1 lên 3 instance, Nginx chia tải gần như đều (~`20–21 req/s` mỗi instance) và giúp `p95` của `/ask` giảm nhẹ từ **`270 ms` xuống `230 ms`** (giảm tranh chấp chờ tại một container), nhưng **RPS (~`63 req/s`) và `p99` (`1700 ms`) gần như giữ nguyên**. Nguyên nhân gồm 2 điểm:
1. **Nút thắt độ trễ nằm ở LLM upstream (`chat mock-llm-small`), không phải CPU của agent:** mỗi lần gọi LLM mất ~`120–180 ms` (và 3% bị slow thêm `1.5s`), thời gian này chiếm ~`98.5%` tổng thời gian request nên thêm replica agent không thể làm model LLM trả lời nhanh hơn.
2. **Mức tải sinh ra bị giới hạn bởi `wait_time = between(0.5, 2)`:** 100 Locust user nghỉ trung bình `1.25s` sau mỗi request nên chỉ tạo ra tổng ~`69 req/s`, mức mà một container FastAPI async đã gánh được vì phần lớn thời gian chỉ `await asyncio.sleep(...)`.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Tail latency & Percentile:** Số `average` dễ gây ảo giác an toàn (thí nghiệm `MOCK_SLOW_RATE=0.1` cho `avg=361.5 ms` nhưng `p95=1703.2 ms`), nên SLO phải đặt theo `p95`/`p99`.
  2. **Chất lượng không hiện trên metric hạ tầng:** Một agent lỗi logic hoặc quay về `v1` vẫn trả HTTP `200` cực nhanh nhưng accuracy tụt còn `4.3%`; cần kết hợp eval trên `golden_dataset.jsonl` + quality gate trong CI + theo dõi metric `cost / câu đúng`.
  3. **Liên kết Metrics → Traces → Logs:** Prometheus báo hiệu bất thường theo cụm/SLO, Jaeger chỉ chính xác span chậm (`chat mock-llm-small` chiếm `98.5%`), và `trace_id` nối thẳng sang dòng log JSON tương ứng.
- **Nếu đưa agent này lên production thật, sẽ thêm các metric / alert sau:**
  - *Time to First Token (TTFT)* cho streaming response và *Tokens Per Second (TPS)* ở tầng LLM.
  - Metric HTTP status (`502`/`504`/`429`) thu thập trực tiếp từ **Nginx/API Gateway ingress** kết hợp Synthetic Health Probe từ bên ngoài (tránh điểm mù như lỗi 504 ở bài D).
  - Alert theo dõi **tỷ lệ retrieval miss** (`agent_retrieval_total{result="miss"}`) và chất lượng/hallucination sampling định kỳ (LLM-as-judge) để bắt suy giảm chất lượng sớm.
