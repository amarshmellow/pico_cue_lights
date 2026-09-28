from machine import Pin
import time
import ws2812
import uasyncio

button = Pin(0, Pin.IN, Pin.PULL_UP)
boardled = Pin("LED", Pin.OUT)


async def led_on():
    ws2812.pixels_fill((16,16,16))
    await ws2812.pixels_show()

async def led_off():
    ws2812.pixels_fill((0,0,0))
    await ws2812.pixels_show()

for i in range(3):
    boardled.value(1)
    time.sleep(0.1)
    boardled.value(0)
    time.sleep(0.1)

while True:
    if button.value() == 1:
        # boardled.value(0)
        uasyncio.run(led_off())
    else:
        # boardled.value(1)
        uasyncio.run(led_on())
