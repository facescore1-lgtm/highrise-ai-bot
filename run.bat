@echo off
set PYTHONIOENCODING=utf-8
if not exist .venv (
    python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -u main.py
