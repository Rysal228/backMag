"""Profile gateway. 1C owns the profile; Django authenticates the request only."""

from rest_framework import permissions, serializers
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.services.onec_users import OneCUserServiceError, OneCUsersClient


class OneCProfilePatchSerializer(serializers.Serializer):
    # Validate the HTTP envelope here; business rules are enforced in 1C.
    firstName = serializers.CharField(required=False, allow_blank=True)
    lastName = serializers.CharField(required=False, allow_blank=True)
    patronymic = serializers.CharField(required=False, allow_blank=True)
    birthday = serializers.DateField(required=False, allow_null=True)


class OneCProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    writable_fields = frozenset({"firstName", "lastName", "patronymic", "birthday"})

    @staticmethod
    def _check_identity(request, user):
        # The native catalog UUID is the only application-user identity.
        if (
            user.get("onecId") != str(request.user.pk)
            or user.get("phone") != request.user.phone.strip().removeprefix("+")
        ):
            raise OneCUserServiceError(
                "onec_identity_mismatch",
                "Идентификатор пользователя в 1С не совпадает с сессией.",
                status_code=502,
            )
        if user.get("isActive") is not True:
            raise AuthenticationFailed("Пользователь деактивирован в 1С.")

        roles = user.get("roles")
        if not isinstance(roles, list) or any(
            role not in ("user", "mechanic", "admin") for role in roles
        ):
            raise OneCUserServiceError(
                "onec_invalid_roles", "1С вернула некорректные роли."
            )
        active_role = getattr(request, "active_role", None)
        if active_role is not None and active_role not in roles:
            raise AuthenticationFailed("Активная роль больше не назначена в 1С.")

    @staticmethod
    def _to_frontend(request, user):
        # Keep the existing Angular profile response contract.
        return {
            "id": user["onecId"],
            "phone": user["phone"],
            "firstName": user.get("firstName", ""),
            "lastName": user.get("lastName", ""),
            "patronymic": user.get("patronymic", ""),
            "birthday": user.get("birthday"),
            "roles": user["roles"],
            "activeRole": getattr(request, "active_role", None),
        }

    def get(self, request):
        user = OneCUsersClient().get_user(request.user.phone)
        self._check_identity(request, user)
        return Response({"user": self._to_frontend(request, user)})

    def patch(self, request):
        if not hasattr(request.data, "keys"):
            raise ValidationError({"profile": "Ожидается JSON-объект."})
        unknown = set(request.data.keys()) - self.writable_fields
        if unknown:
            raise ValidationError({
                "profile": "Нельзя изменить поля: " + ", ".join(sorted(unknown))
            })

        serializer = OneCProfilePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise ValidationError({"profile": "Не указаны поля для изменения."})

        client = OneCUsersClient()
        current = client.get_user(request.user.phone)
        self._check_identity(request, current)

        payload = dict(serializer.validated_data)
        if "birthday" in payload and payload["birthday"] is not None:
            payload["birthday"] = payload["birthday"].isoformat()
        updated = client.patch_user(request.user.phone, payload)
        self._check_identity(request, updated)
        # No request.user.save(), no Django profile mirrors, no local writes.
        return Response({"user": self._to_frontend(request, updated)})
