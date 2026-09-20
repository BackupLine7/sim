# Среда сборки и запуска SITL с физикой JSBSim.
#
# Почему не Dockerfile из ArduPilot. Их образ ставит компилятор под
# микроконтроллеры STM32 и генератор DDS на Java — для полёта на настоящем
# железе это нужно, для симуляции на компьютере не нужно совсем. Это лишние
# двадцать минут сборки и пара гигабайт в образе.
#
# Почему вообще контейнер. ArduPilot запускает JSBSim через fork/exec, которых
# в Windows нет (SIM_JSBSim.cpp, вызов execlp). Значит, только Linux. Ставить
# ради этого компиляторы на рабочую машину незачем.

FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        cmake \
        ccache \
        git \
        pkg-config \
        python3 \
        python3-dev \
        python3-pip \
        python3-setuptools \
        rsync \
    && rm -rf /var/lib/apt/lists/*

# Сборочные зависимости ArduPilot. empy строго 3.3.4: в 4.x сменился
# программный интерфейс, и их сборочные скрипты с ним не работают.
RUN python3 -m pip install --no-cache-dir \
        empy==3.3.4 \
        future \
        lxml \
        packaging \
        pexpect \
        pymavlink

WORKDIR /workspace
