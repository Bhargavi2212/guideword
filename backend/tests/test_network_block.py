"""conftest.py blocks every non-loopback connection; loopback stays open (spec 0.1)."""

import asyncio
import socket

import pytest


def test_non_loopback_connect_raises() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s, pytest.raises(RuntimeError):
        s.connect(("93.184.216.34", 80))


def test_non_loopback_connect_ex_raises() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s, pytest.raises(RuntimeError):
        s.connect_ex(("8.8.8.8", 53))


def test_asyncio_loop_starts() -> None:
    async def answer() -> int:
        await asyncio.sleep(0)
        return 42

    assert asyncio.run(answer()) == 42


def test_loopback_connect_allowed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(server.getsockname())
