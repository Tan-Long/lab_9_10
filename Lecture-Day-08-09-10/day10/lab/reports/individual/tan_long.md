# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Tan Long  
**Vai trò:** Toàn bộ pipeline — Ingestion + Cleaning & Quality + Embed + Monitoring  
**Ngày nộp:** 2026-04-15  
**run_id tham chiếu:** `sprint2-clean`, `sprint1`, `inject-bad`  
**Grading run_id:** `sprint2-clean` → `artifacts/eval/grading_run.jsonl`

---

## 1. Tôi phụ trách phần nào?

**File / module:**

- `etl_pipeline.py` — entrypoint, orchestration ingest → clean → validate → embed → manifest
- `transform/cleaning_rules.py` — thêm 3 rule mới: Rule 7 (`quarantine_missing_exported_at`), Rule 8 (`quarantine_chunk_too_short`), Rule 9 (`quarantine_hr_stale_content_10d_annual`)
- `quality/expectations.py` — thêm E7 (`chunk_min_length_60_warn`) và E8 (`all_required_doc_ids_present`)
- `data/raw/policy_export_dirty.csv` — thêm rows 11–13 để test các rule mới
- `docs/pipeline_architecture.md`, `docs/data_contract.md`, `docs/runbook.md`, `docs/quality_report.md`
- `contracts/data_contract.yaml`
- `reports/group_report.md`, file này

**Bằng chứng:**  
Log `artifacts/logs/run_sprint1.log` dòng: `run_id=sprint1`, `quarantine_records=7` (4 baseline + 3 rule mới). File `artifacts/quarantine/quarantine_sprint1.csv` ghi rõ reason cho từng row.

---

## 2. Một quyết định kỹ thuật

**Vị trí kiểm tra Rule 7 (`missing_exported_at`) trong pipeline — đặt trước hay sau normalize date?**

Tôi đặt Rule 7 ngay sau check `doc_id not in ALLOWED_DOC_IDS` và trước `_normalize_effective_date`. Lý do: `exported_at` là watermark truy vết nguồn export — một row thiếu trường này không thể tham gia đo freshness. Nếu đặt sau normalize date, row thiếu exported_at có thể đã vượt qua 2 bước kiểm tra (doc_id, date) rồi mới bị bắt, làm giảm hiệu quả quarantine pipeline (thêm CPU không cần thiết). Đặt sớm → fail-fast.

Lý do không dùng severity `halt` ở expectation cho trường hợp này mà dùng quarantine rule: expectation chạy trên *cleaned* rows, nhưng row thiếu exported_at phải bị loại ở bước clean để không lọt vào index. Nếu chỉ có expectation mà không có cleaning rule, row vẫn có thể được embed với metadata thiếu exported_at — gây khó debug sau.

---

## 3. Một lỗi / anomaly đã xử lý

**Triệu chứng:** Trong quá trình thiết kế Rule 9 (`hr_stale_content_10d_annual`), tôi phát hiện Row 13 trong CSV có `effective_date=2026-03-01` (hợp lệ, vượt qua rule stale-date của baseline) nhưng nội dung vẫn ghi "10 ngày phép năm". Nếu không có Rule 9, Row 13 sẽ được clean và embed bình thường.

**Phát hiện:** Chạy thử pipeline chỉ với baseline rules → Expectation E6 (`hr_leave_no_stale_10d_annual`) FAIL:
```
expectation[hr_leave_no_stale_10d_annual] FAIL (halt) :: violations=1
PIPELINE_HALT: expectation suite failed (halt).
```

**Fix:** Thêm Rule 9 vào `clean_rows()` — sau check stale date, trước check empty text. Vị trí quan trọng: phải kiểm tra TRƯỚC bước dedupe để tránh Row 13 chiếm slot trong `seen_text`.

**Kết quả:** Với Rule 9, `quarantine_sprint1.csv` có dòng: `13, hr_leave_policy, reason=hr_stale_content_10d_annual, effective_date_normalized=2026-03-01`. E6 PASS. Pipeline exit 0.

---

## 4. Bằng chứng trước / sau

**run_id=inject-bad** (bỏ refund fix, skip validate):
```
q_refund_window, contains_expected=yes, hits_forbidden=yes, top1_doc_id=policy_refund_v4
```

**run_id=sprint2-clean** (pipeline chuẩn):
```
q_refund_window, contains_expected=yes, hits_forbidden=no, top1_doc_id=policy_refund_v4
```

Thay đổi: `hits_forbidden` từ `yes` → `no` sau khi pipeline chuẩn prune chunk stale ("14 ngày làm việc") và upsert version "7 ngày". Log sprint2-clean: `embed_prune_removed=1`.

Cho `q_leave_version`: cả hai run đều `hits_forbidden=no, top1_doc_expected=yes` — Rule 9 bảo vệ HR version trong cả inject scenario lẫn clean run.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ **đo freshness ở 2 boundary** thay vì 1: (1) `ingest_at` = thời điểm pipeline đọc CSV, (2) `publish_at` = thời điểm embed xong vào Chroma. Hiện tại manifest chỉ có `latest_exported_at` (watermark nguồn) và `run_timestamp` (publish), nhưng chưa tính SLA riêng cho lag ingest→publish. Ghi cả hai vào manifest và vẽ alert nếu lag > 5 phút — cải tiến này đáp ứng Distinction criterion (b).

---

## Grading JSONL — kết quả chính thức

**File:** `artifacts/eval/grading_run.jsonl` | **Collection:** `day10_kb` | **top_k=5**

| ID | contains_expected | hits_forbidden | top1_doc_matches | top1_doc_id |
|----|:-----------------:|:--------------:|:----------------:|-------------|
| `gq_d10_01` | ✅ true | ✅ false | — | policy_refund_v4 |
| `gq_d10_02` | ✅ true | ✅ false | — | sla_p1_2026 |
| `gq_d10_03` | ✅ true | ✅ false | ✅ true | hr_leave_policy |

Tất cả 3 câu đạt điều kiện **Merit** theo SCORING.md:
- `gq_d10_01`: `contains_expected=true` + `hits_forbidden=false` — chunk "7 ngày" đúng, không còn "14 ngày làm việc" trong top-5.
- `gq_d10_02`: `contains_expected=true` — "15 phút" và "4 giờ" có trong top-5 của sla_p1_2026.
- `gq_d10_03`: `contains_expected=true` + `hits_forbidden=false` + `top1_doc_matches=true` — "12 ngày phép năm" đúng, không có "10 ngày phép năm", top-1 đúng từ hr_leave_policy. Đây là bằng chứng Rule 9 (`quarantine_hr_stale_content_10d_annual`) hoạt động hiệu quả.
