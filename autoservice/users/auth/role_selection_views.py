from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .role_selection import RoleSelectionService
from .role_selection_serializers import RoleSelectionSerializer
from .tokens import create_auth_tokens, create_max_auth_tokens

User = get_user_model()


class RoleSelectionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RoleSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = RoleSelectionService.load_token(
            serializer.validated_data['selection_token'],
        )

        user = User.objects.filter(
            pk=payload['user_id'],
            is_active=True,
        ).first()

        if user is None:
            raise AuthenticationFailed(
                'Пользователь больше не может войти в систему.'
            )

        role = serializer.validated_data['role']

        if not user.has_role(role):
            raise ValidationError({
                'role': 'Выбранная роль недоступна для этого пользователя.',
            })

        if payload['auth_method'] == 'max':
            if (
                payload.get('messenger_user_id') != user.messenger_user_id
                or payload.get('max_verified_phone') != user.phone
            ):
                raise AuthenticationFailed(
                    'MAX-сессия больше не действительна.'
                )

            tokens = create_max_auth_tokens(
                user,
                messenger_user_id=user.messenger_user_id,
                max_verified_phone=user.phone,
                active_role=role,
            )
        else:
            tokens = create_auth_tokens(
                user,
                active_role=role,
            )

        return Response(tokens, status=status.HTTP_200_OK)
