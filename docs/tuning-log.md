# Tuning Log — RAG Pipeline (Day 08 Lab)

Ghi lại các thử nghiệm, kết quả và nhận xét qua từng Sprint.

---

## Baseline (Sprint 2)

**Ngày:** 2026-04-13  
**Config:**
```
retrieval_mode = "dense"
chunk_size = 400 characters (approx 100 tokens)
overlap = 80 characters
top_k_search = 10
top_k_select = 3
use_rerank = False
llm_model = gpt-4o-mini / gemini-3-flash
```

**Scorecard Baseline (Average):**
| Metric | Average Score |
|--------|--------------|
| Faithfulness | 3.8/5 |
| Answer Relevance | 4.1/5 |
| Context Recall | 4.5/5 |
| Completeness | 3.6/5 |

**Câu hỏi yếu nhất (điểm thấp):**
- **q09 (Insufficient Context)**: Điểm thấp (1/5) do model cố gắng trả lời thay vì từ chối mạnh mẽ khi chỉ dùng Dense search.
- **q10 (Refund VIP)**: Điểm thấp do thiếu dữ liệu cụ thể về khách hàng VIP, dẫn đến model bối rối.

**Giả thuyết nguyên nhân (Error Tree):**
- [x] Retrieval: Dense bỏ lỡ exact keyword / alias cho các truy vấn mang tính lọc tài liệu (như "Hoàn tiền").
- [x] Generation: Prompt grounding tốt nhưng đôi khi bị nhiễu bởi các chunk tương tự nhưng không liên quan.

---

## Variant 1 (Sprint 3: Hybrid Search)

**Ngày:** 2026-04-13  
**Biến thay đổi:** `retrieval_mode = "hybrid"` (Dense + BM25)  
**Lý do chọn biến này:**
- Giúp tăng độ chính xác (Precision) của context bằng cách lọc đúng keyword (ví dụ "SLA", "Hoàn tiền", "Approval").
- Giảm nhiễu cho bước Generation, giúp model trả lời tập trung hơn.

**Scorecard Variant 1:**
| Metric | Baseline | Variant 1 | Delta |
|--------|----------|-----------|-------|
| Faithfulness | 3.8/5 | 4.2/5 | +0.4 |
| Answer Relevance | 4.1/5 | 4.4/5 | +0.3 |
| Context Recall | 4.5/5 | 4.8/5 | +0.3 |
| Completeness | 3.6/5 | 3.8/5 | +0.2 |

**Nhận xét:**
- **Hybrid Search** cải thiện rõ rệt ở các câu hỏi có từ khóa mạnh (q02, q07).
- Đặc biệt tại câu **q02 (Chính sách hoàn tiền)**, Hybrid chỉ trích xuất đúng 1 file `refund-v4.pdf`, trong khi Dense trích xuất 3 file (bao gồm cả HR policy).

**Kết luận:**
- **Variant Hybrid Search tốt hơn hẳn Baseline** nhờ khả năng lọc keyword chính xác cao của BM25 kết hợp với khả năng hiểu ngữ nghĩa của Vector search.

---

## Tóm tắt học được (Sprint 4)

1. **Lỗi phổ biến nhất trong pipeline này là gì?**
   > Semantic noise: Các đoạn văn bản có ý nghĩa tương tự (ví dụ: quy trình phê duyệt) nhưng thuộc các phòng ban khác nhau dễ bị Vector search lấy nhầm.

2. **Biến nào có tác động lớn nhất tới chất lượng?**
   > Hybrid Retrieval (BM25 + Dense) mang lại sự cải thiện ổn định nhất cho hệ thống chứa nhiều thuật ngữ/mã lỗi.

3. **Nếu có thêm 1 giờ, nhóm sẽ thử gì tiếp theo?**
   > Triển khai **Query Transformation (Expansion)** để xử lý các alias (ví dụ: "SLA" -> "Service Level Agreement") nhằm tăng recall hơn nữa.
