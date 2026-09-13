"""本机 SSE 集成探针；独立事件循环中检查退出时生成器清理。"""

import asyncio
import json
import sys
from contextlib import aclosing
from tui_agent.llm.openai_compat import OpenAICompatProvider


async def main(mode):
    errors = []
    handlers = set()
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(lambda _, context: errors.append(context))

    async def serve(reader, writer):
        handlers.add(asyncio.current_task())
        try:
            await reader.readuntil(b"\r\n\r\n")
            chunk = {"id": "test", "object": "chat.completion.chunk", "created": 0,
                     "model": "test", "choices": [{"index": 0, "delta": {"content": "hello"}, "finish_reason": None}]}
            end = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            body = ("data: " + json.dumps(chunk) + "\n\ndata: " + json.dumps(end) + "\n\ndata: [DONE]\n\n").encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(asyncio.current_task())

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    async with server:
        provider = OpenAICompatProvider("fake", f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1", "test", max_retries=0)
        try:
            async with aclosing(provider.chat([{"role": "user", "content": "hi"}])) as stream:
                async for event in stream:
                    if mode == "early" or event["type"] == "finish":
                        break
        finally:
            await provider.aclose()
        # 与 asyncio.run 的最终收尾一致，不能靠 GC 或延迟掩盖并发关闭异常。
        await loop.shutdown_asyncgens()
    if handlers:
        await asyncio.gather(*handlers)
    assert not errors, [(e.get("message"), repr(e.get("exception"))) for e in errors]
    print(mode + ": clean shutdown")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
