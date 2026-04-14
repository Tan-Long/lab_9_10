# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** Tan Long  
**Thành viên:**
| Tên | Vai trò | Email |
|-----|---------|-------|
| Tan Long | Supervisor Owner + Worker Owner + MCP Owner + Trace & Docs Owner | — |

**Ngày nộp:** 2026-04-14  
**Repo:** Lecture-Day-08-09-10/day09/lab  

---

## 1. Kiến trúc nhóm đã xây dựng

**Hệ thống tổng quan:**

Hệ thống Day 09 implement Supervisor-Worker pattern với 3 workers chuyên biệt. Supervisor (`graph.py`) nhận câu hỏi, phân tích keywords và route sang một trong ba path: `retrieval_worker` (tìm evidence từ ChromaDB), `policy_tool_worker` (kiểm tra policy + gọi MCP tools), hoặc `human_review` (HITL cho unknown error codes). Sau đó, `synthesis_worker` tổng hợp câu trả lời có citation từ chunks và policy result. Toàn bộ pipeline lưu trace JSON với đủ fields bắt buộc.

Kết quả: 15/15 test questions chạy thành công, avg confidence 0.653, avg latency 795ms (warm cache ~50ms, cold start ~11 giây do model loading).

**Routing logic cốt lõi:**

Supervisor dùng keyword matching (không gọi LLM) — nhanh ~5ms. Keyword sets:
- Policy keywords (`hoàn tiền`, `refund`, `flash sale`, `license`, `cấp quyền`, `access`, `store credit`) → `policy_tool_worker`
- SLA keywords (`p1`, `sla`, `ticket`, `escalation`, `sự cố`) → `retrieval_worker`
- Error code regex `err-\d+` + risk keywords → `human_review`
- Default → `retrieval_worker`

**MCP tools đã tích hợp:**

- `search_kb`: Tìm kiếm Knowledge Base qua ChromaDB. Được gọi bởi `policy_tool_worker` khi `needs_tool=True` và chưa có retrieved_chunks.
- `get_ticket_info`: Tra cứu mock ticket database. Gọi khi task chứa "ticket", "p1", "jira". Ví dụ trace q15: `mcp_tools_used=['search_kb', 'get_ticket_info']`.
- `check_access_permission`: Kiểm tra điều kiện cấp quyền theo SOP, có logic emergency bypass cho Level 2.
- `create_ticket`: Tạo mock ticket với ID tự sinh.

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** Module-level caching cho SentenceTransformer và ChromaDB client

**Bối cảnh vấn đề:**

Khi chạy graph.py với 3 test queries, mỗi query mất ~11 giây vì SentenceTransformer model được reload từ disk. Đây là vấn đề nghiêm trọng vì 15 test questions sẽ mất ~165 giây chỉ cho model loading.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Reload model mỗi query (default) | Simple code | 11 giây/query — không chấp nhận được |
| Module-level global variable | Load 1 lần, O(1) lookup sau đó | Cần thread-safe cho multi-process |
| LRU cache với functools | Pythonico | Overhead không cần thiết cho 1 model |

**Phương án đã chọn và lý do:**

Module-level globals `_EMBED_FN` và `_COLLECTION` trong `workers/retrieval.py`. Load 1 lần per process, không cần re-initialize. Đủ cho lab (single-process) và production cần thêm lock cho thread-safety.

**Bằng chứng từ trace/code:**

```python
# workers/retrieval.py
_EMBED_FN = None
_COLLECTION = None

def _get_embedding_fn():
    global _EMBED_FN
    if _EMBED_FN is not None:
        return _EMBED_FN
    # ... load model once ...
    _EMBED_FN = embed
    return _EMBED_FN
```

Kết quả: latency giảm từ 11.390ms (q01 cold) xuống 45ms (q02 warm) — giảm 253x.

---

## 3. Kết quả test questions

**Tổng kết 15 test questions:** 15/15 succeeded

**Câu pipeline xử lý tốt nhất:**
- q06: "Ticket P1 không được phản hồi sau 10 phút" → conf=0.77, latency=98ms, route=retrieval_worker đúng
- q12: Temporal scoping refund — phát hiện đúng "trước 01/02/2026" → flag temporal edge case

