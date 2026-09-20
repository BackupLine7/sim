param([int]$HttpPort = 0, [int]$FirstPort = 8080, [int]$LastPort = 8180)
$ErrorActionPreference = 'Stop'
trap {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
$projectDirectory = Split-Path $PSScriptRoot -Parent
Set-Location $projectDirectory

function Get-PortOwner([int]$port) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return $null }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    return "$($processInfo.Name) (PID $($listener.OwningProcess))"
}

function Stop-RunningBridges {
    $bridges = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | Where-Object { $_.CommandLine -match '-m sim_bridge' }
    foreach ($bridge in $bridges) {
        Write-Output "Stopping running bridge PID $($bridge.ProcessId)"
        Stop-Process -Id $bridge.ProcessId -Force -ErrorAction SilentlyContinue
    }
    foreach ($bridge in $bridges) {
        Wait-Process -Id $bridge.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
    }
}

$config = python -c "import yaml,json; print(json.dumps(yaml.safe_load(open('config/simulation.yaml',encoding='utf-8'))))" | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read simulation config' }
$instance = $config.students.first_instance_index
if ($instance -ne 0) { throw 'This workstation currently supports instance 0.' }

$runtimeDirectory = Join-Path $projectDirectory 'build/sessions/0'
New-Item -ItemType Directory -Force $runtimeDirectory, (Join-Path $projectDirectory 'logs') | Out-Null
if (!(Test-Path 'build/jsbsim_root/instance-0')) {
    python scripts/prepare_jsbsim_root.py
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare JSBSim runtime' }
}
$env:PYTHONPATH = Join-Path $projectDirectory 'src'
python -c "from sim_bridge.flight_session import SessionRuntime; from pathlib import Path; SessionRuntime(Path.cwd()).prepare()"
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare session' }

$containerNames = docker ps -a --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop first.' }
if ($containerNames -contains 'sim-sitl-0') {
    docker start sim-sitl-0 | Out-Null
} else {
    $containerCommand = 'exec bash /workspace/build/sessions/0/launch.sh'
    docker run -d --name sim-sitl-0 --volume "${projectDirectory}:/workspace" --workdir /workspace/build/sessions/0 --publish '127.0.0.1:5560:5560' --publish '127.0.0.1:5760:5760' sim/sitl-build:ubuntu-22.04 bash -c $containerCommand | Out-Null
}
if ($LASTEXITCODE -ne 0) { throw 'SITL container did not start' }

Stop-RunningBridges

if ($HttpPort -eq 0) {
    foreach ($candidate in $FirstPort..$LastPort) {
        if (-not (Get-PortOwner $candidate) -and -not (Get-PortOwner ($candidate + 1))) {
            $HttpPort = $candidate
            break
        }
    }
    if ($HttpPort -eq 0) { throw "No free port pair between $FirstPort and $LastPort." }
} else {
    foreach ($required in @($HttpPort, $HttpPort + 1)) {
        $owner = Get-PortOwner $required
        if ($owner) { throw "Port $required is taken by $owner. Choose another SIM_HTTP_PORT." }
    }
}
$websocketPort = $HttpPort + 1

$bridge = Start-Process python -PassThru -ArgumentList '-u', '-m', 'sim_bridge', '--http-port', $HttpPort, '--websocket-port', $websocketPort -WorkingDirectory $projectDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectDirectory 'logs/bridge-live.log') -RedirectStandardError (Join-Path $projectDirectory 'logs/bridge-live.err')

Set-Content -Path (Join-Path $runtimeDirectory 'bridge-port.txt') -Value $HttpPort -Encoding ascii -NoNewline
Write-Output "Bridge PID $($bridge.Id). Open http://127.0.0.1:$HttpPort - press Take off to start. WebSocket $websocketPort. Runtime: logs/bridge-live.*"
