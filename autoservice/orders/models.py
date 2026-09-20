import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from users.models import CustomUser
from cars.models import Car


class StatusAppearance(models.TextChoices):
    POSITIVE = 'positive', 'Положительный'
    WARNING = 'warning', 'Предупреждение'
    NEGATIVE = 'negative', 'Отрицательный'


class WorkType(models.Model):
    class Meta:
        verbose_name = 'Тип работ'
        verbose_name_plural = 'Типы работ'

    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class OrderStatus(models.Model):
    class Meta:
        verbose_name = 'Статус заказа'
        verbose_name_plural = 'Статусы заказов'

    name = models.CharField(max_length=100, unique=True)
    appearance = models.CharField(
        verbose_name='Внешний вид статуса',
        max_length=20,
        choices=StatusAppearance.choices,
        default=StatusAppearance.WARNING,
    )
    is_initial = models.BooleanField(verbose_name='Начальный статус', default=False)
    requires_payment = models.BooleanField(verbose_name='Требует оплаты', default=False)

    def clean(self):
        if self.is_initial and OrderStatus.objects.filter(is_initial=True).exclude(pk=self.pk).exists():
            raise ValidationError({'is_initial': 'Начальный статус заказа уже настроен.'})

    def __str__(self):
        return self.name


class WorkStatus(models.Model):
    class Meta:
        verbose_name = 'Статус работы'
        verbose_name_plural = 'Статусы работ'

    name = models.CharField(max_length=100, unique=True)
    appearance = models.CharField(
        verbose_name='Внешний вид статуса',
        max_length=20,
        choices=StatusAppearance.choices,
        default=StatusAppearance.WARNING,
    )

    def __str__(self):
        return self.name


class AppointmentSettings(models.Model):
    class Meta:
        verbose_name = 'Настройки записи'
        verbose_name_plural = 'Настройки записи'

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    appointment_duration = models.PositiveIntegerField(
        verbose_name='Длительность записи, мин.',
        default=60,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
    )
    slot_interval = models.PositiveIntegerField(
        verbose_name='Интервал начала записи, мин.',
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(1440)],
    )

    def clean(self):
        if self.id != 1:
            raise ValidationError({'id': 'Может существовать только одна запись настроек.'})

        if self.slot_interval > self.appointment_duration:
            raise ValidationError({
                'slot_interval': 'Интервал начала записи не может быть больше длительности записи.'
            })

    def save(self, *args, **kwargs):
        self.id = 1
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return 'Основные настройки записи'


class WeekdaySchedule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, 'Понедельник'
        TUESDAY = 1, 'Вторник'
        WEDNESDAY = 2, 'Среда'
        THURSDAY = 3, 'Четверг'
        FRIDAY = 4, 'Пятница'
        SATURDAY = 5, 'Суббота'
        SUNDAY = 6, 'Воскресенье'

    class Meta:
        verbose_name = 'Расписание по дню недели'
        verbose_name_plural = 'Расписание по дням недели'
        ordering = ('weekday',)
        constraints = [
            models.UniqueConstraint(fields=('weekday',), name='unique_weekday_schedule'),
        ]

    weekday = models.PositiveSmallIntegerField(
        verbose_name='День недели',
        choices=Weekday.choices,
    )
    is_working = models.BooleanField(verbose_name='Рабочий день', default=True)
    start_time = models.TimeField(verbose_name='Начало рабочего дня', null=True, blank=True)
    end_time = models.TimeField(verbose_name='Конец рабочего дня', null=True, blank=True)

    def clean(self):
        if self.is_working and (self.start_time is None or self.end_time is None):
            raise ValidationError('Для рабочего дня необходимо указать начало и конец рабочего времени.')

        if not self.is_working and (self.start_time is not None or self.end_time is not None):
            raise ValidationError('Для выходного дня рабочее время указывать не нужно.')

        if self.is_working and self.start_time >= self.end_time:
            raise ValidationError({'end_time': 'Конец рабочего дня должен быть позже его начала.'})

    def __str__(self):
        return self.get_weekday_display()


class ScheduleBlock(models.Model):
    class Meta:
        verbose_name = 'Недоступный интервал'
        verbose_name_plural = 'Недоступные интервалы'
        ordering = ('date', 'start_time')

    date = models.DateField(verbose_name='Дата')
    start_time = models.TimeField(verbose_name='Начало недоступного интервала')
    end_time = models.TimeField(verbose_name='Конец недоступного интервала')

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError({
                'end_time': 'Конец недоступного интервала должен быть позже его начала.'
            })

    def __str__(self):
        return f'{self.date:%d.%m.%Y} {self.start_time:%H:%M}–{self.end_time:%H:%M}'


class Order(models.Model):
    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    car = models.ForeignKey(Car, on_delete=models.PROTECT, related_name='orders')
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT)
    status = models.ForeignKey(OrderStatus, on_delete=models.PROTECT)
    work_status = models.ForeignKey(WorkStatus, on_delete=models.PROTECT, null=True, blank=True)
    appointment_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.customer_id and self.car_id and self.car.owner_id != self.customer_id:
            raise ValidationError('Автомобиль не принадлежит выбранному клиенту.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
