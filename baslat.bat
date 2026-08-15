@echo off
title Highrise AI Bot
color 0A
cls
echo ========================================
echo    HIGHRISE AI BOT - GEMINI CEVAP BOTU
echo ========================================
echo.
echo Bot baslatiliyor...
echo.
echo [INFO] Bot durdurmak icin CTRL + C yapin
echo.

:: Node.js kontrolu
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [HATA] Node.js bulunamadi!
    echo Node.js yuklemek icin: https://nodejs.org
    echo.
    pause
    exit /b 1
)

:: node_modules kontrolu
if not exist "node_modules" (
    echo [INFO] Bagimliliklar yukleniyor...
    call npm install
    echo.
)

:: Botu baslat
node bot.js

echo.
echo Bot durduruldu.
pause