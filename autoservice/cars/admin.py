from django.contrib import admin

from cars.models import Car, CarBrand, CarModel


@admin.register(CarBrand)
class CarBrandAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(CarModel)
class CarModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'brand')
    search_fields = ('name',)
    list_filter = ('brand',)

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    model = Car

    list_display = (
        'brand',
        'model',
        'year',
        'owner',
    )

    search_fields = (
        'brand',
        'model',
        'vin',
        'plate_number',
    )