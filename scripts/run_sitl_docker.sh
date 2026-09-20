#!/usr/bin/env bash
# Запускает один экземпляр SITL с физикой JSBSim в контейнере.
#
#     bash scripts/run_sitl_docker.sh [номер_ученика]
#
# Куда JSBSim шлёт позу, задано в config/simulation.yaml (pose_output_host).
# Здесь адрес не подменяется: два места, задающие одно и то же, разойдутся.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="sim/sitl-build:ubuntu-22.04"
INSTANCE_INDEX="${1:-0}"

# Git Bash переписывает пути внутри команды. Пути хоста отдаём через cygpath,
# пути контейнера оставляем как есть.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

to_host_path() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi
}
DOCKER_PROJECT_ROOT="$(to_host_path "${PROJECT_ROOT}")"

PORT_STRIDE=10
TERRAIN_PORT=$((5560 + INSTANCE_INDEX * PORT_STRIDE))
POSE_PORT=$((5620 + INSTANCE_INDEX * PORT_STRIDE))
MAVLINK_PORT=$((5760 + INSTANCE_INDEX * PORT_STRIDE))

HOME_LOCATION="${HOME_LOCATION:-50.4501,30.5234,179,90}"
JSBSIM_ROOT="/workspace/build/jsbsim_root/instance-${INSTANCE_INDEX}"

if [ ! -d "${PROJECT_ROOT}/build/jsbsim_root/instance-${INSTANCE_INDEX}" ]; then
    echo "Нет рабочего каталога JSBSim для ученика #${INSTANCE_INDEX}." >&2
    echo "Выполните: python scripts/prepare_jsbsim_root.py" >&2
    exit 1
fi

echo "==> Ученик #${INSTANCE_INDEX}"
echo "    рельеф  <- хост :${TERRAIN_PORT}"
echo "    поза    -> хост :${POSE_PORT}"
echo "    MAVLink <- хост :${MAVLINK_PORT}"

# JSBSim ArduPilot ищет по имени в PATH: он вызывает его через execlp.
CONTAINER_SCRIPT="
install -m 0755 build/jsbsim-linux/src/JSBSim /usr/local/bin/JSBSim
exec third_party/ardupilot/build/sitl/bin/arduplane \
    --model jsbsim \
    --autotest-dir ${JSBSIM_ROOT} \
    --home ${HOME_LOCATION} \
    --instance ${INSTANCE_INDEX} \
    --serial0 tcp:0 \
    --defaults third_party/ardupilot/Tools/autotest/default_params/plane-jsbsim.parm
"

docker run --rm \
    --name "sim-sitl-${INSTANCE_INDEX}" \
    --volume "${DOCKER_PROJECT_ROOT}:/workspace" \
    --workdir /workspace \
    --publish "127.0.0.1:${TERRAIN_PORT}:${TERRAIN_PORT}" \
    --publish "127.0.0.1:${MAVLINK_PORT}:${MAVLINK_PORT}" \
    "${IMAGE_TAG}" \
    bash -euo pipefail -c "${CONTAINER_SCRIPT}"
