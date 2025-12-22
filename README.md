# RetainVar Monitor - Python CAN Communication Library

This is a Python conversion of the C++ RetainVar Monitor CAN communication code. The original C++ code used PEAK CAN hardware and Borland C++ Builder for GUI-based monitoring and programming of various electronic control units (ECUs) in marine propulsion systems.

## Features

- **CAN Bus Communication**: Full CAN bus communication using python-can library
- **Multiple Board Support**: Support for various ECU types (PCU, TCU, BMS, SCU, FCU, WLU, etc.)
- **Bootloader Protocol**: Firmware programming capability using the same protocol as the original C++ code
- **Variable Access**: Read/write retain variables from connected devices
- **Hardware Compatibility**: Works with PEAK PCAN USB adapters and other CAN interfaces

## Requirements

- Python 3.7+
- python-can library
- CAN hardware interface (PCAN USB, SocketCAN, etc.)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install CAN driver for your hardware:
   - For PEAK PCAN: Install PCAN drivers from [PEAK website](https://www.peak-system.com)
   - For SocketCAN (Linux): Built into Linux kernel
   - For other interfaces: Follow python-can documentation

## Files

- `can_communication.py`: Main library implementation
- `example_usage.py`: Comprehensive example and test script
- `test_can_interfaces.py`: CAN interface detection and testing script
- `requirements.txt`: Python dependencies
- `README.md`: This documentation

## Architecture

### Core Classes

1. **CANCommunication**: Low-level CAN bus communication
2. **BootloaderProtocol**: Firmware programming protocol implementation
3. **BoardData**: Board-specific configurations and variable mappings
4. **RetainVarMonitor**: High-level interface combining all functionality

### Supported Board Types

- **PCU**: Power Control Unit
- **TCU**: Transmission Control Unit
- **BMS**: Battery Management System
- **SCU**: Safety Control Unit
- **FCU**: Fuel Cell Unit
- **WLU**: Water Level Unit
- **OBD_DC_DC**: OBD DC-DC Converter
- **CCU**: Central Control Unit
- **GATE**: Gateway
- **PDU**: Power Distribution Unit
- **ZCU**: Zone Control Unit
- **VCU**: Vehicle Control Unit

## Usage

### Basic Example

```python
from can_communication import RetainVarMonitor, BaudRate

# Initialize monitor
monitor = RetainVarMonitor('PCAN_USBBUS1', BaudRate.BAUD_250K)

# Connect to CAN bus
monitor.connect()

# Select board type
monitor.select_board('PCU')

# List available variables
variables = monitor.list_variables()
for idx, name in variables[:10]:  # First 10 variables
    print(f"{idx:2d}: {name}")

# Read a variable (requires hardware)
success, value = monitor.read_variable(0)
if success:
    print(f"Variable 0 value: {value}")

# Write a variable (requires hardware)
monitor.write_variable(0, 1234)

# Program firmware (requires hardware and HEX file)
monitor.program_firmware('firmware.hex')

# Cleanup
monitor.disconnect()
```

### Running the Example

```bash
python example_usage.py
```

This will run through various tests and optionally enter interactive mode for manual testing.

## CAN Protocol Details

### Bootloader Commands

The bootloader protocol uses specific CAN IDs for communication:

- **0x320**: Reset command
- **0x321**: Start bootloader
- **0x322**: Loading command
- **0x323**: Address command
- **0x324**: Data command
- **0x325**: Verify command

### Variable Access

Variables are accessed using board-specific address mappings stored in lookup tables. Each board type has its own set of variable addresses and names.

### Message Format

All CAN messages use standard 11-bit identifiers with 8 data bytes. The protocol follows the same structure as the original C++ implementation.

## Hardware Setup

1. Connect your CAN interface (PCAN USB, etc.) to the computer
2. Connect the CAN bus to your target devices
3. Ensure proper CAN bus termination (120 ohm resistors)
4. Set correct baud rate (typically 250 kbps for marine applications)

## Differences from C++ Version

### Removed Components
- GUI components (Borland C++ Builder forms)
- Windows-specific threading model
- Direct hardware DLL calls

### Added Features
- Cross-platform compatibility
- Pythonic API design
- Better error handling
- Logging support
- Type hints

### API Changes
- Object-oriented design instead of global functions
- Enum-based constants instead of #defines
- Exception-based error handling
- Context managers for resource management

## Troubleshooting

### Finding Your CAN Interface

First, run the interface test script to find working channel names:

```bash
python test_can_interfaces.py
```

This script will test common CAN interface configurations and show you which ones work on your system.

### Connection Issues
- **PCAN Users**: Make sure PCAN drivers are installed from the PEAK website
- **Channel Names**:
  - PCAN: `PCAN_USBBUS1`, `PCAN_USBBUS2`, etc.
  - SocketCAN (Linux): `can0`, `can1`, etc.
  - Vector: `0`, `1`, etc.
- **Baud Rate**: Ensure it matches your CAN network (usually 250 kbps for marine systems)
- **Wiring**: Check CAN bus termination (120 ohm resistors at both ends)

### Hardware Not Responding
- Verify target device is powered and connected
- Check CAN ID configuration matches device
- Ensure device is in correct mode (normal vs bootloader)
- Monitor CAN bus traffic with tools like CANoe or BusMaster

### Permission Issues (Linux)
```bash
sudo ip link set can0 up type can bitrate 250000
```

### Python-Can Version Issues
If you see deprecation warnings about 'bustype', the library automatically handles this for you. The code is compatible with both old and new versions of python-can.

## Development

### Testing Without Hardware
The library can be imported and most functions tested without physical CAN hardware. Hardware-dependent functions will return appropriate error codes.

### Adding New Board Types
1. Add board type to `BoardData.BOARD_TYPES`
2. Implement `_init_<board>_data()` method
3. Define address mappings and variable names

### Extending the Protocol
- Modify `BootloaderProtocol` class for new commands
- Update `CANCommunication` for additional message types
- Add new enums for constants

## License

This Python conversion maintains compatibility with the original C++ codebase's functionality. Check the original C++ files for licensing information.

## Contributing

Contributions welcome! Please ensure:
- Code follows PEP 8 style guidelines
- Type hints are included for new functions
- Documentation is updated for API changes
- Backward compatibility is maintained
