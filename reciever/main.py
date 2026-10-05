from machine import Pin
import time
import ws2812
import uasyncio
import bluetooth
from micropython import const
import random


button = Pin(0, Pin.IN, Pin.PULL_UP)
toggle_led = Pin("LED", Pin.OUT)  # Button toggle status LED

for i in range(3):
    toggle_led.value(1)
    time.sleep(0.1)
    toggle_led.value(0)
    time.sleep(0.1)



# def led_on():
#     ws2812.pixels_fill((16,16,16))
#     ws2812.pixels_show()

# def led_off():
#     ws2812.pixels_fill((0,0,0))
#     ws2812.pixels_show()


# while True:
#     if button.value() == 1:
#         # boardled.value(0)
#         led_off()
#     else:
#         # boardled.value(1)
#         led_on()



_IRQ_SCAN_RESULT = const(5)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_NOTIFY = const(18)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)

_CHAR_UUID = bluetooth.UUID(0x2A56)

class SimpleReceiver:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.irq)
        self.conn_handle = None
        self.value_handle = None
        
    def irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, _, _, adv_data = data
            if self.get_name(adv_data) == "REMOTE_BUTTON":
                self.ble.gap_scan(None)
                self.ble.gap_connect(addr_type, addr)
                print("Found REMOTE_BUTTON - connecting...")
                
        elif event == _IRQ_PERIPHERAL_CONNECT:
            self.conn_handle, _, _ = data
            print("Connected - discovering...")
            self.ble.gattc_discover_characteristics(self.conn_handle, 1, 65535)
            
        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            print("Disconnected - scanning...")
            toggle_led.value(0)  # Turn off LED when disconnected
            self.conn_handle = None
            self.value_handle = None
            self.scan()
            
        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            _, _, value_handle, _, uuid = data
            if uuid == _CHAR_UUID:
                self.value_handle = value_handle
                print(f"Found characteristic - handle: {value_handle}")
                
        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            if self.value_handle:
                # Enable notifications by writing to the CCCD (Client Characteristic Configuration Descriptor)
                self.ble.gattc_write(self.conn_handle, self.value_handle + 1, b'\x01\x00', 1)
                print("Subscribed to notifications!")
            else:
                print("Warning: Characteristic not found")
                
        elif event == _IRQ_GATTC_NOTIFY:
            _, _, notify_data = data
            print(f"Received raw data: {notify_data}")
            
            try:
                # Convert memoryview to bytes first
                state = int(bytes(notify_data).decode())

                # output LEDS
                if state:
                    print("Output LEDS off")
                    ws2812.pixels_fill([0,0,0])
                    ws2812.pixels_show()
                else:
                    print("Output LEDS on")
                    ws2812.pixels_fill([16,16,16])
                    ws2812.pixels_show()
                            
                # Update LED to match transmitter state
                toggle_led.value(state)
                print(f"LED state: {state}")
            except (ValueError, Exception) as e:
                print(f"Error decoding data: {e}")
    
    def get_name(self, adv_data):
        i = 0
        while i < len(adv_data):
            length = adv_data[i]
            if length == 0:
                break
            if adv_data[i + 1] == 0x09:  # Name type
                return bytes(adv_data[i + 2:i + 1 + length]).decode()
            i += 1 + length
        return None
    
    def scan(self):
        print("Starting scan...")
        self.ble.gap_scan(2000, 30000, 30000)

# Setup
rx = SimpleReceiver()
print("Receiver ready - looking for REMOTE_BUTTON...")

rx.scan()

while True:
    time.sleep(1)
