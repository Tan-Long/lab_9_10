# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** Tan Long  
**Ngày:** 2026-04-14

> Số liệu Day 09 lấy từ `artifacts/traces/` (15 câu). Day 08 là ước tính từ kiến trúc (không có eval thực tế do cùng docs set).

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | ~0.70 (estimate) | **0.653** | -0.047 | Day 09 thấp hơn nhẹ do không có LLM synthesis |
| Avg latency (ms) | ~500ms | **795ms** | +295ms | Overhead từ multiple worker calls |
| Abstain rate (%) | ~10% | **6.7%** (1/15) | -3.3% | HITL trigger thay thế abstain |
| Multi-hop accuracy | ~40% (estimate) | **~60%** | +20% | Day 09 route tốt hơn với policy + SLA queries |
| Routing visibility | ✗ Không có | ✓ `route_reason` mỗi query | N/A | Key advantage |
| Debug time (estimate) | ~20 phút | ~5 phút | -15 phút | Nhờ trace + worker isolation |
| MCP tool usage | N/A | 7/15 (47%) | N/A | Policy worker tự động gọi MCP |

> **Day 08 estimates**: Dựa trên kiến trúc single-pipeline không có routing trace.

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | ~80% | ~80% |
| Latency | ~300ms | ~50ms (warm) |
| Observation | Đơn giản, pipeline thẳng | Overhead supervisor + 2 workers nhưng warm cache nhanh |

**Kết luận:** Multi-agent không cải thiện accuracy cho simple queries, nhưng sau khi model warm (lần 2 trở đi) latency tương đương. Overhead chủ yếu từ cold start (load SentenceTransformer lần đầu: ~11 giây).

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | ~40% (estimate) | ~60% |
| Routing visible? | ✗ | ✓ |
| Observation | Không biết retrieval hay generation sai | Trace cho thấy chính xác worker nào fail |

**Kết luận:** Multi-agent cải thiện multi-hop vì supervisor có thể route đúng worker type. Ví dụ q13 (Admin Access + P1) và q15 (Level 2 + P1 notifications) được route sang policy_tool_worker với MCP — Day 08 không có routing strategy, phụ thuộc vào LLM tự xử lý toàn bộ.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | ~10% | 6.7% (HITL 1/15) |
| Hallucination cases | Có thể có (không có trace) | Minimal — synthesis chỉ dùng context |
| Observation | Không rõ khi nào model hallucinate | Confidence < 0.5 visible trong trace |

**Kết luận:** Day 09 abstain tốt hơn nhờ confidence score rõ ràng. q09 (ERR-403-AUTH) trigger HITL đúng — Day 08 có thể hallucinate câu trả lời không có trong docs.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```
Khi answer sai → phải đọc toàn bộ RAG pipeline code
→ Không biết lỗi ở indexing, retrieval, hay generation
→ Không có trace để biết document nào được retrieved
→ Thời gian ước tính: 20–30 phút
```

### Day 09 — Debug workflow
```
Khi answer sai → đọc trace (artifacts/traces/run_xxx.json)
  → Xem supervisor_route: routing có đúng không?
  → Xem retrieved_sources: document nào được dùng?
  → Xem mcp_tools_used: MCP có trả về kết quả đúng không?
  → Nếu route sai → sửa supervisor routing logic (graph.py)
  → Nếu retrieval sai → test: python workers/retrieval.py
  → Nếu synthesis sai → test: python workers/synthesis.py
Thời gian ước tính: 5–10 phút
```

**Case debug thực tế trong lab:**

q11 ("Ticket P1 tạo lúc 22:47...") trả về answer không liên quan (câu về hộp thư đầy). Debug qua trace: `retrieved_sources=['it_helpdesk_faq.txt']` thay vì `sla_p1_2026.txt`. Nguyên nhân: embedding model trả về FAQ doc cao hơn SLA doc cho query này. Fix: tăng `top_k=5` hoặc dùng reranker. Không cần đụng vào policy_tool hay synthesis — isolation giúp pinpoint ngay retrieval.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa toàn prompt + re-test end-to-end | Thêm tool trong `mcp_server.py` + route rule trong supervisor |
| Thêm 1 domain mới (VD: Legal) | Phải redesign prompt với nhiều domains | Thêm `workers/legal.py` + route keyword `["hợp đồng", "pháp lý"]` |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline | Sửa `workers/retrieval.py` độc lập, không ảnh hưởng policy/synthesis |
| A/B test một phần | Phải clone toàn pipeline | Swap `retrieval_worker` với `retrieval_worker_v2` trong `graph.py` |

**Nhận xét:**

Day 09 extensible hơn đáng kể. Trong lab này, thêm 2 MCP tools mới (`check_access_permission`, `create_ticket`) chỉ cần ~30 dòng code trong `mcp_server.py` — không đụng vào supervisor hay synthesis.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 calls | Day 09 calls |
|---------|-------------|-------------|
| Simple query | 1 LLM call | 1 LLM call (synthesis) |
| Complex query (policy) | 1 LLM call | 1 LLM call + 1-2 MCP tool calls |
| Multi-hop | 1 LLM call | 1 LLM call + 1-2 MCP calls |
| HITL trigger | N/A | 0 LLM calls (log + pause) |

**Nhận xét về cost-benefit:**

Day 09 có cùng số LLM calls với Day 08 cho simple queries. Overhead chủ yếu từ MCP tool calls (mock Python calls — không tốn tiền). Với real MCP HTTP server, overhead ~10-50ms. Benefit: routing visibility + debuggability + extensibility rõ ràng vượt trội overhead nhỏ này.

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở điểm nào?**

1. **Debuggability**: Trace file cho phép pinpoint lỗi trong <5 phút thay vì đọc toàn bộ code (~20-30 phút). Mỗi worker có standalone test script.
2. **Routing visibility**: `supervisor_route + route_reason` trong mỗi trace giúp hiểu tại sao hệ thống trả lời như vậy — không có black box.
3. **Extensibility**: Thêm capability mới (tool, domain, worker) mà không cần sửa core pipeline.

**Multi-agent kém hơn hoặc không khác biệt ở điểm nào?**

1. **Cold start latency**: Model loading lần đầu ~11 giây. Single agent cũng gặp vấn đề này nhưng không có thêm overhead từ multiple worker calls.
2. **Single-document simple queries**: Không cải thiện accuracy — cả hai approach đều retrieve đúng tài liệu cho easy questions.

**Khi nào KHÔNG nên dùng multi-agent?**

- Khi latency là critical và queries đều đơn giản (chỉ cần 1 doc, 1 LLM call)
- Khi team nhỏ và complexity của multi-agent không justified
- Khi không có monitoring/tracing infrastructure để khai thác lợi ích của routing visibility

**Nếu tiếp tục phát triển hệ thống này, nhóm sẽ thêm gì?**

1. **LLM-based supervisor**: Thay keyword matching bằng Claude/GPT để classify intent chính xác hơn, đặc biệt với paraphrase
2. **Multi-worker paths**: Cho phép supervisor route sang cả `retrieval_worker` VÀ `policy_tool_worker` cho multi-hop queries
3. **Reranker**: Thêm cross-encoder reranker sau retrieval để cải thiện relevance, đặc biệt cho câu hỏi về thời gian cụ thể (q11)
