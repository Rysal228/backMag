from rest_framework import viewsets

from cars.models import Car, CarBrand, CarModel
from cars.serializers import CarSerializer, CarBrandSerializer, CarModelSerializer

class CarBrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CarBrand.objects.all()
    serializer_class = CarBrandSerializer


class CarModelViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CarModelSerializer

    def get_queryset(self):
        queryset = CarModel.objects.all()

        brand_id = self.request.query_params.get('brand')

        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)

        return queryset

class CarViewSet(viewsets.ModelViewSet):
    queryset = Car.objects.all()
    serializer_class = CarSerializer
