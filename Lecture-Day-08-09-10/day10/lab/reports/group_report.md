# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** Cá nhân  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| Tan Long | Ingestion / Raw Owner + Cleaning & Quality Owner + Embed & Idempotency Owner + Monitoring / Docs Owner | tanlong04.work@gmail.com |

**Ngày nộp:** 2026-04-15  
**Branch:** _lab9_  
**Độ dài:** ~800 từ

---

## 1. Pipeline tổng quan

**Nguồn raw:** `data/raw/policy_export_dirty.csv` — CSV mô phỏng export từ CMS/HRIS/ticketing system, gồm 13 rows (10 rows gốc có lỗi cố ý + 3 rows thêm để test rule mới).

**Chuỗi lệnh end-to-end:**

```bash
# Luồng chuẩn (Sprint 1–2)
python etl_pipeline.py run --run-id sprint2-clean

# Freshness check
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint2-clean.json

# Eval retrieval
python eval_retrieval.py --out artifacts/eval/before_after_eval.csv
```

**Lệnh một dòng:**
```bash
python etl_pipeline.py run && python eval_retrieval.py --out artifacts/eval/grading_eval.csv
```

**run_id:** Có trong mỗi dòng log: `run_id=sprint2-clean`. Cũng được ghi vào `artifacts/manifests/manifest_sprint2-clean.json` và metadata vector trong Chroma (`run_id` field trong metadata).

**Kết quả Sprint 1:**
- `raw_records=13`, `cleaned_records=6`, `quarantine_records=7`
- Pipeline exit 0, PIPELINE_OK

---

## 2. Cleaning & expectation

### 2a. Bảng metric_impact (bắt buộc)

| Rule / Expectation mới | Trước (không có rule) | Sau (có rule) | Chứng cứ |
|------------------------|----------------------|---------------|---------|
| **Rule 7: quarantine_missing_exported_at** | Row 12 (sla_p1_2026, exported_at="") lọt vào cleaned. quarantine_records=4 | Row 12 quarantined, quarantine_records=7 (tổng với 2 rule khác) | `artifacts/quarantine/quarantine_sprint1.csv` dòng 6: `reason=missing_exported_at` |
| **Rule 8: quarantine_chunk_too_short** | Row 11 ("OK.", 3 chars) lọt vào cleaned, chiếm slot dedup, retrieval nhiễu | Row 11 quarantined với `chunk_length=3`. quarantine_records tăng | `artifacts/quarantine/quarantine_sprint1.csv` dòng 5: `reason=chunk_too_short, chunk_length=3` |
| **Rule 9: quarantine_hr_stale_content_10d_annual** | Row 13 (hr_leave 2026-03-01, "10 ngày phép năm") lọt vào cleaned → E6 `hr_leave_no_stale_10d_annual` FAIL (halt). Pipeline dừng. | Row 13 quarantined trước khi reach E6. E6 PASS. Pipeline exit 0 | `artifacts/quarantine/quarantine_sprint1.csv` dòng 7: `reason=hr_stale_content_10d_annual` |
| **E7: chunk_min_length_60_warn** | Không có cảnh báo về chunk ngắn sau clean | `short_chunks=1` (Row 6: lockout FAQ 52 chars) WARN mỗi run | `artifacts/logs/run_sprint1.log`: `expectation[chunk_min_length_60_warn] FAIL (warn) :: short_chunks=1` |
| **E8: all_required_doc_ids_present** | Không có check đầy đủ nguồn | PASS (4/4 doc_ids present). Nếu xóa toàn bộ SLA rows → missing_doc_ids=['sla_p1_2026'] WARN | `artifacts/logs/run_sprint1.log`: `expectation[all_required_doc_ids_present] OK (warn) :: missing_doc_ids=[]` |

**Rule chính (baseline + mở rộng):**

