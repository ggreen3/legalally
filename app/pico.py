from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import websockets

from .config import settings


async def stream_pico(
    app_id: str,
    prompt: str,
    on_chunk: Callable[[str], Awaitable[None]],
) -> str:
    chunks: list[str] = []

    async def relay() -> None:
        async with websockets.connect(
            settings.pico_ws_url,
            open_timeout=10,
            close_timeout=5,
        ) as upstream:
            await upstream.send(
                json.dumps(
                    {
                        "appId": app_id,
                        "prompt": prompt[: settings.pico_max_prompt_chars],
                    }
                )
            )
            async for message in upstream:
                text = message.decode("utf-8", "ignore") if isinstance(message, bytes) else str(message)
                if not text.strip():
                    continue
                chunks.append(text)
                await on_chunk(text)

    await asyncio.wait_for(relay(), timeout=settings.pico_stream_timeout_seconds)
    answer = "".join(chunks).strip()
    if not answer:
        raise RuntimeError("empty pico response")
    return answer
