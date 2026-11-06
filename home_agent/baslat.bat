@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ==== Ayarlar ====
set "RELAY_URL=wss://highrise-ai-bot.onrender.com/relay"
set "RELAY_TOKEN=2c6cafba0887d8a0e2fcd3038b69018644faf0f1"

rem ffmpeg PATH'te degilse asagidaki satiri ffmpeg.exe klasorune gore acin:
rem set "PATH=C:\ffmpeg\bin;%PATH%"

echo Relay cihazi basliyor...
echo Kapatmak icin bu pencereyi kapatabilirsiniz (sarki calarken kapatmayin).
python relay_agent.py --url "%RELAY_URL%" --token "%RELAY_TOKEN%"
pause
