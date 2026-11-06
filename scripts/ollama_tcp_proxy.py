import asyncio
import ipaddress
import logging

LISTEN_HOST = "172.30.0.1"
LISTEN_PORT = 11435
UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 11434
ALLOWED_NETWORK = ipaddress.ip_network("172.30.0.0/24")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass


async def handle_client(client_reader, client_writer):
    peer = client_writer.get_extra_info("peername")
    try:
        address = ipaddress.ip_address(peer[0])
        if address not in ALLOWED_NETWORK:
            logging.warning("拒绝非授权来源：%s", address)
            client_writer.close()
            await client_writer.wait_closed()
            return

        upstream_reader, upstream_writer = await asyncio.open_connection(
            UPSTREAM_HOST, UPSTREAM_PORT
        )
        logging.info("建立 Ollama 转发连接：%s", address)

        tasks = [
            asyncio.create_task(pipe(client_reader, upstream_writer)),
            asyncio.create_task(pipe(upstream_reader, client_writer)),
        ]
        _, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    except (ConnectionError, OSError, ValueError, IndexError) as exc:
        logging.warning("转发连接失败：%s", exc)
        client_writer.close()
        try:
            await client_writer.wait_closed()
        except ConnectionError:
            pass


async def main():
    server = await asyncio.start_server(
        handle_client, LISTEN_HOST, LISTEN_PORT
    )
    logging.info("Ollama 转发服务监听 %s:%s", LISTEN_HOST, LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
