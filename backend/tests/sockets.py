"""Reading a connection until the service closes it, and saying which code it used.

A close at the handshake surfaces as `WebSocketDisconnect` from `aconnect_ws`
itself, which is what `test_websocket.py` asserts on. A close *during* the
connection surfaces from the next read and, because `httpx_ws` runs its reader
in a task group, arrives wrapped — so a test asserting on the code has to reach
through a group. Spelled once here rather than at each of the three close codes.
"""

import contextlib
from collections.abc import Iterator

from httpx_ws import AsyncWebSocketSession, WebSocketDisconnect


async def closed_with(ws: AsyncWebSocketSession, *, timeout: float = 5.0) -> int:
    """Read until the service hangs up, and answer with the code it hung up with.

    Frames that arrive first are drained rather than asserted about: a
    connection being closed for expiry has usually been warned first, and a test
    about the code should not have to count the frames before it.
    """
    try:
        while True:
            await ws.receive_json(timeout=timeout)
    except WebSocketDisconnect as closed:
        return closed.code


@contextlib.contextmanager
def ignoring_the_close() -> Iterator[None]:
    """Leaving an `aconnect_ws` block whose socket the service already closed.

    The reader task has recorded the disconnect, and the task group re-raises it
    on exit however the body ended. A test that has already asserted on the code
    has nothing left to learn from it.

    Only the disconnect is let through. Suppressing the whole group would also
    swallow the `TimeoutError` of a socket that was never closed, which is the
    failure these tests most need to see.
    """
    try:
        yield
    except BaseExceptionGroup as raised:
        _, unexpected = raised.split(WebSocketDisconnect)
        if unexpected is not None:
            raise unexpected from None
    except WebSocketDisconnect:
        pass
