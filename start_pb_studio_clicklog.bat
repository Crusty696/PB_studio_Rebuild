@echo off
title PB Studio - CLICK-LOG Aufzeichnung AN
:: Aufzeichnungs-Modus fuer manuelle GUI-Tests.
:: Setzt PB_CLICK_LOG=1 -> jeder Maus-Klick wird als [CLICK]-Zeile geloggt
:: (Widget-Klasse, objectName, Text, enabled-State, Position) in:
::   outputs\app_run_<ts>.log  und  logs\pb_studio.log
:: Danach kann der Agent die Klicks 1:1 ins GUI-Playbook uebernehmen.
set PB_CLICK_LOG=1
echo ============================================
echo   AUFZEICHNUNGS-MODUS AKTIV (PB_CLICK_LOG=1)
echo   Jeder Klick landet als [CLICK] im Session-Log.
echo ============================================
echo.
call "%~dp0start_pb_studio.bat"
