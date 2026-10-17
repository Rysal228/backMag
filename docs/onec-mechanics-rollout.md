# Список специалистов: данные только из 1С

Angular продолжает обращаться к `GET /api/v1/users/?role=mechanic&search=...&ids=...`.
Django `CustomUserViewSet.list` при `role=mechanic` **всегда** запрашивает 1С:
`GET /ServiceCar/hs/api/users/mechanics`. Ветка поиска/фильтрации специалистов
из локальной базы удалена. Флаг `ONEC_MECHANICS_GATEWAY_ENABLED` больше не существует.

В HTTP-сервисе 1С уже установлен и проверен обработчик `UserListMechanics`:
он выбирает `Специалист` через регистр `РолиПользователей`, поддерживает
`search`, `ids`, возвращает до 20 результатов. Прямой GET из контейнера
Django ответил HTTP 200 с актуальным ФИО специалиста.

Формат ответа Angular — непосредственно массив:
`[{"id":"...","phone":"...","firstName":"...","lastName":"...","patronymic":"...","birthday":null}]`.

Если 1С недоступна, Django не возвращается к локальному списку — отдаёт ошибку.
Для списков других ролей и детализации пользователей без фильтра `role=mechanic`
ещё используется Django. Связь специалистов в заказах по `CustomUser`
пока тоже остаётся в Django; это следующий этап, а не часть перехода списков.

## Проверка после обновления backend

```bash
cd /opt/service-car/backend && git pull origin master
cd /opt/service-car && docker compose up -d --build backend
docker compose exec backend python manage.py test users.tests.test_onec_mechanics_gateway -v 2
docker compose exec backend python -c 'import requests; r=requests.get("http://host.docker.internal:8081/ServiceCar/hs/api/users/mechanics",params={"search":"Серёга125"},timeout=10); print(r.status_code, r.text[:1000])'
```

Для тестирования публичного API используйте существующий JWT через Angular/Network:
`GET /api/v1/users/?role=mechanic&search=Серёга125`, должен вернуть массив
с данными из 1С.

После этих изменений оба флага переключения источника следует удалить
из `docker-compose.yml`. `ONEC_ALLOW_UNAUTHENTICATED_INTERNAL` оставить
до настройки технической HTTP-аутентификации между Django и 1С.

MAX и логика регистрации не менялись.
