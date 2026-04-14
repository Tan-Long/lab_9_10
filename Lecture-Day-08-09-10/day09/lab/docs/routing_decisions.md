# Routing Decisions Log — Lab Day 09

**Nhóm:** Tan Long  
**Ngày:** 2026-04-14

> Dữ liệu lấy từ trace thực tế trong `artifacts/traces/` — 15 câu hỏi đã chạy.

---

## Routing Decision #1

**Task đầu vào:**
> "SLA xử lý ticket P1 là bao lâu?"

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `task contains SLA/ticket keyword(s): ['p1', 'sla', 'ticket']`  
**MCP tools được gọi:** None  
**Workers called sequence:** `['retrieval_worker', 'synthesis_worker']`

**Kết quả thực tế:**
- final_answer: Trả về nội dung từ `sla_p1_2026.txt` — bao gồm thời gian phản hồi và xử lý
- confidence: 0.62
- Correct routing? **Yes** — câu hỏi về SLA/ticket đúng là cần retrieval từ KB

**Nhận xét:** Routing đúng. Keyword matching phát hiện "p1", "sla", "ticket" và route sang retrieval_worker. MCP không cần vì retrieval đơn giản. Confidence 0.62 là hợp lý vì answer trích dẫn từ đầu doc (header, không phải nội dung cụ thể nhất).

---

## Routing Decision #2

**Task đầu vào:**
> "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task contains policy/access keyword(s): ['hoàn tiền', 'flash sale']`  
**MCP tools được gọi:** `search_kb`  
**Workers called sequence:** `['policy_tool_worker', 'synthesis_worker']`

**Kết quả thực tế:**
- final_answer: Nêu exception "Flash Sale không được hoàn tiền (Điều 3, chính sách v4)" — chính xác
- confidence: 0.67
- Correct routing? **Yes** — câu hỏi về policy/exception cần policy_tool_worker

**Nhận xét:** Routing và exception detection đúng. Policy worker phát hiện `flash_sale_exception` từ keyword analysis. MCP `search_kb` được gọi để lấy context (chunks chưa có khi vào policy_tool). Đây là ví dụ tốt về MCP mang lại giá trị — worker không cần biết ChromaDB details.

---

## Routing Decision #3

**Task đầu vào:**
> "ERR-403-AUTH là lỗi gì và cách xử lý?"

**Worker được chọn:** `human_review` → sau đó `retrieval_worker`  
**Route reason (từ trace):** `unknown error code + risk_high → human review | human approved → retrieval`  
**MCP tools được gọi:** None  
**Workers called sequence:** `['human_review', 'retrieval_worker', 'synthesis_worker']`

**Kết quả thực tế:**
- final_answer: Không tìm thấy thông tin chính xác về ERR-403-AUTH (retrieves SLA ticket docs thay vì helpdesk FAQ)
- confidence: 0.44 (thấp nhất trong 15 câu)
- Correct routing? **Partially** — HITL trigger là đúng (câu hỏi không có answer trong docs), nhưng sau khi human approve vẫn route retrieval và trả về kết quả không liên quan

**Nhận xét:** HITL trigger đúng — regex `err-\d+` phát hiện `ERR-403` và flag `risk_high`. Tuy nhiên sau khi auto-approve, retrieval không tìm được answer vì không có doc về ERR-403-AUTH. Đây là case cần abstain rõ ràng hơn: confidence 0.44 < threshold 0.5 → có thể set `hitl_triggered=True` ở synthesis layer để báo cần human escalation thực sự.

---

## Routing Decision #4

**Task đầu vào:**
> "Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình."

**Worker được chọn:** `policy_tool_worker`  
**Route reason:** `task contains policy/access keyword(s): ['level 2', 'access'] | risk_high flagged: ['2am', 'khẩn cấp']`

**Nhận xét: Đây là trường hợp routing khó nhất trong lab. Tại sao?**

Câu hỏi này cần **cả hai** workers — vừa cần policy (Level 2 emergency bypass) vừa cần SLA info (notification channels). Supervisor chỉ route sang một worker (`policy_tool_worker`) vì policy keywords (`level 2`, `access`) xuất hiện trước SLA keywords trong logic. Kết quả là câu trả lời thiếu thông tin SLA notification.

Đây cho thấy giới hạn của keyword routing single-path: với multi-hop queries cần multiple workers, cần thiết kế supervisor có khả năng route sang nhiều workers tuần tự hoặc song song. Giải pháp: thêm logic "nếu task có cả policy_keywords VÀ sla_keywords → gọi cả hai workers trước synthesis".

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 8 | 53% |
| policy_tool_worker | 7 | 47% |
| human_review | 1 (→ retrieval) | 7% |

### Routing Accuracy

- Câu route đúng: **13 / 15** (86.7%)
- Câu route sai/partial:
  - q09 (ERR-403-AUTH): HITL đúng nhưng sau đó vẫn không có answer → nên abstain
  - q15 (multi-hop P1 + Level 2): Chỉ route 1 worker, thiếu SLA context
- Câu trigger HITL: 1 (q09)

### Lesson Learned về Routing

1. **Keyword matching đủ tốt cho most cases (13/15)** nhưng fragile với paraphrase và multi-hop queries. Bước tiếp theo: dùng LLM classifier để detect intent thay vì hard-code keywords.
2. **Routing nên hỗ trợ multi-worker paths** — hiện tại supervisor chọn một worker duy nhất. Với câu hỏi cross-domain, cần thêm route type `both_workers` để gọi retrieval + policy song song.

### Route Reason Quality

Nhìn lại trace: `route_reason` đủ thông tin để debug — nêu rõ keyword nào match, worker nào được chọn. Ví dụ:
- `"task contains policy/access keyword(s): ['hoàn tiền', 'flash sale']"` — rõ ràng
- `"task contains SLA/ticket keyword(s): ['p1', 'sla', 'ticket']"` — rõ ràng

Cải tiến đề xuất: thêm confidence score của routing decision vào `route_reason` để biết khi nào routing "chắc chắn" vs "uncertain". Ví dụ: `"policy keywords matched (3/7 threshold) → policy_tool_worker [routing_conf=0.9]"`.
