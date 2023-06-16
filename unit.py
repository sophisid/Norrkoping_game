'''
This program is designed to run on the Raspberry Pi.
The program is used as an gateway for the Arduino in the laboratory work
assignment.

Tip: There is one method called output built in the code to make it easier
to print out variables or messages.
Example  output("Test!") - Prints the text Test! in the output area.
'''

from datetime import datetime, timedelta, timezone
import json
import socket
import sys
import threading
from queue import PriorityQueue, Queue
import time
from typing import Literal

import serial

UNIT_ID = None
SER = None

HOST = '130.236.81.13'
PORT = 8716

game_master = None

LED_CONTROL = 0xED
PLAY_SOUND = 0x50
BUTTON_STATE = 0xB0


def print_error(*values: object,
                sep: str | None = " ",
                end: str | None = "\n",
                flush: Literal[False] = False):
    print(*values, sep=sep, end=end, file=sys.stderr, flush=flush)


def parse_time(task):
    ''' Converts absolute and relative timestamps to absolute '''
    if "in" in task['data']:
        try:
            delta = timedelta(
                milliseconds=float(task['data']['in']))
        except ValueError:
            print_error(
                f"Invalid relative timedelta string {task['data']['in']}")
            return None
        else:
            return datetime.now(timezone.utc)+delta
    elif 'at' in task['data']:
        # The time information is in the format: "%Y-%m-%d %H:%M:%S.%f"
        try:
            timestamp = datetime.strptime(
                task['data']['at'], "%Y-%m-%d %H:%M:%S.%f")
        except ValueError as error:
            print_error(error)
            return None
        else:
            return timestamp
    else:
        return None


def get_tasks(led_queue: PriorityQueue, sound_queue: PriorityQueue, exit_event: threading.Event):
    ''' Get the task list from the server '''
    global game_master

    request = {"message_type": "GameGetTasks", "unit_id": UNIT_ID}

    while not exit_event.is_set():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as clientsocket:
            clientsocket.connect((HOST, PORT))

            # Dumps the request dictionary as a JSON object.
            # Sending the JSON message to the host. Note: The message must end with a |
            # character and the String should be encoded to bytes with .encode().
            clientsocket.send(f"{json.dumps(request)}|".encode())

            # Reading input from the host.
            receive = b''
            while not receive.endswith(b"|"):
                receive += clientsocket.recv(1024)

        # Creates a string from the receive bytes, removes the trailing | and parses
        # the string as a JSON dictionary.
        # Note the | must be removed from the string before the string is
        # loaded as a JSON dictionary.
        response = json.loads(receive[:-1].decode())

        for task in response["tasks"]:
            match task['data']["action"]:
                case "CHANGE_LED":
                    timestamp = parse_time(task)
                    if timestamp:
                        led_queue.put((timestamp, task))
                    else:
                        print_error(
                            f"CHANGE_LED {task} with no time information")
                case "PLAY_SOUND":
                    timestamp = parse_time(task)
                    if timestamp:
                        sound_queue.put((timestamp, task))
                    else:
                        print_error(
                            f"PLAY_SOUND {task} with no time information")
                case "UPDATE_GM":
                    game_master = task['data']['gamemaster']
                case "PLAY_GAME":
                    if task["data"]["game_state"] == "STOP":
                        exit_event.set()
                        break


def send_request(request):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as clientsocket:
        clientsocket.connect((HOST, PORT))

        # Dumps the request dictionary as a JSON object.
        # Sending the JSON message to the host. Note: The message must end with a |
        # character and the String should be encoded to bytes with .encode().
        clientsocket.send(f"{json.dumps(request)}|".encode())

        # Reading input from the host.
        receive = b''
        while not receive.endswith(b"|"):
            receive += clientsocket.recv(1024)

        return json.loads(receive[:-1])


def handle_server(server_queue: Queue, exit_event: threading.Event):
    ''' This handles the LED '''
    while not exit_event.is_set():
        if not server_queue.empty():
            request = server_queue.get()
            send_request(request)


def parse_color(state, color):
    if state == 'ON':
        match color:
            case "AMBER":
                return "\x00\xff\x00"
            case "RED":
                return "\xff\x00\x00"
            case "GREEN":
                return "\x00\x00\xff"
    else:
        return '\x00'*3


def handle_led(led_queue: PriorityQueue, exit_event: threading.Event):
    ''' This handles the LED '''
    while not exit_event.is_set():
        if not led_queue.empty():
            timestamp, task = led_queue.get()
            if datetime.now() < timestamp:
                color_code = parse_color(task['led_state'], task['led_color'])
                try:
                    time.sleep((datetime.now()-timestamp).total_seconds())
                except ValueError:
                    pass
                send_instructions(LED_CONTROL, color_code)


