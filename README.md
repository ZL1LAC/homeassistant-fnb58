# FNIRSI FNB58 USB Fast Charge Tester — Home Assistant

Home Assistant custom integration for the [FNIRSI FNB58 USB Fast Charge Tester](https://www.fnirsi.com/products/fnb58) (Bluetooth / **FNB58 BT** variant).

Read-only over Bluetooth: live **voltage**, **current**, and **power**, plus **energy** (Wh) and **capacity** (Ah) integrated in Home Assistant while connected.

## Requirements

- Home Assistant with the [Bluetooth](https://www.home-assistant.io/integrations/bluetooth/) integration
- FNB58 **BT** model (Bluetooth); unplug USB **data** when using BLE (USB and BLE cannot run together)

## Installation

### Manual

1. Copy the `fnb58` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration** → search for **FNIRSI FNB58 USB Fast Charge Tester**.

### HACS (optional)

This repository can be added as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/) in HACS if you publish a release; default layout is the `fnb58` integration folder at the repo root.

## Entities

| Entity | Description |
|--------|-------------|
| Voltage | Live bus voltage (V) |
| Current | Live current (A) |
| Power | Live power (W) |
| Energy | Host-side energy total (Wh) |
| Capacity | Host-side capacity total (Ah) |

## Notes

- The meter does not need to stay powered on; the integration reconnects when it is on and in range.
- BLE exposes live measurements only. Fast-charge trigger, clear records, and similar actions use the device UI or USB tools—not this integration.
- Protocol based on community reverse engineering ([parkerlreed gist](https://gist.github.com/parkerlreed/0ce45e907ce536a0541afb90b5b49350), [fnirsi-usb-power-data-logger](https://github.com/baryluk/fnirsi-usb-power-data-logger)).

## License

MIT
