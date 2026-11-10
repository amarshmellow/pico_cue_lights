from micropython import const
import struct

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_APPEARANCE = const(0x19)

def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, appearance=0):
    payload = bytearray()
    
    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value
    
    _append(_ADV_TYPE_FLAGS, struct.pack("B", (0x01 if limited_disc else 0x02) + (0x00 if br_edr else 0x04)))
    
    if name:
        _append(_ADV_TYPE_NAME, name.encode())
    
    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 4:
                _append(_ADV_TYPE_UUID32_COMPLETE, b)
            elif len(b) == 16:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)
    
    if appearance:
        _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))
    
    return payload