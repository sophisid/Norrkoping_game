import asyncio
from enum import IntEnum
from functools import partialmethod
import functools
import json
import random
from typing import Any, Optional, Union

from websockets.server import serve
from websockets.exceptions import ConnectionClosedError

from websockets.server import WebSocketServerProtocol


class Unit:
    def __init__(self, ws: WebSocketServerProtocol, unit_id: int) -> None:
        self.ws = ws
        self.button_pressed = False
        self.unit_id = unit_id

        self.queue = asyncio.Queue()

        self._send_task = asyncio.create_task(self._send())

    def send(self, data: dict[str, Any]):
        self.queue.put_nowait(json.dumps(data).encode())

    async def _send(self):
        while True:
            message = await self.queue.get()
            await self.ws.send(message)

    def start_button_led(self, pattern: Union[str, tuple[int, int, int]]):
        self.send({'type': 'BUTTON_LED', 'value': 'START', 'pattern': pattern})

    def start_matrix(self, pattern: Union[str, tuple[int, int, int]]):
        self.send({'type': 'MATRIX_LED', 'value': 'START', 'pattern': pattern})

    def play_sound(self, filename: str):
        self.send({'type': 'SOUND', 'value': 'START', 'filename': filename})

    def stop_button_led(self):
        self.send({'type': 'BUTTON_LED', 'value': 'OFF'})

    def stop_matrix(self):
        self.send({'type': 'MATRIX_LED', 'value': 'OFF'})

    def stop_sound(self):
        self.send({'type': 'SOUND', 'value': 'STOP'})

    def win(self):
        self.start_button_led("colorscroll")
        self.start_matrix("colorscroll")
        self.play_sound("win.wav")

    def lose(self):
        self.start_button_led("flash_red")
        self.start_matrix("swipe_red")
        self.play_sound("lose.wav")

    def correct_pressed(self):
        self.start_button_led((0, 200, 0))
        self.start_matrix((0, 128, 0))
        self.play_sound("chirping.wav")

    def correct(self):
        self.start_button_led((0, 255, 0))
        self.start_matrix((0, 255, 0))

    def wrong(self):
        self.start_button_led((255, 0, 0))
        self.start_matrix((180, 0, 0))

    def stop_all(self):
        self.stop_button_led()
        self.stop_matrix()
        self.stop_sound()

    def __del__(self):
        self._send_task.cancel()


