from django.core.management.base import BaseCommand, CommandError

from users.auth.max.client import MaxBotApiError, MaxBotClient


class Command(BaseCommand):
    help = 'Отправляет тестовое сообщение пользователю MAX'

    def add_arguments(self, parser):
        parser.add_argument('user_id')
        parser.add_argument(
            '--text',
            default='Тестовое сообщение от ServiceCar.',
        )

    def handle(self, *args, **options):
        try:
            response = MaxBotClient().send_message_to_user(
                user_id=options['user_id'],
                text=options['text'],
            )
        except MaxBotApiError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f'Сообщение отправлено. Ответ MAX: {response}'
            )
        )
