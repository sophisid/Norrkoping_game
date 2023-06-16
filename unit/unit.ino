/*
 * TNK116 - Internet of Things
 * Sketch for blink
 * Board Arduino UNO
 * 1 x green LED
 * 1 x amber LED
 * 1 x red LED
 * 1 x button / pressure plate
 */
#include <SD.h>
#define SD_ChipSelectPin 10
#include <SPI.h>
#include <TMRpcm.h>

TMRpcm tmrpcm;

    // Declaring variable to store LED instructions.
byte type = 0; // NULL;
int length = -1;    // NULL;

const int LED_RED = 3;
const int LED_GREEN = 5;
const int LED_BLUE = 6;
const int PIN_BUTTON = 10;

const int PIN_SPEAKER = 9;

const int LED_CONTROL = 0xED,
          PLAY_SOUND = 0x50,
          BUTTON_STATE = 0xB0;

int buttonState;            // the current reading from the input pin
int lastButtonState = LOW;  // the previous reading from the input pin

unsigned long lastDebounceTime = 0;  // the last time the output pin was toggled
unsigned long debounceDelay = 50;    // the debounce time; increase if the output flickers

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
        tmrpcm.play(parsedValue);
    }
}

// This method reads data from the serial connection.
// The method extracts the type and length and sends the message to the handler
// when all bytes have arrived.
void receiveData() {
    // Checks if no message is in the pipe.
    if (type == 0) {
        // Checks if all bytes for the type and length has arrived.
        if (Serial.available() >= 3) {
            // Creates a byte array and reads the type.
            Serial.readBytes(&type, 1);

            // Creates a byte array and reads the length.
            char lengthBuffer[3];
            Serial.readBytes(lengthBuffer, 2);
            lengthBuffer[2] = '\0';

            // Saves the length as a integer.
            length = atoi(lengthBuffer);
        }
    }

    // Checks if a message is in the pipe.
    if (type != 0) // NULL)
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
    pinMode(LED_RED, OUTPUT);
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_BLUE, OUTPUT);
    pinMode(PIN_BUTTON, INPUT);

    tmrpcm.speakerPin = PIN_SPEAKER;
    if (!SD.begin(SD_ChipSelectPin)) {  // see if the card is present and can be initialized:
        return;   // don't do anything more if not
    }

    // Starting a serial connection.
    Serial.begin(9600);
}

// This is the main loop of the Arduino code.
void loop() {
    while (Serial.available())
        receiveData();

    int reading = digitalRead(PIN_BUTTON);

    // check to see if you just pressed the button
    // (i.e. the input went from LOW to HIGH), and you've waited long enough
    // since the last press to ignore any noise:

    // If the switch changed, due to noise or pressing:
    if (reading != lastButtonState) {
        // reset the debouncing timer
        lastDebounceTime = millis();
    }

    if ((millis() - lastDebounceTime) > debounceDelay) {
        // whatever the reading is at, it's been there for longer than the debounce
        // delay, so take it as the actual current state:

        // if the button state has changed:
        if (reading != buttonState) {
            buttonState = reading;
            if (buttonState == HIGH)
                sendData(BUTTON_STATE, "press");
            else
                sendData(BUTTON_STATE, "release");
        }
    }

    delay(10);
}