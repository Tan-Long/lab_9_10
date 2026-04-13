# Group Report — Lab Day 08: RAG Pipeline

## 1) Mục tiêu nhóm và phạm vi hệ thống

Nhóm triển khai một pipeline RAG phục vụ tra cứu tài liệu nội bộ cho CS + IT Helpdesk. Hệ thống tập trung vào các câu hỏi vận hành như SLA P1, quy trình cấp quyền và chính sách hoàn tiền. Mục tiêu chính là tạo câu trả lời grounded theo ngữ cảnh được retrieve và giảm tối đa hallucination.

## 2) Kiến trúc và quyết định kỹ thuật

- **Indexing**: Tài liệu được preprocess, chunk theo section heading, fallback theo paragraph nếu section quá dài.
- **Metadata**: Mỗi chunk lưu `source`, `section`, `department`, `effective_date`, `access`.
- **Embedding + store**: Dùng Sentence Transformers local model `paraphrase-multilingual-MiniLM-L12-v2`, lưu vào ChromaDB với cosine similarity.
- **Baseline retrieval**: Dense search (`top_k_search=10`, chọn `top_k_select=3`).
- **Variant retrieval**: Hybrid (Dense + BM25) kết hợp bằng RRF, giữ nguyên các tham số khác để đảm bảo A/B chỉ đổi một biến chính.
- **Generation**: Prompt grounded, yêu cầu model chỉ trả lời từ context và ưu tiên citation.

## 3) Kết quả baseline vs variant

Theo dữ liệu tổng hợp trong `docs/tuning-log.md`, variant hybrid cải thiện đồng đều so với baseline:

| Metric | Baseline | Variant (Hybrid) | Delta |
|--------|----------|------------------|-------|
| Faithfulness | 3.8/5 | 4.2/5 | +0.4 |
| Answer Relevance | 4.1/5 | 4.4/5 | +0.3 |
| Context Recall | 4.5/5 | 4.8/5 | +0.3 |
| Completeness | 3.6/5 | 3.8/5 | +0.2 |

Nhóm quan sát hybrid đặc biệt hiệu quả ở các câu hỏi có từ khóa mạnh (SLA, approval, refund), giúp giảm semantic noise từ dense retrieval thuần.

## 4) Khó khăn và cách xử lý

- Dense retrieval có lúc lấy nhầm chunk ngữ nghĩa gần nhưng sai phòng ban/ngữ cảnh.
- Prompt grounding giúp hạn chế bịa, nhưng chất lượng vẫn phụ thuộc mạnh vào retrieval stage.
- Đội đã ưu tiên tuning retrieval trước generation vì đây là điểm nghẽn chính của pipeline.

## 5) Hướng cải tiến tiếp theo

- Thử `query transformation` (alias expansion: SLA -> Service Level Agreement) để tăng recall với câu hỏi ngắn hoặc dùng từ viết tắt.
- Thêm rerank nhẹ cho top candidates nếu corpus mở rộng hơn và tăng nhiễu.
- Chuẩn hóa thêm metadata versioning để xử lý câu hỏi mang yếu tố thời gian hiệu quả hơn.
