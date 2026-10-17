# Список специалистов из 1С — постепенное переключение

**Цель:** существующий Angular `GET /api/v1/users/?role=mechanic&search=...&ids=...` должен возвращать специалистов из 1С, а не из Django ORM.

## Важно перед развёртыванием

Включение происходит **после** установки нового HTTP-обработчика 1С. Новое поведение выключено по умолчанию, чтобы не ломать рабочее приложение.

1. Сделать резервную копию 1С.
2. В Конфигураторе открыть HTTP-сервис `ServiceCarAPI`.
3. Создать шаблон URL `/users/mechanics` (имя `Mechanics`), в нём метод `GET` (имя `GetMechanics`) с обработчиком `UserListMechanics`.
4. Добавить новые функции в конец модуля HTTP-сервиса из `HTTPServices/ServiceCarAPI/Ext/Module.bsl`: `НайтиЦифрыВСтроке`, `СовпадаетПоискСпециалиста`, `UserListMechanics`; или заменить модуль выгрузкой с PR. Убедиться, что ранее настроенная запись пользователей остаётся рабочей.
5. Проверить синтаксис конфигурации, обновить базу, при необходимости перепубликовать HTTP-сервис, затем проверить из Docker:
   `docker compose exec backend python -c 'import requests; r=requests.get("http://host.docker.internal:8081/ServiceCar/hs/api/users/mechanics",params={"search":"Сер"},timeout=10); print(r.status_code, r.text[:1500])'`
6. Только после подтверждения `HTTP 200` и массива специалистов выполнить обновление Django из master (сборка backend) и включить в Docker Compose `ONEC_MECHANICS_GATEWAY_ENABLED: "1"`; пересоздать контейнер `docker compose up -d --force-recreate backend`.
7. Через Angular проверить выбор механика в заказе, поиск по имени, ввод телефона, включение уже выбранного UUID через `ids`, поиск после ручного изменения ФИО в 1С.

Внешний Django API возвращает непосредственно массив, как прежде:
`[{"id":"...","phone":"...","firstName":"...","lastName":"...","patronymic":"...","birthday":null}]`.
Запросы с role, отличным от mechanic, пока продолжают использовать старый Django-код (это не конечная архитектура). Механик выбирается из регистра ролей 1С. Реальный контракт `PATCH /api/v1/users/profile/` не меняется.

Новый 1С HTTP-endpoint является **только серверным**. Прямой публичный доступ не предусматривать; к постоянной эксплуатации требуется техническая HTTP-аутентификация. Это не заменяет проверку полномочий JWT в Django.

## Тесты Django

`docker compose exec backend python manage.py test users.tests.test_onec_mechanics_gateway -v 2`

Выбор механика в заказах пока всё ещё ссылается на `CustomUser` в PostgreSQL Django. Это отдельная зависимость, которую нельзя удалять на этом этапе. MAX-авторизация не затронута.
