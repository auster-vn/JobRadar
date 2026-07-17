import asyncio
from collections.abc import Coroutine
from typing import Any

_runner: asyncio.Runner | None = None


def run_async[Result](awaitable: Coroutine[Any, Any, Result]) -> Result:
    """Run worker coroutines on one event loop per prefork child process."""
    global _runner
    if _runner is None:
        _runner = asyncio.Runner()
    return _runner.run(awaitable)
