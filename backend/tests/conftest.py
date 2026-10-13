"""Blocks every non-loopback network connection in every test.

Loopback stays open: asyncio on Windows builds its event loop from a localhost
socketpair(), and FastAPI's TestClient needs it.
"""

import socket
from collections.abc import Iterator
from typing import Any

import pytest

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_loopback(address: Any) -> bool:
    if isinstance(address, tuple) and address:
        return str(address[0]) in LOOPBACK_HOSTS
    # AF_UNIX paths and other non-IP addresses never leave the machine.
    return isinstance(address, str | bytes)


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(self: socket.socket, address: Any) -> None:
        if not _is_loopback(address):
            raise RuntimeError(f"network access blocked in tests: {address!r}")
        real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> int:
        if not _is_loopback(address):
            raise RuntimeError(f"network access blocked in tests: {address!r}")
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield
