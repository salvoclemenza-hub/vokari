@echo off
cd /d "%~dp0"
title VOKARI

REM Usa direttamente il Python del .venv: nessuna dipendenza da uv sul PATH.
set "VKPY=%~dp0.venv\Scripts\python.exe"

if not exist "%VKPY%" (
  echo [ERRORE] Ambiente Python non trovato: %VKPY%
  echo Esegui prima nel progetto:  uv sync
  echo.
  pause
  exit /b 1
)

REM --- Rebuild della UI se manca la build OPPURE se i sorgenti sono piu' recenti ---
REM    (pywebview serve frontend\dist, NON frontend\src: senza rebuild si vedrebbe
REM     la UI vecchia. Questo evita il classico "dopo le modifiche non cambia nulla".)
set "VKNEEDBUILD="
if not exist "%~dp0frontend\dist\index.html" set "VKNEEDBUILD=1"
if not defined VKNEEDBUILD (
  for /f %%R in ('powershell -NoProfile -Command "$d=(Get-Item '%~dp0frontend\dist\index.html').LastWriteTime; $n=Get-ChildItem -Recurse -File '%~dp0frontend\src' ^| Where-Object { $_.LastWriteTime -gt $d } ^| Select-Object -First 1; if ($n) {'1'} else {'0'}"') do set "VKNEEDBUILD=%%R"
)

if "%VKNEEDBUILD%"=="1" (
  echo [VOKARI] Ricostruisco la UI ^(build del frontend^)...
  if not exist "%~dp0frontend\node_modules" call pnpm --dir "%~dp0frontend" install
  call pnpm --dir "%~dp0frontend" build
  if errorlevel 1 (
    echo [ERRORE] Build del frontend fallita. Correggi l'errore sopra e riavvia.
    echo Manuale:  pnpm --dir frontend install  e poi  pnpm --dir frontend build
    echo.
    pause
    exit /b 1
  )
)

if not exist "%~dp0frontend\dist\index.html" (
  echo [ERRORE] Frontend non buildato: manca frontend\dist\index.html
  echo Esegui a mano:  pnpm --dir frontend install  e poi  pnpm --dir frontend build
  echo.
  pause
  exit /b 1
)

echo [VOKARI] Avvio dell'app desktop. Chiudi la finestra dell'app per terminare.
echo.
"%VKPY%" -m app.main

echo.
echo === VOKARI chiuso (exit %errorlevel%) ===
echo Se sopra ci sono errori (traceback Python), copiali per la diagnosi.
echo.
pause
