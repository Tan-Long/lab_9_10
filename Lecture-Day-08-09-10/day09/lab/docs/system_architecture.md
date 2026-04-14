# System Architecture — Lab Day 09

**Nhóm:** Tan Long  
**Ngày:** 2026-04-14  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

**Pattern đã chọn:** Supervisor-Worker  
**Lý do chọn pattern này (thay vì single agent):**

RAG pipeline Day 08 là một monolith xử lý tất cả mọi thứ trong một hàm (retrieve → generate), khiến việc debug khó khăn khi pipeline trả lời sai. Supervisor-Worker tách rõ trách nhiệm: Supervisor quyết định routing, mỗi Worker chỉ làm một nhiệm vụ cụ thể, cho phép test từng phần độc lập và mở rộng dễ dàng qua MCP.

---

## 2. Sơ đồ Pipeline

```
User Request (task)
        │
        ▼
┌──────────────────────┐
│      Supervisor      │  → phân tích keywords, quyết định route
│    (graph.py)        │  → set: supervisor_route, route_reason,
│                      │         risk_high, needs_tool
└──────────┬───────────┘
           │
     [route_decision]
           │
    ┌──────┴──────────────────┬──────────────┐
    │                         │              │
    ▼                         ▼              ▼
Retrieval Worker      Policy Tool Worker   Human Review
(workers/retrieval)   (workers/policy_tool)  (HITL node)
• Dense search        • Exception detect   • Log + auto-
• ChromaDB query      • MCP tool calls       approve in lab
• Top-k chunks        • search_kb          • Then → retrieval
                      • get_ticket_info    │
    │                         │            │
    └─────────┬───────────────┘────────────┘
              │
              ▼
       Synthesis Worker
       (workers/synthesis)
       • Build context from chunks
       • Call LLM (OpenAI/Gemini/Claude/fallback)
       • Add citations [source.txt]
       • Estimate confidence
              │
              ▼
         Final Output
   (final_answer, sources, confidence, trace)
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích task keywords, quyết định route sang worker nào, đánh giá risk |
| **Input** | `task`: câu hỏi từ user |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Keyword matching: policy/access keywords → policy_tool_worker; SLA/ticket keywords → retrieval_worker; ERR-xxx + risk → human_review; default → retrieval_worker |
| **HITL condition** | `risk_high=True` AND regex match `err-\d+` (unknown error codes) |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Dense semantic search trong ChromaDB, trả về top-k chunks có liên quan nhất |
| **Embedding model** | `all-MiniLM-L6-v2` (Sentence Transformers, offline) |
| **Top-k** | 3 (cấu hình qua `RETRIEVAL_TOP_K` env var) |
| **Stateless?** | Yes — chỉ đọc `task` và ghi `retrieved_chunks`, `retrieved_sources` |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Kiểm tra policy exceptions, gọi MCP tools lấy context nếu chưa có chunks |
| **MCP tools gọi** | `search_kb` (lấy chunks khi chưa có), `get_ticket_info` (khi task có P1/ticket/jira) |
| **Exception cases xử lý** | flash_sale_exception, digital_product_exception, activated_exception, temporal_scoping (đơn trước 01/02/2026) |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | OpenAI gpt-4o-mini → Gemini gemini-1.5-flash → Anthropic claude-haiku → rule-based fallback |
| **Temperature** | 0.1 (low — grounded answers) |
| **Grounding strategy** | Chỉ trả lời từ context được cung cấp. Nếu không có evidence → abstain |
| **Abstain condition** | `retrieved_chunks=[]` → trả về "Không đủ thông tin trong tài liệu nội bộ" |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query`, `top_k` | `chunks`, `sources`, `total_found` |
| `get_ticket_info` | `ticket_id` | ticket details (priority, status, assignee, SLA deadline) |
| `check_access_permission` | `access_level`, `requester_role`, `is_emergency` | `can_grant`, `required_approvers`, `emergency_override` |
| `create_ticket` | `priority`, `title`, `description` | `ticket_id`, `url`, `created_at` |

---

## 4. Shared State Schema

| Field | Type | Mô tả | Ai đọc/ghi |
|-------|------|-------|-----------|
| `task` | str | Câu hỏi đầu vào | supervisor đọc |
| `supervisor_route` | str | Worker được chọn (`retrieval_worker`/`policy_tool_worker`/`human_review`) | supervisor ghi |
| `route_reason` | str | Lý do route cụ thể (keyword matched) | supervisor ghi |
| `risk_high` | bool | True khi có risk keyword hoặc unknown error code | supervisor ghi |
| `needs_tool` | bool | True khi supervisor quyết định cần MCP | supervisor ghi |
| `hitl_triggered` | bool | True khi HITL node được kích hoạt | human_review ghi |
| `retrieved_chunks` | list | Evidence chunks từ retrieval | retrieval_worker ghi, synthesis đọc |
| `retrieved_sources` | list | Unique source filenames | retrieval_worker ghi |
| `policy_result` | dict | `policy_applies`, `exceptions_found`, `policy_name` | policy_tool ghi, synthesis đọc |
| `mcp_tools_used` | list | Danh sách MCP tool calls với input/output/timestamp | policy_tool ghi |
| `final_answer` | str | Câu trả lời tổng hợp có citation | synthesis ghi |
| `sources` | list | Sources được cite | synthesis ghi |
| `confidence` | float | Mức tin cậy 0.0–1.0 | synthesis ghi |
| `workers_called` | list | Danh sách workers đã được gọi theo thứ tự | mỗi worker ghi |
| `history` | list | Log từng bước pipeline | mỗi node ghi |
| `latency_ms` | int | Tổng thời gian xử lý (ms) | graph ghi |
| `run_id` | str | Unique ID với microsecond precision | make_initial_state |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Khó — không rõ lỗi ở đâu | Dễ hơn — xem trace `supervisor_route + route_reason` |
| Thêm capability mới | Phải sửa toàn prompt | Thêm MCP tool trong `mcp_server.py`, không đụng core |
| Routing visibility | Không có | Có `route_reason` trong mỗi trace file |
| Test từng phần | Không thể | Mỗi worker có `if __name__ == "__main__"` test độc lập |
| Risk handling | Không có | `risk_high` flag + HITL node tách biệt |

**Quan sát thực tế từ lab:**

- Routing bằng keyword matching hoạt động tốt cho phần lớn câu hỏi (14/15). Câu q09 (ERR-403-AUTH) được detect đúng là risky → HITL triggered.
- Module-level caching cho SentenceTransformer và ChromaDB collection giảm latency từ ~11 giây (cold start) xuống ~50ms (warm).
- MCP interface cho phép policy_tool_worker thêm context mà không cần biết ChromaDB implementation details.

---

## 6. Giới hạn và điểm cần cải tiến

1. **Keyword routing fragile**: Routing hiện tại dùng keyword matching — có thể sai với paraphrase hoặc câu hỏi mơ hồ. Nên thay bằng LLM-based intent classifier.
2. **Synthesis không có LLM**: Trong môi trường không có API key, synthesis dùng rule-based extraction — câu trả lời không được tổng hợp tự nhiên mà trích dẫn raw text từ docs.
3. **Policy worker không gọi retrieval trước**: Khi `needs_tool=True` nhưng không có `retrieved_chunks`, policy worker gọi MCP `search_kb` — nhưng không luôn tìm đúng tài liệu. Nên chạy retrieval_worker trước, rồi mới chạy policy_tool_worker.
