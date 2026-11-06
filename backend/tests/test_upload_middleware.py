"""上传请求体大小限制中间件测试。"""

import pytest

from app.api.middleware import UploadRequestSizeLimitMiddleware

PATH = "/api/v1/knowledge-bases/1/documents"


async def run_asgi(middleware, messages, headers=None):
    """使用模拟 ASGI 消息执行中间件。"""
    received = iter(messages)
    responses = []

    async def receive():
        return next(received)

    async def send(message):
        responses.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": PATH,
        "headers": headers or [],
    }

    await middleware(scope, receive, send)
    return responses


async def successful_app(scope, receive, send):
    """模拟读取完整请求体的下游应用。"""
    while True:
        message = await receive()

        if message["type"] == "http.disconnect":
            return

        if not message.get("more_body", False):
            break

    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def response_status(responses):
    return next(item["status"] for item in responses if item["type"] == "http.response.start")


@pytest.mark.asyncio
async def test_upload_request_within_limit_is_allowed():
    """测试请求体未超过限制时正常通过。"""
    middleware = UploadRequestSizeLimitMiddleware(successful_app, 10)

    responses = await run_asgi(
        middleware,
        [{"type": "http.request", "body": b"1234567890", "more_body": False}],
    )

    assert response_status(responses) == 200


@pytest.mark.asyncio
async def test_upload_request_with_content_length_over_limit_is_rejected():
    """测试 Content-Length 超限时提前返回 413。"""
    middleware = UploadRequestSizeLimitMiddleware(successful_app, 10)

    responses = await run_asgi(
        middleware,
        [],
        headers=[(b"content-length", b"11")],
    )

    assert response_status(responses) == 413


@pytest.mark.asyncio
async def test_upload_request_without_content_length_is_counted():
    """测试没有 Content-Length 时仍然统计实际请求体。"""
    middleware = UploadRequestSizeLimitMiddleware(successful_app, 10)

    responses = await run_asgi(
        middleware,
        [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"78901", "more_body": False},
        ],
    )

    assert response_status(responses) == 413


@pytest.mark.asyncio
async def test_non_upload_request_is_not_limited():
    """测试其他 API 不受上传请求体限制影响。"""
    middleware = UploadRequestSizeLimitMiddleware(successful_app, 2)

    responses = []

    async def receive():
        return {"type": "http.request", "body": b"12345", "more_body": False}

    async def send(message):
        responses.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/other",
        "headers": [],
    }

    await middleware(scope, receive, send)

    assert response_status(responses) == 200


def test_middleware_rejects_invalid_size():
    """测试拒绝无效请求体大小配置。"""
    with pytest.raises(ValueError):
        UploadRequestSizeLimitMiddleware(successful_app, 0)

    with pytest.raises(ValueError):
        UploadRequestSizeLimitMiddleware(successful_app, True)


def test_testclient_rejects_oversized_multipart_before_route():
    """验证超限 multipart 请求在进入路由前被拒绝。"""
    from fastapi import FastAPI, File, UploadFile
    from fastapi.testclient import TestClient

    app = FastAPI()
    calls = []

    app.add_middleware(
        UploadRequestSizeLimitMiddleware,
        max_size_bytes=128,
    )

    @app.post(PATH)
    async def upload(file: UploadFile = File(...)):
        calls.append(file.filename)
        return {"size": len(await file.read())}

    with TestClient(app) as client:
        response = client.post(
            PATH,
            files={"file": ("large.txt", b"x" * 256, "text/plain")},
        )

    assert response.status_code == 413
    assert calls == []


def test_testclient_accepts_valid_multipart_upload():
    """验证正常 multipart 请求可以进入上传路由。"""
    from fastapi import FastAPI, File, UploadFile
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(
        UploadRequestSizeLimitMiddleware,
        max_size_bytes=1024,
    )

    @app.post(PATH)
    async def upload(file: UploadFile = File(...)):
        return {"size": len(await file.read())}

    with TestClient(app) as client:
        response = client.post(
            PATH,
            files={"file": ("small.txt", b"hello", "text/plain")},
        )

    assert response.status_code == 200
    assert response.json() == {"size": 5}


@pytest.mark.asyncio
async def test_upload_request_at_exact_limit_is_allowed():
    """测试请求体恰好达到上限时允许通过。"""
    middleware = UploadRequestSizeLimitMiddleware(successful_app, 10)

    responses = await run_asgi(
        middleware,
        [{"type": "http.request", "body": b"1234567890", "more_body": False}],
        headers=[(b"content-length", b"10")],
    )

    assert response_status(responses) == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("content_length", [b"invalid", b"-1"])
async def test_invalid_content_length_falls_back_to_actual_size(content_length):
    """测试非法 Content-Length 不绕过实际请求体大小检查。"""
    middleware = UploadRequestSizeLimitMiddleware(successful_app, 10)

    responses = await run_asgi(
        middleware,
        [{"type": "http.request", "body": b"x" * 11, "more_body": False}],
        headers=[(b"content-length", content_length)],
    )

    assert response_status(responses) == 413


@pytest.mark.asyncio
async def test_similar_path_suffix_is_not_treated_as_upload():
    """测试其他以 documents 结尾的路径不应被误认为上传接口。"""
    middleware = UploadRequestSizeLimitMiddleware(successful_app, 2)
    responses = []

    async def receive():
        return {"type": "http.request", "body": b"12345", "more_body": False}

    async def send(message):
        responses.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/other/documents",
        "headers": [],
    }

    await middleware(scope, receive, send)

    assert response_status(responses) == 200
