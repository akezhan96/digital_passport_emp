@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0" || exit /b 1
docker info >nul 2>&1
if errorlevel 1 (
  echo Запустите Docker Desktop, дождитесь готовности и откройте этот файл снова.
  goto :failed
)
if not exist ".env.local" (
  docker volume inspect digital_profile_local_demo_database >nul 2>&1
  if not errorlevel 1 (
    echo Данные уже существуют. Откройте файл запуска в прежней папке, где сохранён .env.local.
    goto :failed
  )
  powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; $keys='DEMO_DB_PASSWORD','DEMO_AUTH_SECRET','PRESENTER_PASSWORD','CUSTOMER_PASSWORD'; $lines=foreach ($key in $keys) { $key + '=' + [guid]::NewGuid().ToString('N') }; $temp=Join-Path $PWD ('.env.local.'+[guid]::NewGuid().ToString('N')+'.tmp'); try { [IO.File]::WriteAllLines($temp,[string[]]$lines); [IO.File]::Move($temp,(Join-Path $PWD '.env.local')) } finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }"
  if errorlevel 1 goto :failed
)
docker image inspect digital_profile_local_demo-app >nul 2>&1
if errorlevel 1 (
  docker compose --env-file .env.local up -d --build --wait --wait-timeout 240
) else (
  docker compose --env-file .env.local up -d --no-build --wait --wait-timeout 240
)
if errorlevel 1 goto :failed
echo.
echo Готово. Откройте http://localhost:8080
echo Логин: presenter
for /f "tokens=2 delims==" %%P in ('findstr /b "PRESENTER_PASSWORD=" ".env.local"') do echo Пароль: %%P
popd
pause
exit /b 0
:failed
echo Запуск не завершён. Проверьте сообщения выше.
popd
pause
exit /b 1
