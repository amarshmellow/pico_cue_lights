import bluetooth
import time
import utime
from machine import Pin
import ws2812

DEBUG = True

def dbg(*args):
    if DEBUG:
        print("[S]", *args)

# Change these for each slave board
NAME = "pico-1"       # must match the master's SLAVES list
MY_SLOT = 0           # pico-1 -> 0, pico-2 -> 1, pico-3 -> 2, pico-4 -> 3
MASTER_NAME = "master"

MAGIC_MASTER = 0x4D   # first byte of every master message
MAGIC_SLAVE = 0x53    # first byte of every slave message

# Phases
WAITING = 0
RED = 1
YELLOW = 2
GREEN = 3

# Green flash timing
GREEN_FLASH_MS = 3000      # flash for this long after green is given, then solid
FLASH_INTERVAL_MS = 100   # time each flash stays on or off

# Hardware
ble = bluetooth.BLE()
ble.active(True)
button = Pin(0, Pin.IN, Pin.PULL_UP)

# State
phase = WAITING
incoming = {}                 # latest message heard from each board, keyed by name
last_reset = None             # last reset counter acted on
last_go = None                # last go counter acted on
last_press = None             # last press counter for this slave acted on
button_last = button.value()
button_down = button_last == 0

# Green flash state
green_start = None            # time green was given (ms)
green_solid = False           # True once the flash period has finished
flash_on = False
last_flash = 0


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
    """Advertise a message (bytes) so the master can read it."""
    name_b = NAME.encode()
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


def read_master():
    """Return (reset, go, press) from the master, or None if not heard yet."""
    message = receive(MASTER_NAME)
    if message is None or message[0] != MAGIC_MASTER:
        return None
    reset_count = message[1]
    go_count = message[2]
    press_count = message[3 + MY_SLOT]   # this slave's own press counter
    return reset_count, go_count, press_count


def show_phase(state):
    if state == RED:
        colour = (0, 255, 0)
    elif state == YELLOW:
        colour = (100, 255, 0)
    elif state == GREEN:
        colour = (255, 0, 0)
    else:
        colour = (0, 0, 0)
    ws2812.pixels_fill(colour)
    ws2812.pixels_show()


def start_green_flash():
    """Called when green is given: LED starts on and flashes for GREEN_FLASH_MS."""
    global green_start, green_solid, flash_on, last_flash
    now = utime.ticks_ms()
    green_start = now
    green_solid = False
    flash_on = True
    last_flash = now


def update_green_flash():
    """Flash the green LED, then hold it solid once the flash period has passed."""
    global green_solid, flash_on, last_flash
    if phase != GREEN or green_solid:
        return
    now = utime.ticks_ms()
    if utime.ticks_diff(now, green_start) >= GREEN_FLASH_MS:
        green_solid = True
        show_phase(GREEN)
        dbg("green now solid")
        return
    if utime.ticks_diff(now, last_flash) >= FLASH_INTERVAL_MS:
        last_flash = now
        flash_on = not flash_on
        show_phase(GREEN if flash_on else WAITING)


def advance(next_phase):
    global phase
    phase = next_phase
    show_phase(phase)
    if phase == GREEN:
        start_green_flash()
    broadcast(bytes([MAGIC_SLAVE, phase]))
    dbg("phase", phase)


def reset_phase():
    global phase
    phase = WAITING
    show_phase(phase)
    broadcast(bytes([MAGIC_SLAVE, phase]))   # tell the master we've reset
    dbg("reset phase to 0 (WAITING)")


def check_master():
    global last_reset, last_go, last_press
    master = read_master()
    if master is None:
        return
    reset_count, go_count, press_count = master

    # Master reset: act only when the counter changes, not on first sight
    if last_reset is not None and reset_count != last_reset:
        reset_phase()
    last_reset = reset_count

    # All go: a YELLOW slave moves to GREEN when the go counter changes
    if last_go is not None and go_count != last_go and phase == YELLOW:
        advance(GREEN)
        dbg("all go received")
    last_go = go_count

    # Master button for this slave: WAITING -> RED, then YELLOW -> GREEN
    if last_press is not None and press_count != last_press:
        if phase == WAITING:
            advance(RED)
        elif phase == YELLOW:
            advance(GREEN)
        dbg("master press", press_count)
    last_press = press_count


def check_own_button():
    global button_last, button_down
    cur = button.value()
    if cur != button_last:
        time.sleep_ms(30)
        cur = button.value()
        if cur != button_last:
            button_last = cur
            is_down = cur == 0
            # Slave's own button confirms readiness after red: RED -> YELLOW
            if is_down and not button_down and phase == RED:
                advance(YELLOW)
            button_down = is_down


ble.irq(irq)
broadcast(bytes([MAGIC_SLAVE, WAITING]))
ble.gap_scan(0, 30000, 30000)   # continuous scan for the master
show_phase(WAITING)
dbg("advertising as", NAME, "slot", MY_SLOT)

while True:
    check_master()
    check_own_button()
    update_green_flash()
    time.sleep_ms(20)