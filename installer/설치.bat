@echo off
chcp 65001 >nul
title 병원 WhatsApp 수집 도구 설치
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/m2nho/sourcing/master/installer/setup.ps1 | iex"
if errorlevel 1 pause
