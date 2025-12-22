"""
CAN Communication Library for RetainVar Monitor
Python implementation converted from C++ PCANLight code

This library provides CAN communication functionality for connecting to and
programming various electronic control units (ECUs) in marine propulsion systems.
"""

import time
import struct
import logging
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum

try:
    import can
except ImportError:
    print("python-can library not found. Install with: pip install python-can")
    raise

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HardwareType(Enum):
    """Hardware types corresponding to different PCAN adapters"""
    ISA_1CH = 0
    ISA_2CH = 1
    PCI_1CH = 2
    PCI_2CH = 3
    PCC_1CH = 4
    PCC_2CH = 5
    USB_1CH = 6
    USB_2CH = 7
    DNP = 8  # DONGLE PRO
    DNG = 9  # DONGLE


class BaudRate(Enum):
    """CAN baud rates"""
    BAUD_1M = 1000000
    BAUD_500K = 500000
    BAUD_250K = 250000
    BAUD_125K = 125000
    BAUD_100K = 100000
    BAUD_50K = 50000
    BAUD_20K = 20000
    BAUD_10K = 10000
    BAUD_5K = 5000


class CANResult(Enum):
    """CAN operation results"""
    ERR_OK = 0x0000
    ERR_XMTFULL = 0x0001
    ERR_OVERRUN = 0x0002
    ERR_BUSLIGHT = 0x0004
    ERR_BUSHEAVY = 0x0008
    ERR_BUSOFF = 0x0010
    ERR_QRCVEMPTY = 0x0020
    ERR_QOVERRUN = 0x0040
    ERR_QXMTFULL = 0x0080
    ERR_REGTEST = 0x0100
    ERR_NOVXD = 0x0200
    ERR_ILLHW = 0x1400
    ERR_RESOURCE = 0x2000
    ERR_PARMTYP = 0x4000
    ERR_PARMVAL = 0x8000
    ERR_NO_DLL = 0xFFFFFFFF


class MessageType(Enum):
    """CAN message types"""
    MSGTYPE_STANDARD = 0x00
    MSGTYPE_RTR = 0x01
    MSGTYPE_EXTENDED = 0x02
    MSGTYPE_STATUS = 0x80


@dataclass
class CANMessage:
    """CAN message structure"""
    id: int
    data: List[int]
    msgtype: MessageType = MessageType.MSGTYPE_STANDARD
    length: int = 8

    def __post_init__(self):
        if len(self.data) > 8:
            raise ValueError("CAN message data cannot exceed 8 bytes")
        self.length = len(self.data)


@dataclass
class CANTimestamp:
    """CAN timestamp structure"""
    millis: int = 0
    millis_overflow: int = 0
    micros: int = 0


class CANError(Exception):
    """Custom exception for CAN communication errors"""
    pass


