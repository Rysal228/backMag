from rest_framework import permissions, viewsets

from cars.models import Car, CarBrand, CarModel
from cars.serializers import CarSerializer, CarBrandSerializer, CarModelSerializer


class CarBrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CarBrand.objects.all().order_by('name')
    serializer_class = CarBrandSerializer
    permission_classes = [permissions.IsAuthenticated]


class CarModelViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CarModelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = CarModel.objects.select_related('brand').all().order_by('name')
        brand_id = self.request.query_params.get('brand')

        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)

        return queryset


class CarViewSet(viewsets.ModelViewSet):
    serializer_class = CarSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Car.objects
            .filter(owner=self.request.user)
            .select_related('brand', 'model')
            .order_by('brand__name', 'model__name')
        )

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
