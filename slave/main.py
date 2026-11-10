import bluetooth
import time
from machine import Pin
import ws2812

DEBUG = True

def dbg(*args):
    if DEBUG:
        print("[S]", *args)

NAME = "pico-1"   # pico-2 on the second slave
MY_BIT = 0        # pico-1 -> 0, pico-2 -> 1

MAGIC_MASTER = 0x4D
MAGIC_SLAVE = 0x53

button = Pin(0, Pin.IN, Pin.PULL_UP)
ble = bluetooth.BLE()
ble.active(True)

master_bit = None    # set by IRQ from master's advertisement
shown_bit = None     # what the LED currently shows

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
    global master_bit
    if event == 5:
        addr_type, addr, adv_type, rssi, adv_data = data
        for t, d in fields(adv_data):
            if t == 0xFF and len(d) >= 4 and d[:2] == b"\xff\xff" and d[2] == MAGIC_MASTER:
                master_bit = (d[3] >> MY_BIT) & 1

def show(bit):
    colour = (0, 255, 0) if bit else (0, 0, 0)
    ws2812.pixels_fill(colour)
    ws2812.pixels_show()

ble.irq(irq)
set_adv(0)
ble.gap_scan(0, 30000, 30000)   # continuous scan for the master
show(0)
dbg("advertising as", NAME)

last = button.value()
state = 0
while True:
    # Apply LED from the master's latest state
    if master_bit is not None and master_bit != shown_bit:
        shown_bit = master_bit
        show(shown_bit)
        dbg("LED", "on" if shown_bit else "off")

    # Read local button, debounce, update advertised state
    cur = button.value()
    if cur != last:
        time.sleep_ms(30)
        cur = button.value()
        if cur != last:
            last = cur
            state = 1 if cur == 0 else 0
            set_adv(state)
            dbg("button", "down" if state else "up", "advertising")
    time.sleep_ms(20)