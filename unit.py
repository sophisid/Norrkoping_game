'''
This program is designed to run on the Raspberry Pi.
The program is used as a controller and interface to the low-level
components of the game, i.e. the button, its backlight and the LED matrix.
'''

import asyncio
from asyncio import PriorityQueue, Event

from websockets.client import connect
from websockets.client import WebSocketClientProtocol

from gpiozero import Button, RGBLED

from rpi_ws281x import PixelStrip

from enum import IntEnum
from typing import Optional, Callable

LED_COUNT = 16      # Number of LED pixels.
LED_PIN = 21        # GPIO pin connected to the pixels (21 uses PCM).


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


async def button_led_control(led: RGBLED, queue: PriorityQueue, exit: Event):
    command = await queue.get()


async def led_matrix_control(matrix: PixelStrip, queue: PriorityQueue, exit: Event):
    command = await queue.get()


async def sound_control(queue: PriorityQueue, exit: Event):
    command = await queue.get()


async def dispatch_message(ws, message):
    pass


async def register(ws):
    print("Open connection")


async def recv_server(socket: WebSocketClientProtocol, exit: Event):
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
    led_matrix = PixelStrip(LED_COUNT, LED_PIN)

    button_led_queue = asyncio.PriorityQueue()
    led_matrix_queue = asyncio.PriorityQueue()
    sound_queue = asyncio.PriorityQueue()

    exit_event = asyncio.Event()

    led_matrix.begin()

    async with connect("ws://139.91.81.218:8001") as socket:
        button.when_pressed = lambda: button_pressed(socket)
        button.when_released = lambda: button_released(socket)
        await asyncio.gather(recv_server(socket, exit_event),
                             button_led_control(
                                 button_led, button_led_queue, exit_event),
                             led_matrix_control(
                                 led_matrix, led_matrix_queue, exit_event),
                             sound_control(sound_queue, exit_event))


if __name__ == "__main__":
    asyncio.run(main())
