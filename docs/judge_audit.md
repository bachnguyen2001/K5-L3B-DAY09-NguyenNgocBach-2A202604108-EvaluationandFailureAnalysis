# Judge Audit — Hiệu Chuẩn và Đánh Giá LLM Judge

## 1. Kết Quả Hiệu Chuẩn (Calibration)

Chạy:
- `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5`
- `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`

| Tiêu chí | n | κ (Cohen's Kappa) | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| **tone_ok** | 100 | **0.757** | **0.857** | **0.800** | **ĐẠT** (vượt cả 3 ngưỡng) | **Dùng** (đủ tiêu chuẩn làm gate chất lượng) |
| **helpful** | 100 | **0.375** | **1.000** | **0.300** | **KHÔNG ĐẠT** (κ < 0.6 và Recall < 0.7) | **Loại** (tuyệt đối không dùng làm CI gate) |

---

## 2. ≥5 Case Audit Thủ Công

Dưới đây là 5 case bất đồng thực tế được trích xuất từ dữ liệu calibration:

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa Rubric |
|---|---|---|---|---|---|
| 1 | `H-008` (tone) | PASS | FAIL | **Người đúng** | *Reply: "Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* Văn phong quá suồng sã, xưng hô "anh - em" và dùng từ lóng "check", không phù hợp với chuẩn mực dịch vụ CSKH doanh nghiệp LogiX. Judge bị lừa bởi câu chữ thân thiện. **Sửa rubric:** Bổ sung quy tắc cấm xưng hô gia đình/bè bạn và cấm dùng từ đệm tiếng Anh không chuẩn. |
| 2 | `H-017` (tone) | PASS | FAIL | **Người đúng** | *Reply: "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha."* Câu xưng hô "bạn ơi... rồi nha" mang tính chất mạng xã hội, thiếu kính ngữ và thiếu sự trang trọng cần thiết khi thông báo tài chính. **Sửa rubric:** Định nghĩa rõ đại từ nhân xưng chuẩn ("Quý khách", "anh/chị"). |
| 3 | `H-029` (tone) | PASS | FAIL | **Người đúng** | *Reply: "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* Câu trả lời có giọng điệu gắt gỏng, xua đuổi khách hàng ("không cần nhắn thêm"). Judge bỏ qua vì thấy có chữ "Dạ, vui lòng". **Sửa rubric:** Cấm các cụm từ mang tính ngăn cản khách phản hồi hoặc thiếu thiện chí hỗ trợ. |
| 4 | `H-042` (tone) | FAIL | PASS | **Judge sai (Người đúng)** | *Reply: "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* Câu trả lời đầy đủ kính ngữ ("Dạ... ạ"), rõ ràng về mốc thời gian. Judge gán nhãn FAIL giả định do câu ngắn gọn. **Sửa rubric:** Nêu rõ ngắn gọn, súc tích và đúng trọng tâm không bị tính là cụt lủn hay thiếu lịch sự. |
| 5 | `HL-016` (helpful) | PASS | FAIL | **Người đúng** | *Reply: "Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này và rất trân trọng sự kiên nhẫn của anh/chị."* Câu xin lỗi sáo rỗng nhưng hoàn toàn không giải quyết được vấn đề của khách (không kiểm tra đơn, không báo kết quả hoàn tiền). Judge đánh giá PASS vì văn phong lịch sự. **Sửa rubric:** Phải phân tách rõ giữa "thái độ lịch sự" và "hữu ích thực sự" (có hành động cụ thể giải quyết khiếu nại). |

---

## 3. Kết Luận & Quyết Định Vận Hành

### Tiêu chí bị loại: `judge_helpful`
- **Ma trận nhầm lẫn:** `tp: 9, fp: 0, fn: 21, tn: 70`.
- **Lý do loại bỏ:** 
  - Tỷ lệ Recall cực kỳ thấp: **0.300** (chỉ phát hiện được 9/30 câu trả lời không hữu ích, bỏ sót tới 21 câu hỏng - False Negatives = 21).
  - Hệ số Cohen's Kappa chỉ đạt **0.375**, thấp hơn nhiều so với sàn 0.60.
  - LLM judge này có xu hướng nhầm lẫn giữa *lịch sự* và *hữu ích*: chỉ cần agent nói lời xin lỗi mượt mà là judge cho qua, dù agent không làm gì để bồi thường cho khách hàng. Nếu dùng làm cổng chặn CI, 70% phản hồi vô dụng sẽ bị lọt lưới.

### Rủi ro còn lại và Giới hạn:
1. `judge_tone` đạt sàn trên bộ dữ liệu replay công khai (100 mẫu). Tuy nhiên, trên dữ liệu thực tế ngoài production, phân phối ngôn ngữ người dùng có thể phong phú và đa dạng hơn (tiếng lóng vùng miền, teencode).
2. Cần định kỳ gắn nhãn thủ công các mẫu mới từ production (held-out set thật) để tái đánh giá (re-calibrate) judge theo chu kỳ release.
