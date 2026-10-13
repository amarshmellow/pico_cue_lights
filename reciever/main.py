import time
import bluetooth
from machine import Pin
from micropython import const
from ble_advertising import advertising_payload

try:
    import ws2812  # Optional: only the board with the LED strip has this
except ImportError:
    ws2812 = None

# ---- Pins ----
BUTTON_PIN = 0
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
toggle_led = Pin("LED", Pin.OUT)

for _ in range(3):
    toggle_led.value(1)
    time.sleep(0.1)
    toggle_led.value(0)
    time.sleep(0.1)

# ---- BLE constants ----
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_SCAN_RESULT = const(5)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_NOTIFY = const(18)

_FLAG_READ = const(0x0002)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

DEVICE_NAME = "REMOTE_BUTTON"
_SERVICE_UUID = bluetooth.UUID(0x1815)
_CHAR_UUID = bluetooth.UUID(0x2A56)
_CHAR = (_CHAR_UUID, _FLAG_READ | _FLAG_WRITE | _FLAG_NOTIFY)
_SERVICE = (_SERVICE_UUID, (_CHAR,))


def get_name(adv_data):
    adv = bytes(adv_data)
    i = 0
    while i < len(adv):
        length = adv[i]
        if length == 0:
            break
        if adv[i + 1] == 0x09:  # Complete local name
            try:
                return adv[i + 2:i + 1 + length].decode()
            except ValueError:
                return None
        i += 1 + length
    return None


class TwoWayBLE:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.irq)
        ((self.handle,),) = self.ble.gatts_register_services((_SERVICE,))

        self.my_addr = self.ble.config("mac")[1]  # Used to decide who connects
        self.conn_handle = None
        self.role = None                 # "central" or "peripheral"
        self.peer_value_handle = None    # Only used when we are central
        self.connecting = False
        self.led_state = 0

        self.start_discovery()

    # ---- Discovery ----
    def start_discovery(self):
        self.connecting = False
        self.ble.gap_advertise(
            100000,
            adv_data=advertising_payload(name=DEVICE_NAME, services=[_SERVICE_UUID]),
        )
        self.ble.gap_scan(0, 30000, 30000)  # 0 = scan until stopped
        print("Advertising and scanning for", DEVICE_NAME)

    def stop_discovery(self):
        self.ble.gap_scan(None)
        self.ble.gap_advertise(None)

    # ---- IRQ handler ----
    def irq(self, event, data):
        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, _, _, adv_data = data
            if self.conn_handle is not None or self.connecting:
                return
            if get_name(adv_data) != DEVICE_NAME:
                return
            addr = bytes(addr)
            # Tie-break: only the board with the lower address connects,
            # so both boards don't try to connect to each other at once.
            if self.my_addr < addr:
                self.connecting = True
                self.ble.gap_scan(None)
                self.ble.gap_connect(addr_type, addr)
                print("Found peer - connecting...")

        elif event == _IRQ_CENTRAL_CONNECT:
            # Another board connected to us: we are the peripheral
            self.conn_handle, _, _ = data
            self.role = "peripheral"
            self.stop_discovery()
            print("Connected (peripheral)")

        elif event == _IRQ_PERIPHERAL_CONNECT:
            # We connected to another board: we are the central
            self.conn_handle, _, _ = data
            self.role = "central"
            self.stop_discovery()
            print("Connected (central) - discovering...")
            self.ble.gattc_discover_characteristics(self.conn_handle, 1, 65535)

        elif event in (_IRQ_CENTRAL_DISCONNECT, _IRQ_PERIPHERAL_DISCONNECT):
            print("Disconnected - restarting discovery")
            self.conn_handle = None
            self.role = None
            self.peer_value_handle = None
            self.start_discovery()

        # ---- Central-side events ----
        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            _, _, value_handle, _, uuid = data
            if uuid == _CHAR_UUID:
                self.peer_value_handle = value_handle

        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            if self.peer_value_handle is not None:
                # Subscribe to notifications (CCCD is right after the value handle)
                self.ble.gattc_write(self.conn_handle, self.peer_value_handle + 1, b"\x01\x00", 1)
                print("Subscribed to peer notifications")
            else:
                print("Warning: peer characteristic not found")

        elif event == _IRQ_GATTC_NOTIFY:
            _, _, notify_data = data
            self._handle_incoming(notify_data)

        # ---- Peripheral-side events ----
        elif event == _IRQ_GATTS_WRITE:
            _, value_handle = data
            if value_handle == self.handle:  # Ignore the CCCD subscribe write
                self._handle_incoming(self.ble.gatts_read(self.handle))

    # ---- Receiving ----
    def _handle_incoming(self, raw):
        try:
            state = int(bytes(raw).decode())
        except ValueError:
            print("Bad data:", raw)
            return
        print("Received state:", state)
        self.set_state(state)

    # ---- Sending ----
    def send(self, value):
        if self.conn_handle is None:
            print("Not connected - not sent")
            return
        payload = str(value).encode()
        if self.role == "central":
            if self.peer_value_handle is not None:
                self.ble.gattc_write(self.conn_handle, self.peer_value_handle, payload, 1)
        else:
            self.ble.gatts_notify(self.conn_handle, self.handle, payload)

    # ---- LED handling ----
    def set_state(self, state):
        self.led_state = state
        toggle_led.value(state)
        if ws2812:
            if state:
                ws2812.pixels_fill([0, 0, 0])   # Same mapping as the original receiver
            else:
                ws2812.pixels_fill([16, 16, 16])
            ws2812.pixels_show()


bt = TwoWayBLE()
last_pressed = False
print("Ready")

while True:
    pressed = button.value() == 0
    if pressed and not last_pressed:
        new_state = 1 - bt.led_state
        bt.set_state(new_state)
        bt.send(new_state)
        print("Button pressed - sent state:", new_state)
    last_pressed = pressed
    time.sleep(0.05)