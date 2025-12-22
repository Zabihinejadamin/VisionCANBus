#!/usr/bin/env python3
"""
CAN Interface Test Script

This script helps diagnose CAN interface issues and find working channel names.
Run this script first to determine which CAN interface and channel works on your system.
"""

import sys
import time
from can_communication import CANCommunication, BaudRate, CANResult


def test_interface(channel_name, baudrate=BaudRate.BAUD_250K):
    """Test a specific CAN interface"""
    print(f"Testing {channel_name}...", end=" ", flush=True)

    try:
        can_comm = CANCommunication(channel_name, baudrate)
        result = can_comm.connect()

        if result == CANResult.ERR_OK:
            print("[OK]")
            can_comm.disconnect()
            return True
        else:
            print("[FAILED]")
            return False

    except Exception as e:
        print(f"[ERROR: {e}]")
        return False


def main():
    """Main test function"""
    print("=" * 50)
    print("CAN Interface Test Script")
    print("=" * 50)
    print()

    # Common PCAN channels
    pcan_channels = [
        'PCAN_USBBUS1', 'PCAN_USBBUS2', 'PCAN_USBBUS3', 'PCAN_USBBUS4',
        'PCAN_ISABUS1', 'PCAN_ISABUS2',
        'PCAN_PCIBUS1', 'PCAN_PCIBUS2', 'PCAN_PCIBUS3', 'PCAN_PCIBUS4'
    ]

    # SocketCAN channels (Linux)
    socketcan_channels = ['can0', 'can1', 'can2', 'can3', 'vcan0', 'vcan1']

    # Vector channels
    vector_channels = ['0', '1', '2', '3']

    # IXXAT channels
    ixxat_channels = ['0', '1', '2', '3']

    # Kvaser channels
    kvaser_channels = ['0', '1', '2', '3']

    print("Testing PCAN interfaces...")
    working_pcan = []
    for channel in pcan_channels:
        if test_interface(channel):
            working_pcan.append(channel)

    print("\nTesting SocketCAN interfaces...")
    working_socketcan = []
    for channel in socketcan_channels:
        if test_interface(channel):
            working_socketcan.append(channel)

    print("\nTesting Vector interfaces...")
    working_vector = []
    for channel in vector_channels:
        if test_interface(channel):
            working_vector.append(channel)

    print("\nTesting IXXAT interfaces...")
    working_ixxat = []
    for channel in ixxat_channels:
        if test_interface(channel):
            working_ixxat.append(channel)

    print("\nTesting Kvaser interfaces...")
    working_kvaser = []
    for channel in kvaser_channels:
        if test_interface(channel):
            working_kvaser.append(channel)

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)

    all_working = working_pcan + working_socketcan + working_vector + working_ixxat + working_kvaser

    if all_working:
        print(f"[OK] Found {len(all_working)} working interface(s):")
        for channel in all_working:
            print(f"  - {channel}")

        print(f"\nUse one of these channel names in your application:")
        print(f"monitor = RetainVarMonitor('{all_working[0]}', BaudRate.BAUD_250K)")
    else:
        print("[ERROR] No working CAN interfaces found.")
        print("\nTroubleshooting:")
        print("1. Make sure your CAN interface drivers are installed")
        print("2. Check that the CAN hardware is connected and powered")
        print("3. Verify the interface is not in use by another application")
        print("4. For PCAN: Install drivers from https://www.peak-system.com")
        print("5. For SocketCAN: Configure with 'ip link set can0 up type can bitrate 250000'")
        print("6. For other interfaces: Check manufacturer documentation")

    print("\nNote: Some interfaces may appear to connect but fail during actual communication.")
    print("If you get connection success but communication fails, try a different channel.")

    return len(all_working) > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
