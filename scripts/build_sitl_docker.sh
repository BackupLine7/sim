#!/usr/bin/env bash
# Собирает JSBSim и ArduPilot SITL внутри контейнера.
#
#     bash scripts/build_sitl_docker.sh
#
# Результат:
#   build/jsbsim-linux/bin/JSBSim              — физика
#   third_party/ardupilot/build/sitl/bin/arduplane — автопилот
#
# Сборка JSBSim кладётся в build/, а не в third_party: чужой каталог должен
# оставаться чистым, иначе git в субмодуле вечно показывает изменения.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="sim/sitl-build:ubuntu-22.04"

# Git Bash на Windows считает пути внутри команды своими и переписывает их:
# /workspace превращается в C:/Program Files/Git/workspace, и docker такое не
# принимает. Отключаем эту подстановку и отдаём путь к проекту в том виде,
# который понимает Docker Desktop.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

# Пути на ХОСТЕ отдаём в виде, понятном Docker Desktop. Пути ВНУТРИ
# контейнера (/workspace) оставляем как есть — их подстановку и отключает
# MSYS_NO_PATHCONV выше.
to_host_path() {
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$1"
    else
        printf '%s' "$1"
    fi
}

DOCKER_PROJECT_ROOT="$(to_host_path "${PROJECT_ROOT}")"
DOCKER_DOCKERFILE="$(to_host_path "${PROJECT_ROOT}/docker/sitl.Dockerfile")"
DOCKER_CONTEXT="$(to_host_path "${PROJECT_ROOT}/docker")"

if [ ! -d "${PROJECT_ROOT}/third_party/ardupilot/libraries" ]; then
    echo "Нет исходников ArduPilot. Выполните: git submodule update --init" >&2
    exit 1
fi

echo "==> Образ ${IMAGE_TAG}"
docker build --tag "${IMAGE_TAG}" --file "${DOCKER_DOCKERFILE}" "${DOCKER_CONTEXT}"

echo "==> Сборка внутри контейнера"
python "${PROJECT_ROOT}/scripts/prepare_sitl_overrides.py"
docker run --rm \
    --volume "${DOCKER_PROJECT_ROOT}:/workspace" \
    --volume "${DOCKER_PROJECT_ROOT}/build/sitl-overrides/SIM_JSBSim.cpp:/workspace/third_party/ardupilot/libraries/SITL/SIM_JSBSim.cpp:ro" \
    --workdir /workspace \
    "${IMAGE_TAG}" \
    bash -euo pipefail -c '
        git config --global --add safe.directory "*"

        echo "--- JSBSim ---"
        cmake -S third_party/jsbsim -B build/jsbsim-linux \
              -DCMAKE_BUILD_TYPE=Release -DBUILD_PYTHON_MODULE=OFF
        cmake --build build/jsbsim-linux --parallel "$(nproc)" --target JSBSim

        echo "--- ArduPilot SITL ---"
        cd third_party/ardupilot
        ./waf configure --board sitl
        ./waf plane
    '

echo "==> Готово:"
ls -la "${PROJECT_ROOT}/build/jsbsim-linux/src/JSBSim" 2>/dev/null || true
ls -la "${PROJECT_ROOT}/third_party/ardupilot/build/sitl/bin/arduplane" 2>/dev/null \
    || echo "ВНИМАНИЕ: arduplane не найден, смотрите вывод выше"