class CANCommunication:
    """
    Main CAN communication class
    Provides interface for CAN bus communication using python-can library
    """

    @staticmethod
    def list_available_interfaces() -> List[str]:
        """
        List available CAN interfaces

        Returns:
            List of available interface names
        """
        interfaces = []

        # Try PCAN interfaces
        try:
            import can.interfaces.pcan
            pcan_channels = ['PCAN_USBBUS1', 'PCAN_USBBUS2', 'PCAN_USBBUS3', 'PCAN_USBBUS4',
                           'PCAN_ISABUS1', 'PCAN_ISABUS2', 'PCAN_PCIBUS1', 'PCAN_PCIBUS2']
            interfaces.extend(pcan_channels)
        except ImportError:
            pass

        # Try SocketCAN (Linux)
        try:
            import can.interfaces.socketcan
            socketcan_channels = ['can0', 'can1', 'can2', 'can3']
            interfaces.extend(socketcan_channels)
        except ImportError:
            pass

        # Try Vector interfaces
        try:
            import can.interfaces.vector
            vector_channels = ['0', '1', '2', '3']
            interfaces.extend(vector_channels)
        except ImportError:
            pass

        return interfaces

    def __init__(self, channel: str = 'PCAN_USBBUS1', baudrate: BaudRate = BaudRate.BAUD_250K):
        """
        Initialize CAN communication

        Args:
            channel: CAN interface channel (e.g., 'PCAN_USBBUS1', 'can0')
            baudrate: CAN baud rate
        """
        self.channel = channel
        self.baudrate = baudrate.value
        self.bus = None
        self.is_connected = False
        self.message_filter = None
        self.last_messages = []

    def connect(self) -> CANResult:
        """
        Establish CAN bus connection

        Returns:
            CANResult: Connection status
        """
        try:
            # Determine interface type
            if self.channel.startswith('PCAN'):
                interface = 'pcan'
            elif self.channel.startswith('can'):
                interface = 'socketcan'
            else:
                # Try to auto-detect interface
                interface = 'pcan'  # Default to pcan for compatibility

            # Configure CAN interface with updated API
            self.bus = can.interface.Bus(
                channel=self.channel,
                interface=interface,  # Use 'interface' instead of deprecated 'bustype'
                bitrate=self.baudrate
            )
            self.is_connected = True
            logger.info(f"Connected to CAN bus: {self.channel} at {self.baudrate} bps")
            return CANResult.ERR_OK
        except Exception as e:
            logger.error(f"Failed to connect to CAN bus: {e}")
            logger.error("Make sure your CAN interface is properly installed and the channel name is correct.")
            logger.error("For PCAN: Try 'PCAN_USBBUS1', 'PCAN_USBBUS2', etc.")
            logger.error("For SocketCAN: Try 'can0', 'can1', etc.")
            self.is_connected = False
            return CANResult.ERR_ILLHW

    def disconnect(self) -> CANResult:
        """
        Close CAN bus connection

        Returns:
            CANResult: Disconnection status
        """
        try:
            if self.bus:
                self.bus.shutdown()
                self.bus = None
            self.is_connected = False
            logger.info("Disconnected from CAN bus")
            return CANResult.ERR_OK
        except Exception as e:
            logger.error(f"Error disconnecting from CAN bus: {e}")
            return CANResult.ERR_RESOURCE

    def send_message(self, message: CANMessage) -> CANResult:
        """
        Send a CAN message

        Args:
            message: CAN message to send

        Returns:
            CANResult: Send status
        """
        if not self.is_connected or not self.bus:
            return CANResult.ERR_ILLHW

        try:
            # Create python-can message
            can_msg = can.Message(
                arbitration_id=message.id,
                data=message.data,
                is_extended_id=(message.msgtype == MessageType.MSGTYPE_EXTENDED),
                is_remote_frame=(message.msgtype == MessageType.MSGTYPE_RTR)
            )

            # Send message
            self.bus.send(can_msg)
            logger.debug(f"Sent CAN message: ID=0x{message.id:03X}, Data={message.data}")
            return CANResult.ERR_OK

        except Exception as e:
            logger.error(f"Error sending CAN message: {e}")
            return CANResult.ERR_XMTFULL

    def receive_message(self, timeout: float = 0.1) -> Tuple[CANResult, Optional[CANMessage], Optional[CANTimestamp]]:
        """
        Receive a CAN message

        Args:
            timeout: Receive timeout in seconds

        Returns:
            Tuple of (result, message, timestamp)
        """
        if not self.is_connected or not self.bus:
            return CANResult.ERR_ILLHW, None, None

        try:
            # Receive message
            can_msg = self.bus.recv(timeout)

            if can_msg is None:
                return CANResult.ERR_QRCVEMPTY, None, None

            # Debug logging for received messages (only errors and warnings)
            # logger.debug(f"CAN message received: ID=0x{can_msg.arbitration_id:03X}, Data={[f'{b:02X}' for b in can_msg.data]}")

            # Convert to our message format
            msgtype = MessageType.MSGTYPE_STANDARD
            if can_msg.is_extended_id:
                msgtype = MessageType.MSGTYPE_EXTENDED
            elif can_msg.is_remote_frame:
                msgtype = MessageType.MSGTYPE_RTR

            message = CANMessage(
                id=can_msg.arbitration_id,
                data=list(can_msg.data),
                msgtype=msgtype
            )

            timestamp = CANTimestamp(
                millis=int(can_msg.timestamp * 1000),
                micros=int((can_msg.timestamp * 1000000) % 1000)
            )

            logger.debug(f"Received CAN message: ID=0x{message.id:03X}, Data={message.data}")
            return CANResult.ERR_OK, message, timestamp

        except Exception as e:
            logger.error(f"Error receiving CAN message: {e}")
            return CANResult.ERR_OVERRUN, None, None

    def set_message_filter(self, from_id: int, to_id: int, msg_type: MessageType) -> CANResult:
        """
        Set message filter for incoming messages

        Args:
            from_id: Start of ID range
            to_id: End of ID range
            msg_type: Message type to filter

        Returns:
            CANResult: Filter setting status
        """
        # Note: python-can filtering is more limited than PCANLight
        # This is a simplified implementation
        self.message_filter = {
            'from_id': from_id,
            'to_id': to_id,
            'msg_type': msg_type
        }
        logger.info(f"Set message filter: 0x{from_id:03X} - 0x{to_id:03X}, Type: {msg_type}")
        return CANResult.ERR_OK

    def get_status(self) -> CANResult:
        """
        Get CAN bus status

        Returns:
            CANResult: Bus status
        """
        if not self.is_connected:
            return CANResult.ERR_ILLHW

        # In python-can, we can't directly get bus status like PCANLight
        # This is a simplified status check
        return CANResult.ERR_OK


