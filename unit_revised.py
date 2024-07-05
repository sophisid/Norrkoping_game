import sys
import os

# Add the directory containing sensor_lib.py to the Python path
sys.path.append('/home/pi/Team_Art_Sof')
import argparse
import asyncio
from asyncio import PriorityQueue, Event
import http
from itertools import cycle
import json
import re
import signal
import ssl
import sys
import requests
import websockets
import time
import math

from websockets.client import connect
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosedError

from gpiozero import Button, RGBLED
from colorzero import Color, Hue

from rpi_ws281x import PixelStrip

import pygame

from enum import IntEnum
from typing import Optional
from abc import ABC, abstractmethod

import sensor_lib  # Import the sensor library

LED_COUNT = 16      # Number of LED pixels.
LED_PIN = 21        # GPIO pin connected to the pixels (21 uses PCM).

RECHECK_INTERVAL = 10
button_pressed_state = False


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
        print("eiamia stin run")
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
        elif 'pulse' in args[0]: 
            print("allallalal")
            # na kanw slice to time
            disval = args[0]
            distance = disval[6:]
            color = Color.rgb[0]*255
            while self.state == Controller.STATES.RUNNING:
                for i in range(self.matrix.numPixels()):
                    self.matrix.setPixelColorRGB(
                        i,
                        int(color.rgb[0]*255),
                        int(color.rgb[1]*255),
                        int(color.rgb[2]*255))
                self.matrix.show()

                # color += Hue(deg=3.6)
                await asyncio.sleep(0.04)

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

        while self.state == Controller.STATES.RUNNING:
            await asyncio.sleep(0.1)

    async def stop(self):
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        await super().stop()
    off = stop


async def button_led_control(led: RGBLED, queue: PriorityQueue[tuple[int, dict[str, str]]], exit: Event):
    async def execute(timestamp: int, command: dict[str, str], controller: ButtonLEDController):
        if command['value'] == "START":
            await controller.start(command['pattern'])
        elif command['value'] == "STOP":
            await controller.stop()
        elif command['value'] == "OFF":
            await controller.off()

    async with ButtonLEDController(led) as controller:
        background_tasks = set()
        while not exit.is_set():
            timestamp, command = await queue.get()

            if command['type'] == 'DIE':
                await controller.stop()
                break

            task = asyncio.create_task(execute(timestamp, command, controller))

            background_tasks.add(task)

            task.add_done_callback(background_tasks.discard)


async def led_matrix_control(matrix: PixelStrip, queue: PriorityQueue[tuple[int, dict[str, str]]], exit: Event):
    async def execute(timestamp: int, command: dict[str, str], controller: MatrixLEDController):
        if command['value'] == "START":
            await controller.start(command['pattern'])
        elif command['value'] == "OFF":
            await controller.off()

    async with MatrixLEDController(matrix) as controller:
        background_tasks = set()
        while not exit.is_set():
            timestamp, command = await queue.get()

            if command['type'] == 'DIE':
                await controller.stop()
                break
            print(command)
            task = asyncio.create_task(execute(timestamp, command, controller))
            print(task)

            background_tasks.add(task)

            task.add_done_callback(background_tasks.discard)


async def sound_control(queue: PriorityQueue[tuple[int, dict[str, str]]], exit: Event):
    async def execute(timestamp: int, command: dict[str, str], controller: SoundController):
        if command['value'] == "START":
            await controller.start(command['filename'])
        elif command['value'] == "STOP":
            await controller.stop()

    async with SoundController() as controller:
        background_tasks = set()
        while not exit.is_set():
            timestamp, command = await queue.get()

            if command['type'] == 'DIE':
                await controller.stop()
                exit.set()

            task = asyncio.create_task(execute(timestamp, command, controller))

            background_tasks.add(task)

            task.add_done_callback(background_tasks.discard)


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
                      button_led_queue: PriorityQueue[tuple[int, dict[str, str]]],
                      matrix_queue: PriorityQueue[tuple[int, dict[str, str]]],
                      sound_queue: PriorityQueue[tuple[int, dict[str, str]]]):
    i = 0
    async for msg in socket:
        if exit.is_set():
            break

        message: dict[str, str] = json.loads(msg)
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
    print("lalallla")
    global button_pressed_state
    button_pressed_state = True 
    message = json.dumps({'type': "BUTTON_PRESSED"}).encode()
    asyncio.run_coroutine_threadsafe(send_server(ws, message), eventloop)