- **Baseline**: quarantine unknown_doc_id, normalize effective_date (dd/mm/yyyy→ISO), quarantine stale HR date (< 2026-01-01), quarantine empty chunk_text, dedupe by normalized text, fix refund 14→7 ngày.
- **Rule 7 mới**: `missing_exported_at` — quarantine nếu exported_at trống. Vị trí: sau check doc_id, trước normalize date.
- **Rule 8 mới**: `chunk_too_short` (< 30 chars) — quarantine sau check empty text, trước dedupe.
- **Rule 9 mới**: `hr_stale_content_10d_annual` — quarantine hr_leave_policy chứa "10 ngày phép năm" dù date hợp lệ. Ngăn conflict version HR lọt qua khi ngày đã update nhưng nội dung chưa.

**Ví dụ expectation fail và xử lý:**

Sprint 3 inject (`--no-refund-fix --skip-validate`):
```
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1
WARN: expectation failed but --skip-validate → tiếp tục embed (chỉ dùng cho demo Sprint 3).
```
Xử lý: Chạy lại pipeline chuẩn (không có flags) → prune chunk stale → E3 PASS lại.

---

## 3. Before / after ảnh hưởng retrieval

**Kịch bản inject (Sprint 3):**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```
Cố ý embed chunk "14 ngày làm việc" vào Chroma bằng cách bỏ qua bước fix và vượt qua expectation halt.

**Kết quả định lượng:**

| Câu hỏi | inject-bad | sprint2-clean | Thay đổi |
|---------|------------|---------------|---------|
| q_refund_window | contains=yes, **hits_forbidden=yes** | contains=yes, hits_forbidden=no | Stale chunk bị prune sau clean run |
| q_p1_sla | contains=yes, hits_forbidden=no | contains=yes, hits_forbidden=no | Không đổi |
| q_lockout | contains=yes, hits_forbidden=no | contains=yes, hits_forbidden=no | Không đổi |
| q_leave_version | contains=yes, hits_forbidden=no, top1=yes | contains=yes, hits_forbidden=no, top1=yes | Không đổi (Rule 9 bảo vệ cả 2 run) |

**Bằng chứng artifacts:**
- `artifacts/eval/after_inject_bad.csv` — eval sau inject
- `artifacts/eval/before_after_eval.csv` — eval sau clean
- Log `artifacts/logs/run_inject-bad.log`: `embed_prune_removed=1` (1 chunk bị prune khi restore)

---

## 4. Freshness & monitoring

**SLA:** 24 giờ (FRESHNESS_SLA_HOURS=24).

**Kết quả:** `freshness_check=FAIL` — age_hours=121.033, latest_exported_at=2026-04-10T08:00:00.

**Giải thích PASS/WARN/FAIL:**
- **PASS**: `age_hours ≤ 24` — dữ liệu đủ tươi, không cần can thiệp.
- **FAIL**: `age_hours > 24` — CSV mẫu dùng timestamp cố định từ ngày tạo (5 ngày trước). FAIL là hợp lý và có chủ đích: SLA áp dụng cho `latest_exported_at` (watermark nguồn), không phải `run_timestamp`. Trong production, upstream phải cập nhật timestamp theo batch thực tế.

Runbook ghi rõ: "freshness FAIL từ CSV mẫu là known issue; không điều chỉnh SLA mà ghi nhận timestamp cũ".

---

## 5. Liên hệ Day 09

Pipeline Day 10 sử dụng cùng corpus `data/docs/` nhưng qua tầng ETL: CSV export → clean → validate → embed vào collection `day10_kb` (tách riêng khỏi collection Day 09 để tránh inject corruption ảnh hưởng đến agent Day 09).

Multi-agent Day 09 có thể tích hợp: thay retrieval tool trỏ sang `day10_kb` thay vì collection cũ — đảm bảo agent đọc đúng version đã validated, có run_id trong metadata để trace.

---

## 6. Rủi ro còn lại & việc chưa làm

- Freshness chỉ đo 1 boundary (exported_at). Distinction yêu cầu 2 boundary.
- E7 (`chunk_min_length_60_warn`) luôn WARN với lockout FAQ chunk (52 chars). Known issue, ghi trong quality_report.
- Grading JSONL (`grading_run.jsonl`) chờ public grading_questions.json sau 17:00.
- Không có LLM-judge; eval keyword-based có thể miss paraphrase.
