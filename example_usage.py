#!/usr/bin/env python3
"""
Example usage script for the RetainVar Monitor CAN communication library.

This script demonstrates how to:
1. Connect to a CAN bus
2. Select different board types
3. Read and write retain variables
4. Program firmware to devices

Requirements:
- python-can library (pip install python-can)
- PCAN USB adapter or compatible CAN interface
- Actual hardware connected to CAN bus (optional for testing)
"""

import time
import sys
from can_communication import (
    RetainVarMonitor, CANResult, BaudRate,
    CANError, MessageType, CANMessage
)


def print_banner():
    """Print application banner"""
    print("=" * 60)
    print("    RetainVar Monitor - Python CAN Communication Demo")
    print("=" * 60)
    print()

def show_available_interfaces():
    """Show available CAN interfaces"""
    from can_communication import CANCommunication

    print("Available CAN interfaces:")
    interfaces = CANCommunication.list_available_interfaces()

    if interfaces:
        print("Common interface names to try:")
        for interface in interfaces[:8]:  # Show first 8
            print(f"  - {interface}")
        if len(interfaces) > 8:
            print(f"  ... and {len(interfaces) - 8} more")
    else:
        print("No interfaces detected. Make sure python-can is installed correctly.")

    print()
    print("If connection fails, try these common channel names:")
    print("  Windows with PCAN: PCAN_USBBUS1, PCAN_USBBUS2")
    print("  Linux with SocketCAN: can0, can1")
    print("  Windows with Vector: 0, 1")
    print()


def test_connection(monitor):
    """Test CAN bus connection"""
    print("Testing CAN bus connection...")
    result = monitor.connect()

    if result == CANResult.ERR_OK:
        print("[OK] Successfully connected to CAN bus")
        return True
    else:
        print(f"[FAILED] Failed to connect to CAN bus: {result}")
        print("\nTroubleshooting tips:")
        print("- Make sure your CAN interface drivers are installed")
        print("- Check that the CAN channel name is correct:")
        print("  * PCAN: 'PCAN_USBBUS1', 'PCAN_USBBUS2', etc.")
        print("  * SocketCAN (Linux): 'can0', 'can1', etc.")
        print("  * Vector: '0', '1', etc.")
        print("- Verify the CAN interface is not in use by another application")
        print("- Check CAN bus wiring and termination (120 ohm resistors)")
        return False


def test_board_selection(monitor):
    """Test board type selection"""
    print("\nTesting board selection...")

    board_types = ['PCU', 'TCU', 'BMS', 'SCU', 'FCU']

    for board_type in board_types:
        if monitor.select_board(board_type):
            info = monitor.get_board_info()
            print(f"[OK] Selected {board_type} board")
            print(f"  - Variables: {info['variables_count']}")
            print(f"  - CAN ID Base: {info['can_id_base']}")
            break
        else:
            print(f"[ERROR] Failed to select {board_type} board")

    return True


def test_variable_operations(monitor):
    """Test variable read/write operations (requires actual hardware)"""
    print("\nTesting variable operations...")

    if not monitor.current_board:
        print("[ERROR] No board selected")
        return False

    # List first few variables
    variables = monitor.list_variables()
    print(f"Available variables ({len(variables)} total):")

    for i, (idx, name) in enumerate(variables[:5]):
        print("2d")

    print("  ... (truncated)")

    # Note: Actual read/write operations require connected hardware
    print("\nNote: Variable read/write operations require actual CAN hardware.")
    print("To test with real hardware:")
    print("  success, value = monitor.read_variable(0)  # Read variable 0")
    print("  monitor.write_variable(0, 1234)            # Write value 1234 to variable 0")

    return True


def test_firmware_programming(monitor):
    """Test firmware programming (requires HEX file and hardware)"""
    print("\nTesting firmware programming...")

    # This is just a demonstration - actual programming requires:
    # 1. A valid HEX file
    # 2. Connected target device in bootloader mode
    # 3. Proper CAN ID configuration

    print("Firmware programming requires:")
    print("  1. Valid HEX file (e.g., 'firmware.hex')")
    print("  2. Target device in bootloader mode")
    print("  3. Correct CAN ID base configuration")
    print()
    print("Example usage:")
    print("  success = monitor.program_firmware('firmware.hex', can_id_base=0x300)")

    return True


def test_raw_can_operations(monitor):
    """Test raw CAN message operations"""
    print("\nTesting raw CAN operations...")

    try:
        # Create a test message
        test_msg = CANMessage(
            id=0x100,
            data=[0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88],
            msgtype=MessageType.MSGTYPE_STANDARD
        )

        print(f"Created test message: ID=0x{test_msg.id:03X}, Data={test_msg.data}")

        # Send message (will fail without hardware, but shows API usage)
        result = monitor.can_comm.send_message(test_msg)
        if result == CANResult.ERR_OK:
            print("[OK] Message sent successfully")
        else:
            print(f"Message send result: {result} (expected with no hardware)")

        # Try to receive message
        result, received_msg, timestamp = monitor.can_comm.receive_message(0.1)
        if result == CANResult.ERR_OK and received_msg:
            print(f"[OK] Received message: ID=0x{received_msg.id:03X}, Data={received_msg.data}")
        else:
            print(f"No message received: {result} (expected with no hardware)")

    except Exception as e:
        print(f"[ERROR] Error in raw CAN operations: {e}")

    return True