def button_released(ws: WebSocketClientProtocol, eventloop: asyncio.AbstractEventLoop):
    message = json.dumps({'type': "BUTTON_RELEASED"}).encode()
    asyncio.run_coroutine_threadsafe(send_server(ws, message), eventloop)


def parse_arguments(args: list[str]):
    parser = argparse.ArgumentParser()

    parser.add_argument('-ca', '--ca-certificate',
                        metavar='path',
                        help='The path to the CA certificate', required=True)
    parser.add_argument('-g', '--gamemaster-url',
                        action='append', required=True)

    return parser.parse_args(args)


def discover_gamemaster(gamemaster_urls: list[str], ca_certificate: str):
    gamemaster = None
    for url in gamemaster_urls:
        try:
            response = requests.get(
                f"https://{url}:8002/alive",
                verify=ca_certificate,
                timeout=1)

            gamemaster = response.content.decode().strip()
        except (requests.ReadTimeout, requests.TooManyRedirects, requests.ConnectionError):
            pass

    return gamemaster


# Function to control the sensor, read data and adjust brightness
async def sensor_control(sensor, queue: PriorityQueue[tuple[int, dict[str, str]]], exit: Event,maxDis: float):
    distances_with_accuracy = []  # List to store distances along with their accuracy

    async def execute(queue: PriorityQueue[tuple[int, dict[str, str]]], timestamp: int, distance: float): 
        #na kollisw distance sto string
        command = {'value': 'START', 'pattern':"pulse_"+distance}
        await queue.put((timestamp, command))

    '''def pulse_effect(brightness: float, distance: float, maxdis: float):
        normalized_distance = max(0, min(1, (distance - 1) / (2 - 1)))
        # Create a pulsing effect by changing the brightness in a sine wave pattern
        steps = int(50*(maxdis*0.1-distance*0.1)*(distance*0.1))  # Number of steps in one pulse cycle
        max_sleep_time = 0.1  # Maximum sleep time (slowest pulse)
        min_sleep_time = 0.01  # Minimum sleep time (fastest pulse)
        #sleep_time = max_sleep_time - (normalized_distance * (max_sleep_time - min_sleep_time))
        sleep_time= max_sleep_time-(distance*0.01)

        for i in range(steps):
            factor = (1 + math.sin(i * 2 * math.pi / steps)) / 2  # Create a sine wave factor
            scaled_brightness = int(255 * brightness * factor)
            
            for j in range(matrix.numPixels()):
                matrix.setPixelColorRGB(j, scaled_brightness, 0, 0)
            matrix.show()
        await asyncio.sleep(sleep_time)  # Adjust sleep time to create a distance-dependent pulse frequency
    '''

    while not exit.is_set():
        if sensor._s.in_waiting > 0:
            data = sensor._s.readline().decode('utf-8', errors='ignore').strip()
            if data.startswith('$JYRPO'):
                parts = data.split(',')
                print(parts)
                if len(parts) >= 6:
                    detected_items = int(parts[1])
                    item_id = int(parts[2])
                    distance = float(parts[3])  # The 4th part is the distance
                    accuracy = float(parts[5])  # The 6th part is the accuracy                        
                    timestamp = int(time.time())  # Use the current timestamp
                    distances_with_accuracy.append((distance, accuracy))
                    if distances_with_accuracy:
                        best_distance, best_accuracy = min(distances_with_accuracy, key=lambda x: x[0])
                        print(f"Best Distance: {best_distance}, Accuracy: {best_accuracy}")
                        await execute(queue,-1, distance)  # Send maximum distance to the queue
                        distances_with_accuracy.clear()

                #    # Store the distance and accuracy
                #    distances_with_accuracy.append((distance, accuracy))

                #    current_time = time.time()
                #    if current_time - last_print_time >= 2:
                        # Find the distance with the best accuracy
                #        if distances_with_accuracy:
                #            best_distance, best_accuracy = min(distances_with_accuracy, key=lambda x: x[0])
                #            print(f"Best Distance: {best_distance}, Accuracy: {best_accuracy}")
                #            # Apply pulsing effect based on the best distance
                #            brightness = max(0, min(1, (maxDis - best_distance) / maxDis))  # Normalize distance to brightness
                #            pulse_effect(brightness, best_distance,maxDis)
                #            distances_with_accuracy.clear()  # Clear the list after processing

                #        last_print_time = current_time
            else:
                print("Error reading from sensor")
        await asyncio.sleep(0.1)

async def main(args: list[str]):
    ''' The main function for the unit '''

    options = parse_arguments(args)
    i = 0
    range=10.0
    # Initialize the hardware interface
    button: Button = Button(26)
    button_led: RGBLED = RGBLED(17, 27, 22)
    led_matrix: PixelStrip = PixelStrip(LED_COUNT, LED_PIN)
    sensor = sensor_lib.DFRobot_mmWave_Radar('/dev/serial0')  # Initialize the sensor
    sensor.sensorStop()
    data = sensor._s.readline().decode('utf-8', errors='ignore').strip()
    if data.startswith('Response'):
        parts = data.split(' ')
        print(parts)
        if len(parts) == 3:
            range = parts[2]; 
    sensor.sensorStart()
    button_led_queue: PriorityQueue[tuple[int,
                                          dict[str, str]]] = asyncio.PriorityQueue()
    led_matrix_queue: PriorityQueue[tuple[int,
                                          dict[str, str]]] = asyncio.PriorityQueue()
    sound_queue: PriorityQueue[tuple[int,
                                     dict[str, str]]] = asyncio.PriorityQueue()
    exit_event = asyncio.Event()

    led_matrix.begin()

    loop = asyncio.get_event_loop()

    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.load_verify_locations(options.ca_certificate)

    button_led_task = asyncio.create_task(
        button_led_control(
            button_led,
            button_led_queue,
            exit_event))
    led_matrix_task = asyncio.create_task(
        led_matrix_control(
            led_matrix,
            led_matrix_queue,
            exit_event))
    sound_task = asyncio.create_task(
        sound_control(
            sound_queue,
            exit_event))
    sensor_task = asyncio.create_task(  # Add a task for sensor control
        sensor_control(
            sensor,
            led_matrix_queue,  # Send sensor events to the button LED queue as an example
            exit_event,
            range))
    
    #await asyncio.gather(button_led_task, led_matrix_task, sound_task, sensor_task)

    while not exit_event.is_set():
        gamemaster_url = discover_gamemaster(
            options.gamemaster_url, options.ca_certificate)
        if gamemaster_url:
            print('lalalallala')
            async with connect(f"wss://{gamemaster_url}:8001", ssl=ssl_context) as socket:
                loop.add_signal_handler(
                    signal.SIGTERM, loop.create_task, socket.close())
                button.when_pressed = lambda: button_pressed(socket, loop)
                button.when_released = lambda: button_released(
                    socket, loop)

                await register(socket)
                try:
                    await recv_server(socket,
                                      exit_event,
                                      button_led_queue,
                                      led_matrix_queue,
                                      sound_queue,
                                      )
                except ConnectionClosedError:
                    pass
                else:
                    await unregister(socket)
        else:
            start_blink = {
                'type': 'BUTTON_LED', 'value': 'START', 'pattern': "flash_red"}

            stop_matrix = {'type': 'MATRIX_LED', 'value': 'OFF'}
            stop_sound = {'type': 'SOUND', 'value': 'STOP'}

            await button_led_queue.put((i, start_blink))
            await led_matrix_queue.put((i, stop_matrix))
            await sound_queue.put((i, stop_sound))

            await asyncio.sleep(RECHECK_INTERVAL)

            stop_blink = {'type': 'BUTTON_LED', 'value': 'STOP'}

            await button_led_queue.put((i, stop_blink))
            i += 1

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))


