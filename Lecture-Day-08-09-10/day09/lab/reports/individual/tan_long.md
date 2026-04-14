# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Tan Long  
**Vai trò trong nhóm:** Supervisor Owner + Worker Owner + MCP Owner + Trace & Docs Owner  
**Ngày nộp:** 2026-04-14

---

## 1. Tôi phụ trách phần nào?

Tôi implement toàn bộ pipeline:

- **`graph.py`**: `supervisor_node()` với keyword routing logic, `route_decision()`, graph orchestration, `make_initial_state()` với microsecond-precision `run_id`
- **`workers/retrieval.py`**: Module-level singleton pattern cho `_EMBED_FN` và `_COLLECTION` để tránh reload model mỗi query
- **`workers/policy_tool.py`**: `_call_mcp_tool()` integration, `analyze_policy()` với 3 exception types
- **`workers/synthesis.py`**: Multi-provider LLM fallback chain (OpenAI → Gemini → Anthropic → `_rule_based_synthesis()`), `_estimate_confidence()` based on chunk scores
- **`mcp_server.py`**: 4 tools đã implement (`search_kb`, `get_ticket_info`, `check_access_permission`, `create_ticket`), `dispatch_tool()` với error handling
- **`eval_trace.py`**: End-to-end eval với 15 test questions, `analyze_traces()`, `compare_single_vs_multi()`
- **Build ChromaDB index**: 80 chunks từ 5 docs với paragraph-level chunking và overlap 50 chars

Công việc kết nối: supervisor quyết định routing → workers nhận state và cập nhật → synthesis đọc `retrieved_chunks` + `policy_result` để tổng hợp. Contract tuân theo `contracts/worker_contracts.yaml`.

**Bằng chứng:** `artifacts/traces/` chứa 15 trace files từ eval run, `artifacts/eval_report.json` có comparison metrics.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Implement multi-provider LLM fallback chain trong synthesis worker thay vì chỉ dùng 1 provider

**Bối cảnh:** Lab cần LLM để tổng hợp câu trả lời nhưng không có API key nào được set trong môi trường. Nếu hardcode 1 provider và key không có → toàn bộ synthesis fail.

**Các lựa chọn thay thế:**
- Hardcode 1 provider, raise error nếu không có key
- Chỉ dùng rule-based synthesis (không LLM)
- Fallback chain: thử nhiều providers, cuối cùng fallback về rule-based

**Lý do chọn fallback chain:** Resilient — pipeline vẫn chạy được dù không có API key. Rule-based fallback extract raw text từ chunks với citations, không hallucinate. Khi có key thật, chỉ cần set env var, không cần sửa code.

**Trade-off:** Rule-based fallback không tổng hợp tự nhiên như LLM — câu trả lời là raw text blocks thay vì prose. Acceptable cho lab environment.

**Bằng chứng từ code:**

```python
# workers/synthesis.py
def _call_llm(messages: list) -> str:
    # Option A: OpenAI
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("sk-..."):
        try:
            # ... OpenAI call ...
        except Exception:
            pass
    
    # Option B: Gemini
    # Option C: Anthropic Claude
    
    # Option D: Rule-based extraction fallback
    return _rule_based_synthesis(messages)
```

Trace q01 (cold start): `final_answer` bắt đầu bằng "SLA TICKET - QUY ĐỊNH XỬ LÝ SỰ CỐ..." — text từ doc, không hallucinate.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** Trace files bị ghi đè vì `run_id` chỉ có second-level precision

**Symptom:** Sau khi chạy 15 test questions, `analyze_traces()` chỉ báo cáo 5 traces thay vì 15. Nhiều queries chạy trong cùng 1 giây → cùng `run_id` → file sau ghi đè file trước.

**Root cause:** `make_initial_state()` dùng `datetime.now().strftime('%Y%m%d_%H%M%S')` — precision chỉ đến giây. Khi queries warm cache chạy trong ~50ms, nhiều queries có cùng timestamp.

**Cách sửa:** Thêm microsecond vào format string:

```python
# Before (graph.py)
"run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",

# After
"run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
```

**Bằng chứng trước/sau:**

Trước: `analyze_traces()` báo `total_traces: 5` (sau 15 queries)

Sau: `analyze_traces()` báo `total_traces: 15` với đủ routing distribution:
```
routing_distribution:
  policy_tool_worker: 7/15 (46%)
  retrieval_worker: 8/15 (53%)
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

Module-level caching cho retrieval worker — đây là quyết định performance quan trọng nhất. Giảm latency từ 11 giây (cold) xuống 50ms (warm). Không có fix này, 15 test questions sẽ mất 165 giây chỉ cho model loading, làm eval trở nên không thực tế.

MCP integration cũng clean — `policy_tool_worker` chỉ gọi `dispatch_tool()`, không biết ChromaDB implementation. Đây đúng spirit của MCP: decoupling tool interface khỏi implementation.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Supervisor routing quá đơn giản với keyword matching. Câu q11 và q15 cho thấy với multi-hop queries, single-path routing không đủ. Nên thử implement LLM-based intent classifier, hoặc ít nhất là multi-path routing logic.

Synthesis fallback trả về raw text thay vì prose tổng hợp — nếu có LLM thật, chất lượng câu trả lời sẽ tốt hơn nhiều.

**Nhóm phụ thuộc vào tôi ở đâu?**

Là người duy nhất trong nhóm, toàn bộ pipeline phụ thuộc vào tôi. Critical path: graph.py (supervisor) phải xong trước khi có thể test workers; ChromaDB index phải có trước khi retrieval worker chạy được.

**Phần tôi phụ thuộc vào thành viên khác:**

Không có (solo). Trong nhóm thật, Worker Owner phụ thuộc vào Supervisor Owner để biết format `AgentState`, và MCP Owner phụ thuộc vào Worker Owner để biết tools nào cần thiết.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **multi-worker routing** trong supervisor vì trace của q15 cho thấy rõ limitation hiện tại: `supervisor_route='policy_tool_worker'` nhưng final_answer thiếu SLA notification info. Câu hỏi này cần cả `access_control_sop.txt` VÀ `sla_p1_2026.txt`.

Fix cụ thể: thêm route type `retrieval_then_policy` — chạy retrieval_worker trước để lấy chunks từ nhiều docs, sau đó policy_tool_worker nhận `retrieved_chunks` đã có và chỉ thực hiện exception analysis. Synthesis cuối cùng có đủ context từ cả hai sources.

---

*Lưu tại: `reports/individual/tan_long.md`*