**Câu pipeline fail hoặc partial:**
- q09 (ERR-403-AUTH): HITL trigger đúng nhưng sau approve, retrieval trả về SLA docs thay vì helpdesk FAQ. Root cause: embedding similarity của "ERR-403-AUTH" cao nhất với SLA docs do chứa nhiều mã lỗi-like patterns.
- q11 ("Ticket P1 tạo lúc 22:47"): Retrieved `it_helpdesk_faq.txt` thay vì `sla_p1_2026.txt`. Root cause: query về "ai nhận thông báo" match FAQ docs cao hơn SLA docs.
- q15 (multi-hop): Policy route đúng nhưng SLA notification info bị thiếu vì chỉ route 1 worker.

**Câu abstain (q09):** Pipeline trigger HITL (confidence=0.44) — hoạt động đúng như thiết kế. Sau auto-approve, trả về kết quả liên quan SLA tickets, không hallucinate về ERR-403-AUTH.

---

## 4. So sánh Day 08 vs Day 09

**Metric thay đổi rõ nhất:**

Debuggability: Day 08 không có trace → khi answer sai cần đọc toàn bộ code (~20-30 phút). Day 09 có trace JSON với `supervisor_route`, `retrieved_sources`, `mcp_tools_used` → pinpoint lỗi trong <5 phút. Ví dụ q11: đọc trace thấy ngay `retrieved_sources=['it_helpdesk_faq.txt']` thay vì SLA doc.

**Điều bất ngờ nhất khi chuyển từ single sang multi-agent:**

Cold start latency là bottleneck chính — không phải architecture overhead. SentenceTransformer load lần đầu 11 giây dù có 3 workers. Sau khi fix với module-level caching, latency warm cache chỉ ~50ms — nhanh hơn nhiều so với dự kiến.

**Trường hợp multi-agent không giúp hoặc làm chậm:**

Simple queries (q04, q05, q14) — retrieval 1 document, không cần routing decision. Single agent pipeline cho đây kết quả tương đương nhưng ít code hơn. Multi-agent overhead justified khi có routing phức tạp hoặc cần MCP tools.

---

## 5. Phân công và đánh giá nhóm

**Phân công thực tế:**

| Thành viên | Phần đã làm | Sprint |
|------------|-------------|--------|
| Tan Long | graph.py (supervisor + routing logic) | Sprint 1 |
| Tan Long | workers/retrieval.py (module-level caching) | Sprint 2 |
| Tan Long | workers/policy_tool.py (MCP integration) | Sprint 2+3 |
| Tan Long | workers/synthesis.py (multi-LLM fallback chain) | Sprint 2 |
| Tan Long | mcp_server.py (4 tools), eval_trace.py (15 questions), docs, reports | Sprint 3+4 |

**Điều làm tốt:**

- Module-level caching fix giảm latency 253x
- 15/15 questions chạy không lỗi end-to-end
- Trace format đầy đủ tất cả required fields
- MCP integration clean — policy_tool không cần biết ChromaDB details

**Điều làm chưa tốt:**

- Synthesis không có LLM thật → answer là raw text từ docs, không được tổng hợp tự nhiên
- Supervisor single-path routing không handle multi-hop queries tốt (q15)
- Routing accuracy 86.7% (13/15) — 2 câu partial

**Nếu làm lại:**

Implement LLM-based supervisor để handle multi-hop routing (route sang nhiều workers tuần tự). Quyết định này sẽ giải quyết 2 câu fail (q11, q15).

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

Thêm **multi-worker routing** vào supervisor: khi task chứa cả policy keywords VÀ SLA keywords, tạo route type `both_workers` → chạy retrieval_worker trước, sau đó policy_tool_worker nhận retrieved_chunks từ đó, cuối cùng synthesis tổng hợp từ cả hai outputs.

Bằng chứng từ trace: q15 (`supervisor_route='policy_tool_worker'`) trả về Level 2 access info nhưng thiếu SLA notification channels. Câu này cần cả `sla_p1_2026.txt` VÀ `access_control_sop.txt` — single-path routing hiện tại không đáp ứng được.

---

*File này lưu tại: `reports/group_report.md`*