class Game:
    STATES = IntEnum(
        'States', ['NoUnits',
                   'PreGameSingle',
                   'PreGameMultiple',
                   'Playing',
                   'PlayingAllReleased',
                   'WaitRelease'])

    def __init__(self) -> None:
        self._state = Game.STATES.NoUnits
        self.ACTIVE: dict[int, Unit] = {}

        self.previous_correct: set[int] = set()
        self.unit_list: list[int] = []
        self.correct: Optional[int] = None
        self.wrong: Optional[int] = None

        self.pressed_units: set[Unit] = set()

        self._button_pressed_callbacks = {
            Game.STATES.PreGameSingle: self._button_pressed_PreGameSingle,
            Game.STATES.PreGameMultiple: self._button_pressed_PreGameMultiple,
            Game.STATES.Playing: self._button_pressed_Playing,
            Game.STATES.PlayingAllReleased: self._button_pressed_PlayingAllReleased,
            Game.STATES.WaitRelease: self._button_pressed_WaitRelease
        }

        self._button_released_callbacks = {
            Game.STATES.PreGameSingle: self._button_released_PreGameSingle,
            Game.STATES.PreGameMultiple: self._button_released_PreGameMultiple,
            Game.STATES.Playing: self._button_released_Playing,
            Game.STATES.WaitRelease: self._button_released_WaitRelease
        }

        self._register_callbacks = {
            Game.STATES.NoUnits: self._register_NoUnits,
            Game.STATES.PreGameSingle: self._register_PreGameSingle
        }

        self._control_task: Optional[asyncio.Task] = None

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, next_state: STATES):
        print(f"Transition {self.state.name}->{next_state.name}")
        self._state = next_state

    def button_pressed(self, unit_id: int):
        if unit_id in self.ACTIVE:
            unit = self.ACTIVE[unit_id]

            unit.button_pressed = True
            self.pressed_units.add(unit)

            self._button_pressed_callbacks[self.state](unit)

    def button_released(self, unit_id: int):
        if unit_id in self.ACTIVE:
            unit = self.ACTIVE[unit_id]

            unit.button_pressed = False
            self.pressed_units.discard(unit)

            self._button_released_callbacks[self.state](unit)

    def register(self, unit_id: int, unit: Unit):
        self.ACTIVE[unit_id] = unit

        if self.state in (Game.STATES.NoUnits, Game.STATES.PreGameSingle):
            self._register_callbacks[self.state](unit)

        unit.stop_button_led()
        unit.stop_matrix()
        unit.stop_sound()

    def unregister(self, unit_id: int):
        self.ACTIVE.pop(unit_id, None)
        self.previous_correct.discard(unit_id)

        if unit_id in self.unit_list:
            self.unit_list.remove(unit_id)
        elif unit_id == self.correct:
            self._next_correct()
            self._next_wrong()

        if unit_id == self.wrong:
            self._next_wrong()

        if len(self.ACTIVE) == 0:
            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = None

            self.state = Game.STATES.NoUnits
        elif self.state == Game.STATES.PreGameMultiple and len(self.ACTIVE) == 1:
            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(
                self._control_PreGameSingle())

            self.state = Game.STATES.PreGameSingle
        elif self.state == Game.STATES.Playing and len(self.ACTIVE) == 1:
            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(
                self._control_WaitRelease())

            self.state = Game.STATES.WaitRelease

    def _register_NoUnits(self, unit: Unit):
        assert (self._control_task is None)
        self._control_task = asyncio.create_task(self._control_PreGameSingle())

        self.state = Game.STATES.PreGameSingle

    def _register_PreGameSingle(self, unit: Unit):
        if len(self.ACTIVE) > 1:
            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(
                self._control_PreGameMultiple())

            self.state = Game.STATES.PreGameMultiple
        elif len(self.ACTIVE) == 1:
            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(
                self._control_PreGameSingle())

            self.state = Game.STATES.PreGameSingle

    def _button_pressed_PreGameSingle(self, unit: Unit):
        unit.win()

        assert (self._control_task is not None)
        self._control_task.cancel()
        self._control_task = asyncio.create_task(self._control_WaitRelease())

        self.state = Game.STATES.WaitRelease

    def _button_pressed_PreGameMultiple(self, unit: Unit):
        if unit.unit_id == self.correct:
            unit.stop_all()

            self._setup_game()

            self._next_correct()
            self._next_wrong()

            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(self._control_Playing())

            self.state = Game.STATES.Playing

    def _button_pressed_Playing(self, unit: Unit):
        if unit.unit_id in self.previous_correct:
            unit.correct_pressed()
        elif unit.unit_id == self.wrong:
            for pressed_unit in self.pressed_units:
                pressed_unit.lose()

            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(
                self._control_WaitRelease())

            self.state = Game.STATES.WaitRelease
        elif unit.unit_id == self.correct:
            unit.correct_pressed()

            self.previous_correct.add(unit.unit_id)

            self._next_correct()
            self._next_wrong()

            if not self.unit_list:
                assert (self._control_task is not None)
                self._control_task.cancel()
                self._control_task = asyncio.create_task(
                    self._control_WaitRelease())

                self.state = Game.STATES.WaitRelease

    def _button_pressed_PlayingAllReleased(self, unit: Unit):
        if unit.unit_id in self.previous_correct:
            unit.correct_pressed()

            self.state = Game.STATES.Playing
        elif unit.unit_id == self.wrong:
            for pressed_unit in self.pressed_units:
                pressed_unit.lose()

            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(
                self._control_WaitRelease())

            self.state = Game.STATES.WaitRelease
        elif unit.unit_id == self.correct:
            unit.correct_pressed()

            self.previous_correct.add(unit.unit_id)

            self._next_correct()
            self._next_wrong()

            if not self.unit_list:
                assert (self._control_task is not None)
                self._control_task.cancel()
                self._control_task = asyncio.create_task(
                    self._control_WaitRelease())

                self.state = Game.STATES.WaitRelease
            else:
                assert (self._control_task is not None)
                self._control_task.cancel()
                self._control_task = asyncio.create_task(
                    self._control_Playing())

                self.state = Game.STATES.Playing

    def _button_pressed_WaitRelease(self, unit: Unit):
        unit.start_button_led((0xFF, 0xA5, 0x00))

    def _button_released_PreGameSingle(self, unit: Unit):
        pass
    _button_released_PreGameMultiple = _button_pressed_PreGameSingle

    def _button_released_Playing(self, unit: Unit):
        unit.stop_button_led()
        unit.stop_matrix()
        unit.stop_sound()

        if not self.pressed_units:
            assert (self._control_task is not None)
            self._control_task.cancel()
            self._control_task = asyncio.create_task(
                self._control_PlayingAllReleased())

            self.state = Game.STATES.PlayingAllReleased

    def _button_released_WaitRelease(self, unit: Unit):
        unit.stop_button_led()
        unit.stop_matrix()
        unit.stop_sound()

        self.previous_correct.discard(unit.unit_id)

        if not self.pressed_units:
            if len(self.ACTIVE) > 1:
                assert (self._control_task is not None)
                self._control_task.cancel()
                self._control_task = asyncio.create_task(
                    self._control_PreGameMultiple())

                self.state = Game.STATES.PreGameMultiple
            elif len(self.ACTIVE) == 1:
                assert (self._control_task is not None)
                self._control_task.cancel()
                self._control_task = asyncio.create_task(
                    self._control_PreGameSingle())

                self.state = Game.STATES.PreGameSingle

    def _setup_game(self):
        self.unit_list = list(self.ACTIVE.keys())
        random.shuffle(self.unit_list)

    def _next_correct(self):
        if self.unit_list:
            self.correct = self.unit_list.pop(0)

            correct_unit = self.ACTIVE[self.correct]
            correct_unit.send({'type': 'BUTTON_LED', 'value': 'START'})
        else:
            self.correct = None

    def _next_wrong(self):
        if self.unit_list:
            self.wrong = random.choice(self.unit_list)
            wrong_unit = self.ACTIVE[self.wrong]
            wrong_unit.send({'type': 'BUTTON_LED', 'value': 'START'})
        else:
            self.wrong = None

    def _finish_game(self):
        self.state = Game.STATES.PreGame

    async def _control(self):
        while True:
            if self.state == Game.STATES.PreGame:
                await self._control_PreGame()

    async def _control_PreGame(self):
        if self.correct is not None:
            self.ACTIVE[self.correct].send(
                {'type': 'BUTTON_LED', 'value': 'STOP'})
        if self.ACTIVE:
            while self.correct == (next_unit := random.choice(list(self.ACTIVE.keys()))):
                pass

            self.correct = next_unit
            self.ACTIVE[self.correct].send(
                {'type': 'BUTTON_LED', 'value': 'START'})
        await asyncio.sleep(5)


async def handler(websocket: WebSocketServerProtocol, game: Game):
    async for msg in websocket:
        decoded = json.loads(msg)
        unit_id = None

        print(decoded)
        if decoded['type'] == 'REGISTER':
            unit_id = int(decoded['id'], 16)
            game.register(unit_id, Unit(websocket, unit_id))
        elif decoded['type'] == 'BUTTON_PRESSED':
            if unit_id is not None:
                game.button_pressed(unit_id)
        elif decoded['type'] == 'BUTTON_RELEASED':
            if unit_id is not None:
                game.button_pressed(unit_id)
        elif decoded['type'] == 'UNREGISTER':
            if unit_id is not None:
                game.unregister(unit_id)
                break


async def main():
    game = Game()
    async with serve(functools.partial(handler, game=game), "", 8001):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
