from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from rest_framework.exceptions import ValidationError as DRFValidationError

from .auth.services import PhoneNormalizer
from .models import CustomUser


class PhoneNormalizationMixin:
    def clean_phone(self):
        try:
            return PhoneNormalizer.normalize(self.cleaned_data['phone'])
        except DRFValidationError as error:
            detail = error.detail

            if isinstance(detail, dict) and 'phone' in detail:
                message = detail['phone']
                if isinstance(message, list):
                    message = message[0]

                raise forms.ValidationError(message)

            raise forms.ValidationError('Введите корректный номер телефона.')


class CustomUserCreationForm(PhoneNormalizationMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser

        fields = UserCreationForm.Meta.fields + (
            'last_name',
            'first_name',
            'patronymic',
            'birthday',
        )


class CustomUserChangeForm(PhoneNormalizationMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = CustomUser

        fields = UserCreationForm.Meta.fields + (
            'last_name',
            'first_name',
            'patronymic',
            'birthday',
        )
