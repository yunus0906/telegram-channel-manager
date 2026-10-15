import asyncio
import json
from typing import Any

from fastapi import WebSocket


class SocketPeer:
    def __init__(self, socket: WebSocket):
        self.socket = socket
        self.channels: set[str] = set()
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)


class EventHub:
    def __init__(self) -> None:
        self.peers: set[SocketPeer] = set()

    async def publish(self, event: dict[str, Any]) -> None:
        channel_id = event.get("channel_id")
        for peer in tuple(self.peers):
            if channel_id and channel_id not in peer.channels:
                continue
            if peer.queue.full():
                try:
                    peer.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            peer.queue.put_nowait(event)

    async def serve(self, socket: WebSocket) -> None:
        peer = SocketPeer(socket)
        self.peers.add(peer)

        async def sender() -> None:
            while True:
                await socket.send_json(await peer.queue.get())

        task = asyncio.create_task(sender())
        try:
            while True:
                raw = await socket.receive_text()
                data = json.loads(raw)
                if data.get("action") == "subscribe":
                    ids = data.get("channel_ids", [])
                    if isinstance(ids, list) and len(ids) <= 100 and all(isinstance(item, str) for item in ids):
                        peer.channels = set(ids)
                        await socket.send_json({"type": "subscribed", "channel_ids": ids})
        finally:
            task.cancel()
            self.peers.discard(peer)

