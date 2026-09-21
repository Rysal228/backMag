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
                'first_slot': None,
                'last_slot': None,
                'busy_slots': [],
                'blocked_slots': [],
            }

        duration = timedelta(minutes=settings.appointment_duration)
        last_slot_minutes = (
            schedule.end_time.hour * 60
            + schedule.end_time.minute
            - settings.appointment_duration
        )
        first_slot_minutes = schedule.start_time.hour * 60 + schedule.start_time.minute
        current_local = timezone.localtime(timezone.now())

        if target_date == current_local.date():
            current_minutes = current_local.hour * 60 + current_local.minute
            current_seconds = current_local.second
            start_minutes = first_slot_minutes

            if current_minutes > first_slot_minutes or current_seconds:
                elapsed_seconds = (current_minutes - first_slot_minutes) * 60 + current_seconds
                interval_seconds = settings.slot_interval * 60
                intervals = max(0, (elapsed_seconds + interval_seconds - 1) // interval_seconds)
                start_minutes += intervals * settings.slot_interval

            first_slot = (
                time(hour=start_minutes // 60, minute=start_minutes % 60)
                if start_minutes <= last_slot_minutes
                else None
            )
        else:
            first_slot = schedule.start_time if first_slot_minutes <= last_slot_minutes else None

        last_slot = (
            time(hour=last_slot_minutes // 60, minute=last_slot_minutes % 60)
            if first_slot is not None
            else None
        )

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
            'first_slot': first_slot,
            'last_slot': last_slot,
            'busy_slots': [
                {
                    'from': appointment.appointment_at.astimezone(timezone.get_current_timezone()).time(),
                    'to': (
                        appointment.appointment_at
                        + duration
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

        elapsed_minutes = int((local_datetime - schedule_start).total_seconds() // 60)
        if local_datetime.second or local_datetime.microsecond or elapsed_minutes % settings.slot_interval:
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
