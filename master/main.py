import bluetooth
import time
from machine import Pin

DEBUG = True

def dbg(*args):
    if DEBUG:
        print("[M]", *args)

MAGIC_MASTER = 0x4D   # marks master packets
MAGIC_SLAVE = 0x53    # marks slave packets
TARGET_BIT = {"pico-1": 0, "pico-2": 1}   # which bit each slave reads
BUTTON_PIN = {"pico-1": 1, "pico-2": 2}   # master button for each slave
RESET_PIN = 3                              # master reset button

onboard_led = Pin("LED", Pin.OUT)
buttons = {n: Pin(p, Pin.IN, Pin.PULL_UP) for n, p in BUTTON_PIN.items()}
btn_last = {n: buttons[n].value() for n in buttons}
reset_btn = Pin(RESET_PIN, Pin.IN, Pin.PULL_UP)
reset_last = reset_btn.value()
reset_count = 0          # incremented on each reset press, wraps at 256
btn_bits = 0             # bit set = that slave's button is pressed
adv_bits = None          # bits currently being advertised
slave_pressed = {}       # slave name -> bool, from scan results
slave_printed = {}       # for printing changes only

ble = bluetooth.BLE()
ble.active(True)

def fields(payload):
    i = 0
    while i < len(payload):
        length = payload[i]
        if length == 0:
            break
        yield payload[i + 1], bytes(payload[i + 2:i + 1 + length])
        i += 1 + length

def build_adv(bits):
    flags = bytes([2, 0x01, 0x06])
    # length 6: type 0xFF, company ID 0xFFFF, magic, bits, reset counter
    mfr = bytes([6, 0xFF, 0xFF, 0xFF, MAGIC_MASTER, bits, reset_count])
    return flags + mfr

def set_adv(bits):
    ble.gap_advertise(None)
    ble.gap_advertise(100_000, adv_data=build_adv(bits))
    dbg("advertising bits", bin(bits), "reset", reset_count)

def irq(event, data):
    if event == 5:
        addr_type, addr, adv_type, rssi, adv_data = data
        name = None
        state = None
        for t, d in fields(adv_data):
            if t == 0x09:
                name = d.decode("utf-8", "ignore")
            elif t == 0xFF and len(d) >= 4 and d[:2] == b"\xff\xff" and d[2] == MAGIC_SLAVE:
                state = d[3]
        if name in TARGET_BIT and state is not None:
            slave_pressed[name] = bool(state)

def tick():
    global btn_bits, adv_bits, reset_last, reset_count
    # Read each master button, debounce, and update the bit for its slave
    for name, pin in buttons.items():
        cur = pin.value()
        if cur != btn_last[name]:
            time.sleep_ms(30)
            cur = pin.value()
            if cur != btn_last[name]:
                btn_last[name] = cur
                bit = 1 << TARGET_BIT[name]
                if cur == 0:
                    btn_bits |= bit
                else:
                    btn_bits &= ~bit
    if btn_bits != adv_bits:
        adv_bits = btn_bits
        set_adv(adv_bits)

    # Reset button: each press bumps the counter, which the slaves act on
    cur = reset_btn.value()
    if cur != reset_last:
        time.sleep_ms(30)
        cur = reset_btn.value()
        if cur != reset_last:
            reset_last = cur
            if cur == 0:
                reset_count = (reset_count + 1) & 0xFF
                adv_bits = btn_bits
                set_adv(adv_bits)
                dbg("reset pressed, counter", reset_count)

    # Print slave button changes
    for name, pressed in slave_pressed.items():
        if slave_printed.get(name) != pressed:
            slave_printed[name] = pressed
            dbg(name, "button", "down" if pressed else "up")
    # Onboard LED: on if any slave button is pressed
    onboard_led.value(1 if any(slave_pressed.values()) else 0)

ble.irq(irq)
set_adv(0)
ble.gap_scan(0, 30000, 30000)   # 0 = scan continuously
dbg("running")

while True:
    tick()
    time.sleep_ms(20)