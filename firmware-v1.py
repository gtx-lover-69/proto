import time
import struct
import bluetooth
from micropython import const
from machine import Pin, SPI, PWM, ADC

# ________DISPLAY_STUFF_________
LCD_SDA = 2
LCD_SCL = 3
LCD_CS = 0
LCD_DC = 1

# ___________BATTERY____________
adc = ADC(28)
DIV = 2.0
VREF = 3.3

vbus = Pin('WL_GPIO2', Pin.IN)

# ___________INPUTS_____________
# UP, DOWN, LEFT, RIGHT = 7, 8, 9, 6
# A, B, C, D = 17, 18, 19, 20
BUTTON_PINS = 7, 8, 9, 6, 17, 18, 19, 20
buttons = [Pin(p, Pin.IN, Pin.PULL_UP) for p in BUTTON_PINS]

# _________BLUETOOTH____________
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)

APPEARANCE = const(963)  # joystick
F_R = bluetooth.FLAG_READ
F_N = bluetooth.FLAG_NOTIFY
F_WNR = bluetooth.FLAG_WRITE_NO_RESPONSE

REPORT_MAP = bytes([
    0x05, 0x01, 0x09, 0x04, 0xA1, 0x01,
    0x05, 0x09, 0x19, 0x01, 0x29, 0x08,
    0x15, 0x00, 0x25, 0x01,
    0x75, 0x01, 0x95, 0x08, 0x81, 0x02,
    0xC0,
])

HID_SERVICE = (
    bluetooth.UUID(0x1812),
    (
        (bluetooth.UUID(0x2A4A), F_R),
        (bluetooth.UUID(0x2A4B), F_R),
        (bluetooth.UUID(0x2A4C), F_WNR),
        (bluetooth.UUID(0x2A4D), F_R | F_N,
            ((bluetooth.UUID(0x2908), F_R),)),
        (bluetooth.UUID(0x2A4E), F_R | F_WNR),
    ),
)

BATTERY_SERVICE = (
    bluetooth.UUID(0x180F),
    ((bluetooth.UUID(0x2A19), F_R | F_N),),
)

DEVINFO_SERVICE = (
    bluetooth.UUID(0x180A),
    (
        (bluetooth.UUID(0x2A29), F_R),
        (bluetooth.UUID(0x2A24), F_R),
    ),
)

ble = bluetooth.BLE()
ble.active(True)
ble.config(gap_name="proto")
ble.config(bond=True)

(
    (h_info, h_map, h_ctrl, h_report, h_ref, h_proto),
    (h_batt,),
    (h_mfr, h_model),
) = ble.gatts_register_services((HID_SERVICE, BATTERY_SERVICE, DEVINFO_SERVICE))

ble.gatts_write(h_info, b"\x11\x01\x00\x02")
ble.gatts_write(h_map, REPORT_MAP)
ble.gatts_write(h_ref, b"\x00\x01")
ble.gatts_write(h_proto, b"\x01")
ble.gatts_write(h_report, b"\x00")
ble.gatts_write(h_batt, b"\x64")
ble.gatts_write(h_mfr, b"matteoduda")
ble.gatts_write(h_model, b"Proto")

_name = b"proto"
ADV = (
    b"\x02\x01\x06"
    + b"\x03\x19" + struct.pack("<H", APPEARANCE)
    + b"\x05\x03\x12\x18\x0F\x18"
    + bytes([len(_name) + 1, 0x09]) + _name
)

conn = None


def irq(event, data):
    global conn
    if event == _IRQ_CENTRAL_CONNECT:
        conn = data[0]
    elif event == _IRQ_CENTRAL_DISCONNECT:
        conn = None
        ble.gap_advertise(100_000, adv_data=ADV)


ble.irq(irq)
ble.gap_advertise(100_000, adv_data=ADV)

# ________BATTERY_FUNCS_________
CURVE = [(4.20, 100), (4.10, 90), (4.00, 80), (3.90, 65), (3.80, 50),
         (3.70, 35), (3.60, 20), (3.50, 10), (3.30, 3), (3.00, 0)]


def battery_voltage():
    total = 0
    for _ in range(16):
        total += adc.read_u16()
        time.sleep_ms(2)
    return (total / 16) / 65535 * VREF * DIV


def battery_percent(v):
    if v >= CURVE[0][0]:
        return 100
    for (v1, p1), (v2, p2) in zip(CURVE, CURVE[1:]):
        if v >= v2:
            return int(p2 + (p1 - p2) * (v - v2) / (v1 - v2))
    return 0


def usb_power():
    return vbus.value() == 1

def is_charging(v):
    return usb_power() and v < 4.15


last_pct = -1


def update_battery():
    global last_pct
    v = battery_voltage()
    pct = battery_percent(v)
    if is_charging(v) and pct > 95:
        pct = 95
    if usb_power() and not is_charging(v):
        pct = 100
    if pct != last_pct:
        ble.gatts_write(h_batt, bytes([pct]))
        if conn is not None:
            ble.gatts_notify(conn, h_batt)
        last_pct = pct


# ________READING_BUTTONS_______
def read_buttons():
    state = 0
    for i, b in enumerate(buttons):
        if not b.value():
            state |= 1 << i
    return state


def send(state):
    if conn is not None:
        ble.gatts_write(h_report, struct.pack("<B", state))
        ble.gatts_notify(conn, h_report)


# ____________MAIN______________
last = 0
last_batt = time.ticks_ms() - 60_000

while True:
    s = read_buttons()
    if s != last:
        send(s)
        last = s

    if time.ticks_diff(time.ticks_ms(), last_batt) > 30_000:
        update_battery()
        last_batt = time.ticks_ms()

    time.sleep_ms(5)