def interactive_mode(monitor):
    """Interactive mode for manual testing"""
    print("\n" + "=" * 40)
    print("Interactive Mode")
    print("=" * 40)

    commands = {
        'help': 'Show this help',
        'select': 'Select board type (PCU, TCU, BMS, etc.)',
        'list': 'List available variables',
        'read': 'Read variable (requires hardware)',
        'write': 'Write variable (requires hardware)',
        'program': 'Program firmware (requires hardware)',
        'status': 'Show connection status',
        'quit': 'Exit interactive mode'
    }

    while True:
        try:
            cmd = input("\nCommand (help for options): ").strip().lower()

            if cmd == 'help':
                print("\nAvailable commands:")
                for cmd_name, description in commands.items():
                    print("10")

            elif cmd == 'select':
                board_type = input("Board type (PCU, TCU, BMS, SCU, FCU): ").strip().upper()
                if monitor.select_board(board_type):
                    print(f"[OK] Selected {board_type} board")
                else:
                    print(f"[ERROR] Failed to select {board_type} board")

            elif cmd == 'list':
                if monitor.current_board:
                    variables = monitor.list_variables()
                    print(f"\nAvailable variables ({len(variables)} total):")
                    for i, (idx, name) in enumerate(variables):
                        print("3d")
                else:
                    print("[ERROR] No board selected")

            elif cmd == 'read':
                if monitor.current_board:
                    try:
                        var_idx = int(input("Variable index: "))
                        success, value = monitor.read_variable(var_idx)
                        if success:
                            print(f"[OK] Variable {var_idx}: 0x{value:04X} ({value})")
                        else:
                            print("[ERROR] Failed to read variable")
                    except ValueError:
                        print("[ERROR] Invalid variable index")
                else:
                    print("[ERROR] No board selected")

            elif cmd == 'write':
                if monitor.current_board:
                    try:
                        var_idx = int(input("Variable index: "))
                        value = int(input("Value (decimal): "))
                        if monitor.write_variable(var_idx, value):
                            print(f"[OK] Wrote {value} to variable {var_idx}")
                        else:
                            print("[ERROR] Failed to write variable")
                    except ValueError:
                        print("[ERROR] Invalid input")
                else:
                    print("[ERROR] No board selected")

            elif cmd == 'program':
                hex_file = input("HEX file path: ").strip()
                try:
                    can_id_base = int(input("CAN ID base (hex, e.g. 300): "), 16)
                    if monitor.program_firmware(hex_file, can_id_base):
                        print("[OK] Firmware programming completed")
                    else:
                        print("[ERROR] Firmware programming failed")
                except ValueError:
                    print("[ERROR] Invalid CAN ID base")

            elif cmd == 'status':
                if monitor.can_comm.is_connected:
                    print("[OK] Connected to CAN bus")
                    if monitor.current_board:
                        info = monitor.get_board_info()
                        print(f"  Current board: {info['board_type']}")
                        print(f"  Variables: {info['variables_count']}")
                    else:
                        print("  No board selected")
                else:
                    print("[ERROR] Not connected to CAN bus")

            elif cmd == 'quit':
                break

            else:
                print("[ERROR] Unknown command. Type 'help' for options.")

        except KeyboardInterrupt:
            print("\nExiting interactive mode...")
            break
        except Exception as e:
            print(f"[ERROR] Error: {e}")


def main():
    """Main function"""
    print_banner()

    # Show available interfaces
    show_available_interfaces()

    # Configuration
    CAN_CHANNEL = 'PCAN_USBBUS1'  # Change this for your CAN interface
    CAN_BAUDRATE = BaudRate.BAUD_250K

    print("Configuration:")
    print(f"  CAN Channel: {CAN_CHANNEL}")
    print(f"  Baud Rate: {CAN_BAUDRATE.value} bps")
    print()

    # Initialize monitor
    monitor = RetainVarMonitor(CAN_CHANNEL, CAN_BAUDRATE)

    try:
        # Run tests
        if not test_connection(monitor):
            print("Cannot continue without CAN connection.")
            return 1

        test_board_selection(monitor)
        test_variable_operations(monitor)
        test_firmware_programming(monitor)
        test_raw_can_operations(monitor)

        # Interactive mode
        interactive = input("\nEnter interactive mode? (y/n): ").strip().lower()
        if interactive == 'y':
            interactive_mode(monitor)

        # Cleanup
        print("\nCleaning up...")
        monitor.disconnect()
        print("[OK] Disconnected from CAN bus")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        monitor.disconnect()
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        monitor.disconnect()
        return 1

    print("\nDemo completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
