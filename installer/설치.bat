@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/m2nho/sourcing/master/installer/setup.ps1 | iex"
if errorlevel 1 pause
