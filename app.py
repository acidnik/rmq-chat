import asyncio
import logging
import sys
from typing import Dict
from aio_pika import ExchangeType, Message, connect
from aio_pika.abc import AbstractIncomingMessage
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseSettings
import uvicorn
from fastapi.staticfiles import StaticFiles

logging.basicConfig(stream=sys.stdout, level='DEBUG', format='%(asctime)s | [%(levelname)s] | %(name)s | %(message)s')


logger = logging.getLogger()

app = FastAPI()
app.mount('/static', StaticFiles(directory='static'), name='static')

class Settings(BaseSettings):
    AMQP_URL: str
    CHAT_EXCHANGE: str = 'chat'
    PORT: int

settings = Settings()


class WSChat:
    """
    Работа с веб-сокетами
    """

    _clients: Dict[int, WebSocket] = {}

    def __init__(self, ws: WebSocket, sender):
        self._ws = ws
        self._sender = sender
        WSChat._clients[id(ws)] = ws

    @classmethod
    async def send(cls, message: str):
        """
        отправляем сообщение во все подключенные веб-сокеты
        """
        for ws in WSChat._clients.values():
            await ws.send_text(message)

    async def response(self):
        """
        цикл обработки сообщений из веб-сокета
        """
        await self._ws.accept()
        try:
            while True:
                message = await self._ws.receive_text()
                await self._sender.send(message)
        except WebSocketDisconnect:
            logger.info(f"client disconnected")
            del WSChat._clients[id(self._ws)]

class WSChatRMQ:
    """
    работа с rmq
    """
    def __init__(self):
        pass

    async def setup(self):
        while True:
            try:
                connection = await connect(settings.AMQP_URL)
                channel = await connection.channel()
                exchange = await channel.declare_exchange('wschat', ExchangeType.FANOUT, durable=True)
                queue = await channel.declare_queue(exclusive=True)
                
                async def on_message(message: AbstractIncomingMessage):
                    """
                    при получении сообщения из rmq - отправляем его всем подключенным клиентам
                    """
                    async with message.process():
                        await WSChat.send(message.body.decode())

                await queue.bind(exchange)
                await queue.consume(on_message)

                self.exchange = exchange
                
                return
            except Exception as e:
                logger.exception('failed to connect to rmq')
                await asyncio.sleep(0.3)

    async def send(self, message: str):
        await self.exchange.publish(Message(message.encode()), routing_key='')
            

@app.on_event('startup')
async def setup_rmq():
    app.state.rmq = WSChatRMQ()
    await app.state.rmq.setup()


@app.websocket('/chat')
async def chat(ws: WebSocket):
    await WSChat(ws, ws.app.state.rmq).response()

if __name__ == '__main__':
    uvicorn.run('app:app', host='0.0.0.0', port=settings.PORT)