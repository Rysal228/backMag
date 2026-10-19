"""Choose the current native-1C role after password or MAX authentication."""
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.services.onec_users import OneCUsersClient
from .identity import user_from_profile
from .role_selection import RoleSelectionService
from .role_selection_serializers import RoleSelectionSerializer
from .tokens import create_auth_tokens, create_max_auth_tokens


class RoleSelectionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RoleSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = RoleSelectionService.load_token(
            serializer.validated_data["selection_token"],
        )
        profile = OneCUsersClient().get_user_by_onec_id(payload["user_id"])
        user = user_from_profile(profile)

        role = serializer.validated_data["role"]
        if not user.has_role(role):
            raise ValidationError({
                "role": "Выбранная роль недоступна для этого пользователя.",
            })

        if payload["auth_method"] == "max":
            messenger = payload.get("messenger_user_id", "")
            verified_phone = payload.get("max_verified_phone", "")
            if (
                not messenger
                or messenger != profile.get("messengerUserId")
                or verified_phone != user.phone
            ):
                raise AuthenticationFailed("MAX-сессия больше не действительна.")

            from .max.services import MaxAuthService
            MaxAuthService.validate_current_binding(
                user=user, messenger_user_id=messenger,
                max_verified_phone=verified_phone,
            )
            tokens = create_max_auth_tokens(
                user, messenger_user_id=messenger,
                max_verified_phone=verified_phone, active_role=role,
            )
        elif payload["auth_method"] == "password":
            tokens = create_auth_tokens(user, active_role=role)
        else:
            raise AuthenticationFailed("Сессия выбора роли недействительна.")

        return Response(tokens, status=status.HTTP_200_OK)
