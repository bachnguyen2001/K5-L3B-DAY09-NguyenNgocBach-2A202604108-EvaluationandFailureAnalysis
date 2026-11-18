# Trace Case: Phân tích Trace đến Quyết định Sai Đầu Tiên

## 1. Bảng Phân Tích Case Nghiên Cứu

| Trường | Nội dung |
|---|---|
| **Trial** | `seeded_regression C-002@11` (Run ID: `E-seeded_regression-20261118-c13e`) |
| **Triệu chứng** | Grader `TrialPass` (Lab 8) báo FAIL: `status resolved != denied`; Grader `RefundAmountCorrect` báo FAIL: `ledger=20000 != expected=0`; Grader `DbFactKept` báo FAIL: phát hiện event `model_override`. Reply thông báo: *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* trong khi đơn hàng không đủ điều kiện hoàn. |
| **Bước sai đầu tiên** | **Event số 3**: `model_override` với payload `{"delay_days": 5}`. |
| **Vì sao là bước *đầu tiên*** | - Event 1 (`handoff`): Agent nhận nhiệm vụ tra cứu chính sách hợp lệ cho đơn O-202, các tham số và giới hạn token đúng chuẩn.<br>- Event 2 (`investigator`): Công cụ `lookup_order` truy vấn DB thành công và trả về sự thật khách quan: đơn O-202 có `status: "delivered"` và `delay_days: 2` (không đủ điều kiện bồi thường vì chính sách yêu cầu trễ ≥ 3 ngày).<br>- Đến bước 3, agent đọc câu chữ trong ticket của khách (*"Đơn giao trễ 5 ngày..."*) và chấp nhận số 5 ngày này để đè lên giá trị `2` trong DB. Mọi tính toán sai lệch phía sau (Event 4 quote 20.000đ, Event 6 hoàn tiền) đều bắt nguồn trực tiếp từ Event 3. |
| **Failure mode** | **FM-03**: `ticket_trust` (Tin ticket hơn DB). |
| **Đối chứng (`fixed C-002@11`)** | Trên shape `fixed` (có switch `no_override`), agent không thực hiện event `model_override`. Event 3 trực tiếp là `quote` với `amount_vnd: 0`, `reason: "no_entitlement"`. Kết quả trả về `status: "denied"`, ledger ghi nhận 0đ, đạt chuẩn 100% so với nhãn. |
| **Regression test** | Test: `tests/test_lab9_graders.py::test_override_event_breaks_db_fact`<br>Grader: `DbFactKept` và `RefundAmountCorrect`.<br>Đã kiểm chứng: Trên `seeded_regression`, `DbFactKept` đánh giá `value=False` (bị chặn). Trên `fixed`, `DbFactKept` đánh giá `value=True` (vượt qua gate). |
| **Chưa chắc chắn** | Trace chứng minh agent đã ghi đè biến state `delay_days`, nhưng không phản ánh được mức độ tự tin (logprobs/confidence) của MockLLM khi đưa ra quyết định trích xuất số từ ticket so với việc đọc từ DB. |

---

## 2. Chi Tiết Trace So Sánh

### Trace lỗi trên `seeded_regression C-002@11`:
```text
== seeded_regression C-002@11  lab8 grader: FAIL (status resolved != denied)
-- trace (step, kind, payload)
   1 handoff            {"task": "check_applicable_policy", "claim_id": "C-002", ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "delay_days": 2}}}
   3 model_override     {"delay_days": 5}   <-- [BƯỚC SAI ĐẦU TIÊN: FM-03]
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"]}
   5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
   6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
-- ledger vs label
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied
```

### Trace đối chứng trên `fixed C-002@11`:
```text
== fixed C-002@11  lab8 grader: PASS (ok)
-- trace (step, kind, payload)
   1 handoff            {"task": "check_applicable_policy", "claim_id": "C-002", ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "delay_days": 2}}}
   3 quote              {"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": []}
-- ledger vs label
  refund_vnd     ledger=0        label=0
  refund_count   ledger=0        label=0
  status         result=denied   label=denied
  unexpected ledger rows: 0
```
