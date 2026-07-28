"""The CP-SAT solve must not block the asyncio event loop.

A blocked loop means one user's 40s generate freezes health checks, login and
every other in-flight request on that Cloud Run instance.
"""

import asyncio
import time

import pytest

from app.services import layout_store


@pytest.mark.asyncio
async def test_solve_layouts_async_does_not_block_event_loop(monkeypatch):
    def slow_generate(cfg):
        time.sleep(0.5)  # stands in for a real CP-SAT solve
        return ["layout"]

    monkeypatch.setattr(layout_store, "generate", slow_generate)

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(20):
            await asyncio.sleep(0.02)
            ticks += 1

    result, _ = await asyncio.gather(
        layout_store.solve_layouts_async(object()),
        ticker(),
    )

    assert result == ["layout"]
    # With the solve on the loop, the ticker cannot advance at all during the
    # 0.5s sleep. Off-loop it should complete nearly all 20 ticks.
    assert ticks >= 15, f"event loop was blocked during solve (ticks={ticks})"
