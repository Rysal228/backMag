# Получение пользователя по родному UUID 1С (подготовка JWT)

На VPS успешно проверена привязка всех 3 существующих пользователей:
`bind_onec_user_ids --apply` → `APPLIED: 3`;
`audit_onec_relationships` → `Coverage OK`, все проверенные связи имеют `onec_id`.

Следующий обязательный строительный блок для отказа от `CustomUser`:
`GET /ServiceCar/hs/api/user/id/{id}`, где `id` — UUID ссылки справочника **1С**, не `externalId` Django.

Это точечное чтение **одной** учётной записи, не универсальный поиск и не новый публичный Django endpoint.

## Установка в конфигураторе 1С

В рабочем HTTP-сервисе `ServiceCarAPI` добавить URL-шаблон:
- Имя: `UserByOneCId`
- Шаблон: `/user/id/{id}`
- Метод: `GetUserByOneCId`
- HTTP-метод: `GET`
- Обработчик: `UserGetByOneCId`.

Содержимое функции `UserGetByOneCId` взять в конце актуального
`HTTPServices/ServiceCarAPI/Ext/Module.bsl` из репозитория 1C. Не нужно перезаписывать
весь рабочий модуль без сравнения. Новая функция:

1. Проверяет формат UUID;
2. Получает ссылку на элемент справочника из UUID;
3. Проверяет реальное существование элемента и отсутствие пометки удаления;
4. Отдаёт обычный JSON `{"user": ...}` через `ПредставлениеПользователя`, в том числе `onecId`, `externalId`, телефон, роли, `isActive`;
5. Возвращает 400 для неверного UUID, 404 для отсутствующего элемента. Ничего не записывает.

Обновить конфигурацию базы данных и при необходимости перепубликовать HTTP-сервис.

## Проверка из контейнера

После обновления кода Django:

```bash
docker compose exec backend python manage.py test users.tests.test_onec_native_lookup users.tests.test_onec_profile_gateway users.tests.test_onec_mechanics_gateway -v 2
```

Проверка интеграции с работающей 1С:

```bash
docker compose exec backend python manage.py shell -c 'from integrations.services.onec_users import OneCUsersClient; u=OneCUsersClient().get_user_by_onec_id("37262ee6-c98a-11f1-9abc-fa163e59c328"); print({k:u.get(k) for k in ("onecId","externalId","phone","isActive","roles")})'
```

Затем проверить другие два `onecId` из ранее сверенной таблицы.

В этом PR не изменены JWT, профиль Angular, регистрация, MAX, связи автомобилей/заказов/чатов или UUID, которые сейчас приходят фронтенду. Новый метод клиента пока не вызывается рабочими маршрутами; его роль — обязательный адресный lookup в следующем этапе перевода аутентификации с `CustomUser.pk` на ссылки 1С.

**Не удалять** `externalId` из 1С или `CustomUser` из Django. Не включать прямой внешний доступ к HTTP-службе 1С; для постоянной эксплуатации настроить техническую авторизацию вместо `ONEC_ALLOW_UNAUTHENTICATED_INTERNAL`.
