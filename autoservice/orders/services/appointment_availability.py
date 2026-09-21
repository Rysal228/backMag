from datetime import date, datetime, time, timedelta

from django.utils import timezone

from orders.models import AppointmentSettings, Order, ScheduleBlock, WeekdaySchedule


class AppointmentAvailabilityService:
    @staticmethod
    def get_availability(target_date: date) -> dict:
        settings = AppointmentSettings.objects.first()

        if settings is None:
            settings = AppointmentSettings.objects.create()

        schedule = WeekdaySchedule.objects.filter(weekday=target_date.weekday()).first()

        if schedule is None or not schedule.is_working:
            return {
                'date': target_date,
                'working_hours': None,
                'appointment_duration': settings.appointment_duration,
                'slot_interval': settings.slot_interval,
                'busy_slots': [],
                'blocked_slots': [],
            }

        blocks = ScheduleBlock.objects.filter(date=target_date).order_by('start_time')

        busy_orders = (
            Order.objects
            .filter(appointment_at__date=target_date)
            .exclude(appointment_at__isnull=True)
            .order_by('appointment_at')
        )

        return {
            'date': target_date,
            'working_hours': {
                'from': schedule.start_time,
                'to': schedule.end_time,
            },
            'appointment_duration': settings.appointment_duration,
            'slot_interval': settings.slot_interval,
            'busy_slots': [
                {
                    'from': appointment.appointment_at.astimezone(timezone.get_current_timezone()).time(),
                    'to': (
                        appointment.appointment_at
                        + timedelta(minutes=settings.appointment_duration)
                    ).astimezone(timezone.get_current_timezone()).time(),
                }
                for appointment in busy_orders
            ],
            'blocked_slots': [
                {
                    'from': block.start_time,
                    'to': block.end_time,
                }
                for block in blocks
            ],
        }

    @staticmethod
    def is_slot_available(appointment_at: datetime) -> bool:
        settings = AppointmentSettings.objects.first()

        if settings is None:
            settings = AppointmentSettings.objects.create()

        local_datetime = timezone.localtime(appointment_at)
        target_date = local_datetime.date()
        schedule = WeekdaySchedule.objects.filter(weekday=target_date.weekday()).first()

        if schedule is None or not schedule.is_working:
            return False

        duration = timedelta(minutes=settings.appointment_duration)
        appointment_end = local_datetime + duration

        schedule_start = timezone.make_aware(
            datetime.combine(target_date, schedule.start_time),
            timezone.get_current_timezone(),
        )
        schedule_end = timezone.make_aware(
            datetime.combine(target_date, schedule.end_time),
            timezone.get_current_timezone(),
        )

        if local_datetime < schedule_start or appointment_end > schedule_end:
            return False

        if local_datetime <= timezone.now():
            return False

        for block in ScheduleBlock.objects.filter(date=target_date):
            block_start = timezone.make_aware(
                datetime.combine(target_date, block.start_time),
                timezone.get_current_timezone(),
            )
            block_end = timezone.make_aware(
                datetime.combine(target_date, block.end_time),
                timezone.get_current_timezone(),
            )

            if local_datetime < block_end and appointment_end > block_start:
                return False

        for order in (
            Order.objects
            .filter(appointment_at__date=target_date)
            .exclude(appointment_at__isnull=True)
        ):
            order_start = timezone.localtime(order.appointment_at)
            order_end = order_start + duration

            if local_datetime < order_end and appointment_end > order_start:
                return False

        return True
