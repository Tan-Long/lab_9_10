# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Long  
**Vai trò:** Ingestion / Raw Owner  
**Ngày nộp:** 2026-04-15  
**run_id tham chiếu:** `sprint1`, `sprint2-clean`, `inject-bad`

---

## 1. Tôi phụ trách phần nào?

**File / module:**

- `etl_pipeline.py` — phần `cmd_run()`: đọc CSV raw, gọi `load_raw_csv()`, ghi log `raw_records` / `cleaned_records` / `quarantine_records`, tạo manifest JSON với `run_id`.
- `transform/cleaning_rules.py` — hàm `load_raw_csv()` và `write_quarantine_csv()`: load CSV raw với encoding UTF-8, strip whitespace, ghi quarantine artifact.
- `data/raw/policy_export_dirty.csv` — thêm rows 11–13 để chứng minh impact của các rule mới (phối hợp với Quang).

**Kết nối với thành viên khác:**  
Sau khi ingest, tôi truyền `List[Dict]` rows sang Quang (Cleaning) qua hàm `clean_rows()`. Manifest tôi tạo được Huy (Embed) dùng để ghi `run_id` vào metadata vector. Freshness check cũng đọc manifest do tôi ghi.

**Bằng chứng:**  
`artifacts/logs/run_sprint1.log`:
```
run_id=sprint1
raw_records=13
cleaned_records=6
quarantine_records=7
manifest_written=artifacts/manifests/manifest_sprint1.json
```

---

## 2. Một quyết định kỹ thuật

**Cấu trúc manifest và trường `latest_exported_at`**

Khi thiết kế manifest, tôi phải chọn: dùng `run_timestamp` (thời điểm pipeline chạy) hay `latest_exported_at` (max của `exported_at` trong cleaned rows) làm mốc đo freshness.

Tôi chọn `latest_exported_at` làm watermark chính vì nó phản ánh độ tươi của *dữ liệu nguồn*, không phải thời điểm pipeline chạy. Nếu dùng `run_timestamp`, freshness sẽ luôn PASS ngay sau khi pipeline chạy — nhưng data thực tế vẫn có thể stale nếu upstream không export mới. Ví dụ: pipeline chạy lúc 3am nhưng upstream export từ hôm qua 8am → `run_timestamp` cho PASS sai, `latest_exported_at` cho FAIL đúng.

Cả hai trường đều ghi vào manifest để có thể đo lag ingest→publish nếu cần mở rộng sau.

---

## 3. Một lỗi / anomaly đã xử lý

**Triệu chứng:** Khi thêm rows 11–13 vào CSV, Row 12 (`sla_p1_2026`) có `exported_at` để trống. Lần đầu chạy pipeline, row này lọt vào cleaned vì code chưa có Rule 7.

**Phát hiện:** Kiểm tra `artifacts/cleaned/cleaned_sprint1.csv` — thấy row 12 với `exported_at=""` trong cleaned output. Điều này có nghĩa là một chunk sẽ được embed vào Chroma mà không có watermark timestamp → không thể đo freshness cho chunk đó, và `latest_exported_at` trong manifest sẽ tính sai (dùng empty string).

**Fix:** Phối hợp với Quang thêm Rule 7 (`quarantine_missing_exported_at`) vào `clean_rows()`: kiểm tra `exported_at` ngay sau check `doc_id`, trước khi xử lý date. Row 12 bị quarantine với `reason=missing_exported_at`.

**Kết quả:** `quarantine_sprint1.csv` dòng 6: `12, sla_p1_2026, reason=missing_exported_at`. `latest_exported_at` trong manifest tính chính xác từ 6 cleaned rows còn lại.

---

## 4. Bằng chứng trước / sau

**Trước (inject-bad, run_id=inject-bad):**
```
q_refund_window | contains_expected=yes | hits_forbidden=yes
```
→ Chunk "14 ngày làm việc" còn trong index (Huy embed nhưng refund fix bị bỏ qua).

**Sau (run_id=sprint2-clean):**
```
q_refund_window | contains_expected=yes | hits_forbidden=no
```
→ Pipeline chuẩn: `embed_prune_removed=1` — chunk stale bị Huy prune, version "7 ngày" thay thế.

Manifest sprint2-clean: `raw_records=13`, `quarantine_records=7` — 3 rows mới (11, 12, 13) đều bị quarantine đúng rule.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ **versioning raw file** theo timestamp trong tên file (`policy_export_dirty_20260415.csv`) và lưu đường dẫn đầy đủ vào manifest. Hiện tại nếu file raw bị ghi đè, không có cách rollback ingest về batch cũ. Thêm cơ chế này giúp reproduce lại bất kỳ run nào từ manifest.
