from collections.abc import Mapping, Sequence

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


DEFAULT_MESSAGE = 'Произошла ошибка при выполнении запроса.'
VALIDATION_MESSAGE = 'Проверьте корректность введённых данных.'
SERVER_ERROR_MESSAGE = 'Произошла внутренняя ошибка сервера.'


def _stringify(value):
    if isinstance(value, Mapping):
        return {str(key): _stringify(item) for key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_stringify(item) for item in value]

    return str(value)


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is None:
        return Response(
            {
                'code': 'internal_server_error',
                'message': SERVER_ERROR_MESSAGE,
                'details': None,
            },
            status=500,
        )

    data = _stringify(response.data)
    code = getattr(exc, 'default_code', 'api_error')

    if isinstance(data, dict) and 'detail' in data:
        message = data['detail']
        details = None

        extra_details = {
            key: value
            for key, value in data.items()
            if key != 'detail'
        }

        if extra_details:
            details = extra_details
    elif isinstance(data, (dict, list)):
        message = VALIDATION_MESSAGE
        details = data
    else:
        message = str(data) if data else DEFAULT_MESSAGE
        details = None

    return Response(
        {
            'code': code,
            'message': message,
            'details': details,
        },
        status=response.status_code,
        headers=response.headers,
    )
