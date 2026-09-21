from datetime import date, datetime, time, timedelta

from django.utils import timezone

from orders.models import AppointmentSettings, BusySlot, Order, ScheduleBlock, WeekdaySchedule


class AppointmentAvailabilityService:
    @staticmethod
    def _get_settings():
        settings = AppointmentSettings.objects.first()
        return settings or AppointmentSettings.objects.create()

    @classmethod
    def get_availability(cls, target_date: date) -> dict:
        settings = cls._get_settings()
        schedule = WeekdaySchedule.objects.filter(weekday=target_date.weekday()).first()

        if schedule is None or not schedule.is_working:
            return {
                'date': target_date,
                'day_type': 'nonWorking',
                'working_hours': None,
                'appointment_duration': settings.appointment_duration,
                'slot_interval': settings.slot_interval,
                'available_slots': [],
                'busy_slots': [],
                'blocked_slots': [],
            }

        duration = timedelta(minutes=settings.appointment_duration)
        current_local = timezone.localtime(timezone.now())
        start_minutes = schedule.start_time.hour * 60 + schedule.start_time.minute
        end_minutes = schedule.end_time.hour * 60 + schedule.end_time.minute
        last_slot_minutes = end_minutes - settings.appointment_duration

        blocks = ScheduleBlock.objects.filter(date=target_date).order_by('start_time')
        busy_slots = BusySlot.objects.filter(date=target_date).order_by('start_time')

        available_slots = []
        for start_minutes in range(start_minutes, last_slot_minutes + 1, settings.slot_interval):
            slot_start = time(hour=start_minutes // 60, minute=start_minutes % 60)
            slot_end_minutes = start_minutes + settings.appointment_duration
            slot_end = time(hour=slot_end_minutes // 60, minute=slot_end_minutes % 60)
            slot_datetime = timezone.make_aware(
                datetime.combine(target_date, slot_start),
                timezone.get_current_timezone(),
            )

            if slot_datetime <= current_local:
                continue

            if any(cls._overlaps(slot_start, slot_end, block.start_time, block.end_time) for block in blocks):
                continue

            if any(cls._overlaps(slot_start, slot_end, busy.start_time, busy.end_time) for busy in busy_slots):
                continue

            available_slots.append(slot_start.strftime('%H:%M'))

        return {
            'date': target_date,
            'day_type': 'working',
            'working_hours': {
                'from': schedule.start_time,
                'to': schedule.end_time,
            },
            'appointment_duration': settings.appointment_duration,
            'slot_interval': settings.slot_interval,
            'available_slots': available_slots,
            'busy_slots': [
                {'from': busy.start_time, 'to': busy.end_time}
                for busy in busy_slots
            ],
            'blocked_slots': [
                {'from': block.start_time, 'to': block.end_time}
                for block in blocks
            ],
        }

    @staticmethod
    def _overlaps(start: time, end: time, other_start: time, other_end: time) -> bool:
        return start < other_end and end > other_start

    @classmethod
    def is_slot_available(cls, appointment_at: datetime, exclude_order_id=None) -> bool:
        settings = cls._get_settings()
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

        if local_datetime <= timezone.localtime(timezone.now()):
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

        busy_query = BusySlot.objects.filter(date=target_date)
        if exclude_order_id is not None:
            busy_query = busy_query.exclude(order_id=exclude_order_id)

        for busy in busy_query:
            if cls._overlaps(local_datetime.time(), appointment_end.time(), busy.start_time, busy.end_time):
                return False

        return True

    @classmethod
    def sync_order_busy_slot(cls, order: Order):
        if order.appointment_at is None:
            BusySlot.objects.filter(order=order).delete()
            return None

        settings = cls._get_settings()
        local_datetime = timezone.localtime(order.appointment_at)
        end_datetime = local_datetime + timedelta(minutes=settings.appointment_duration)

        busy_slot, _ = BusySlot.objects.get_or_create(
            order=order,
            defaults={
                'date': local_datetime.date(),
                'start_time': local_datetime.time().replace(second=0, microsecond=0),
                'end_time': end_datetime.time().replace(second=0, microsecond=0),
            },
        )

        if busy_slot.date != local_datetime.date():
            busy_slot.date = local_datetime.date()

        busy_slot.start_time = local_datetime.time().replace(second=0, microsecond=0)
        busy_slot.end_time = end_datetime.time().replace(second=0, microsecond=0)
        busy_slot.full_clean()
        busy_slot.save()

        return busy_slot
