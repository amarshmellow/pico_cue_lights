import bluetooth
import time
from machine import Pin
import ws2812

DEBUG = True

def dbg(*args):
    if DEBUG:
        print("[M]", *args)

# Board names and message markers
MASTER_NAME = "master"
SLAVES = ["pico-1", "pico-2", "pico-3", "pico-4"]
MAGIC_MASTER = 0x4D   # first byte of every master message
MAGIC_SLAVE = 0x53    # first byte of every slave message

# Pins
BUTTON_PIN = {"pico-1": 21, "pico-2": 21, "pico-3": 19, "pico-4": 18}   # one button per slave
RESET_PIN = 16
GO_PIN = 17

# Phases and their LED colours (in the byte order ws2812 expects)
WAITING = 0
RED = 1
YELLOW = 2
GREEN = 3
COLOURS = {
    WAITING: (0, 0, 0),
    RED: (0, 255, 0),
    YELLOW: (100, 255, 0),
    GREEN: (255, 0, 0),
}

# Hardware
ble = bluetooth.BLE()
ble.active(True)
onboard_led = Pin("LED", Pin.OUT)

buttons = {name: Pin(pin, Pin.IN, Pin.PULL_UP) for name, pin in BUTTON_PIN.items()}
button_last = {name: buttons[name].value() for name in SLAVES}

reset_btn = Pin(RESET_PIN, Pin.IN, Pin.PULL_UP)
reset_last = reset_btn.value()

go_btn = Pin(GO_PIN, Pin.IN, Pin.PULL_UP)
go_last = go_btn.value()

# Values this master broadcasts
press_count = [0] * len(SLAVES)   # one per slave, wraps at 256
reset_count = 0
go_count = 0

# Latest message heard from each board, keyed by name
incoming = {}

# What each LED currently shows
shown_phase = {}

onboard_led.value(1)


def fields(payload):
    """Split raw advertisement data into (type, data) pairs."""
    i = 0
    while i < len(payload):
        length = payload[i]
        if length == 0:
            break
        yield payload[i + 1], bytes(payload[i + 2:i + 1 + length])
        i += 1 + length


def broadcast(message):
    """Advertise a message (bytes) so the slaves can read it."""
    name_b = MASTER_NAME.encode()
    flags = bytes([2, 0x01, 0x06])
    name_field = bytes([len(name_b) + 1, 0x09]) + name_b
    # manufacturer data: type 0xFF, company 0xFFFF, then the message
    mfr = bytes([len(message) + 3, 0xFF, 0xFF, 0xFF]) + message
    ble.gap_advertise(None)
    ble.gap_advertise(100_000, adv_data=flags + name_field + mfr)


def receive(name):
    """Return the latest message heard from a board, or None."""
    return incoming.get(name)


def irq(event, data):
    if event != 5:
        return
    addr_type, addr, adv_type, rssi, adv_data = data
    name = None
    message = None
    for t, d in fields(adv_data):
        if t == 0x09:
            name = d.decode("utf-8", "ignore")
        elif t == 0xFF and d[:2] == b"\xff\xff":
            message = bytes(d[2:])
    if name is not None and message is not None:
        incoming[name] = message


def read_phase(name):
    """The phase a slave last reported, or WAITING if we haven't heard it."""
    message = receive(name)
    if message is not None and message[0] == MAGIC_SLAVE:
        return message[1]
    return WAITING


def send_state():
    """Build the master message from the current counters and broadcast it."""
    broadcast(bytes([MAGIC_MASTER, reset_count, go_count] + press_count))
    dbg("sent presses", press_count, "reset", reset_count, "go", go_count)


def update_leds():
    changed = False
    for index, name in enumerate(SLAVES):
        phase = read_phase(name)
        if shown_phase.get(name) != phase:
            shown_phase[name] = phase
            ws2812.pixels_set(index, COLOURS[phase])
            changed = True
            dbg(name, "phase", phase)
    if changed:
        ws2812.pixels_show()

    # Onboard LED is on if any slave is past WAITING
    any_active = any(read_phase(name) != WAITING for name in SLAVES)
    #onboard_led.value(1 if any_active else 0)


def check_slave_buttons():
    global press_count
    for index, name in enumerate(SLAVES):
        cur = buttons[name].value()
        if cur != button_last[name]:
            time.sleep_ms(30)
            cur = buttons[name].value()
            if cur != button_last[name]:
                button_last[name] = cur
                if cur == 0:   # pressed
                    press_count[index] = (press_count[index] + 1) & 0xFF
                    send_state()
                    dbg(name, "pressed, count", press_count[index])


def check_reset_button():
    global reset_last, reset_count
    cur = reset_btn.value()
    if cur != reset_last:
        time.sleep_ms(30)
        cur = reset_btn.value()
        if cur != reset_last:
            reset_last = cur
            if cur == 0:
                reset_count = (reset_count + 1) & 0xFF
                send_state()
                dbg("reset pressed, counter", reset_count)


def check_go_button():
    global go_last, go_count
    cur = go_btn.value()
    if cur != go_last:
        time.sleep_ms(30)
        cur = go_btn.value()
        if cur != go_last:
            go_last = cur
            if cur == 0:
                go_count = (go_count + 1) & 0xFF
                send_state()
                dbg("all-go pressed, counter", go_count)


ble.irq(irq)
send_state()
ws2812.pixels_fill(COLOURS[WAITING])
ws2812.pixels_show()
ble.gap_scan(0, 30000, 30000)   # 0 = scan continuously
dbg("running")

while True:
    check_slave_buttons()
    check_reset_button()
    check_go_button()
    update_leds()
    time.sleep_ms(20)