import bluetooth
from ble_advertising import advertising_payload
from micropython import const
from machine import Pin
import time

# Pin definitions
# connection_led = Pin(10, Pin.OUT)  # Connection status LED
toggle_led = Pin("LED", Pin.OUT)   # Button toggle status LED
button = Pin(1, Pin.IN, Pin.PULL_UP)

for i in range(3):
    toggle_led.value(1)
    time.sleep(0.1)
    toggle_led.value(0)    
    time.sleep(0.1)

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_FLAG_NOTIFY = const(0x0010)

# Simple service
_SERVICE_UUID = bluetooth.UUID(0x1815)
_CHAR_UUID = bluetooth.UUID(0x2A56)
_CHAR = (_CHAR_UUID, _FLAG_NOTIFY)
_SERVICE = (_SERVICE_UUID, (_CHAR,))

class SimpleTransmitter:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.irq)
        ((self.handle,),) = self.ble.gatts_register_services((_SERVICE,))
        self.connected = False
        self.conn_handle = None  # Store connection handle
        self.advertise()
        
    def irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self.conn_handle = data[0]  # Save the connection handle
            self.connected = True
            print("Connected")
# connection_led.value(1)  # Turn on connection LED
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self.conn_handle = None
            self.connected = False
            print("Disconnected")
# connection_led.value(0)  # Turn off connection LED
            self.advertise()
    
    def advertise(self):
        payload = advertising_payload(name="REMOTE_BUTTON", services=[_SERVICE_UUID])
        self.ble.gap_advertise(100000, adv_data=payload)
    
    def send(self, value):
        if self.connected and self.conn_handle is not None:
            # Use the actual connection handle, not 0
            self.ble.gatts_notify(self.conn_handle, self.handle, str(value).encode())

# Setup
tx = SimpleTransmitter()
last_button = 1  # Start with button unpressed (pull-up = 1 when not pressed)
led_state = 0    # LED starts off
toggle_led.value(0)  # Make sure LED is off at start

print("Transmitter ready - advertising as REMOTE_BUTTON")

while True:
    current_button = button.value()

    
    inverted = 1 if current_button == 0 else 0

    if inverted == 1 and last_button == 0:
        # Button was just pressed - toggle LED
        led_state = 1 - led_state  # Toggle between 0 and 1
        toggle_led.value(led_state)  # Update LED immediately
        print(f"Button pressed - LED toggled to: {led_state}")
        tx.send(led_state)
    
    last_button = inverted
    time.sleep(0.05)