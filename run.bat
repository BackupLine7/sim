@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if "%SIM_HTTP_PORT%"=="" set "SIM_HTTP_PORT=0"
set "IMAGE=sim/sitl-build:ubuntu-22.04"
set "ARDUPLANE=third_party\ardupilot\build\sitl\bin\arduplane"
set "JSBSIM=build\jsbsim-linux\src\JSBSim"

echo.
echo === 1/6  Инструменты ===
call :need python  || goto :fail
call :need git     || goto :fail
call :need docker  || goto :fail
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop не отвечает. Запустите его и повторите.
    goto :fail
)
echo Всё на месте.

echo.
echo === 2/6  Библиотеки Python ===
python -m pip install --quiet --disable-pip-version-check --requirement requirements.txt
if errorlevel 1 goto :fail
echo Установлены.

echo.
echo === 3/6  Чужой код из third_party ===
if not exist "third_party\ardupilot\libraries" (
    git submodule update --init
    if errorlevel 1 goto :fail
)
if not exist "third_party\ardupilot\modules\waf\waf-light" (
    git -C third_party\ardupilot submodule update --init --recursive
    if errorlevel 1 goto :fail
)
echo Готово.

echo.
echo === 4/6  Сборка JSBSim и ArduPilot SITL ===
if exist "%ARDUPLANE%" if exist "%JSBSIM%" (
    echo Уже собрано, пропускаю. Пересобрать: удалите build\jsbsim-linux
    goto :built
)
call :need bash || goto :fail
echo Первая сборка занимает 15-30 минут.
bash scripts/build_sitl_docker.sh
if errorlevel 1 goto :fail
if not exist "%ARDUPLANE%" (
    echo Сборка прошла, но arduplane не найден. Смотрите вывод выше.
    goto :fail
)
:built

echo.
echo === 5/6  Физика, автопилот и мост ===
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_simulator.ps1 -HttpPort %SIM_HTTP_PORT% %*
if errorlevel 1 goto :fail

echo.
echo === 6/6  Страница занятия ===
set "PORT="
set /p PORT=<"build\sessions\0\bridge-port.txt"
start "" http://127.0.0.1:%PORT%
echo Открыто: http://127.0.0.1:%PORT%
echo Журнал моста: logs\bridge-live.log
echo Остановить: docker stop sim-sitl-0  и закрыть процесс python -m sim_bridge
exit /b 0

:need
where %1 >nul 2>&1
if errorlevel 1 (
    echo Не найдено: %1
    exit /b 1
)
exit /b 0

:fail
echo.
echo Запуск прерван.
exit /b 1
