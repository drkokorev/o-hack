# Генераторы миниатюр

Исходники коллекции из 32 моделей. Генератор создаёт модели в `tools/landmarks-3d/models/`, а сцену Blender — в `tools/landmarks-3d/odin-landmarks.blend`. Для публикации полученные GLB нужно перенести в `apps/static/models/landmarks/`.

Готовые модели уже находятся в `apps/static/models/landmarks/`. Для установщика Blender не нужен. Порядок объединения, состав ресурсов и проверка готовой сборки: [инструкция](../../docs/landmarks-3d-20261029/INTEGRATION.md).

`blender --background --factory-startup --threads 4 --python tools/landmarks-3d/source/build_landmarks.py -- no-render`

Для проверки готовых моделей скопировать папку `apps/static/models/landmarks/` в `tools/landmarks-3d/models/`, установить gltf-validator, @gltf-transform/core, @gltf-transform/extensions, draco3dgltf и выполнить `node tools/landmarks-3d/source/validate_models.cjs`.

Браузерные сценарии являются воспроизводимыми процедурами Playwright CLI и предполагают отдельно запущенную галерею пакета на порту 18135 и приложение на 18136. Пути сохранения изображений нужно адаптировать под свою рабочую папку. Полный пакет с галереей, .blend и PNG поставляется отдельно, не дублируется в репозитории.
