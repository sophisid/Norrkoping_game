'''
This program is designed to run on the Raspberry Pi.
The program is used as a controller and interface to the low-level
components of the game, i.e. the button, its backlight and the LED matrix.
'''

import asyncio
from asyncio import PriorityQueue

from websockets.client import connect
from websockets.client import WebSocketClientProtocol

from gpiozero import Button, RGBLED


async def button_led_control(queue: PriorityQueue):
from enum import IntEnum
from typing import Optional, Callable



class controller():
    STATES = IntEnum('States', ['IDLE', 'RUNNING'])

    def __init__(self) -> None:
        self.state = controller.STATES.IDLE
        self.sleep_task: Optional[asyncio.Task] = None

    async def _cancellable_sleep(self, delay: float, result=None):
        await asyncio.sleep(delay, result)

    async def start(self, control: Callable[..., None], *args) -> None:
        self.state = controller.STATES.RUNNING

        while self.state == controller.STATES.RUNNING:
            control(args)
            self.sleep_task = asyncio.create_task(self._cancellable_sleep(0.1))

    def stop(self) -> None:
        if self.sleep_task:
            try:
                self.sleep_task.cancel()
            except asyncio.CancelledError:
                pass

        self.state = controller.STATES.IDLE


    command = await queue.get()


async def led_matrix_control(queue: PriorityQueue):
    command = await queue.get()


async def sound_control(queue: PriorityQueue):
    command = await queue.get()


async def dispatch_message(ws, message):
    pass


async def register(ws):
    print("Open connection")


async def recv_server(socket: WebSocketClientProtocol):
    while not socket.closed:
        message = await socket.recv()
        await dispatch_message(socket, message)


async def send_server(socket: WebSocketClientProtocol, message: bytes):
    await socket.send(message)


def button_pressed(ws: WebSocketClientProtocol):
    asyncio.run(send_server(ws, b"Button pressed"))


def button_released(ws: WebSocketClientProtocol):
    asyncio.run(send_server(ws, b"Button released"))


async def main():
    ''' The main function for the unit '''

    # Initialize the hardware interface
    button: Button = Button(26)
    button_led: RGBLED = RGBLED(17, 27, 22)

    button_led_queue = asyncio.PriorityQueue()
    led_matrix_queue = asyncio.PriorityQueue()
    sound_queue = asyncio.PriorityQueue()

    async with connect("ws://139.91.81.218:8001") as socket:
        button.when_pressed = lambda: button_pressed(socket)
        button.when_released = lambda: button_released(socket)
        await asyncio.gather(recv_server(socket),
                             button_led_control(button_led_queue),
                             led_matrix_control(led_matrix_queue),
                             sound_control(sound_queue))


if __name__ == "__main__":
    asyncio.run(main())
