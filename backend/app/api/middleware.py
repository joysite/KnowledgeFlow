"""KnowledgeFlow API 请求安全中间件。"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

ASGIApp = Callable[[dict[str, Any], Callable, Callable], Awaitable[None]]


class UploadRequestSizeLimitMiddleware:
    """限制文档上传请求体大小，不缓存完整请求体。"""

    UPLOAD_PATH_PREFIX = "/api/v1/knowledge-bases/"
    UPLOAD_PATH_SUFFIX = "/documents"

    def __init__(
        self,
        app: ASGIApp,
        max_size_bytes: int,
    ) -> None:
        """初始化请求体大小限制。"""
        if (
            isinstance(max_size_bytes, bool)
            or not isinstance(max_size_bytes, int)
            or max_size_bytes <= 0
        ):
            raise ValueError("max_size_bytes 必须是正整数")

        self.app = app
        self.max_size_bytes = max_size_bytes

    async def _send_too_large(self, send: Callable) -> None:
        """返回统一的 413 响应。"""
        body = json.dumps(
            {"detail": "上传请求体超过允许大小"},
            ensure_ascii=False,
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        """统计上传请求体实际大小，超限时提前终止处理。"""
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        path_parts = scope["path"].strip("/").split("/")
        is_upload_path = (
            scope["path"].startswith(self.UPLOAD_PATH_PREFIX)
            and len(path_parts) == 5
            and path_parts[0:3] == ["api", "v1", "knowledge-bases"]
            and path_parts[3].isdigit()
            and int(path_parts[3]) > 0
            and path_parts[4] == self.UPLOAD_PATH_SUFFIX.removeprefix("/")
        )

        if not is_upload_path:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")

        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0

            if declared_size > self.max_size_bytes:
                await self._send_too_large(send)
                return

        received_size = 0
        rejected = False

        async def limited_receive() -> dict[str, Any]:
            """逐块统计实际请求体大小。"""
            nonlocal received_size, rejected

            message = await receive()

            if message["type"] == "http.request":
                received_size += len(message.get("body", b""))

                if received_size > self.max_size_bytes:
                    rejected = True
                    await self._send_too_large(send)
                    return {"type": "http.disconnect"}

            return message

        async def limited_send(message: dict[str, Any]) -> None:
            """请求超限后阻止下游重复发送响应。"""
            if not rejected:
                await send(message)

        try:
            await self.app(scope, limited_receive, limited_send)
        except Exception:
            if not rejected:
                raise
