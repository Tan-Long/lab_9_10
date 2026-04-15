# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Quang  
**Vai trò:** Cleaning & Quality Owner  
**Ngày nộp:** 2026-04-15  
**run_id tham chiếu:** `sprint1`, `sprint2-clean`, `inject-bad`

---

## 1. Tôi phụ trách phần nào?

**File / module:**

- `transform/cleaning_rules.py` — toàn bộ hàm `clean_rows()`: baseline rules + 3 rule mới (Rule 7, 8, 9), hàm `_normalize_effective_date()`, `_norm_text()`, `write_cleaned_csv()`.
- `quality/expectations.py` — toàn bộ hàm `run_expectations()`: baseline E1–E6 + 2 expectation mới (E7, E8).
- `data/raw/policy_export_dirty.csv` — thiết kế rows 11–13 để tạo failure mode có chủ đích cho từng rule mới.

**Kết nối với thành viên khác:**  
Nhận raw rows từ Long (Ingest), trả về `(cleaned, quarantine)` cho entrypoint. Huy (Embed) nhận cleaned rows để upsert vào Chroma; nếu expectation halt, Huy không được phép embed. Expectations tôi viết là "bức tường" cuối trước khi data vào vector store.

**Bằng chứng:**  
`artifacts/logs/run_sprint1.log`:
```
expectation[hr_leave_no_stale_10d_annual] OK (halt) :: violations=0
expectation[chunk_min_length_60_warn] FAIL (warn) :: short_chunks=1
expectation[all_required_doc_ids_present] OK (warn) :: missing_doc_ids=[]
quarantine_records=7
```

---

## 2. Một quyết định kỹ thuật

**Chọn quarantine (cleaning rule) vs halt (expectation) cho Rule 9 (`hr_stale_content_10d_annual`)**

HR chunk với `effective_date=2026-03-01` nhưng text "10 ngày phép năm" là conflict version — date đã cập nhật nhưng nội dung chưa. Tôi có 2 lựa chọn:

1. Chỉ dùng expectation E6 (đã có): để row lọt vào cleaned → E6 FAIL → pipeline HALT.
2. Thêm Rule 9 trong `clean_rows()`: quarantine row trước khi tới expectation.

Tôi chọn **option 2 (Rule 9 + quarantine)** vì: quarantine ghi lý do vào `artifacts/quarantine/` — audit trail rõ ràng. Nếu chỉ dùng HALT, pipeline dừng và team phải debug thủ công. Với Rule 9, pipeline chạy xuyên suốt, row lỗi bị cách ly nhưng các row khác vẫn được embed — ít downtime hơn. E6 giữ nguyên làm safety net: nếu Rule 9 có bug và bỏ sót một row, E6 vẫn HALT để bắt.

---

## 3. Một lỗi / anomaly đã xử lý

**Triệu chứng:** Khi thiết kế Rule 8 (`quarantine_chunk_too_short`, threshold 30 chars), lo ngại rằng rule này có thể quarantine nhầm các chunk ngắn nhưng hợp lệ như mã ticket, tên lệnh CLI.

**Phát hiện:** Kiểm tra toàn bộ cleaned rows trong sprint1 — chunk ngắn nhất trong dữ liệu hợp lệ là "Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp." (52 chars). Threshold 30 chars an toàn với toàn bộ dữ liệu lab.

**Thêm expectation E7** (`chunk_min_length_60_warn`, warn): cảnh báo ở ngưỡng 60 chars — cao hơn threshold quarantine (30) — để phát hiện chunk "vừa sống sót" nhưng vẫn khá ngắn. Kết quả: E7 WARN `short_chunks=1` mỗi run chuẩn (lockout FAQ 52 chars), cung cấp signal monitoring mà không dừng pipeline.

**Kết quả:** `artifacts/logs/run_sprint1.log`: `expectation[chunk_min_length_60_warn] FAIL (warn) :: short_chunks=1`. Đây là **known issue** được ghi nhận trong quality_report.md — chunk lockout FAQ quá ngắn nhưng nội dung chính xác, không nên quarantine.

---

## 4. Bằng chứng trước / sau

**Inject (run_id=inject-bad)** — bỏ refund fix, vượt halt:
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed
```

**Clean (run_id=sprint2-clean)**:
```
expectation[refund_no_stale_14d_window] OK (halt) :: violations=0
```

Grading (`gq_d10_03`): `contains_expected=True`, `hits_forbidden=False`, `top1_doc_matches=True` — Rule 9 quarantine Row 13 thành công, hr_leave_policy trả về "12 ngày phép năm" không bị nhiễu "10 ngày".

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ **thêm rule phát hiện version conflict tự động**: so sánh tất cả chunk cùng `doc_id` trong cleaned — nếu có 2 chunk cùng doc_id nhưng `effective_date` khác nhau hơn 30 ngày, WARN để team review. Hiện tại chỉ hard-code ngưỡng 2026-01-01 cho HR; rule tự động sẽ không cần cập nhật code khi policy thay đổi.
