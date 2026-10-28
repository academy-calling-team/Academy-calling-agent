@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where node.exe >nul 2>nul
if errorlevel 1 goto missing_node
where npm.cmd >nul 2>nul
if errorlevel 1 goto missing_node
if not exist "node_modules\vite\bin\vite.js" (
  echo 최초 설치가 필요합니다. 이 폴더에서 npm.cmd ci를 실행하세요.
  pause
  exit /b 1
)
if not exist ".env.local" (
  echo README를 참고하여 .env.local에 공동 API 주소를 설정하세요.
  pause
  exit /b 1
)
echo 프론트를 시작합니다. 준비되면 브라우저가 열립니다. 종료는 Ctrl+C입니다.
call npm.cmd run dev -- --open
exit /b %errorlevel%
:missing_node
echo Node.js 24를 설치한 뒤 다시 실행하세요.
pause
exit /b 1
