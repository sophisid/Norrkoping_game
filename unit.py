'''
This program is designed to run on the Raspberry Pi.
The program is used as a controller and interface to the low-level
components of the game, i.e. the button, its backlight and the LED matrix.
'''

import asyncio
from asyncio import PriorityQueue, Event
from itertools import cycle
import json

from websockets.client import connect
from websockets.client import WebSocketClientProtocol

from gpiozero import Button, RGBLED
from colorzero import Color, Hue

from rpi_ws281x import PixelStrip

import pygame

from enum import IntEnum
from typing import Optional
from abc import ABC, abstractmethod

LED_COUNT = 16      # Number of LED pixels.
LED_PIN = 21        # GPIO pin connected to the pixels (21 uses PCM).


class Controller(ABC):
    STATES = IntEnum('States', ['IDLE', 'RUNNING'])

    def __init__(self) -> None:
        self.state = Controller.STATES.IDLE
        self.task: Optional[asyncio.Task] = None

    @abstractmethod
    async def _run(self, *args):
        raise NotImplementedError(
            "You have to override this function in the derivative")

    async def start(self, *args):
        await self.stop()
        self.state = Controller.STATES.RUNNING

        self.task = asyncio.create_task(self._run(*args))

    async def stop(self) -> None:
        if self.task:
            try:
                self.task.cancel()
                await self.task

                self.task = None
            except asyncio.CancelledError:
                pass

        self.state = Controller.STATES.IDLE

    @abstractmethod
    async def off(self):
        ...

    async def __aenter__(self):
        return self

    async def __aexit__(self, type, value, traceback):
        await self.off()


class ButtonLEDController(Controller):
    def __init__(self, led: RGBLED):
        super().__init__()
        self.i = 0
        self.pattern = ["A", "B"]
        self.led = led

    async def _run(self, *args):
        while self.state == Controller.STATES.RUNNING:
            print(self.pattern[self.i])
            self.i= (self.i+1) % len(self.pattern)
            await asyncio.sleep(0.1)

class MatrixLEDController(Controller):
    def __init__(self, matrix: PixelStrip):
        super().__init__()
        self.i = 0
        self.pattern = ["C", "D"]
        self.matrix = matrix

    async def _run(self, *args):
        while self.state == Controller.STATES.RUNNING:
            print(self.pattern[self.i])
            self.i= (self.i+1) % len(self.pattern)
            await asyncio.sleep(0.1)


async def button_led_control(led: RGBLED, queue: PriorityQueue[str], exit: Event):
    async with ButtonLEDController(led) as controller:
        while not exit.is_set():
            command = await queue.get()

            if command == "START":
                controller.start()
            elif command == "STOP":
                await controller.stop()


async def led_matrix_control(matrix: PixelStrip, queue: PriorityQueue[str], exit: Event):
    async with MatrixLEDController(matrix) as controller:
        while not exit.is_set():
            command = await queue.get()

            if command == "START":
                controller.start()
            elif command == "STOP":
                await controller.stop()



async def sound_control(queue: PriorityQueue[str], exit: Event):
    pass


async def dispatch_message(message,
                           button_led_queue: PriorityQueue[str],
                           matrix_queue: PriorityQueue[str],
                           sound_queue: PriorityQueue[str]):
async def register(ws):
    print("Open connection")


async def recv_server(socket: WebSocketClientProtocol,
                      exit: Event,
                      button_led_queue:PriorityQueue[str],
                      matrix_queue: PriorityQueue[str],
                      sound_queue:PriorityQueue[str]):
    while not socket.closed and not exit.is_set():
        message = await socket.recv()
        await dispatch_message(message,
                               button_led_queue,
                               matrix_queue,
                               sound_queue)


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
        await asyncio.gather(recv_server(socket,
                                         exit_event,
                                         button_led_queue,
                                         led_matrix_queue,
                                         sound_queue),
                             button_led_control(
                                 button_led, button_led_queue, exit_event),
                             led_matrix_control(
                                 led_matrix, led_matrix_queue, exit_event),
                             sound_control(sound_queue, exit_event))


if __name__ == "__main__":
    asyncio.run(main())
