# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case của nhóm: trừ hai lần khoản đã hoàn (C-014)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11`, dòng `E-014@11` trong report `E-seeded_regression-20261117-50d2` (eval set `50d276cb621b`) |
| Triệu chứng | Grader Lab 8 trả `proposal_mismatch`. `refund_amount_correct` FAIL: ledger 90.000đ, nhãn 120.000đ. `proposal_correct` FAIL: đề xuất 120.000đ, quote 150.000đ. `reply_matches_ledger` FAIL: reply nói "đã hoàn 120.000đ" nhưng ledger chỉ có 90.000đ. Status `resolved` khớp nhãn, nên chỉ nhìn status hoặc reply thì tưởng là đúng. |
| Bước sai đầu tiên | event 5 `proposal` `{"amount_vnd": 120000}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` và event 2 `investigator` (O-515 trễ 5 ngày, hàng hỏng đã xác minh) đúng. Event 3 `quote` 150.000đ (lấy max của SHIP-LATE-03 30.000 và DMG-04 150.000) khớp hoàn toàn với `fixed`. Event 4 `refund_history` (đơn đã được hoàn 30.000đ) chỉ là đọc thêm; `honest_refactor` cũng đọc và vẫn đúng. Tại event 5, agent tự trừ 30.000đ, trong khi host (`durability.issue_refund`) cũng trừ khoản đã hoàn của đơn, nên số tiền bị trừ hai lần. |
| Failure mode | FM-05 (pre_deducted), kéo theo FM-08 (reply nói số agent tự tính, không phải số host đã ghi) |
| Đối chứng | `fixed C-014@11` không có event `refund_history` và `proposal`. Quote 150.000đ được gửi thẳng cho host, host trừ 30.000đ, ledger còn 120.000đ, và reply "đã hoàn 120.000đ" khớp ledger. |
| Regression test | `src/tests/test_lab9_fm_probes.py::test_trace_case_c014_double_deduction` khẳng định: event thứ 5 là `proposal 120000`; ledger 90.000đ; cả `refund_amount_correct`, `proposal_correct` và `reply_matches_ledger` đều FAIL trên `seeded_regression` và cùng PASS trên `fixed`. Đã chạy: fail đúng trên variant lỗi, pass trên `fixed`. Ngoài ra `test_probe_is_flagged_and_fixed_is_clean[FM-05-pre_deducted]` khóa riêng FM-05 trên C-013 (trừ về 0 rồi tự từ chối). |
| Chưa chắc chắn | Trace không có event cho phản hồi của host (`issue_refund` trả gì), nên phải đọc ledger mới thấy lần trừ thứ hai. Trace cũng không chứng minh agent "biết" host sẽ trừ; nó chỉ cho thấy số gửi đi đã bị trừ trước. Trên MockLLM lỗi xảy ra ở cả 5 seed; với LLM thật, bước 5 có thể chỉ hỏng ở một số seed. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
