@echo off
setlocal enabledelayedexpansion
set BASE=http://localhost:8000
set DIR=%~dp0cases

echo ============================================
echo  06 llm_generation - รันเทสทุกเคส (mock mode)
echo  ตรวจก่อนว่า uvicorn รันอยู่ที่ %BASE%
echo ============================================
echo.

call :run "01 grounded ปกติ ควรมี [1] และ sources" generate 01_grounded_normal.json
call :run "02 grounded contexts ว่าง ควรตอบ insufficient" generate 02_grounded_insufficient_empty_context.json
call :run "03 grounded ขอทีเด็ด ควร blocked=true model=none" generate 03_grounded_gambling_blocked.json
call :run "04 grounded 2 แมตช์ chunk เดียว ควรตอบ 3-0 ผ่าน ไม่ insufficient" generate 04_grounded_two_matches_same_chunk.json
call :run "05 grounded ref ซ้ำ ควร 422 VALIDATION_ERROR" generate 05_grounded_duplicate_ref_422.json
call :run "06 grounded prompt injection ในcontext ควรไม่ทำตาม ไม่มี odds ในคำตอบ" generate 06_grounded_injection_attempt.json
call :run "07 passthrough ภาษาตรงแล้ว ควร model=none ไม่เรียก LLM" generate 07_passthrough_same_language_no_llm.json
call :run "08 passthrough ต้องแปลภาษา ควรเรียก LLM แปล" generate 08_passthrough_needs_translation.json
call :run "09 passthrough มีคำพนัน ควร blocked=true" generate 09_passthrough_gambling_blocked.json
call :run "10 passthrough draft ว่าง ควร 422" generate 10_passthrough_draft_empty_422.json
call :run "11 report/weekly ครบทุก section" report/weekly 11_report_weekly_full.json
call :run "12 report/weekly นัดเลื่อน ไม่มีสกอร์" report/weekly 12_report_weekly_postponed.json
call :run "13 report/weekly matches ว่าง ควร 422" report/weekly 13_report_weekly_empty_matches_422.json
call :run "14 report/weekly lineups/statistics เป็น list (fix PR11 ขอ2) ควรไม่ 422" report/weekly 14_report_weekly_list_lineups_statistics.json

echo.
echo ============================================
echo  รันครบทุกเคสแล้ว เลื่อนขึ้นไปดูผลแต่ละเคสด้านบน
echo ============================================
pause
goto :eof

:run
echo --------------------------------------------
echo [%~1]
echo ไฟล์: %~3
curl -s -X POST %BASE%/%~2 -H "Content-Type: application/json" -d @"%DIR%\%~3"
echo.
echo.
goto :eof
