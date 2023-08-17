import asyncio
from enum import IntEnum
from functools import partialmethod
import functools
import json
import random
from typing import Optional

from websockets.server import serve

from websockets.server import WebSocketServerProtocol


class Unit:
    def __init__(self, ws: WebSocketServerProtocol, unit_id: int) -> None:
        self.ws = ws
        self.button_pressed = False
        self.unit_id = unit_id

        self.queue = asyncio.Queue()

        self._send_task = asyncio.create_task(self._send())

    def send(self, data: dict[str, str]):
        self.queue.put_nowait(json.dumps(data).encode())

    async def _send(self):
        while True:
            message = await self.queue.get()
            await self.ws.send(message)

    def __del__(self):
        try:
            self._send_task.cancel()
        except asyncio.CancelledError:
            pass


class Game:
    STATES = IntEnum('States', ['PreGame', 'Game', 'PostGame'])

    def __init__(self) -> None:
        self.state = Game.STATES.PreGame
        self.ACTIVE: dict[int, Unit] = {}

        self.previous_correct: set[int] = set()
        self.unit_list: list[int] = []
        self.correct: Optional[int] = None
        self.wrong: Optional[int] = None

        self.pressed_units: set[Unit] = set()

        self._button_pressed_callbacks = {
            Game.STATES.PreGame: self._button_pressed_PreGame,
            Game.STATES.Game: self._button_pressed_Game,
            Game.STATES.PostGame: self._button_pressed_PostGame
        }

        self._button_released_callbacks = {
            Game.STATES.PreGame: self._button_released_PreGame,
            Game.STATES.Game: self._button_released_Game,
            Game.STATES.PostGame: self._button_released_PostGame
        }

        self._control_task = asyncio.create_task(self._control())

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

        unit.send({'type': 'BUTTON_LED', 'value': 'STOP'})
        unit.send({'type': 'MATRIX_LED', 'value': 'STOP'})
        unit.send({'type': 'SOUND', 'value': 'STOP'})

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

    def _button_pressed_PreGame(self, unit: Unit):
        if unit.unit_id == self.correct:
            unit.send({'type': 'BUTTON_LED', 'value': 'STOP'})
            unit.send({'type': 'MATRIX_LED', 'value': 'STOP'})
            unit.send({'type': 'SOUND', 'value': 'STOP'})

            self._setup_game()

            self._next_correct()
            self._next_wrong()

            if self.unit_list:
                self.state = Game.STATES.Game
            else:
                self.state = Game.STATES.PostGame

    def _button_pressed_Game(self, unit: Unit):
        if unit.unit_id in self.previous_correct:
            unit.send({'type': 'BUTTON_LED', 'value': 'START'})
            unit.send({'type': 'MATRIX_LED', 'value': 'START'})
            unit.send({'type': 'SOUND', 'value': 'START'})
        elif unit.unit_id == self.wrong:
            unit.send({'type': 'SOUND', 'value': 'START'})

            for pressed_unit in self.pressed_units:
                pressed_unit.send({'type': 'SOUND', 'value': 'START'})
        elif unit.unit_id == self.correct:
            unit.send({'type': 'BUTTON_LED', 'value': 'STOP'})
            unit.send({'type': 'MATRIX_LED', 'value': 'STOP'})
            unit.send({'type': 'SOUND', 'value': 'STOP'})

            self.previous_correct.add(unit.unit_id)

            self._next_correct()
            self._next_wrong()

    def _button_pressed_PostGame(self, unit: Unit):
        unit.send({'type': 'BUTTON_LED', 'value': 'START'})

    def _button_released_PreGame(self, unit: Unit):
        pass

    def _button_released_Game(self, unit: Unit):
        unit.send({'type': 'BUTTON_LED', 'value': 'STOP'})
        unit.send({'type': 'MATRIX_LED', 'value': 'STOP'})
        unit.send({'type': 'SOUND', 'value': 'STOP'})

        if not self.unit_list:
            self.state = Game.STATES.PostGame

    def _button_released_PostGame(self, unit: Unit):
        unit.send({'type': 'BUTTON_LED', 'value': 'STOP'})
        unit.send({'type': 'MATRIX_LED', 'value': 'STOP'})
        unit.send({'type': 'SOUND', 'value': 'STOP'})

        self.previous_correct.discard(unit.unit_id)

        if not self.pressed_units:
            self._finish_game()

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
