# World streaming and camera modes

The flight position (never inspection camera position) selects a fixed 3x3
window of z14 tiles. Resident chunks <=9, concurrent requests <=2. Each chunk
owns its imagery rectangle, trees, nearby building primitives and debug outline.
Eviction destroys the whole group. Late responses for an evicted key are ignored.
RAM geometry budget: 9 chunks x 180 deterministic trees, one batched primitive
per material; source disk cache does not count as resident GPU data. Main render
target 60 FPS; chunk planning 2 Hz outside the render callback.

The regional overview covers 18–66°E, 40–72°N (Ukraine, Scandinavia through the
Urals), prefetched at z7. Existing eastern-Ukraine z9 imagery is retained.
Detailed imagery is prefetched for example sites; offline missing detail falls
back to the best cached parent tile, with actual source level shown in debug
counters. This is not uniform
10m coverage. `allow_network_during_session` is false by default. The downloader
can fill a chosen region at finer levels before a lesson. Disk cache persists;
browser geometry unloads. Network requests have bounded concurrency/timeouts.

Nose camera derives forward/right/up from heading, pitch and roll in ENU and
transforms them to ECEF. Positive physical bank is right wing down. Keyboard
labels express aircraft directions, independent of camera mode. Verify actual
FDM roll response before reversing RC channels.

Day/night affects lighting; night vision and monochrome thermal are pedagogic
postprocessing effects, not physical radiometric sensor models. Thermal mode
has no target detection or temperature measurement. Procedural vegetation is
deterministic decoration and does not certify real tree locations or collisions.

Debug orbit is available only in autopilot modes. Camera movement never changes
the anchor. Display active keys, loads/evictions, pending requests and source
resolution, and test distant aircraft updates plus camera-only movement.

## Проверка реализации, 2026-09-10

- Живой FBWA: +0.5 roll → примерно +26° крена и правый разворот;
  -0.5 → примерно -27° и левый разворот.
- После контрольного перелёта в интерфейсе: загружено 15, выгружено 6,
  осталось 9/9, запросы 0/2; 4 подробных и 5 обзорных участков.
- Просмотр карты всего региона не изменяет область подробной сцены.
- Переход из debug в FBWA автоматически включает камеру из носа;
  попытка снова открыть debug в FBWA отклоняется понятным сообщением.
- Обычный, ночной зелёный, чёрно-белый режимы и ночь проверены визуально.
- 10 unittest-проверок Python, 4 проверки ограничителя высоты, Node-проверки
  базиса камеры, границ набора участков, удаления ресурсов и отмены запросов.
- HTTP-проверка пяти подробных примеров и одной точки обзорного покрытия.
- Во время визуальных проверок счётчик интерфейса около 60 кадров/с;
  это не нагрузочный тест пяти одновременных учеников.

Обнаруженный при проверке конфликт вкладок устранён: наблюдатель не посылает
стики только из-за того, что увидел FBWA в телеметрии. Не-владелец не может
захватить управление пустой командой release.
