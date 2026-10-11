from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.exceptions import ValidationError
from .models import UserRole
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import (
    CustomUserSerializer,
    ProfileCustomUserSerializer,
)


User = get_user_model()


class CustomUserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = CustomUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        role = self.request.query_params.get('role')

        if not role:
            return queryset

        if role not in UserRole.values:
            raise ValidationError({
                'role': 'Invalid user role.',
            })

        queryset = queryset.filter(role_assignments__role=role).distinct()

        if role != UserRole.MECHANIC:
            return queryset

        search = self.request.query_params.get('search', '').strip()
        mechanic_ids = [
            value.strip()
            for value in self.request.query_params.get('ids', '').split(',')
            if value.strip()
        ]

        if not search and not mechanic_ids:
            return queryset.none()

        matching_users = None
        if search:
            matching_users = Q()
            for term in search.split():
                term_query = (
                    Q(first_name__icontains=term)
                    | Q(last_name__icontains=term)
                    | Q(patronymic__icontains=term)
                )
                digits = ''.join(character for character in term if character.isdigit())
                if digits:
                    term_query |= Q(phone__icontains=digits)
                matching_users &= term_query

        if mechanic_ids and matching_users is not None:
            queryset = queryset.filter(Q(id__in=mechanic_ids) | matching_users)
        elif mechanic_ids:
            queryset = queryset.filter(id__in=mechanic_ids)
        elif matching_users is not None:
            queryset = queryset.filter(matching_users)

        return queryset.order_by('last_name', 'first_name', 'patronymic')[:20]


class ProfileCustomUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = ProfileCustomUserSerializer(request.user, context={'request': request})

        return Response({
            'user': serializer.data,
        })

    def patch(self, request):
        serializer = ProfileCustomUserSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'user': serializer.data,
        })


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refreshToken')

        if not refresh_token:
            raise ValidationError({
                'refreshToken': 'Refresh token is required.',
            })

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            raise ValidationError({
                'refreshToken': 'Invalid refresh token.',
            })

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )
