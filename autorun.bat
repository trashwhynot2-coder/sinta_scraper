@echo off
REM ===========================================================================
REM  autorun.bat - SINTA Scraper (klik dua kali untuk menjalankan)
REM
REM  File ini TIDAK berisi logika apa pun. Tugasnya hanya:
REM    1. pindah ke folder tempat file ini berada (%~dp0)
REM    2. cari Python
REM    3. serahkan semuanya ke autorun.py
REM
REM  Semua pengaturan ada di autorun_config.ini (buka pakai Notepad).
REM ===========================================================================
setlocal
chcp 65001 >nul 2>nul
title SINTA Scraper - autorun
cd /d "%~dp0"

echo ============================================================
echo   SINTA SCRAPER - AUTORUN
echo   folder : %CD%
echo ============================================================
echo.

REM --- cari Python (pakai ^&^& agar tidak perlu %ERRORLEVEL% di dalam blok) ---
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"

if not defined PY goto NOPY

%PY% autorun.py %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" goto FAILED
echo ============================================================
echo  SELESAI. Hasil ada di folder hasil\
echo ============================================================
echo.
pause
exit /b 0

:FAILED
echo ============================================================
echo  SELESAI dengan kode %RC% - ada masalah, baca pesan di atas.
echo  Log lengkap tersimpan di folder logs\
echo ============================================================
echo.
pause
exit /b %RC%

:NOPY
echo [GAGAL] Python tidak ditemukan di PATH.
echo.
echo  1. Install Python 3.9 atau lebih baru: https://www.python.org/downloads/
echo  2. Saat instalasi, CENTANG "Add python.exe to PATH"
echo  3. Tutup jendela ini, lalu klik dua kali autorun.bat lagi
echo.
pause
exit /b 1
