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
        self.led = led

    async def _run(self, *args, **kwargs):
        if isinstance(args[0], list):
            pattern = tuple(args[0][i]/255 for i in range(3))
            self.led.color = pattern
        elif args[0] == 'colorscroll':
            if self.led.color in (Color(0, 0, 0), Color(1, 1, 1)):
                self.led.color = Color(1, 0, 0)
            color = Color(self.led.color)
            while self.state == Controller.STATES.RUNNING:
                self.led.color = color

                color += Hue(deg=3.6)
                await asyncio.sleep(0.04)
        elif args[0] == 'flash_red':
            self.led.blink(0.1, 0.1, on_color=(1, 0, 0))
        elif args[0] == 'flash_blue':
            self.led.blink(0.1, 0.1, on_color=(0, 0, 1))

    async def off(self):
        await self.stop()
        self.led.off()


class MatrixLEDController(Controller):
    def __init__(self, matrix: PixelStrip):
        super().__init__()
        self.matrix = matrix

    async def _run(self, *args):
        if isinstance(args[0], list):
            for i in range(self.matrix.numPixels()):
                self.matrix.setPixelColorRGB(i, *args[0])
            self.matrix.show()
        elif args[0] == 'colorscroll':
            color = Color.from_hsv(h=1/3, s=1, v=1)
            while self.state == Controller.STATES.RUNNING:
                for i in range(self.matrix.numPixels()):
                    self.matrix.setPixelColorRGB(
                        i,
                        int(color.rgb[0]*255),
                        int(color.rgb[1]*255),
                        int(color.rgb[2]*255))
                self.matrix.show()

                color += Hue(deg=3.6)
                await asyncio.sleep(0.04)
        elif args[0] == 'swipe_red':
            pattern: list[tuple[int, int, int]] = [(255, 0, 0), (0, 0, 0)]

            loop = cycle(pattern)

            while self.state == Controller.STATES.RUNNING:
                color = next(loop)
                for led_index in range(self.matrix.numPixels()):
                    self.matrix.setPixelColorRGB(led_index, *color)
                self.matrix.show()

                await asyncio.sleep(0.1)

    async def off(self):
        await self.stop()
        for i in range(self.matrix.numPixels()):
            self.matrix.setPixelColorRGB(i, 0, 0, 0)

        self.matrix.show()


class SoundController(Controller):
    def __init__(self):
        super().__init__()
        pygame.mixer.init(buffer=1024)

    async def _run(self, *args):
        pygame.mixer.music.load(args[0])
        pygame.mixer.music.play(loops=-1)

        pattern = tuple(0.1*i for i in range(int(1/0.1+1)))
        pattern += pattern[-2::-1]

        volume_loop = cycle(pattern)

        while self.state == Controller.STATES.RUNNING:
            pygame.mixer.music.set_volume(next(volume_loop))
            await asyncio.sleep(0.1)

    async def stop(self):
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        await super().stop()
    off = stop


async def button_led_control(led: RGBLED, queue: PriorityQueue[tuple[float, dict[str, str]]], exit: Event):
    async with ButtonLEDController(led) as controller:
        while not exit.is_set():
            offset, command = await queue.get()

            if command['type'] == 'DIE':
                await controller.stop()
                break
            elif command['value'] == "START":
                await controller.start(command['pattern'])
            elif command['value'] == "STOP":
                await controller.stop()
            elif command['value'] == "OFF":
                await controller.off()


async def led_matrix_control(matrix: PixelStrip, queue: PriorityQueue[tuple[float, dict[str, str]]], exit: Event):
    async with MatrixLEDController(matrix) as controller:
        while not exit.is_set():
            offset, command = await queue.get()

            if command['type'] == 'DIE':
                await controller.stop()
                break
            elif command['value'] == "START":
                await controller.start(command['pattern'])
            elif command['value'] == "OFF":
                await controller.stop()


async def sound_control(queue: PriorityQueue[tuple[float, dict[str, str]]], exit: Event):
    async with SoundController() as controller:
        while not exit.is_set():
            offset, command = await queue.get()

            if command['type'] == 'DIE':
                await controller.stop()
                break
            elif command['value'] == "START":
                await controller.start(command['filename'])
            elif command['value'] == "STOP":
                await controller.stop()


def get_cpu_id():
    with open("unit_id.txt") as unit_id:
        return unit_id.read()


async def register(ws):
    message = json.dumps({'type': "REGISTER", "id": get_cpu_id()}).encode()
    await send_server(ws, message)


async def unregister(ws):
    message = json.dumps({'type': "UNREGISTER"}).encode()
    await send_server(ws, message)


async def recv_server(socket: WebSocketClientProtocol,
                      exit: Event,
                      button_led_queue: PriorityQueue[tuple[float, dict[str, str]]],
                      matrix_queue: PriorityQueue[tuple[float, dict[str, str]]],
                      sound_queue: PriorityQueue[tuple[float, dict[str, str]]]):
    i = 0
    while not socket.closed and not exit.is_set():
        message: dict[str, str] = json.loads(await socket.recv())
        print(message)
        if message['type'] == "BUTTON_LED":
            await button_led_queue.put((i, message))
        elif message['type'] == "MATRIX_LED":
            await matrix_queue.put((i, message))
        elif message['type'] == "SOUND":
            await sound_queue.put((i, message))
        elif message['type'] == "DIE":
            exit.set()
            await button_led_queue.put((i, message))
            await matrix_queue.put((i, message))
            await sound_queue.put((i, message))
        i += 1


async def send_server(socket: WebSocketClientProtocol, message: bytes):
    await socket.send(message)


def button_pressed(ws: WebSocketClientProtocol, eventloop: asyncio.AbstractEventLoop):
    message = json.dumps({'type': "BUTTON_PRESSED"}).encode()
    asyncio.run_coroutine_threadsafe(send_server(ws, message), eventloop)


def button_released(ws: WebSocketClientProtocol, eventloop: asyncio.AbstractEventLoop):
    message = json.dumps({'type': "BUTTON_RELEASED"}).encode()
    asyncio.run_coroutine_threadsafe(send_server(ws, message), eventloop)


async def main():
    ''' The main function for the unit '''

    # Initialize the hardware interface
    button: Button = Button(26)
    button_led: RGBLED = RGBLED(17, 27, 22)
    led_matrix: PixelStrip = PixelStrip(LED_COUNT, LED_PIN)

    button_led_queue: PriorityQueue[tuple[float,
                                          dict[str, str]]] = asyncio.PriorityQueue()
    led_matrix_queue: PriorityQueue[tuple[float,
                                          dict[str, str]]] = asyncio.PriorityQueue()
    sound_queue: PriorityQueue[tuple[float,
                                     dict[str, str]]] = asyncio.PriorityQueue()

    exit_event = asyncio.Event()

    led_matrix.begin()

    loop = asyncio.get_event_loop()

    async with connect("ws://139.91.68.15:8001") as socket:
        try:
            button.when_pressed = lambda: button_pressed(socket, loop)
            button.when_released = lambda: button_released(socket, loop)

            await register(socket)

            await asyncio.gather(recv_server(socket,
                                             exit_event,
                                             button_led_queue,
                                             led_matrix_queue,
                                             sound_queue),
                                 button_led_control(
                button_led, button_led_queue, exit_event),
                led_matrix_control(
                led_matrix, led_matrix_queue, exit_event),
                sound_control(sound_queue, exit_event),
                return_exceptions=True)
        finally:
            await unregister(socket)

if __name__ == "__main__":
    asyncio.run(main())