class BootloaderProtocol:
    """
    Bootloader protocol implementation for firmware programming
    """

    # Bootloader command IDs
    CMD_RESET = 0x320
    CMD_START_BOOTLOADER = 0x321
    CMD_LOADING = 0x322
    CMD_ADDRESS = 0x323
    CMD_DATA = 0x324
    CMD_VERIFY = 0x325

    # BSI Commands
    BSI_CMD_RUN = 0x01
    BSI_CMD_EEPROM = 0x02
    BSI_CMD_HEART = 0x03
    BSI_CMD_SLAVE = 0x04

    BSI_RUN_RESET = 0x01
    BSI_RUN_WAIT = 0x02
    BSI_RUN_GO = 0x03
    BSI_RUN_APC_ON = 0x04
    BSI_RUN_APC_OFF = 0x05
    BSI_RUN_CHG_ON = 0x06
    BSI_RUN_CHG_OFF = 0x07

    BSI_EEPROM_WR = 0x01
    BSI_EEPROM_RD = 0x02

    def __init__(self, can_comm: CANCommunication):
        """
        Initialize bootloader protocol

        Args:
            can_comm: CAN communication instance
        """
        self.can = can_comm
        self.upload_step = 0
        self.request_step = 0
        self.pic_address = 0
        self.data_bytes = None
        self.data_ptr = None

    def send_command(self, command_id: int) -> CANResult:
        """
        Send a bootloader command

        Args:
            command_id: Command CAN ID

        Returns:
            CANResult: Send status
        """
        message = CANMessage(
            id=command_id,
            data=[0x00] * 8,
            msgtype=MessageType.MSGTYPE_STANDARD
        )

        result = self.can.send_message(message)
        if result == CANResult.ERR_OK:
            self.upload_step += 1
        else:
            logger.error("CAN communication error during command send")
            self.upload_step = 0

        return result

    def send_address(self, address_id: int, address: int) -> CANResult:
        """
        Send an address for programming

        Args:
            address_id: Address CAN ID
            address: Memory address to program

        Returns:
            CANResult: Send status
        """
        message = CANMessage(
            id=address_id,
            data=[
                address & 0xFF,
                (address >> 8) & 0xFF,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00
            ],
            msgtype=MessageType.MSGTYPE_STANDARD
        )

        result = self.can.send_message(message)
        if result == CANResult.ERR_OK:
            self.upload_step += 1
        else:
            logger.error("CAN communication error during address send")
            self.upload_step = 0

        return result

    def send_data(self, data_id: int) -> CANResult:
        """
        Send data bytes for programming

        Args:
            data_id: Data CAN ID

        Returns:
            CANResult: Send status
        """
        if not self.data_ptr or not self.data_bytes:
            return CANResult.ERR_PARMVAL

        message = CANMessage(
            id=data_id,
            data=[],
            msgtype=MessageType.MSGTYPE_STANDARD
        )

        # Fill message with 8 bytes of data (4 words)
        for i in range(8):
            if self.data_ptr < len(self.data_bytes):
                # Pack 16-bit words into bytes (little-endian)
                word = self.data_bytes[self.data_ptr]
                if i % 2 == 0:
                    message.data.append(word & 0xFF)
                else:
                    message.data.append((word >> 8) & 0xFF)
                    self.data_ptr += 1
            else:
                message.data.append(0xFF)

        result = self.can.send_message(message)
        if result == CANResult.ERR_OK:
            # Check if we've sent 64 bytes (8 messages * 8 bytes)
            addr_offset = (self.data_ptr * 2) - (len(self.data_bytes) * 2 if hasattr(self, 'start_addr') else 0)
            if addr_offset % 64 == 0:
                self.upload_step -= 1
                self.pic_address += 64
        else:
            logger.error("CAN communication error during data send")
            self.data_ptr -= 8  # Rewind on error

        return result

    def load_hex_file(self, filename: str) -> bool:
        """
        Load and parse HEX file for programming

        Args:
            filename: Path to HEX file

        Returns:
            bool: Success status
        """
        try:
            self.data_bytes = []
            max_address = 0

            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith(':'):
                        continue

                    # Parse Intel HEX format
                    byte_count = int(line[1:3], 16)
                    address = int(line[3:7], 16)
                    record_type = int(line[7:9], 16)

                    if record_type == 0:  # Data record
                        data_start = 9
                        for i in range(byte_count // 2):  # 2 bytes per word
                            word = int(line[data_start:data_start+4], 16)
                            self.data_bytes.append(word)
                            data_start += 4
                            max_address = max(max_address, address + i * 2)
                    elif record_type == 1:  # End of file
                        break

            self.data_ptr = 0
            logger.info(f"Loaded HEX file: {len(self.data_bytes)} words, max address: 0x{max_address:04X}")
            return True

        except Exception as e:
            logger.error(f"Error loading HEX file: {e}")
            return False

    def program_device(self, device_id: int, hex_file: str) -> bool:
        """
        Program a device using the bootloader protocol

        Args:
            device_id: Device CAN ID base
            hex_file: Path to HEX file

        Returns:
            bool: Programming success
        """
        if not self.load_hex_file(hex_file):
            return False

        # Reset device
        logger.info("Resetting device...")
        if self.send_command(device_id + 0) != CANResult.ERR_OK:
            return False

        # Wait for bootloader start
        time.sleep(0.1)

        # Send loading command
        logger.info("Starting firmware upload...")
        if self.send_command(device_id + 2) != CANResult.ERR_OK:
            return False

        # Send data in chunks
        self.pic_address = 0
        self.upload_step = 4

        while self.data_ptr < len(self.data_bytes):
            # Send address
            if self.send_address(device_id + 3, self.pic_address) != CANResult.ERR_OK:
                return False

            # Send 8 data messages (64 bytes)
            for i in range(8):
                if self.send_data(device_id + 4) != CANResult.ERR_OK:
                    return False

        # Send verify command
        logger.info("Verifying firmware...")
        if self.send_command(device_id + 5) != CANResult.ERR_OK:
            return False

        logger.info("Firmware programming completed successfully")
        return True


class BoardData:
    """
    Board-specific data structures and configurations
    """

    TABLE_ADDR_MAX = 51

    # Board types
    BOARD_TYPES = {
        'PCU': 0,   # Power Control Unit
        'TCU': 1,   # Transmission Control Unit
        'WLU': 2,   # Water Level Unit
        'OBD_DC_DC': 3,  # OBD DC-DC Converter
        'CCU': 4,   # Central Control Unit
        'GATE': 5,  # Gateway
        'PDU': 6,   # Power Distribution Unit
        'ZCU': 7,   # Zone Control Unit
        'VCU': 8,   # Vehicle Control Unit
        'SCU': 9,   # Safety Control Unit
        'FCU': 10,  # Fuel Cell Unit
        'BMS': 11   # Battery Management System
    }

    # Default CAN ID bases for each board type
    BOARD_CAN_ID_BASES = {
        'PCU': 0x300,   # Power Control Unit
        'TCU': 0x400,   # Transmission Control Unit
        'WLU': 0x500,   # Water Level Unit
        'OBD_DC_DC': 0x600,  # OBD DC-DC Converter
        'CCU': 0x380,   # Central Control Unit
        'GATE': 0x480,  # Gateway
        'PDU': 0x580,   # Power Distribution Unit
        'ZCU': 0x680,   # Zone Control Unit
        'VCU': 0x700,   # Vehicle Control Unit (as specified)
        'SCU': 0x780,   # Safety Control Unit
        'FCU': 0x800,   # Fuel Cell Unit
        'BMS': 0x880    # Battery Management System
    }

    def __init__(self, board_type: str):
        """
        Initialize board data

        Args:
            board_type: Type of board (PCU, TCU, etc.)
        """
        self.board_type = board_type
        self.table_addr = [0] * self.TABLE_ADDR_MAX
        self.variable_names = []
        self.can_id_base = 0x300  # Default CAN ID base

        # Initialize board-specific data
        if board_type == 'PCU':
            self._init_pcu_data()
        elif board_type == 'TCU':
            self._init_tcu_data()
        elif board_type == 'BMS':
            self._init_bms_data()
        elif board_type == 'SCU':
            self._init_scu_data()
        elif board_type == 'FCU':
            self._init_fcu_data()
        elif board_type == 'WLU':
            self._init_wlu_data()
        elif board_type == 'OBD_DC_DC':
            self._init_obd_dcdc_data()
        elif board_type == 'CCU':
            self._init_ccu_data()
        elif board_type == 'GATE':
            self._init_gate_data()
        elif board_type == 'PDU':
            self._init_pdu_data()
        elif board_type == 'ZCU':
            self._init_zcu_data()
        elif board_type == 'VCU':
            self._init_vcu_data()

    def _init_pcu_data(self):
        """Initialize PCU (Power Control Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 60, 62,
            64, 66, 68, 70, 72, 74, 76, 77, 78, 79,
            80, 81, 82, 83, 84, 85, 87, 91, 95, 99, 103
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Setup", "Option", "Verbose",
            "Debug", "Param", "Top speed FW", "Top speed RV", "Min speed FW",
            "Min speed RV", "Dock speed FW", "Dock speed RV", "Max torque FW", "Max torque RV",
            "Mtn max torque", "Eco/Sport ratio", "Filter RPM step", "Filter rpm step", "Filter TRQ step",
            "Filter trq step", "Reverse dir.", "Forward dir.", "Motor low temp", "Motor cool LPM",
            "F/R speed max", "Ramp FW acc.", "Ramp RV acc.", "Ramp FW dec.", "Ramp RV dec.", "Batt low temp"
        ]

    def _init_tcu_data(self):
        """Initialize TCU (Transmission Control Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 60, 62,
            64, 66, 68, 70, 71, 73, 74, 76, 78, 80,
            82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "Ana1 value min", "Ana1 value max", "Ana2 value min",
            "Ana2 value max", "Ana3 value min", "Ana3 value max", "Brake trigger", "Openwire limit",
            "POT3 volt. gap", "POT3 R value", "POT3 N value", "POT3 D value", "POT3 P value",
            "LOG dot 1", "LOG dot 2", "LOG dot 3", "LOG dot 4", "LOG dot 5",
            "LOG dot 6", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_bms_data(self):
        """Initialize BMS (Battery Management System) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 60, 62,
            64, 66, 68, 70, 72, 74, 76, 77, 78, 79,
            80, 81, 82, 83, 84, 85, 87, 91, 95, 99, 103
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "Abs. max speed F", "Abs. max speed R", "Lim. max speed F",
            "Lim. max speed R", "Mtn. max speed F", "Mtn. max pseed R", "Max torque FW", "Max torque RV",
            "Mtn max torque", "Eco/Sport ratio", "Filter RPM step", "Filter rpm step", "Filter TRQ step",
            "Filter trq step", "Reverse dir.", "Forward dir.", "Speed mode val.", "Torq mode val.",
            "F/R speed max", "HVBATT addr", "DISCHG filter", "CHG filter", "VCU addr"
        ]

    def _init_scu_data(self):
        """Initialize SCU (Safety Control Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, 62, 63, 64, 65, 66, 67, 68, 69, 70,
            71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "Temp max", "Temp min", "Frame rate",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_fcu_data(self):
        """Initialize FCU (Fuel Cell Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, 62, 63, 64, 65, 66, 67, 68, 69, 70,
            71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "Flow max", "Flow min", "Frame rate",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_wlu_data(self):
        """Initialize WLU (Water Level Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, 62, 66, 70, 72, 74, 76, 77, 78, 79,
            80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "Temp max", "Current coeff", "Voltage min",
            "Current max", "Warning CANID", "Warning filter", "Warning value", "Warning ON time",
            "Warning OFF time", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_obd_dcdc_data(self):
        """Initialize OBD DC-DC data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 60, 62,
            66, 70, 74, 75, 76, 77, 78, 79, 80, 81,
            82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "DCDC voltage", "DCDC current", "HVBATT CAN id",
            "Discharge filter", "Charge filter", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_ccu_data(self):
        """Initialize CCU (Central Control Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, 62, 63, 64, 65, 66, 67, 68, 69, 70,
            71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "Flow setpoint", "ZCU curr", "Service pump %",
            "ZCU rated curr", "ZCU timeout", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_gate_data(self):
        """Initialize GATE (Gateway) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 62, 66,
            70, 74, 78, 82, 86, 90, 94, 98, 102, 106,
            110, 114, 118, 122, 123, 124, 125, 126, 127, 128, 129
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "CAN2 src (ADDR1)", "CAN1 dst (ADDR1)", "CAN1 src (ADDR1)",
            "CAN2 dst (ADDR1)", "CAN2 src (ADDR2)", "CAN1 dst (ADDR2)", "CAN1 src (ADDR2)", "CAN2 dst (ADDR2)",
            "CAN2 src (ADDR3)", "CAN1 dst (ADDR3)", "CAN1 src (ADDR3)", "CAN2 dst (ADDR3)", "CAN2 src (ADDR4)",
            "CAN1 dst (ADDR4)", "CAN1 src (ADDR4)", "CAN2 dst (ADDR4)", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_pdu_data(self):
        """Initialize PDU (Power Distribution Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, 62, 63, 64, 65, 66, 67, 68, 69, 70,
            71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Mode init", "Mode option", "Mode verbose",
            "Mode debug", "Mode param", "Motor2 enable", "Generator enable", "Precharge2 enable",
            "Leakage enable", "Batt delay", "Precharge1 delay", "Precharge2 delay", "Generator delay",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_zcu_data(self):
        """Initialize ZCU (Zone Control Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            62, 63, 65, 66, 67, 68, 70, 72, 74, 75,
            76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Setup", "Option", "Verbose",
            "Debug", "Param", "Nom peak current", "Max peak current", "Peak timeout",
            "Max cont current", "Cont timeout", "Max MOS temp", "Min MOS temp", "Pump type",
            "Throttle max", "Tick to Min%", "Tick to Max%", "Min PWM to flow", "Derating PWM %",
            "Derating temp diff", "Derating delay", "Min flow derating", "CAN timeout", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def _init_vcu_data(self):
        """Initialize VCU (Vehicle Control Unit) data structure"""
        self.table_addr = [
            0, 2, 6, 10, 14, 18, 19, 20, 21, 22,
            23, 27, 31, 35, 37, 39, 41, 43, 45, 47,
            51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
            61, 63, 65, 67, 69, 71, 73, 74, 75, 76,
            77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87
        ]

        self.variable_names = [
            "Flash CRC16", "Flash counter", "Supervisor key", "Admin key", "User key",
            "Manuf. rev.", "Model", "Type", "Software rev.", "Hardware rev.",
            "Date manuf.", "Date service", "Date current", "Log number", "Log index",
            "Event number", "Event index", "Failure number", "Failure index", "Com ID",
            "Com index", "Com type", "Setup", "Option", "Verbose",
            "Debug", "Param", "BAT low temp", "CHG high temp", "Free",
            "PDU config", "End of charge", "HV Bat max", "HV pack energy", "SHD threshold",
            "IGNoff timeout", "DCDC Setpoint", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
            "Reserved", "Reserved", "Reserved", "Reserved", "Reserved"
        ]

    def get_variable_address(self, index: int) -> int:
        """
        Get memory address for a variable index

        Args:
            index: Variable index

        Returns:
            int: Memory address
        """
        if 0 <= index < len(self.table_addr):
            return self.table_addr[index]
        return 0

    def get_default_can_id_base(self) -> int:
        """
        Get the default CAN ID base for this board type

        Returns:
            int: Default CAN ID base
        """
        return self.BOARD_CAN_ID_BASES.get(self.board_type, 0x300)

    def get_variable_name(self, index: int) -> str:
        """
        Get variable name for an index

        Args:
            index: Variable index

        Returns:
            str: Variable name
        """
        if 0 <= index < len(self.variable_names):
            return self.variable_names[index]
        return f"Unknown_Var_{index}"


class RetainVarMonitor:
    """
    Main class for RetainVar Monitor functionality
    """

    def __init__(self, can_channel: str = 'PCAN_USBBUS1', baudrate: BaudRate = BaudRate.BAUD_250K):
        """
        Initialize RetainVar Monitor

        Args:
            can_channel: CAN interface channel
            baudrate: CAN baud rate
        """
        self.can_comm = CANCommunication(can_channel, baudrate)
        self.bootloader = BootloaderProtocol(self.can_comm)
        self.current_board = None

    def connect(self) -> CANResult:
        """
        Connect to CAN bus

        Returns:
            CANResult: Connection status
        """
        return self.can_comm.connect()

    def disconnect(self) -> CANResult:
        """
        Disconnect from CAN bus

        Returns:
            CANResult: Disconnection status
        """
        return self.can_comm.disconnect()

    def select_board(self, board_type: str) -> bool:
        """
        Select and initialize board type

        Args:
            board_type: Board type (PCU, TCU, BMS, etc.)

        Returns:
            bool: Success status
        """
        try:
            self.current_board = BoardData(board_type)
            logger.info(f"Selected board type: {board_type}")
            return True
        except Exception as e:
            logger.error(f"Error selecting board {board_type}: {e}")
            return False

    def read_variable(self, var_index: int, can_id_base: int = None, board_index: int = 0) -> Tuple[bool, int]:
        """
        Read a retain variable from the board using the correct protocol

        Args:
            var_index: Variable index to read
            can_id_base: CAN ID base for the board (None = use board default)
            board_index: Board index (0 for first board)

        Returns:
            Tuple of (success, value)
        """
        if not self.current_board:
            logger.error("No board selected")
            return False, 0

        # Use board default if not explicitly provided
        if can_id_base is None:
            can_id_base = self.current_board.get_default_can_id_base()

        try:
            # Get the memory address for this variable
            address = self.current_board.get_variable_address(var_index)

            # Calculate CAN ID for read request: canid + 0x05 + (board_index << 4)
            read_can_id = can_id_base + 0x05 + (board_index << 4)

            # Calculate length (next address - current address, max 4)
            if var_index + 1 < len(self.current_board.table_addr):
                length = min(4, self.current_board.table_addr[var_index + 1] - address)
            else:
                length = 4  # Default for last variable

            # Send read request
            message = CANMessage(
                id=read_can_id,
                data=[
                    0x10 + length,  # Command byte for read request
                    address & 0xFF,
                    (address >> 8) & 0xFF,
                    (address >> 16) & 0xFF,
                    0x00, 0x00, 0x00, 0x00
                ]
            )

            result = self.can_comm.send_message(message)
            if result != CANResult.ERR_OK:
                logger.debug(f"Failed to send read request for variable {var_index}: {result}")
                return False, 0

            # Wait for response
            time.sleep(0.01)
            result, response, _ = self.can_comm.receive_message(0.1)

            if result == CANResult.ERR_OK and response:
                # Calculate response CAN ID: canid + 0x0A + (board_index << 4)
                expected_response_id = can_id_base + 0x0A + (board_index << 4)

                if response.id == expected_response_id:
                    # Extract value from response data (bytes 4-7, 32-bit little endian)
                    value = (response.data[4] |
                           (response.data[5] << 8) |
                           (response.data[6] << 16) |
                           (response.data[7] << 24))

                    # Handle different data types based on response byte 0
                    data_type = response.data[0] & 0x07
                    if data_type == 0x01:  # 8-bit signed
                        if value > 127:
                            value -= 256
                    elif data_type == 0x02:  # 16-bit signed
                        if value > 32767:
                            value -= 65536
                    elif data_type == 0x04:  # 32-bit signed
                        if value > 2147483647:
                            value -= 4294967296

                    logger.debug(f"Successfully read variable {var_index}: {value} (type: {data_type})")
                    return True, value
                else:
                    logger.debug(f"Received response on wrong CAN ID: {response.id}, expected: {expected_response_id}")
                    return False, 0
            else:
                logger.debug(f"No response received for variable {var_index} read request")
                return False, 0

        except Exception as e:
            logger.error(f"Error reading variable {var_index}: {e}")
            return False, 0

    def write_variable(self, var_index: int, value: int, can_id_base: int = None, board_index: int = 0) -> bool:
        """
        Write a retain variable to the board using the correct protocol

        Args:
            var_index: Variable index to write
            value: Value to write
            can_id_base: CAN ID base for the board (None = use board default)
            board_index: Board index (0 for first board)

        Returns:
            bool: Success status
        """
        if not self.current_board:
            logger.error("No board selected")
            return False

        # Use board default if not explicitly provided
        if can_id_base is None:
            can_id_base = self.current_board.get_default_can_id_base()

        try:
            # Get the memory address for this variable
            address = self.current_board.get_variable_address(var_index)

            # Calculate CAN ID for write request: canid + 0x05 + (board_index << 4)
            write_can_id = can_id_base + 0x05 + (board_index << 4)

            # Calculate length (next address - current address, max 4)
            if var_index + 1 < len(self.current_board.table_addr):
                length = min(4, self.current_board.table_addr[var_index + 1] - address)
            else:
                length = 4  # Default for last variable

            # Send write request
            message = CANMessage(
                id=write_can_id,
                data=[
                    0x20 + length,  # Command byte for write request
                    address & 0xFF,
                    (address >> 8) & 0xFF,
                    (address >> 16) & 0xFF,
                    value & 0xFF,
                    (value >> 8) & 0xFF,
                    (value >> 16) & 0xFF,
                    (value >> 24) & 0xFF
                ]
            )

            result = self.can_comm.send_message(message)
            if result != CANResult.ERR_OK:
                logger.debug(f"Failed to send write request for variable {var_index}: {result}")
                return False

            logger.debug(f"Successfully sent write request for variable {var_index} = {value}")
            return True
            # Send write command with variable address and value
            address = self.current_board.get_variable_address(var_index)

            message = CANMessage(
                id=can_id_base + 2,  # Write command ID
                data=[
                    address & 0xFF,
                    (address >> 8) & 0xFF,
                    value & 0xFF,
                    (value >> 8) & 0xFF,
                    0x00, 0x00, 0x00, 0x00
                ]
            )

            result = self.can_comm.send_message(message)
            return result == CANResult.ERR_OK

        except Exception as e:
            logger.error(f"Error writing variable {var_index}: {e}")
            return False

    def program_firmware(self, hex_file: str, can_id_base: int = 0x300) -> bool:
        """
        Program firmware to a board

        Args:
            hex_file: Path to HEX file
            can_id_base: CAN ID base for the board

        Returns:
            bool: Programming success
        """
        return self.bootloader.program_device(can_id_base, hex_file)

    def get_board_info(self) -> Dict[str, str]:
        """
        Get current board information

        Returns:
            Dict with board information
        """
        if not self.current_board:
            return {"error": "No board selected"}

        return {
            "board_type": self.current_board.board_type,
            "can_id_base": f"0x{self.current_board.can_id_base:03X}",
            "variables_count": len(self.current_board.variable_names),
            "variable_names": self.variable_names[:10]  # First 10 for display
        }

    def list_variables(self) -> List[Tuple[int, str]]:
        """
        List all available variables for current board

        Returns:
            List of (index, name) tuples
        """
        if not self.current_board:
            return []

        return [(i, name) for i, name in enumerate(self.current_board.variable_names)]


# Example usage and test functions
def example_usage():
    """
    Example usage of the CAN communication library
    """
    print("RetainVar Monitor Python Library Example")
    print("=" * 50)

    # Initialize monitor
    monitor = RetainVarMonitor(can_channel='PCAN_USBBUS1', baudrate=BaudRate.BAUD_250K)

    try:
        # Connect to CAN bus
        print("Connecting to CAN bus...")
        result = monitor.connect()
        if result != CANResult.ERR_OK:
            print(f"Failed to connect: {result}")
            return

        print("Connected successfully!")

        # Select board type
        print("Selecting PCU board...")
        if not monitor.select_board('PCU'):
            print("Failed to select board")
            return

        # List first few variables
        print("Available variables:")
        variables = monitor.list_variables()
        for i, (idx, name) in enumerate(variables[:10]):
            print("2d")

        print("... and more")

        # Example: Read a variable (this would require actual hardware)
        # print("Reading variable 0 (Flash CRC16)...")
        # success, value = monitor.read_variable(0)
        # if success:
        #     print(f"Value: 0x{value:04X}")
        # else:
        #     print("Failed to read variable")

        print("Example completed. Disconnecting...")
        monitor.disconnect()

    except Exception as e:
        print(f"Error: {e}")
        monitor.disconnect()


if __name__ == "__main__":
    example_usage()
