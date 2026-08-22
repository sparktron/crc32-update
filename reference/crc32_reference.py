"""Normative reflected IEEE CRC-32 update model.

The function in this module intentionally mirrors SPEC.md. It consumes data[0]
first, shifts the raw state right, and applies the reflected 0xEDB88320
polynomial without initial or final complementation.
"""

from __future__ import annotations

import argparse

POLY = 0xEDB88320
CRC_MASK = 0xFFFFFFFF
DATA_MASK = 0xFFFFFFFFFFFFFFFF


def crc32_update_reference(crc: int, data: int) -> int:
    """Return the raw CRC state after consuming exactly 64 reflected bits."""

    crc &= CRC_MASK
    data &= DATA_MASK

    for i in range(64):
        feedback = (crc ^ (data >> i)) & 1
        crc >>= 1
        if feedback:
            crc ^= POLY

    return crc & CRC_MASK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crc", type=lambda value: int(value, 0))
    parser.add_argument("data", type=lambda value: int(value, 0))
    args = parser.parse_args()
    print(f"0x{crc32_update_reference(args.crc, args.data):08x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
