"""Constants for the FNIRSI FNB58 USB Fast Charge Tester integration."""

DOMAIN = "fnb58"

# Official product name (FNIRSI store: FNB58 BT = Bluetooth variant)
DEVICE_NAME = "FNIRSI FNB58 USB Fast Charge Tester"
DEVICE_MODEL = "FNB58 BT"

# BLE characteristics (confirmed via nRF Connect)
NOTIFY_CHARACTERISTIC = "0000ffe4-0000-1000-8000-00805f9b34fb"
WRITE_CHARACTERISTIC  = "0000ffe9-0000-1000-8000-00805f9b34fb"

# Stream-start handshake only (not device control); required to receive notifications
INIT_COMMANDS = [
    bytes([0xAA, 0x81, 0x00, 0xF4]),
    bytes([0xAA, 0x82, 0x00, 0xA7]),
]

# Packet parsing: 3× little-endian int32 at offset 21, divide by 10000
DATA_OFFSET = 21
DATA_SCALE  = 10000.0

# Config entry keys
CONF_ADDRESS = "address"

# Connection / reconnect timing
CONNECT_TIMEOUT = 15
RECONNECT_MIN_DELAY = 30
RECONNECT_MAX_DELAY = 120

# Ignore integration gaps longer than this (seconds) after disconnect/reconnect
MAX_SAMPLE_INTERVAL = 10
