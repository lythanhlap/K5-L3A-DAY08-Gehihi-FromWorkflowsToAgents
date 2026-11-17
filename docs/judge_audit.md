# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend REPLAY: kết quả judge đã lưu sẵn trong CSV, không cần API key).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt cả 3 | **dùng**, nhưng chỉ cho giọng văn; tiền và approval không chấm bằng judge |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không: κ và recall dưới sàn | **loại**, không dùng làm gate |

Ma trận nhầm lẫn (FAIL là lớp dương, vì việc của judge là tìm lỗi):

| | tp | fp | fn | tn | Tỉ lệ FAIL judge báo | Sau hiệu chỉnh Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

Judge helpful đếm thiếu lỗi tới 3 lần: báo 9%, trong khi tỉ lệ thật khoảng 30%.

## ≥5 case audit thủ công

Gồm cả 10 bất đồng của `tone_ok` (judge được dùng) và 5 ca đại diện của `helpful` (judge bị loại).

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú: sửa rubric thế nào |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em … nha" quá suồng sã với khách đang khiếu nại. Thêm quy tắc xưng hô "LogiX – anh/chị" và dùng H-008 làm ví dụ few-shot cho FAIL. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Không biết tuổi khách thì mặc định "anh/chị", không xưng "bạn". Đưa vào cùng mục xưng hô. |
| 3 | H-029 "Dạ, vui lòng chờ … không cần nhắn thêm." | PASS | FAIL | Người | Judge chấm theo từ khóa lịch sự ("Dạ, vui lòng"). Rubric cần ghi rõ: câu mệnh lệnh hoặc chặn khách liên hệ là FAIL dù có kính ngữ. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu lời xin lỗi. Rubric: không bắt buộc xin lỗi; ngắn gọn mà đủ số tiền và thời gian là PASS. |
| 5 | H-051 "…đã refund 90.000đ…" | FAIL | PASS | Người | Style guide CSKH của LogiX cho phép từ "refund". Thêm danh sách từ tiếng Anh được phép vào rubric. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người, nhưng sai chỗ | Hứa một khoản ngoài kết quả hệ thống là lỗi **nội dung tiền**, không phải giọng văn. Chuyển sang grader code (reply chỉ được nêu số đã ghi trong ledger, FM-08); không nhét vào rubric tone. |
| 7 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Thêm luật: không dùng emoji khi trả lời khiếu nại. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Người gán nhãn đọc nhầm ticket. Sửa nhãn ở vòng gán nhãn sau, có người duyệt thứ 2; trong lab không sửa CSV công khai. Nếu sửa: tp 25, fp 3 → P 0.893, R 0.806, κ ≈ 0.784. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người | Lỗi gõ nhỏ, không đổi nghĩa và không thô lỗ. Rubric: lỗi gõ như vậy không làm FAIL tone; nếu cần thì theo dõi bằng metric chính tả riêng. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ…" | PASS | FAIL | Người | Câu mất dấu do dịch máy. Thêm luật: tiếng Việt phải có dấu đầy đủ. |
| 11 | HL-015 "…đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể chấm số tiền. Bỏ tiêu chí tiền khỏi judge và dùng grader code `reply_matches_ledger` (FM-08). |
| 12 | HL-043 "…đã hoàn 35.000đ cho đơn O-202." (ledger 20.000đ) | PASS | FAIL | Người | Cùng dạng với C-008: approval giới hạn dưới quote, reply nói theo quote. `reply_matches_ledger` bắt được, judge thì không. |
| 13 | HL-016 xin lỗi 2 lần, dài, "đã hoàn 55.000đ" (ledger 35.000đ) | PASS | FAIL | Người | Judge thiên vị câu dài, lịch sự (verbosity bias): cả 18 ca "sai tiền" đều được cho PASS, nhiều ca có lời xin lỗi lặp lại. Rubric: xin lỗi lặp lại không làm câu trả lời hữu ích hơn. |
| 14 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Sai xưng hô là tiêu chí của tone. Giao cho judge `tone_ok` đã calibrate, không để `helpful` chấm. |
| 15 | HL-074 "…đã hoàn 140.000đ cho đơn O-458." (ledger 120.000đ) | PASS | FAIL | Người | Thêm một ca sai tiền. Judge chỉ FAIL các lỗi hiển nhiên (giọng cụt 4/4, không hỏi mã đơn 3/3, lạc đề 2/2), nên P = 1.0 không có ý nghĩa. |

## Kết luận

- **Loại `helpful`:** κ = 0.375 < 0.6 và R = 0.30 < 0.7.
  - Theo ma trận nhầm lẫn, judge bỏ sót 21/30 reply hỏng (fn = 21): gồm 18/18 ca "sai tiền" và 3/3 ca "sai xưng hô".
  - P = 1.0 chỉ cho thấy judge rất hiếm khi nói FAIL.
  - Nếu dùng judge này làm gate, ta sẽ báo tỉ lệ lỗi 9% trong khi thực tế khoảng 30%.
  - Số tiền là việc của code: `reply_matches_ledger` (blocking, sàn 1.0).
- **Dùng `tone_ok` cho giọng văn:** judge đạt cả 3 sàn.
  - Tuy vậy P = 0.857 nghĩa là khoảng 1/7 cờ FAIL là báo nhầm.
  - Lỗi bỏ sót tập trung ở xưng hô, mệnh lệnh, emoji và mất dấu, nên phải sửa rubric theo các ca 1–3, 7, 10 trước khi đưa vào gate.
  - Hiện chưa đưa judge vào gate CI.
- **Rủi ro còn lại:**
  - Judge mới chỉ được kiểm trên dữ liệu replay đã công khai, nên chưa có held-out thật.
  - Có 1/10 bất đồng do chính nhãn người sai (H-081), nên cần 2 người gán nhãn độc lập và đo κ giữa người với người trước khi tin vào sàn κ ≥ 0.6.
