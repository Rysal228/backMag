from rest_framework import serializers

from orders.models import Order, WorkType, OrderStatus

class WorkTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = WorkType
        fields = (
            'id',
            'name',
        )


class OrderStatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderStatus
        fields = (
            'id',
            'name',
        )


class OrderSerializer(serializers.ModelSerializer):

    class Meta:
        model = Order
        fields = '__all__'