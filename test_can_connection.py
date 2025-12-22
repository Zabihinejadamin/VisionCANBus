#!/usr/bin/env python3
"""
CAN Connection Test Script
Tests basic CAN connectivity and message sending/receiving
"""

import time
import sys
import os

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from can_communication import CANCommunication, CANResult, BaudRate, CANMessage, MessageType
except ImportError as e:
    print(f"Error importing can_communication: {e}")
    print("Make sure can_communication.py is in the same directory")
    sys.exit(1)


def test_can_connection():
    """Test CAN connection and basic functionality"""
    print("CAN Connection Test")
    print("=" * 50)

    # Test different interfaces and baud rates
    interfaces = ['PCAN_USBBUS1', 'PCAN_USBBUS2', 'can0', 'can1']
    baud_rates = [BaudRate.BAUD_250K, BaudRate.BAUD_500K, BaudRate.BAUD_125K]

    for interface in interfaces:
        print(f"\nTesting interface: {interface}")
        for baud_rate in baud_rates:
            print(f"  Baud rate: {baud_rate.value} bps")

            can_comm = CANCommunication(interface, baud_rate)
            result = can_comm.connect()

            if result == CANResult.ERR_OK:
                print(f"    ✓ Connected successfully to {interface} at {baud_rate.value} bps")

                # Test receiving messages for 5 seconds
                print("    Testing message reception (5 seconds)...")
                messages_received = 0
                start_time = time.time()

                while time.time() - start_time < 5.0:
                    result, message, timestamp = can_comm.receive_message(0.1)
                    if result == CANResult.ERR_OK and message:
                        messages_received += 1
                        print(f"      Received: ID=0x{message.id:03X}, Data={message.data}")
                        if messages_received >= 5:  # Don't flood output
                            break

                if messages_received > 0:
                    print(f"    ✓ Received {messages_received} messages")
                else:
                    print("    ⚠ No messages received - check if VCU is transmitting")

                # Test sending a message (if no messages were received)
                if messages_received == 0:
                    print("    Testing message transmission...")
                    test_msg = CANMessage(id=0x123, data=[1, 2, 3, 4])
                    result = can_comm.send_message(test_msg)
                    if result == CANResult.ERR_OK:
                        print("    ✓ Test message sent successfully")
                        # Try to receive it back (loopback)
                        time.sleep(0.1)
                        result, message, timestamp = can_comm.receive_message(0.1)
                        if result == CANResult.ERR_OK and message:
                            print("    ✓ Test message received (loopback working)")
                        else:
                            print("    ⚠ Test message not received (loopback may not be enabled)")
                    else:
                        print(f"    ✗ Failed to send test message: {result}")

                can_comm.disconnect()
                print(f"    ✓ Disconnected from {interface}")

                # If we found a working connection, stop testing
                if messages_received > 0:
                    print(f"\n✓ SUCCESS: Found working CAN connection on {interface} at {baud_rate.value} bps")
                    return True

            else:
                print(f"    ✗ Failed to connect: {result}")

    print("\n✗ No working CAN connections found")
    print("Troubleshooting tips:")
    print("1. Check if CAN interface is properly installed")
    print("2. Verify CAN interface name (PCAN_USBBUS1, can0, etc.)")
    print("3. Check baud rate matches VCU configuration")
    print("4. Ensure CAN bus is properly terminated")
    print("5. Verify VCU is powered on and transmitting")
    return False


def send_test_messages(interface='PCAN_USBBUS1', baud_rate=BaudRate.BAUD_250K):
    """Send test messages to verify transmission works"""
    print(f"\nSending test messages on {interface} at {baud_rate.value} bps")
    print("=" * 50)

    can_comm = CANCommunication(interface, baud_rate)
    result = can_comm.connect()

    if result != CANResult.ERR_OK:
        print(f"Failed to connect: {result}")
        return

    try:
        # Send messages continuously for testing
        print("Sending test messages every 500ms. Press Ctrl+C to stop...")
        i = 0
        while True:
            test_msg = CANMessage(id=0x100 + (i % 10), data=[i % 256, 0xAA, 0xBB, 0xCC, i % 256])
            result = can_comm.send_message(test_msg)
            if result == CANResult.ERR_OK:
                print(f"Sent: ID=0x{test_msg.id:03X}, Data={[f'{b:02X}' for b in test_msg.data]}")
            else:
                print(f"Failed to send message {i}: {result}")
            i += 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped sending messages")
    finally:
        can_comm.disconnect()
        print("Disconnected")


def receive_test_messages(interface='PCAN_USBBUS1', baud_rate=BaudRate.BAUD_250K, duration=30):
    """Receive test messages to verify reception works"""
    print(f"\nReceiving test messages on {interface} at {baud_rate.value} bps for {duration} seconds")
    print("=" * 60)

    can_comm = CANCommunication(interface, baud_rate)
    result = can_comm.connect()

    if result != CANResult.ERR_OK:
        print(f"Failed to connect: {result}")
        return

    try:
        print("Listening for CAN messages...")
        start_time = time.time()
        messages_received = 0

        while time.time() - start_time < duration:
            result, message, timestamp = can_comm.receive_message(0.1)
            if result == CANResult.ERR_OK and message:
                messages_received += 1
                print(f"Received: ID=0x{message.id:03X}, Data={[f'{b:02X}' for b in message.data]}, Time={timestamp}")
            elif result != CANResult.ERR_QRCVEMPTY:
                print(f"Receive error: {result}")

        print(f"\nReceived {messages_received} messages in {duration} seconds")

    finally:
        can_comm.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "send":
            # Send test messages mode
            interface = sys.argv[2] if len(sys.argv) > 2 else 'PCAN_USBBUS1'
            send_test_messages(interface)
        elif sys.argv[1] == "receive":
            # Receive test messages mode
            interface = sys.argv[2] if len(sys.argv) > 2 else 'PCAN_USBBUS1'
            duration = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            receive_test_messages(interface, duration=duration)
        else:
            print("Usage: python test_can_connection.py [send|receive] [interface] [duration]")
    else:
        # Connection test mode
        test_can_connection()
