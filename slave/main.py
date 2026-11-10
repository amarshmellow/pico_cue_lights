import bluetooth
import time
from machine import Pin
import ws2812

DEBUG = True

def dbg(*args):
    if DEBUG:
        print("[S]", *args)

# TODO: make this configurable via JSON file
NAME = "pico-1"   # pico-2 on the second slave
MY_BIT = 0        # pico-1 -> 0, pico-2 -> 1

MAGIC_MASTER = 0x4D
MAGIC_SLAVE = 0x53

WAITING = 0
RED = 1
YELLOW = 2
GREEN = 3

button = Pin(0, Pin.IN, Pin.PULL_UP)
ble = bluetooth.BLE()
ble.active(True)

master_bit = None     # set by IRQ from master's advertisement
master_reset = None   # reset counter from master's advertisement
last_reset = None     # last counter value acted on
phase = WAITING

def fields(payload):
    i = 0
    while i < len(payload):
        length = payload[i]
        if length == 0:
            break
        yield payload[i + 1], bytes(payload[i + 2:i + 1 + length])
        i += 1 + length

def build_adv(state):
    name_b = NAME.encode()
    flags = bytes([2, 0x01, 0x06])
    name_field = bytes([len(name_b) + 1, 0x09]) + name_b
    # length 5: type 0xFF, company ID 0xFFFF (test value), magic, state
    mfr = bytes([5, 0xFF, 0xFF, 0xFF, MAGIC_SLAVE, state])
    return flags + name_field + mfr

def set_adv(state):
    ble.gap_advertise(None)
    ble.gap_advertise(100_000, adv_data=build_adv(state))

def irq(event, data):
    global master_bit, master_reset
    if event == 5:
        addr_type, addr, adv_type, rssi, adv_data = data
        for t, d in fields(adv_data):
            if t == 0xFF and len(d) >= 4 and d[:2] == b"\xff\xff" and d[2] == MAGIC_MASTER:
                master_bit = (d[3] >> MY_BIT) & 1
                if len(d) >= 5:
                    master_reset = d[4]

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

def advance(next_phase):
    global phase
    phase = next_phase
    show_phase(phase)
    set_adv(phase)
    dbg("phase", phase)

def reset_phase():
    global phase
    phase = WAITING
    show_phase(phase)
    set_adv(phase)   # advertise the reset so the master sees it
    dbg("Reset phase to 0 (WAITING)")

ble.irq(irq)
set_adv(WAITING)
ble.gap_scan(0, 30000, 30000)   # continuous scan for the master
show_phase(WAITING)
dbg("advertising as", NAME)

last_button = button.value()
button_down = last_button == 0
last_master_bit = 0
while True:
    # Master reset: act only when the counter changes, not on first sight
    current_reset = master_reset
    if current_reset is not None:
        if last_reset is not None and current_reset != last_reset:
            reset_phase()
        last_reset = current_reset

    # The first master press starts the exchange; the next one completes it.
    current_master_bit = master_bit

    if current_master_bit is not None and current_master_bit != last_master_bit:
        last_master_bit = current_master_bit
        if current_master_bit == 1 and phase == YELLOW:
            advance(GREEN)
        elif current_master_bit == 1 and phase == WAITING:
            advance(RED)

    # The slave's button confirms readiness after the red acknowledgement.
    cur = button.value()

    if cur != last_button:
        time.sleep_ms(30)
        cur = button.value()
        if cur != last_button:
            last_button = cur
            is_down = cur == 0
            if is_down and not button_down and phase == RED:
                advance(YELLOW)
            button_down = is_down
    time.sleep_ms(20)