def send_instructions(message_type, value):
    '''
    This method sends measurements to the Arduino over the serial
    connection. The data is sent in a TLV structure. [Type][Length][Value].
    The size of the type field is 1 byte.
    The size of the length field is 2 bytes.
    The size of the value field varies.
    '''
    assert SER

    value = str(value)
    SER.write(f"{chr(message_type&0xFF)}{len(value):02}{value}".encode())


def convert_to_filename(sound_name):
    ''' Convert between sound name to file name '''
    mapping = {
        "WIN": "1.wav",
        "LOSE": "2.wav",
        "CLICK_CORRECT": "3.wav",
        "CLICK_WRONG": "4.wav"
    }

    return mapping[sound_name]


def handle_sound(sound_queue: PriorityQueue, exit_event: threading.Event):
    ''' This handles the LED '''
    while not exit_event.is_set():
        if not sound_queue.empty():
            timestamp, task = sound_queue.get()
            if datetime.now() < timestamp:
                filename = convert_to_filename(task['sound'])
                try:
                    time.sleep((datetime.now()-timestamp).total_seconds())
                except ValueError:
                    pass
                send_instructions(PLAY_SOUND, filename)


def read_from_arduino(timeout=None):
    assert SER

    if timeout is not None:
        SER.timeout = timeout
    message = {
        "type": 0,
        "length": 0,
        "value": ''
    }

    type_read = SER.read(1)

    # Reads the messageType (first byte) and the message length (next two bytes).
    # Then stores them as integers.
    if timeout is not None and len(type_read) == 1:
        message['type'] = int(str(type_read, 'utf-8'))
    else:
        return None

    length_read = SER.read(2)
    if timeout is not None and len(length_read) == 2:
        message['length'] = int(str(length_read, 'utf-8'))
    else:
        return None

    # Waits until all the bytes for the message have arrived.
    if SER.in_waiting < message['length']:
        return None
    # Reads the message.
    message['value'] = SER.read(message['length']).decode()

    SER.timeout = None
    return message


def handle_button(server_queue: Queue, exit_event: threading.Event):
    while not exit_event.is_set():
        # If there is a button press event, wait a few moments
        # and check if there has been a button release event.
        # If so, send button click. Otherwise, send button press
        # If there is a button release event, send button release
        state1 = read_from_arduino()
        if state1:
            if state1['type'] == BUTTON_STATE and state1['value'] == 'press':
                state2 = read_from_arduino(0.7)
                if state2 is not None:
                    if state1['type'] == BUTTON_STATE and state1['value'] == 'release':
                        request = {"message_type": "GameButtonControl",
                                   "from": UNIT_ID, "to": game_master, "button_state": "clicked"}
                        server_queue.put(request)
                    else:
                        print_error("Received the same button status twice")
                else:
                    request = {"message_type": "GameButtonControl",
                               "from": UNIT_ID, "to": game_master, "button_state": "pressed"}
                    server_queue.put(request)
            elif state1['type'] == BUTTON_STATE and state1['value'] == 'release':
                request = {"message_type": "GameButtonControl",
                           "from": UNIT_ID, "to": game_master, "button_state": "released"}
                server_queue.put(request)


def main():
    ''' The main function for the unit '''

    global UNIT_ID, SER, game_master

    id_string = input("What is this unit's ID? ")
    try:
        UNIT_ID = int(id_string)
    except ValueError:
        print(f"ERROR: Invalid ID {id_string}", file=sys.stderr)
        sys.exit(1)

    arduino_path = input(
        "What is the path to the Arduino? (default: /dev/ttyUSB0) ").strip()
    if arduino_path == "":
        arduino_path = '/dev/ttyUSB0'

    try:
        SER = serial.Serial(arduino_path, 9600)
    except serial.SerialException:
        print(
            f"ERROR: Couldn't open serial connection to path {arduino_path}", file=sys.stderr)
        sys.exit(1)

    led_queue = PriorityQueue()
    sound_queue = PriorityQueue()
    server_queue = Queue()

    exit_event = threading.Event()

    request = {"message_type": "GameRegister",
               "unit_id": UNIT_ID, "registration_type": "register"}

    # Passes the request to a method that handles server connections.
    server_queue.put(request)

    while game_master is None:
        request = {"message_type": "GameMasterControl",
                   "unit_id": UNIT_ID, "sub_action": "LIST_GM"}
        response = send_request(request)

        if 'unit_id' in response:
            game_master = response['unit_id']

    receiver = threading.Thread(
        target=get_tasks, args=(led_queue, sound_queue, exit_event))
    led_handler = threading.Thread(
        target=handle_led, args=(led_queue, exit_event))
    sound_handler = threading.Thread(
        target=handle_sound, args=(sound_queue, exit_event))
    server_handler = threading.Thread(
        target=handle_server, args=(server_queue, exit_event))
    button_handler = threading.Thread(
        target=handle_button, args=(server_queue, exit_event))

    handlers = [receiver, led_handler, sound_handler,
                server_handler, button_handler]

    _ = [handler.run() for handler in handlers]
    _ = [handler.join() for handler in handlers]


if __name__ == "__main__":
    main()
