"""Backend package initialization with Python 3.14 compatibility shim."""

import asyncio
import inspect

if hasattr(asyncio, "iscoroutinefunction"):
    asyncio.iscoroutinefunction = inspect.iscoroutinefunction
