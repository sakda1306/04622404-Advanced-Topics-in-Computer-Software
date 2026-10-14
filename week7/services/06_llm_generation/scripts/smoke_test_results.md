# ผล Smoke Test (สร้างอัตโนมัติโดย smoke_test_runner.py)

Base URL: http://127.0.0.1:8000

| เคส | Endpoint | Status | เวลาฝั่ง client (s) | latency_ms (server) | ผ่าน deadline | Model | Token usage (in/out) | Safety blocked | Citations removed | Error |
|---|---|---|---|---|---|---|---|---|---|---|
| 01_grounded_normal.json | /generate | 200 | 1.03 | 706 | ✅ | openai/gpt-oss-120b | in:806 / out:58 | False | 0 | - |
| 02_grounded_insufficient_empty_context.json | /generate | 200 | 0.21 | 0 | ✅ | none | in:0 / out:0 | False | 0 | - |
| 03_grounded_gambling_blocked.json | /generate | 200 | 0.23 | 0 | ✅ | none | in:0 / out:0 | True | 0 | - |
| 04_grounded_two_matches_same_chunk.json | /generate | 200 | 0.73 | 494 | ✅ | openai/gpt-oss-120b | in:831 / out:51 | False | 0 | - |
| 05_grounded_duplicate_ref_422.json | /generate | 422 | 0.23 | - | ✅ | - | - | - | - | - |
| 06_grounded_injection_attempt.json | /generate | 200 | 0.22 | 0 | ✅ | none | in:0 / out:0 | True | 0 | - |
| 07_passthrough_same_language_no_llm.json | /generate | 200 | 0.21 | 0 | ✅ | none | in:0 / out:0 | False | 0 | - |
| 08_passthrough_needs_translation.json | /generate | 200 | 0.8 | 587 | ✅ | openai/gpt-oss-120b | in:197 / out:39 | False | 0 | - |
| 09_passthrough_gambling_blocked.json | /generate | 200 | 0.22 | 0 | ✅ | none | in:0 / out:0 | True | 0 | - |
| 10_passthrough_draft_empty_422.json | /generate | 422 | 0.23 | - | ✅ | - | - | - | - | - |
| 11_report_weekly_full.json | /report/weekly | 200 | 1.22 | 1002 | ✅ | openai/gpt-oss-120b | in:432 / out:234 | - | - | - |
| 12_report_weekly_postponed.json | /report/weekly | 200 | 0.8 | 587 | ✅ | openai/gpt-oss-120b | in:391 / out:100 | - | - | - |
| 13_report_weekly_empty_matches_422.json | /report/weekly | 422 | 0.22 | - | ✅ | - | - | - | - | - |
| 14_report_weekly_list_lineups_statistics.json | /report/weekly | 200 | 1.07 | 861 | ✅ | openai/gpt-oss-120b | in:399 / out:150 | - | - | - |