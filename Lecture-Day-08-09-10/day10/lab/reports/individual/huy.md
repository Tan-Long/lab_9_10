# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Huy  
**Vai trò:** Embed & Idempotency Owner  
**Ngày nộp:** 2026-04-15  
**run_id tham chiếu:** `sprint2-clean`, `inject-bad`

---

## 1. Tôi phụ trách phần nào?

**File / module:**

- `etl_pipeline.py` — hàm `cmd_embed_internal()`: kết nối ChromaDB, upsert theo `chunk_id`, prune vector id không còn trong cleaned batch, ghi log `embed_upsert count` và `embed_prune_removed`.
- `eval_retrieval.py` — toàn bộ: query Chroma theo top-k, đánh giá `contains_expected` / `hits_forbidden` / `top1_doc_expected`, ghi CSV kết quả.
- `grading_run.py` — chạy 3 câu grading, ghi JSONL cho giảng viên.
- `artifacts/eval/` — quản lý file eval: `before_after_eval.csv`, `after_inject_bad.csv`, `grading_run.jsonl`.

**Kết nối với thành viên khác:**  
Nhận `cleaned_csv` path từ entrypoint (sau khi Long và Quang hoàn thành ingest + clean). Chỉ embed khi Quang xác nhận expectations không halt. `run_id` do Long ghi vào manifest được tôi đưa vào metadata mỗi vector để trace được từng chunk thuộc run nào.

**Bằng chứng:**  
`artifacts/logs/run_sprint2-clean.log`:
```
embed_prune_removed=1
embed_upsert count=6 collection=day10_kb
```

---

## 2. Một quyết định kỹ thuật

**Idempotency: upsert + prune thay vì delete-all + reinsert**

Để embed idempotent, tôi có 2 chiến lược:
1. Xóa toàn bộ collection rồi insert lại từ đầu (delete-all + reinsert).
2. Upsert theo `chunk_id` + prune id không còn trong cleaned batch.

Tôi chọn **option 2 (upsert + prune)** vì: delete-all khiến collection trống trong khoảng thời gian ngắn giữa delete và reinsert — nếu agent query trong lúc đó sẽ nhận kết quả rỗng. Upsert + prune đảm bảo collection luôn có data, chỉ xóa những chunk thực sự bị loại khỏi cleaned batch.

Code prune:
```python
prev = col.get(include=[])
prev_ids = set(prev.get("ids") or [])
drop = sorted(prev_ids - set(ids))
if drop:
    col.delete(ids=drop)
    log(f"embed_prune_removed={len(drop)}")
```

Khi inject-bad embed chunk "14 ngày" rồi clean run restore: `embed_prune_removed=1` — đúng 1 chunk bị prune (chunk stale). Verify: rerun lần 2 → `embed_prune_removed=0` (index đã sạch).

---

## 3. Một lỗi / anomaly đã xử lý

**Triệu chứng:** Sau khi chạy `inject-bad` (embed chunk "14 ngày làm việc"), chạy eval `after_inject_bad.csv` thấy `hits_forbidden=yes` cho `q_refund_window`. Đây là kết quả đúng với inject, nhưng tôi cần verify rằng sau khi chạy clean pipeline, chunk stale thực sự bị xóa khỏi Chroma — không chỉ bị upsert đè.

**Phát hiện:** `chunk_id` của chunk "14 ngày" và chunk "7 ngày" (sau fix) khác nhau vì text đã thay đổi → hash SHA256 khác → `chunk_id` khác. Nếu chỉ upsert chunk "7 ngày" mà không prune, chunk "14 ngày" vẫn còn trong Chroma với id cũ → `hits_forbidden` vẫn có thể `yes`.

**Fix:** Prune logic đã xử lý đúng: `prev_ids - set(new_ids)` tính được id chunk "14 ngày" không còn trong cleaned → `col.delete([stale_id])`. Log sprint2-clean: `embed_prune_removed=1`.

**Kết quả:** `artifacts/eval/before_after_eval.csv`: `q_refund_window hits_forbidden=no` sau clean run. Grading `gq_d10_01`: `hits_forbidden=False` ✅.

---

## 4. Bằng chứng trước / sau

**Trước — run_id=inject-bad** (`after_inject_bad.csv`):
```
q_refund_window | hits_forbidden=yes | top1_doc=policy_refund_v4
```

**Sau — run_id=sprint2-clean** (`before_after_eval.csv`):
```
q_refund_window | hits_forbidden=no | top1_doc=policy_refund_v4
```

Grading JSONL (`grading_run.jsonl`, collection `day10_kb`, top_k=5):

| gq_d10_01 | contains=True | forbidden=False | top1=null |
| gq_d10_02 | contains=True | forbidden=False | top1=null |
| gq_d10_03 | contains=True | forbidden=False | top1=True |

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ, tôi sẽ **thêm eval mở rộng với slice câu hỏi theo doc_id**: thay vì 4 câu chung, tạo ít nhất 2 câu per doc_id (8 câu tổng) để đảm bảo mỗi nguồn đều được test coverage. Hiện tại nếu `sla_p1_2026` bị corrupt hoàn toàn, chỉ có 1 câu (`q_p1_sla`) phát hiện — coverage quá mỏng cho production pipeline.
