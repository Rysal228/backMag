"""Contract for a future Russian acquiring provider; deliberately no live adapter.

The adapter must use server-side credentials, create payments with an
idempotency key, and verify provider status independently of redirect URLs.
It must not accept card numbers or CVV from the application.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class PaymentSession:
    external_id: str
    redirect_url: str
    status: str


class PaymentProvider(Protocol):
    def create(self, *, order_id: UUID, amount: Decimal, idempotency_key: UUID) -> PaymentSession:
        ...

    def retrieve(self, external_id: str) -> dict:
        ...


class ProviderNotConfigured(RuntimeError):
    pass


def get_payment_provider() -> PaymentProvider:
    # Fail closed. A live provider and its signed notification/status check
    # must be reviewed, tested, and enabled through a separate PR.
    raise ProviderNotConfigured("Интернет-эквайринг пока не подключён.")
