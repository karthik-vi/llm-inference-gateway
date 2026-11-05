"""Fake llama-server: streams 32 tokens with ~1 ms spacing, so measured latency = gateway cost."""
from __future__ import annotations

import asyncio
import json
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()


@app.post("/v1/chat/completions")
async def chat() -> StreamingResponse:
    async def gen():
        for i in range(32):
            await asyncio.sleep(0.001)
            yield ("data: " + json.dumps({"choices": [{"delta": {"content": f"t{i} "}}]}) + "\n\n").encode()
        yield ("data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": 200,
               "completion_tokens": 32}, "timings": {"prompt_n": 50, "cache_n": 150}}) + "\n\n").encode()
        yield b"data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="error")
