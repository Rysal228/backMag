# Профиль пользователя: единственный источник — 1С

Маршрут Angular `GET/PATCH /api/v1/users/profile/` **всегда** использует `OneCProfileView`.
Больше нет `ONEC_PROFILE_GATEWAY_ENABLED`, старого `ProfileCustomUserView` или сериализатора записи профиля Django.

- Для GET Django проверяет JWT, запрашивает `GET /ServiceCar/hs/api/user/{phone}` и сверяет UUID, телефон, активность и выбранную роль с 1С.
- Для PATCH Django допускает только `firstName`, `lastName`, `patronymic`, `birthday`, запрашивает текущего пользователя из 1С, проверяет идентичность, отправляет `PATCH /user/{phone}`, возвращает прочитанный ответ 1С.
- Django не сохраняет изменения профиля в своей базе. Если 1С недоступна — возвращается ошибка, без перехода на старые локальные данные.
- Контракт Angular сохранён: `{"user":{"id":...,"phone":...,"firstName":...,"lastName":...,"patronymic":...,"birthday":...,"roles":[...],"activeRole":...}}`.

## Развёртывание

Реальные GET и PATCH в 1С уже проверены, включая изменение имени через Angular и через 1С:Предприятие.

1. На VPS: `cd /opt/service-car/backend && git pull origin master`.
2. `cd /opt/service-car && docker compose up -d --build backend`.
3. Удалить `ONEC_PROFILE_GATEWAY_ENABLED` и `ONEC_MECHANICS_GATEWAY_ENABLED` из `environment` сервиса `backend` в `docker-compose.yml`. Эти переменные **игнорируются новым кодом**; их удаление — уборка конфигурации, а не переключение.
4. Проверить `docker compose exec backend python manage.py test users.tests.test_onec_profile_gateway users.tests.test_onec_mechanics_gateway -v 2`.
5. Проверить GET/PATCH профиля через Angular и получение списка специалистов в UI или через JWT.

`ONEC_ALLOW_UNAUTHENTICATED_INTERNAL=1` — временное разрешение подключения к внутреннему HTTP-сервису без аутентификации. **Не удалять**, пока не настроены `ONEC_API_USER` и `ONEC_API_PASSWORD`: это не флаг старого/нового источника.

Технический `CustomUser` пока остаётся для JWT и связей Django с заказами/автомобилями. Регистрация, MAX, другие роли в списке пользователей и некоторые поля заказов ещё используют Django. Этот этап не меняет их; окончательное удаление `CustomUser` потребует отдельной миграции отношений и аутентификации.
