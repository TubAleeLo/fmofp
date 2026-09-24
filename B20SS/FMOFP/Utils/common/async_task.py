"""Safe teardown for a task that may belong to another event loop.

Several response services capture whichever loop was running when their
start() was awaited and create self._task on it. Their stop() then ran
`await self._task`, which is only legal from that same loop -- and by shutdown
time that loop may not be running at all, in which case there is no loop the
await is legal on. Awaiting from the shutdown loop raised

    RuntimeError: ... got Future <Task ...> attached to a different loop

on every shutdown of the affected service. See
fmofp-finding-crossloop-task-await.md; the identical shape existed in seven
services, so it lives here once rather than seven times.
"""

import asyncio

from FMOFP.Utils.logger.sys_logger import get_logger

logger = get_logger()


async def cancel_and_await(task, label):
    """Cancel task, and await it only when the running loop owns it.

    Awaiting a task from a loop that does not own it raises RuntimeError, and a
    task whose own loop has stopped can never be awaited at all. In both cases
    the cancellation has still been requested; the task simply cannot be
    joined from here, which is logged rather than raised.
    """
    if task is None:
        return

    task.cancel()

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    try:
        task_loop = task.get_loop()
    except Exception:
        task_loop = None

    if running is not None and task_loop is running:
        try:
            await task
        except asyncio.CancelledError:
            pass
        return

    logger.warning(
        f"{label}: task belongs to a different event loop "
        f"(running={running!r}, task={task_loop!r}); cancelled without awaiting"
    )
