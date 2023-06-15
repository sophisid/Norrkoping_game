/*
 * TNK116 - Internet of Things
 * Sketch for blink
 * Board Arduino UNO
 * 1 x green LED
 * 1 x amber LED
 * 1 x red LED
 * 1 x button / pressure plate
 */

// Declaring variable to store LED instructions.
int type = -1;   // NULL;
int length = -1; // NULL;

// TODO: Selecting the pins for different purpose.
const int LED_RED = 11;
const int LED_GREEN = 13;
const int LED_BLUE = 12;
const int PIN_BUTTON = 10;

const int PIN_SPEAKER = 8;

const int LED_CONTROL = 0xED,
          PLAY_SOUND = 0x50,
          BUTTON_STATE = 0xB0;

enum button_status {
    PRESSED,
    RELEASED
} game_button;

// This method sends measurements to the Raspberry pi over the serial
// connection. The data is sent in a TLV structure. [Type][Length][Value].
// The size of the type field is 1 byte.
// The size of the length field is 2 bytes.
// The size of the value field varies.
void sendData(int type, String value) {
    // Printing the type.
    String message = String(type);

    // Printing the length.
    int length = value.length();
    if (length < 10) {
        message += 0;
    }

    message += value.length();
    message += value;
    // Printing the value.
    Serial.print(message);
}

// This method handles messages received from the Raspberry Pi.
// The type is used for identifying the type of message.
void handleMessage(int type, char value[]) {
    // Handle LED instructions
    if (type == LED_CONTROL) // Todo: Set this type number to match the gateway code.
    {
        // Adds a \0 to make the ascii-to-integer code to work.
        analogWrite(LED_RED, value[0]);
        analogWrite(LED_GREEN, value[1]);
        analogWrite(LED_BLUE, value[2]);
    } else if (type == PLAY_SOUND) {
        char parsedValue[length + 1];
        for (int i = 0; i < length; i++) {
            parsedValue[i] = value[i];
        }

        // Adds a \0 to make the ascii-to-integer code to work.
        parsedValue[length] = '\0';
        // TODO: Write the code to play sound
    }
}

// This method reads data from the serial connection.
// The method extracts the type and length and sends the message to the handler
// when all bytes have arrived.
void receiveData() {
    // Checks if no message is in the pipe.
    if (type == -1) {
        // Checks if all bytes for the type and length has arrived.
        if (Serial.available() >= 3) {
            // Creates a byte array and reads the type.
            Serial.readBytes(&type, 1);

            // Creates a byte array and reads the length.
            char lengthBuffer[3];
            Serial.readBytes(lengthBuffer, 2);

            // Adds a \0 to make the ascii-to-integer code to work.
            typeBuffer[2] = '\0';

            // Saves the length as a integer.
            length = atoi(lengthBuffer);
        }
    }

    // Checks if a message is in the pipe.
    if (type != -1) // NULL)
    {
        // Checks if all bytes for the message has arrived.
        if (Serial.available() >= length) {
            // Creates a byte array and reads the type.
            char valueBuffer[length];
            Serial.readBytes(valueBuffer, length);

            // Handles the message.
            handleMessage(type, valueBuffer);

            // Setting the message as handled by setting the type to -1 (formerly NULL).
            type = -1; // NULL;
        }
    }
}

void setup() {
    // Setup for that runs once in the beginning.
    // Defining the type of pins, in this case output.
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_AMBER, OUTPUT);
    pinMode(LED_RED, OUTPUT);
    pinMode(PIN_BUTTON, INPUT);

    game_button = RELEASED;

    // Starting a serial connection.
    Serial.begin(9600);
}

// This is the main loop of the Arduino code.
void loop() {
    while (Serial.available())
        receiveData();

    // Waiting 0.05 second.
    delay(50);
}