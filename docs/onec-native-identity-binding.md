# Этап B: связать существующие CustomUser со штатным UUID 1С

## Почему только одно поле, а не дубли всех связей

Проверено в рабочей базе: 3 локальных Django пользователя соответствуют 3 разным ссылкам справочника 1С (`audit_onec_user_ids --all` → 3/3 OK).

Текущая система использует старые `CustomUser.id` как FK в автомобилях, истории владения, заказах, назначениях специалистов, чатах, авторстве сообщений, ролях и одноразовых MAX-кодах. До перехода JWT и MAX эти старые связи **нельзя удалять**.

Вместо добавления шести параллельных ID к каждой таблице добавлено только **одно временное** поле `CustomUser.onec_id` (nullable, unique). Пока отношения продолжают указывать на `CustomUser`; с помощью `onec_id` можно проверить покрытие любых связей родными ID 1С. Это техническая карта миграции, **не профиль пользователя и не постоянная модель бизнес-данных**.

Никаких изменений в API фронтенда, JWT, MAX, логике заказов, 1С или существующих ForeignKey.

## Развёртывание

**Перед обновлением бэкенда сделайте проверенный backup PostgreSQL Django.** Новая миграция `users.0009_customuser_onec_id` добавляет только nullable UUID-колонку; исходные данные не преобразует. `entrypoint.sh` сам вызывает `python manage.py migrate --noinput` при пересоздании backend.

```bash
cd /opt/service-car/backend && git pull origin master
cd /opt/service-car
docker compose up -d --build backend
docker compose exec backend python manage.py showmigrations users
docker compose exec backend python manage.py test users.tests.test_bind_onec_user_ids -v 2
```

Сначала сухой прогон:

```bash
docker compose exec backend python manage.py bind_onec_user_ids
```

Должен показать три строки `VERIFY` и `DRY RUN OK: 3 users. No database writes`. При ошибке/несовпадении UUID остановиться и **не** выполнять `--apply`.

Затем, только при проверенном backup и полном соответствии:

```bash
docker compose exec backend python manage.py bind_onec_user_ids --apply
docker compose exec backend python manage.py audit_onec_relationships
```

Первый запуск `--apply` пишет только `CustomUser.onec_id`. Он проверяет **всех** текущих пользователей в 1С, UUID, телефон и дубликаты, затем повторно проверяет данные Django внутри атомарной транзакции. При обнаруженном несовпадении ничего не записывает. Повторный запуск идемпотентен. Команда **не импортирует/не обновляет пользователей в 1С** и не пишет ФИО, роли, MAX, заказы, автомобили, чаты.

`audit_onec_relationships` проверяет, что у всех связанных пользователей есть `onec_id`, и считает:

- `cars.Car.owner`, `cars.CarOwnership.owner`;
- `orders.Order.customer` и строки M2M `orders.Order.mechanics`;
- `chats.ChatRoom.mechanic` (только непустые), `chats.ChatMessage.sender`;
- `users.UserRoleAssignment.user`, `users.MaxAuthCode.user`;
- вложения чатов учитываются отдельно и не содержат прямого FK на пользователя.

Список `CustomUser` по-прежнему не является источником профиля: GET/PATCH профиля и список специалистов продолжают читать 1С. `onec_id` специально пока не используется для авторизации или рабочих записей.

## Далее

1. По результатам аудита связей определить способ перевода JWT/refresh/role-selection на нативный ID пользователя 1С. На этом этапе отдельно учесть MAX и сначала согласовать его будущую архитектуру.
2. Убрать все связанные с `CustomUser` ForeignKey/M2M в автомобилях, заказах и чатах в согласованном порядке, без потери записей и без многомесячных двойных связей.
3. После перевода всех зависимостей удалить `CustomUser`, временную карту `onec_id` в Django и `externalId` в 1С.

**Не меняйте** поле `id` во внешнем Angular API на `onecId`, не удаляйте `externalId` в 1С и не удаляйте `CustomUser` до переключения JWT и всех связей.

### Если понадобится откат

Остановить дальнейшее переключение. Новый код не использует `onec_id` для прикладных операций, поэтому само его заполнение не меняет их поведение. Для отката релиза использовать обычный Git/Docker release rollback. **Не удалять заполненную колонку миграцией назад, пока не сохранена проверенная карта соответствий.**
