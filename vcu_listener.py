# vcu_can_tool_FINAL_1806E5F4_16BIT_VALUE_PLUS_FULL_BATTERY.py
# FULL BATTERY SUPPORT ADDED: 402/404/405/406 + 422/424/425/426 + 442/444/445/446

import sys
import cantools
import can
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer, Qt
import threading
import time

# === CONFIG ===
DBC_FILE = 'DBC/vcu_updated.dbc'
BITRATE = 250000
# CAN1 Configuration
CHANNEL1 = 'PCAN_USBBUS1'
BUSTYPE1 = 'pcan'
# CAN2 Configuration
CHANNEL2 = 'PCAN_USBBUS2'
BUSTYPE2 = 'pcan'

# Alternative CAN2 channels to try if PCAN_USBBUS2 doesn't work
# CHANNEL2 = 'PCAN_USBBUS3'  # Try this if BUS2 doesn't work
# CHANNEL2 = 'PCAN_USBBUS4'  # Or this
# CHANNEL2 = 'PCAN_USBBUS5'  # Or this

def list_pcan_channels():
    """List available PCAN channels"""
    import can
    try:
        # Try to detect available PCAN channels
        channels = []
        for i in range(1, 10):  # Try BUS1 through BUS9
            try:
                channel_name = f'PCAN_USBBUS{i}'
                bus = can.interface.Bus(channel=channel_name, bustype='pcan', bitrate=250000)
                bus.shutdown()
                channels.append(channel_name)
            except:
                pass
        return channels
    except:
        return []

# === CAN IDs ===
ID_727 = 0x727
ID_587 = 0x587
ID_107 = 0x107
ID_607 = 0x607
ID_CMD_BMS = 0x4F0
ID_PDU_STATUS = 0x580
ID_HMI_STATUS = 0x740
ID_PCU_COOL = 0x722
ID_PCU_MOTOR = 0x720
ID_PCU_POWER = 0x724
ID_CCU_STATUS = 0x600
ID_ZCU_PUMP = 0x72E
ID_HV_CHARGER_STATUS = 0x18FF50E5
ID_HV_CHARGER_CMD = 0x1806E5F4
ID_DC12_COMM = 0x1800F5E5
ID_DC12_STAT = 0x1800E5F5
ID_TEMP_FRAME = 0x111
ID_VOLT_FRAME = 0x112
ID_CURRENT_FRAME = 0x113
ID_DRIVE_FRAME = 0x114
ID_SPDTQ_FRAME = 0x115
ID_TCU_ENABLE_FRAME = 0x0CFF0BD0
ID_TCU_PRND_FRAME = 0x18F005D0
ID_TCU_THROTTLE_FRAME = 0x0CF003D0
ID_TCU_TRIM_FRAME = 0x0CFF08D0
ID_GPS_SPEED_FRAME = 0x09F8020A

# ALL BATTERY FRAMES (now complete)
BAT1_FRAMES = [0x400, 0x401, 0x402, 0x403, 0x404, 0x405, 0x406]
BAT2_FRAMES = [0x420, 0x421, 0x422, 0x423, 0x424, 0x425, 0x426]
BAT3_FRAMES = [0x440, 0x441, 0x442, 0x443, 0x444, 0x445, 0x446]

# PCU FRAMES (Power Control Unit)
PCU_FRAMES = [0x720, 0x722, 0x724]

# Emulator uses all frames for Battery 1
BAT1_EMULATOR_IDS = [0x400, 0x401, 0x402, 0x403, 0x404, 0x405, 0x406]

EMULATOR_STATES = {k: False for k in [
    0x727,0x587,0x107,0x607,0x4F0,0x580,0x600,0x720,0x722,0x724,0x72E,
    ID_HV_CHARGER_STATUS, ID_HV_CHARGER_CMD, ID_DC12_COMM, ID_DC12_STAT,
    ID_TEMP_FRAME, ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME
]}

# Refresh intervals for different frame types (in seconds)
EMULATOR_INTERVALS = {
    0x600: 0.05,  # 50ms for CCU status
    0x720: 0.05,  # 50ms for motor status
    0x722: 0.2,   # 200ms for PCU cooling status
    # Battery frames and temperature frame use 150ms (0.15 seconds)
    0x400: 0.15, 0x401: 0.15, 0x402: 0.15, 0x403: 0.15, 0x404: 0.15, 0x405: 0.15, 0x406: 0.15,
    0x420: 0.15, 0x421: 0.15, 0x422: 0.15, 0x423: 0.15, 0x424: 0.15, 0x425: 0.15, 0x426: 0.15,
    0x440: 0.15, 0x441: 0.15, 0x442: 0.15, 0x443: 0.15, 0x444: 0.15, 0x445: 0.15, 0x446: 0.15,
    ID_TEMP_FRAME: 0.1,  # 100ms for temperature frame (0x111)
    ID_VOLT_FRAME: 0.5,  # 500ms for voltage frame (0x112)
    ID_CURRENT_FRAME: 0.5,  # 500ms for current frame (0x113)
    ID_DRIVE_FRAME: 0.5,  # 500ms for drive frame (0x114)
    ID_SPDTQ_FRAME: 0.5,  # 500ms for speed/torque frame (0x115)
    ID_TCU_ENABLE_FRAME: 0.5,  # 500ms for TCU enable frame
    ID_TCU_PRND_FRAME: 0.5,  # 500ms for TCU PRND frame
    ID_TCU_THROTTLE_FRAME: 0.5,  # 500ms for TCU throttle frame
    ID_TCU_TRIM_FRAME: 0.5,  # 500ms for TCU trim frame
    ID_GPS_SPEED_FRAME: 0.5,  # 500ms for GPS speed frame
}

# Default interval for other frames (100ms)
EMULATOR_INTERVAL_DEFAULT = 0.1

EMULATOR_BAT1_ENABLED = False
EMULATOR_PCU_ENABLED = False


def get_emulator_interval(can_id):
    """Get the appropriate refresh interval for a CAN ID"""
    return EMULATOR_INTERVALS.get(can_id, EMULATOR_INTERVAL_DEFAULT)


class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Tool – Full Battery + 1806E5F4 16-bit EOC")
        self.resize(3000, 1600)
        self.bus1 = None
        self.bus2 = None
        self.bus1_connected = False
        self.bus2_connected = False
        self.active_can = 1  # 1 or 2
        self.tables = {}
        self.battery_tabs = {}
        self.lock = threading.Lock()
        self.raw_log_lines = []
        self.error_count = 0
        self.first_fill = {}
        self.bat1_cycle_index = 0

        try:
            self.db = cantools.database.load_file(DBC_FILE)
            print(f"DBC loaded: {len(self.db.messages)} messages")
        except Exception as e:
            print("DBC load failed:", e)
            self.db = cantools.database.Database()

        all_ids = [ID_727,ID_587,ID_107,ID_607,ID_CMD_BMS,ID_PDU_STATUS,ID_HMI_STATUS,
                   ID_PCU_COOL,ID_PCU_MOTOR,ID_PCU_POWER,ID_CCU_STATUS,ID_ZCU_PUMP,
                   ID_HV_CHARGER_STATUS, ID_HV_CHARGER_CMD, ID_DC12_COMM, ID_DC12_STAT,
                   ID_TEMP_FRAME, ID_VOLT_FRAME, ID_CURRENT_FRAME, ID_DRIVE_FRAME, ID_SPDTQ_FRAME,
                   ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME]
        all_ids += BAT1_FRAMES + BAT2_FRAMES + BAT3_FRAMES

        self.signals = {id_: {} for id_ in set(all_ids)}
        self.current_hex = {id_: "00 00 00 00 00 00 00 00" for id_ in set(all_ids)}
        self.hex_labels = {}
        self.first_fill = {k: True for k in self.signals}
        self.first_fill.update({f"BT{i}": True for i in [1,2,3]})
        self.first_fill["HMI"] = True
        self.first_fill["TCU"] = True

        # Store user-modified table values separately from live CAN data
        self.modified_signals = {id_: {} for id_ in set(all_ids)}

        self.init_ui()
        self.gui_timer = QTimer()
        self.gui_timer.timeout.connect(self.update_gui)
        self.gui_timer.start(100)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(8)

        top = QHBoxLayout()

        # CAN1 controls
        can1_layout = QVBoxLayout()
        self.connect_btn1 = QPushButton("Connect CAN1")
        self.connect_btn1.setFixedHeight(36)
        self.connect_btn1.clicked.connect(self.toggle_can1)
        can1_layout.addWidget(self.connect_btn1)
        self.status_label1 = QLabel("CAN1: DISCONNECTED")
        self.status_label1.setStyleSheet("color:#d32f2f; font-weight:bold;")
        can1_layout.addWidget(self.status_label1)
        top.addLayout(can1_layout)

        # CAN2 controls
        can2_layout = QVBoxLayout()
        self.connect_btn2 = QPushButton("Connect CAN2")
        self.connect_btn2.setFixedHeight(36)
        self.connect_btn2.clicked.connect(self.toggle_can2)
        can2_layout.addWidget(self.connect_btn2)

        # Add test button for CAN2
        self.test_btn2 = QPushButton("Test CAN2")
        self.test_btn2.clicked.connect(self.test_can2)
        can2_layout.addWidget(self.test_btn2)
        self.status_label2 = QLabel("CAN2: DISCONNECTED")
        self.status_label2.setStyleSheet("color:#d32f2f; font-weight:bold;")
        can2_layout.addWidget(self.status_label2)
        top.addLayout(can2_layout)

        top.addStretch()
        layout.addLayout(top)

        self.setStyleSheet("""
            * { font-family: Segoe UI, Arial; font-size: 11px; }
            QLineEdit, QPushButton, QTabBar::tab { font-size: 11px; }
            QTableWidget { font-size: 11px; }
        """)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # === Existing Emulators (unchanged) ===
        self.create_emulator_tab(0x727, "0x727 – VCU→PCU", "VCU to PCU Command", "44 40 00 14 F8 11 64 00",
                                 [("Standby","00 00 00 00 00 00 00 00"), ("Drive","01 00 00 00 00 00 00 00"), ("Reset","03 00 00 00 00 00 00 00")])
        self.create_emulator_tab(0x587, "0x587 – PDU Cmd", "PDU Command", "01 01 00 00 01 00 07 04",
                                 [("All OFF","00 00 00 00 00 00 00 00"), ("Precharge","01 00 00 00 00 00 00 00"), ("Main+Pre","03 00 00 00 00 00 00 00")])
        self.create_emulator_tab(0x107, "0x107 – Pump", "Pump Command", "00 00 00 00 00 00 00 00",
                                 [("OFF","00 00 00 00 00 00 00 00"), ("50%","01 32 00 00 00 00 00 00"), ("100%","01 64 00 00 00 00 00 00")])
        self.create_emulator_tab(0x607, "0x607 – CCU/ZCU Cmd", "CCU/ZCU Command", "01 00 00 00 00 00 00 00")
        self.create_emulator_tab(0x4F0, "0x4F0 – VCU→BMS", "VCU to BMS", "00 01 00 01 00 00 00 00",
                                 [("Idle","00 00 00 00 00 00 00 00"), ("Precharge","02 00 00 00 00 00 00 00"), ("Close","01 00 00 00 00 00 00 00")])
        
        self.create_emulator_tab(
            can_id=ID_HV_CHARGER_CMD,
            tab_name="HVC CMD",
            title="VCU → Charger Command",
            default_payload="1D 88 00 96 01 00 00 00",
            presets=[
                ("Stop (No EOC)", "00 00 00 00 00 00 00 00"),
                ("60A + EOC", "1D 88 00 3C 01 00 00 00"),
                ("100A + EOC", "1D 88 00 64 01 00 00 00"),
                ("150A + EOC", "1D 88 00 96 01 00 00 00"),
                ("200A + EOC", "1D 88 00 C8 01 00 00 00"),
                ("150A No EOC", "00 00 00 96 00 00 00 00"),
            ]
        )

        self.create_emulator_tab(
            can_id=ID_DC12_COMM,
            tab_name="DC12 Comm",
            title="DC12 Charger Communication",
            default_payload="00 01 90 00 F4 01 00 00",
            presets=[
                ("Stop", "55 00 41 0E CC 00 DC 00"),
                ("Start 90V 20A", "55 01 5A 0E C8 01 DC 00"),
                ("Start 60V 15A", "55 01 3C 0E 96 01 DC 00"),
            ]
        )

        self.create_emulator_tab(0x580, "PDU Stat", "PDU Relays", "99 00 00 99 04 00 00 F3",
                                 [("All OFF","00 00 00 00 00 00 00 00"), ("Main+Pre","03 00 00 00 00 00 00 00"), ("All ON","FF FF FF FF FF FF FF FF")])
        self.create_emulator_tab(0x600, "CCU stat", "CCU Stat", "3A 39 50 54 8D 00 3C 00")
        self.create_pcu_tab_with_emulator("PCU stat", PCU_FRAMES)
        self.create_emulator_tab(0x72E, "ZCU stat", "ZCU Pump Stat", "28 00 00 00 00 3C 08 00",
                                 [("OFF","00 00 00 00 00 00 00 00"), ("50%","01 32 00 00 00 00 00 00"), ("100%","01 64 00 00 00 00 00 00")])

        self.create_emulator_tab(
            can_id=ID_HV_CHARGER_STATUS,
            tab_name="HVC Stat",
            title="HV Charger Feedback (FULLY DECODED)",
            default_payload="1B 01 00 80 00 00 43 00",
            presets=[
                ("No Comm", "00 00 00 00 00 00 00 00"),
                ("Ready", "00 00 00 00 00 28 00 00"),
                ("400V 150A", "90 0F DC 05 01 64 00 00"),
                ("550V 100A", "56 10 3E 08 01 5A 00 00"),
                ("Done", "90 0F 00 00 00 78 00 00"),
            ]
        )

        self.create_emulator_tab(
            can_id=ID_DC12_STAT,
            tab_name="DC12 Stat",
            title="DC12 Charger Status",
            default_payload="00 00 00 47 00 47 01 46",
            presets=[
                ("Ready State_C", "55 00 41 0E CC 01 DC 00"),
                ("Charging 15A 400V", "55 01 96 0F A0 01 DC 00"),
                ("Charging 20A 450V", "55 01 C8 11 2C 01 DC 00"),
            ]
        )

        self.create_tab(ID_HMI_STATUS, "0x740 – HMI", "HMI Stat", ["Signal","Value","Unit","TS"])
        self.create_hmi_tab()
        self.create_battery_tab_with_emulator("Battery 1", 1, BAT1_FRAMES)
        self.create_battery_tab("Battery 2", 2, BAT2_FRAMES)
        self.create_battery_tab("Battery 3", 3, BAT3_FRAMES)

        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        self.raw_log.setStyleSheet("font-family: Consolas; font-size: 10px;")
        # Add control buttons for modified values
        controls_layout = QHBoxLayout()
        self.clear_modified_btn = QPushButton("Clear Modified Values (PDU, PCU, CCU, ZCU, HVC, DC12 & TCU)")
        self.clear_modified_btn.clicked.connect(self.clear_modified_values)
        self.clear_modified_btn.setStyleSheet("background:#ff9800;color:white;font-weight:bold;")
        controls_layout.addWidget(self.clear_modified_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        layout.addWidget(QLabel("Raw CAN Log (last 8 frames):"))
        layout.addWidget(self.raw_log)

    # === NEW: Full manual decoding of battery frames (402,404,405,406) ===
    def decode_battery_frame(self, frame_id: int, data: bytes):
        if len(data) < 8:
            return {}
        b = data
        signals = {}

        if frame_id in (0x402, 0x422, 0x442):  # Alarms 1-8
            alarms = ["Alarm_1","Alarm_2","Alarm_3","Alarm_4","Alarm_5","Alarm_6","Alarm_7","Alarm_8"]
            for i, name in enumerate(alarms):
                signals[name] = {"d": f"{b[i]}", "v": b[i], "u": ""}

        elif frame_id in (0x404, 0x424, 0x444):
            # Byte 0
            signals["Isol_Board_Powered"] = {"d": "Yes" if b[0] & 0x01 else "No", "v": bool(b[0] & 0x01), "u": ""}
            # Byte 1
            signals["Open_Sw_Error"] = {"d": "Yes" if b[1] & 0x01 else "No", "v": bool(b[1] & 0x01), "u": ""}
            signals["No_Closing_Sw_Error"] = {"d": "Yes" if (b[1] & 0x02) else "No", "v": bool(b[1] & 0x02), "u": ""}
            # Byte 2-3: V_Cell_Avg
            v_avg = (b[2] << 8) | b[3]
            signals["V_Cell_Avg"] = {"d": f"{v_avg}", "v": v_avg, "u": "mV"}
            # Byte 4: Contactor states
            aux = b[4] & 0x0F
            main = (b[4] >> 4) & 0x0F
            signals["Contactor_4_Aux"] = {"d": "Closed" if aux & 0x01 else "Open", "v": bool(aux & 0x01), "u": ""}
            signals["Contactor_3_Aux"] = {"d": "Closed" if aux & 0x02 else "Open", "v": bool(aux & 0x02), "u": ""}
            signals["Contactor_2_Aux"] = {"d": "Closed" if aux & 0x04 else "Open", "v": bool(aux & 0x04), "u": ""}
            signals["Contactor_1_Aux"] = {"d": "Closed" if aux & 0x08 else "Open", "v": bool(aux & 0x08), "u": ""}
            signals["Contactor_4_State"] = {"d": "Closed" if main & 0x01 else "Open", "v": bool(main & 0x01), "u": ""}
            signals["Contactor_3_State_Precharge"] = {"d": "Closed" if main & 0x02 else "Open", "v": bool(main & 0x02), "u": ""}
            signals["Contactor_2_State_Neg"] = {"d": "Closed" if main & 0x04 else "Open", "v": bool(main & 0x04), "u": ""}
            signals["Contactor_1_State_Pos"] = {"d": "Closed" if main & 0x08 else "Open", "v": bool(main & 0x08), "u": ""}
            # Byte 5
            signals["Is_Balancing_Active"] = {"d": "Yes" if b[5] & 0x01 else "No", "v": bool(b[5] & 0x01), "u": ""}

        elif frame_id in (0x405, 0x425, 0x445):
            nb_cycles = (b[3] << 24) | (b[2] << 16) | (b[1] << 8) | b[0]
            ah_discharged = (b[7] << 24) | (b[6] << 16) | (b[5] << 8) | b[4]
            signals["Nb_Cycles"] = {"d": str(nb_cycles), "v": nb_cycles, "u": ""}
            signals["Ah_Discharged"] = {"d": f"{ah_discharged / 10.0:.1f}", "v": ah_discharged / 10.0, "u": "Ah"}
            signals["Remaining_Time_Before_Opening"] = {"d": str(b[7]), "v": b[7], "u": "s"}

        elif frame_id in (0x406, 0x426, 0x446):  # Alarms 9-16
            alarms = ["Alarm_9","Alarm_10","Alarm_11","Alarm_12","Alarm_13","Alarm_14","Alarm_15","Alarm_16"]
            for i, name in enumerate(alarms):
                signals[name] = {"d": f"{b[i]}", "v": b[i], "u": ""}

        return signals

    def decode_hv_charger_cmd(self, data):
        if len(data) < 8: return {}
        b = data
        end_of_charge_raw = (b[0] << 8) | b[1]
        current_setpoint = b[3] * 0.1
        state = "State_A (Request Charging)" if (b[4] & 0x01) else "State_C (Stop)"
        return {
            "End_of_Charge_Value": {"d": str(end_of_charge_raw), "u": ""},
            "Charger_Current_Setpoint": {"d": f"{current_setpoint:.1f}", "u": "A"},
            "Charger_State_Request": {"d": state, "u": ""},
        }

    def decode_hv_charger_status(self, data):
        if len(data) < 8: return {}
        b = data
        voltage = (b[0] * 256 + b[1]) / 10.0
        current = (b[2] * 256 + b[3]) / 10.0
        status_bit = bool(b[4] & 0x01)
        status = "State_A (Charging)" if status_bit else "State_C (Ready/Finished)"
        temp = b[5] - 40
        return {
            "HV_Charger_Voltage": {"d": f"{voltage:.1f}", "u": "V", "v": voltage},
            "HV_Charger_Current": {"d": f"{current:.1f}", "u": "A", "v": current},
            "HV_Charger_Status": {"d": status, "u": "", "v": status_bit},
            "HV_Charger_Temp": {"d": f"{temp:+.0f}", "u": "°C", "v": temp},
        }

    def decode_dc12_comm(self, data):
        if len(data) < 8: return {}
        b = data
        start_stop = "Start" if b[1] == 1 else "Stop"
        voltage_setpoint = b[2] * 0.1  # 1 bit per 0.1V (user wrote "0.1 A" but that must be a typo)
        max_current = b[4] * 0.1  # 1 bit per 0.1A
        active = "Active" if b[5] == 1 else "Not Active"
        return {
            "Start_Stop": {"d": start_stop, "u": ""},
            "Voltage_Setpoint": {"d": f"{voltage_setpoint:.1f}", "u": "V"},
            "Max_Current": {"d": f"{max_current:.1f}", "u": "A"},
            "Charger_Active": {"d": active, "u": ""},
        }

    def decode_dc12_stat(self, data):
        if len(data) < 8: return {}
        b = data
        status_bit = bool(b[1] == 1)
        status = "State_A" if status_bit else "State_C"
        current = b[3] * 0.1  # Charging current in A, 1 bit per 0.1A
        voltage = b[5] * 0.1  # DC bus voltage in V, 1 bit per 0.1V
        temperature = b[7] - 40  # Temperature in °C, offset by -40
        return {
            "Charger_Status": {"d": status, "u": "", "v": status_bit},
            "Charging_Current": {"d": f"{current:.1f}", "u": "A", "v": current},
            "DC_Bus_Voltage": {"d": f"{voltage:.1f}", "u": "V", "v": voltage},
            "Charger_Temperature": {"d": f"{temperature:+}", "u": "°C", "v": temperature},
        }

    def decode_ccu_stat(self, data):
        if len(data) < 8: return {}
        b = data

        # CCU_COOL_IN: 8-bit, scale 1, offset -40, unit Celcius
        cool_in = b[0] - 40

        # CCU_COOL_OUT: 8-bit, scale 1, offset -40, unit Celcius
        cool_out = b[1] - 40

        # CCU_GLYCOL_FLOW: 8-bit, scale 0.1, offset 0, unit L/min
        glycol_flow = b[2] * 0.1

        # CCU_GLYCOL_THROTTLE: 8-bit, scale 1, offset 0, unit %
        glycol_throttle = b[3]

        # CCU_12V_BAT: 8-bit, scale 1, offset 0, unit %
        bat_12v = b[4]

        # CCU_ZCU_CURRENT: 8-bit, scale 0.2, offset 0, unit A
        zcu_current = b[5] * 0.2

        # CCU_ZCU_TEMP: 8-bit, scale 1, offset -40, unit Celcius
        zcu_temp = b[6] - 40

        # CCU_ERROR_CODES: 8-bit, scale 1, offset 0, unit ""
        error_codes = b[7]

        return {
            "CCU_COOL_IN": {"d": f"{cool_in:+.0f}", "u": "Celcius", "v": cool_in},
            "CCU_COOL_OUT": {"d": f"{cool_out:+.0f}", "u": "Celcius", "v": cool_out},
            "CCU_GLYCOL_FLOW": {"d": f"{glycol_flow:.1f}", "u": "L/min", "v": glycol_flow},
            "CCU_GLYCOL_THROTTLE": {"d": f"{glycol_throttle:.0f}", "u": "%", "v": glycol_throttle},
            "CCU_12V_BAT": {"d": f"{bat_12v:.0f}", "u": "%", "v": bat_12v},
            "CCU_ZCU_CURRENT": {"d": f"{zcu_current:.1f}", "u": "A", "v": zcu_current},
            "CCU_ZCU_TEMP": {"d": f"{zcu_temp:+.0f}", "u": "Celcius", "v": zcu_temp},
            "CCU_ERROR_CODES": {"d": f"{error_codes:.0f}", "u": "", "v": error_codes},
        }

    def decode_zcu_stat(self, data):
        if len(data) < 8: return {}
        b = data

        # Current: 8-bit, scale 0.2, offset 0, unit A
        current = b[0] * 0.2

        # Temp_CPU: 8-bit, scale 1, offset 40, unit °C
        temp_cpu = b[1] - 40

        # Temp_Mos: 8-bit, scale 1, offset 40, unit °C
        temp_mos = b[2] - 40

        # Voltage: 8-bit, scale 0.1, offset 0, unit V
        voltage = b[3] * 0.1

        # Power: 16-bit little-endian, scale 0.1, offset 0, unit W
        power = ((b[5] << 8) | b[4]) * 0.1

        # Status: 8-bit, scale 1, offset 0, unit ""
        status = b[6]

        return {
            "Current": {"d": f"{current:.1f}", "u": "A", "v": current},
            "Temp_CPU": {"d": f"{temp_cpu:+.0f}", "u": "°C", "v": temp_cpu},
            "Temp_Mos": {"d": f"{temp_mos:+.0f}", "u": "°C", "v": temp_mos},
            "Voltage": {"d": f"{voltage:.1f}", "u": "V", "v": voltage},
            "Power": {"d": f"{power:.1f}", "u": "W", "v": power},
            "Status": {"d": f"{status:.0f}", "u": "", "v": status},
        }

    def decode_temperature_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # Each temperature is 1 bit per °C - 40 offset
        return {
            "SCU1_Fresh_Water_Outboard_Temp": {"d": f"{b[0] - 40:+.0f}", "u": "°C"},
            "SCU2_Fresh_Water_Battery_Temp": {"d": f"{b[1] - 40:+.0f}", "u": "°C"},
            "SCU3_Glycol_Water_Battery_Temp": {"d": f"{b[2] - 40:+.0f}", "u": "°C"},
            "Rotor_Outboard_Temp": {"d": f"{b[3] - 40:+.0f}", "u": "°C"},
            "Inverter_Outboard_Temp": {"d": f"{b[4] - 40:+.0f}", "u": "°C"},
            "Motor_Outboard_Temp": {"d": f"{b[5] - 40:+.0f}", "u": "°C"},
            "Charger_DCDC_Temp": {"d": f"{b[6] - 40:+.0f}", "u": "°C"},
            "Battery_Cell_Temp": {"d": f"{b[7] - 40:+.0f}", "u": "°C"},
        }

    def decode_voltage_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # HV voltages are 16-bit little-endian, 1 bit per 0.1V
        # Low voltages are 8-bit, 1 bit per 0.1V
        hv_batt = ((b[1] << 8) | b[0]) * 0.1
        hv_mot = ((b[3] << 8) | b[2]) * 0.1
        dcdc = b[4] * 0.1
        aux1 = b[5] * 0.1
        aux2 = b[6] * 0.1
        lvbat = b[7] * 0.1
        return {
            "HV_BATT": {"d": f"{hv_batt:.1f}", "u": "V"},
            "HV_MOT": {"d": f"{hv_mot:.1f}", "u": "V"},
            "DCDC": {"d": f"{dcdc:.1f}", "u": "V"},
            "AUX1": {"d": f"{aux1:.1f}", "u": "V"},
            "AUX2": {"d": f"{aux2:.1f}", "u": "V"},
            "LVBAT": {"d": f"{lvbat:.1f}", "u": "V"},
        }

    def decode_current_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # HV currents are 16-bit little-endian signed, 1 bit per 0.1A
        # Low currents are 8-bit signed, 1 bit per 1A
        hv_batt_raw = (b[1] << 8) | b[0]
        hv_mot_raw = (b[3] << 8) | b[2]
        # Convert to signed 16-bit
        hv_batt = ((hv_batt_raw + 0x8000) % 0x10000 - 0x8000) * 0.1
        hv_mot = ((hv_mot_raw + 0x8000) % 0x10000 - 0x8000) * 0.1
        # 8-bit signed values
        dcdc = ((b[4] + 128) % 256 - 128)
        aux1 = ((b[5] + 128) % 256 - 128)
        aux2 = ((b[6] + 128) % 256 - 128)
        lvbat = ((b[7] + 128) % 256 - 128)
        return {
            "HV_BATT_Current": {"d": f"{hv_batt:+.1f}", "u": "A"},
            "HV_MOT_Current": {"d": f"{hv_mot:+.1f}", "u": "A"},
            "DCDC_Current": {"d": f"{dcdc:+.0f}", "u": "A"},
            "AUX1_Current": {"d": f"{aux1:+.0f}", "u": "A"},
            "AUX2_Current": {"d": f"{aux2:+.0f}", "u": "A"},
            "LVBAT_Current": {"d": f"{lvbat:+.0f}", "u": "A"},
        }

    def decode_drive_frame(self, data):
        if len(data) < 8: return {}
        b = data

        # Throttle: 1 bit per %, Range [0,100]
        throttle = b[0]

        # Status: bit field
        status = b[1]
        limp_mode_bit = bool(status & 0x01)
        limited_range_bit = bool(status & 0x02)
        limp_mode = "Yes" if limp_mode_bit else "No"
        limited_range = "Yes" if limited_range_bit else "No"

        # TCU RND: bit field
        tcu_rnd = b[2]
        tcu_validated_bit = bool(tcu_rnd & 0x01)
        tcu_reverse_bit = bool(tcu_rnd & 0x02)
        tcu_neutral_bit = bool(tcu_rnd & 0x04)
        tcu_drive_bit = bool(tcu_rnd & 0x08)
        tcu_eco_sport_bit = bool(tcu_rnd & 0x10)
        tcu_dock_bit = bool(tcu_rnd & 0x20)
        # TCU_ENABLED removed - duplicate of TCU_ENABLE from TCU input frame
        tcu_error_kill_bit = bool(tcu_rnd & 0x80)
        tcu_validated = "Yes" if tcu_validated_bit else "No"
        tcu_reverse = "Yes" if tcu_reverse_bit else "No"
        tcu_neutral = "Yes" if tcu_neutral_bit else "No"
        tcu_drive = "Yes" if tcu_drive_bit else "No"
        tcu_eco_sport = "Yes" if tcu_eco_sport_bit else "No"
        tcu_dock = "Yes" if tcu_dock_bit else "No"
        # tcu_enabled removed - duplicate
        tcu_error_kill = "Yes" if tcu_error_kill_bit else "No"

        # PCU RND: similar bit field (assuming same format)
        pcu_rnd = b[3]
        pcu_validated_bit = bool(pcu_rnd & 0x01)
        pcu_reverse_bit = bool(pcu_rnd & 0x02)
        pcu_neutral_bit = bool(pcu_rnd & 0x04)
        pcu_drive_bit = bool(pcu_rnd & 0x08)
        pcu_eco_sport_bit = bool(pcu_rnd & 0x10)
        pcu_dock_bit = bool(pcu_rnd & 0x20)
        pcu_enabled_bit = bool(pcu_rnd & 0x40)
        pcu_error_kill_bit = bool(pcu_rnd & 0x80)
        pcu_validated = "Yes" if pcu_validated_bit else "No"
        pcu_reverse = "Yes" if pcu_reverse_bit else "No"
        pcu_neutral = "Yes" if pcu_neutral_bit else "No"
        pcu_drive = "Yes" if pcu_drive_bit else "No"
        pcu_eco_sport = "Yes" if pcu_eco_sport_bit else "No"
        pcu_dock = "Yes" if pcu_dock_bit else "No"
        pcu_enabled = "Yes" if pcu_enabled_bit else "No"
        pcu_error_kill = "Yes" if pcu_error_kill_bit else "No"

        # Trim: 1 bit per %, Range [0,100]
        trim = b[4]

        # Range, Power, SOC: assuming direct values
        range_val = b[5]
        power = b[6]
        soc = b[7]

        return {
            "Throttle": {"d": f"{throttle:.0f}", "u": "%", "v": throttle},
            "LIMP_MODE": {"d": limp_mode, "u": "", "v": limp_mode_bit},
            "LIMITED_RANGE": {"d": limited_range, "u": "", "v": limited_range_bit},
            "TCU_VALIDATED": {"d": tcu_validated, "u": "", "v": tcu_validated_bit},
            "TCU_REVERSE": {"d": tcu_reverse, "u": "", "v": tcu_reverse_bit},
            "TCU_NEUTRAL": {"d": tcu_neutral, "u": "", "v": tcu_neutral_bit},
            "TCU_DRIVE": {"d": tcu_drive, "u": "", "v": tcu_drive_bit},
            "TCU_ECO_SPORT": {"d": tcu_eco_sport, "u": "", "v": tcu_eco_sport_bit},
            "TCU_DOCK": {"d": tcu_dock, "u": "", "v": tcu_dock_bit},
            # TCU_ENABLED removed - duplicate of TCU_ENABLE from TCU input frame
            "TCU_ERROR_KILL": {"d": tcu_error_kill, "u": "", "v": tcu_error_kill_bit},
            "PCU_VALIDATED": {"d": pcu_validated, "u": "", "v": pcu_validated_bit},
            "PCU_REVERSE": {"d": pcu_reverse, "u": "", "v": pcu_reverse_bit},
            "PCU_NEUTRAL": {"d": pcu_neutral, "u": "", "v": pcu_neutral_bit},
            "PCU_DRIVE": {"d": pcu_drive, "u": "", "v": pcu_drive_bit},
            "PCU_ECO_SPORT": {"d": pcu_eco_sport, "u": "", "v": pcu_eco_sport_bit},
            "PCU_DOCK": {"d": pcu_dock, "u": "", "v": pcu_dock_bit},
            "PCU_ENABLED": {"d": pcu_enabled, "u": "", "v": pcu_enabled_bit},
            "PCU_ERROR_KILL": {"d": pcu_error_kill, "u": "", "v": pcu_error_kill_bit},
            "Trim": {"d": f"{trim:.0f}", "u": "%", "v": trim},
            "Range": {"d": f"{range_val:.0f}", "u": "", "v": range_val},
            "Power": {"d": f"{power:.0f}", "u": "", "v": power},
            "SOC": {"d": f"{soc:.0f}", "u": "%", "v": soc},
        }

    def decode_spdtq_frame(self, data):
        if len(data) < 8: return {}
        b = data

        # Motor Speed: 16-bit little-endian signed, 1 rpm per bit
        motor_speed_raw = (b[1] << 8) | b[0]
        motor_speed = ((motor_speed_raw + 0x8000) % 0x10000 - 0x8000)  # Signed 16-bit

        # Motor Torque: 16-bit little-endian signed, 0.1 Nm per bit
        motor_torque_raw = (b[3] << 8) | b[2]
        motor_torque = ((motor_torque_raw + 0x8000) % 0x10000 - 0x8000) * 0.1  # Signed 16-bit

        # Motor hours: 16-bit little-endian unsigned, 1 hour per bit
        motor_hours = (b[5] << 8) | b[4]

        # OB Err: 8-bit bit field
        ob_err = b[6]
        motor_failure = "Yes" if ob_err & 0x01 else "No"
        inv_failure = "Yes" if ob_err & 0x02 else "No"
        power_failure = "Yes" if ob_err & 0x04 else "No"
        internal_failure = "Yes" if ob_err & 0x08 else "No"
        cooling_failure = "Yes" if ob_err & 0x10 else "No"
        can_failure = "Yes" if ob_err & 0x20 else "No"
        flash_failure = "Yes" if ob_err & 0x40 else "No"
        temp_failure = "Yes" if ob_err & 0x80 else "No"

        # Mode: 8-bit bit field
        mode = b[7]
        temp_derating = "Yes" if mode & 0x01 else "No"
        maintenance_mode = "Yes" if mode & 0x02 else "No"
        sport_mode = "SPORT" if mode & 0x04 else "ECO"
        boost_enabled = "Yes" if mode & 0x08 else "No"
        critical_mode = "Yes" if mode & 0x10 else "No"
        inverter_detected = "Yes" if mode & 0x20 else "No"
        hv_detected = "Yes" if mode & 0x40 else "No"
        propulsion_enabled = "Yes" if mode & 0x80 else "No"

        return {
            "Motor_Speed": {"d": f"{motor_speed:+.0f}", "u": "RPM"},
            "Motor_Torque": {"d": f"{motor_torque:+.1f}", "u": "Nm"},
            "Motor_Hours": {"d": f"{motor_hours:.0f}", "u": "h"},
            "MOTOR_FAILURE": {"d": motor_failure, "u": ""},
            "INV_FAILURE": {"d": inv_failure, "u": ""},
            "POWER_FAILURE": {"d": power_failure, "u": ""},
            "INTERNAL_FAILURE": {"d": internal_failure, "u": ""},
            "COOLING_FAILURE": {"d": cooling_failure, "u": ""},
            "CAN_FAILURE": {"d": can_failure, "u": ""},
            "FLASH_FAILURE": {"d": flash_failure, "u": ""},
            "TEMP_FAILURE": {"d": temp_failure, "u": ""},
            "TEMP_DERATING": {"d": temp_derating, "u": ""},
            "MAINTENANCE_MODE": {"d": maintenance_mode, "u": ""},
            "DRIVE_MODE": {"d": sport_mode, "u": ""},
            "BOOST_ENABLED": {"d": boost_enabled, "u": ""},
            "CRITICAL_MODE": {"d": critical_mode, "u": ""},
            "INVERTER_DETECTED": {"d": inverter_detected, "u": ""},
            "HV_DETECTED": {"d": hv_detected, "u": ""},
            "PROPULSION_ENABLED": {"d": propulsion_enabled, "u": ""},
        }

    def decode_power_frame(self, data):
        if len(data) < 8: return {}
        b = data

        # Mode: power mode & status bit field
        mode = b[0]
        auxiliary_power = "Yes" if mode & 0x01 else "No"
        maintenance_mode = "Yes" if mode & 0x02 else "No"
        eco_mode = "Yes" if mode & 0x04 else "No"
        sport_mode = "Yes" if mode & 0x08 else "No"
        regen_enabled = "Yes" if mode & 0x10 else "No"
        inverter_detected = "Yes" if mode & 0x20 else "No"
        hv_detected = "Yes" if mode & 0x40 else "No"
        start_stop = "Yes" if mode & 0x80 else "No"

        # BattServ: battery service voltage, 1 bit per 0.1V
        battserv = b[1] * 0.1

        # Pump: 12V pump current, 1 bit per 0.1A
        pump_current = b[2] * 0.1

        # Trim: 12V/24V trim current, 1 bit per 1A
        trim_current = b[3]

        # Inverter voltage: 16-bit little-endian, 1 bit per 0.1V
        inv_voltage = ((b[5] << 8) | b[4]) * 0.1

        # Inverter current: 16-bit little-endian signed, 1 bit per 0.1A
        inv_current_raw = (b[7] << 8) | b[6]
        inv_current = ((inv_current_raw + 0x8000) % 0x10000 - 0x8000) * 0.1

        return {
            "AUXILIARY_POWER": {"d": auxiliary_power, "u": "", "v": bool(mode & 0x01)},
            "MAINTENANCE_MODE": {"d": maintenance_mode, "u": "", "v": bool(mode & 0x02)},
            "ECO_MODE": {"d": eco_mode, "u": "", "v": bool(mode & 0x04)},
            "SPORT_MODE": {"d": sport_mode, "u": "", "v": bool(mode & 0x08)},
            "REGEN_ENABLED": {"d": regen_enabled, "u": "", "v": bool(mode & 0x10)},
            "INVERTER_DETECTED": {"d": inverter_detected, "u": "", "v": bool(mode & 0x20)},
            "HV_DETECTED": {"d": hv_detected, "u": "", "v": bool(mode & 0x40)},
            "START_STOP": {"d": start_stop, "u": "", "v": bool(mode & 0x80)},
            "BATT_SERV": {"d": f"{battserv:.1f}", "u": "V", "v": battserv},
            "PUMP_CURRENT": {"d": f"{pump_current:.1f}", "u": "A", "v": pump_current},
            "TRIM_CURRENT": {"d": f"{trim_current:.0f}", "u": "A", "v": trim_current},
            "INVERTER_VOLTAGE": {"d": f"{inv_voltage:.1f}", "u": "V", "v": inv_voltage},
            "INVERTER_CURRENT": {"d": f"{inv_current:+.1f}", "u": "A", "v": inv_current},
        }

    def decode_pcu_frame(self, frame_id: int, data: bytes):
        if len(data) < 8:
            return {}
        b = data
        signals = {}

        if frame_id == 0x720:  # Motor Status
            # Motor Hours: 16-bit little-endian unsigned, range 0-10000
            motor_hours = (b[1] << 8) | b[0]
            signals["MOTOR_HOURS"] = {"d": f"{motor_hours}", "u": "h", "v": motor_hours}

            # Motor Torque: 16-bit little-endian signed, 1 bit per 0.1Nm, range -30000 to 30000
            torque_raw = (b[3] << 8) | b[2]
            torque = ((torque_raw + 0x8000) % 0x10000 - 0x8000) * 0.1
            signals["MOTOR_TORQUE"] = {"d": f"{torque:+.1f}", "u": "Nm", "v": torque}

            # Motor Speed: 16-bit little-endian unsigned, 1 bit per rpm, range 0-30000
            motor_speed = (b[5] << 8) | b[4]
            signals["MOTOR_SPEED"] = {"d": f"{motor_speed}", "u": "RPM", "v": motor_speed}

            # PRND: byte 6, bit field for drive selection and states
            prnd = b[6]
            prnd_status = []
            if prnd & 0x01: prnd_status.append("P")  # Parking
            if prnd & 0x02: prnd_status.append("R")  # Reverse
            if prnd & 0x04: prnd_status.append("N")  # Neutral
            if prnd & 0x08: prnd_status.append("D")  # Drive
            signals["PRND"] = {"d": "/".join(prnd_status) if prnd_status else "None", "u": "", "v": prnd}

            # Additional PRND states
            signals["JAKE_STATE"] = {"d": "Active" if prnd & 0x10 else "Inactive", "u": "", "v": bool(prnd & 0x10)}
            signals["BOOST_STATE"] = {"d": "Active" if prnd & 0x20 else "Inactive", "u": "", "v": bool(prnd & 0x20)}
            signals["TRIM_STATE"] = {"d": "Active" if prnd & 0x40 else "Inactive", "u": "", "v": bool(prnd & 0x40)}
            signals["IGN_STATE"] = {"d": "On" if prnd & 0x80 else "Off", "u": "", "v": bool(prnd & 0x80)}

            # Failure: byte 7, bit field for various failures
            failure = b[7]
            signals["MOTOR_FAILURE"] = {"d": "Yes" if failure & 0x01 else "No", "u": "", "v": bool(failure & 0x01)}
            signals["INV_FAILURE"] = {"d": "Yes" if failure & 0x02 else "No", "u": "", "v": bool(failure & 0x02)}
            signals["POWER_FAILURE"] = {"d": "Yes" if failure & 0x04 else "No", "u": "", "v": bool(failure & 0x04)}
            signals["INTERNAL_FAILURE"] = {"d": "Yes" if failure & 0x08 else "No", "u": "", "v": bool(failure & 0x08)}
            signals["COOLING_FAILURE"] = {"d": "Yes" if failure & 0x10 else "No", "u": "", "v": bool(failure & 0x10)}
            signals["CANBUS_FAILURE"] = {"d": "Yes" if failure & 0x20 else "No", "u": "", "v": bool(failure & 0x20)}
            signals["FLASH_FAILURE"] = {"d": "Yes" if failure & 0x40 else "No", "u": "", "v": bool(failure & 0x40)}
            signals["TEMP_FAILURE"] = {"d": "Yes" if failure & 0x80 else "No", "u": "", "v": bool(failure & 0x80)}

        elif frame_id == 0x722:  # PCU Cooling
            # Cool_MT: outboard coolant temperature, 8-bit with -40°C offset, 1°C per bit
            cool_mt = b[0] - 40
            signals["COOL_MT"] = {"d": f"{cool_mt:+.0f}", "u": "°C", "v": cool_mt}

            # Cool_BT: battery coolant temperature, 8-bit with -40°C offset, 1°C per bit
            cool_bt = b[1] - 40
            signals["COOL_BT"] = {"d": f"{cool_bt:+.0f}", "u": "°C", "v": cool_bt}

            # FlowSea: sea water flow rate, 8-bit unsigned, 1 L/m per bit, range 0-255
            flow_sea = b[2]
            signals["FLOW_SEA"] = {"d": f"{flow_sea:.0f}", "u": "L/m", "v": flow_sea}

            # FlowGlycol: glycol-water flow rate, 8-bit unsigned, 0.1 L/m per bit, range 0-255
            flow_glycol = b[3] * 0.1
            signals["FLOW_GLYCOL"] = {"d": f"{flow_glycol:.1f}", "u": "L/m", "v": flow_glycol}

            # Stator: motor temperature, 8-bit with -40°C offset, 1°C per bit
            stator_temp = b[4] - 40
            signals["STATOR_TEMP"] = {"d": f"{stator_temp:+.0f}", "u": "°C", "v": stator_temp}

            # Inv: inverter temperature, 8-bit with -40°C offset, 1°C per bit
            inv_temp = b[5] - 40
            signals["INV_TEMP"] = {"d": f"{inv_temp:+.0f}", "u": "°C", "v": inv_temp}

            # Rotor: rotor temperature, 8-bit with -40°C offset, 1°C per bit
            rotor_temp = b[6] - 40
            signals["ROTOR_TEMP"] = {"d": f"{rotor_temp:+.0f}", "u": "°C", "v": rotor_temp}

            # Battery: battery temperature, 8-bit with -40°C offset, 1°C per bit
            battery_temp = b[7] - 40
            signals["BATTERY_TEMP"] = {"d": f"{battery_temp:+.0f}", "u": "°C", "v": battery_temp}

        elif frame_id == 0x724:  # PCU Power - reuse existing decode_power_frame logic
            return self.decode_power_frame(data)

        return signals

    def decode_tcu_enable_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # Enable: Byte 4, bit 2 (1 = TCU is talking, 0 = no TCU or fault)
        enable_bit = bool(b[4] & 0x04)
        enable = "Yes" if enable_bit else "No"
        return {
            "TCU_ENABLE": {"d": enable, "u": "", "v": enable_bit},
        }

    def decode_tcu_prnd_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # PRND: Byte 0 (8 bits) - 0x01=P, 0x02=R, 0x04=N, 0x08=D, 0x10=Auto, etc.
        prnd_val = b[0]
        prnd_status = []
        if prnd_val & 0x01: prnd_status.append("P")
        if prnd_val & 0x02: prnd_status.append("R")
        if prnd_val & 0x04: prnd_status.append("N")
        if prnd_val & 0x08: prnd_status.append("D")
        if prnd_val & 0x10: prnd_status.append("Auto")
        prnd_str = "/".join(prnd_status) if prnd_status else "None"
        return {
            "TCU_PRND": {"d": prnd_str, "u": "", "v": prnd_val},
        }

    def decode_tcu_throttle_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # Throttle: Byte 1 (8 bits) 0–255 → 0–100 %
        throttle_raw = b[1]
        throttle_percent = (throttle_raw / 255.0) * 100.0
        return {
            "TCU_Throttle": {"d": f"{throttle_percent:.1f}", "u": "%", "v": throttle_percent},
        }

    def decode_tcu_trim_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # Trim: Byte 0, bits 0–3 - 0x01 = "+" pressed, 0x02 = "-" pressed, etc.
        trim_bits = b[0] & 0x0F
        trim_plus_bit = bool(trim_bits & 0x01)
        trim_minus_bit = bool(trim_bits & 0x02)
        trim_plus = "Yes" if trim_plus_bit else "No"
        trim_minus = "Yes" if trim_minus_bit else "No"
        # Other bits could be defined as needed
        return {
            "TCU_Trim_Plus": {"d": trim_plus, "u": "", "v": trim_plus_bit},
            "TCU_Trim_Minus": {"d": trim_minus, "u": "", "v": trim_minus_bit},
        }

    def decode_gps_speed_frame(self, data):
        if len(data) < 8: return {}
        b = data
        # GPS speed: Byte 4 and byte 5 (16-bit little-endian)
        gps_speed_raw = (b[5] << 8) | b[4]
        # Assuming it's in some unit, probably km/h or mph - need to check the scaling
        gps_speed = gps_speed_raw  # Placeholder - may need scaling
        return {
            "GPS_Speed": {"d": f"{gps_speed:.0f}", "u": "km/h", "v": gps_speed},  # Adjust unit as needed
        }

    HEX_TO_DBC_ID = {
        0x727:1831, 0x587:1415, 0x107:263, 0x607:1543, 0x4F0:1264, 0x580:1408, 0x740:1856,
        0x722:1826, 0x720:1824, 0x600:1536, 0x72E:1838,
        0x400:1024, 0x401:1025, 0x403:1027, 0x405:1029, 0x406:1030,
        0x420:1056, 0x421:1057, 0x423:1059, 0x425:1061, 0x426:1062,
        0x440:1088, 0x441:1089, 0x443:1091, 0x445:1093, 0x446:1094,
        ID_HV_CHARGER_STATUS: None, ID_HV_CHARGER_CMD: None, ID_DC12_COMM: None, ID_DC12_STAT: None,
        ID_TEMP_FRAME: None
    }

    # === GUI CREATION ===
    def create_tab(self, fid, name, title, headers):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(title))

        # Add hex display label
        hex_label = QLabel(f"0x{fid:03X}: {self.current_hex.get(fid, '00 00 00 00 00 00 00 00')}")
        hex_label.setStyleSheet("font-family: Consolas; font-size: 11px; color: #666; padding: 2px;")
        self.hex_labels[fid] = hex_label
        l.addWidget(hex_label)

        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tables[fid] = table
        l.addWidget(table)
        self.tabs.addTab(w, name)

    def create_hmi_tab(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("HMI Frames (Temperature, Voltage, Current, Drive, Motor, TCU & GPS)"))

        # Add hex displays for HMI frames (excluding TCU frames which are shown separately)
        hex_layout = QHBoxLayout()
        for fid in [ID_TEMP_FRAME, ID_VOLT_FRAME, ID_CURRENT_FRAME, ID_DRIVE_FRAME, ID_SPDTQ_FRAME]:
            hex_label = QLabel(f"0x{fid:08X}: {self.current_hex.get(fid, '00 00 00 00 00 00 00 00')}")
            hex_label.setStyleSheet("font-family: Consolas; font-size: 10px; color: #666; padding: 1px; margin-right: 10px;")
            self.hex_labels[fid] = hex_label
            hex_layout.addWidget(hex_label)
        l.addLayout(hex_layout)

        # Add TCU emulator controls
        emu_group = QGroupBox("TCU Emulators")
        emu_layout = QVBoxLayout(emu_group)

        # Master TCU emulation control
        master_layout = QHBoxLayout()
        self.tcu_master_btn = QPushButton("OFF to Click to Enable ALL TCU")
        self.tcu_master_btn.setStyleSheet("background:#555;color:white;font-weight:bold;")
        master_layout.addWidget(self.tcu_master_btn)
        master_layout.addWidget(QLabel("  → Sends all TCU frames continuously at 500ms intervals"))
        master_layout.addStretch()
        emu_layout.addLayout(master_layout)

        # Individual payload editors
        payloads_layout = QVBoxLayout()
        payloads_group = QGroupBox("TCU Payloads (editable during transmission)")
        payloads_inner = QVBoxLayout(payloads_group)

        # Create input fields for each TCU frame
        self.tcu_inputs = {}
        self.tcu_inputs[ID_TCU_ENABLE_FRAME] = QLineEdit("00 00 00 00 04 00 00 00")
        self.tcu_inputs[ID_TCU_PRND_FRAME] = QLineEdit("01 00 00 00 00 00 00 00")
        self.tcu_inputs[ID_TCU_THROTTLE_FRAME] = QLineEdit("00 10 00 00 00 00 00 00")
        self.tcu_inputs[ID_TCU_TRIM_FRAME] = QLineEdit("00 00 00 00 00 00 00 00")
        self.tcu_inputs[ID_GPS_SPEED_FRAME] = QLineEdit("00 00 00 00 00 11 00 00")

        # Add labeled input fields
        enable_input_layout = QHBoxLayout()
        enable_input_layout.addWidget(QLabel("TCU Enable (0CFF0BD0):"))
        enable_input_layout.addWidget(self.tcu_inputs[ID_TCU_ENABLE_FRAME])
        payloads_inner.addLayout(enable_input_layout)

        prnd_input_layout = QHBoxLayout()
        prnd_input_layout.addWidget(QLabel("TCU PRND (18F005D0):"))
        prnd_input_layout.addWidget(self.tcu_inputs[ID_TCU_PRND_FRAME])
        payloads_inner.addLayout(prnd_input_layout)

        throttle_input_layout = QHBoxLayout()
        throttle_input_layout.addWidget(QLabel("TCU Throttle (0CF003D0):"))
        throttle_input_layout.addWidget(self.tcu_inputs[ID_TCU_THROTTLE_FRAME])
        payloads_inner.addLayout(throttle_input_layout)

        trim_input_layout = QHBoxLayout()
        trim_input_layout.addWidget(QLabel("TCU Trim (0CFF08D0):"))
        trim_input_layout.addWidget(self.tcu_inputs[ID_TCU_TRIM_FRAME])
        payloads_inner.addLayout(trim_input_layout)

        gps_input_layout = QHBoxLayout()
        gps_input_layout.addWidget(QLabel("GPS Speed (09F8020A):"))
        gps_input_layout.addWidget(self.tcu_inputs[ID_GPS_SPEED_FRAME])
        payloads_inner.addLayout(gps_input_layout)

        payloads_layout.addWidget(payloads_group)
        emu_layout.addLayout(payloads_layout)

        l.addWidget(emu_group)

        # Connect the master button
        self.tcu_master_btn.clicked.connect(self.toggle_all_tcu_emulation)

        # Add TCU table section (like PCU stat)
        tcu_layout = QHBoxLayout()
        tcu_layout.addWidget(QLabel("TCU Parameters – Editable Table"))

        tcu_table = QTableWidget()
        tcu_table.setColumnCount(4)
        tcu_table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        tcu_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tcu_tab = tcu_table
        tcu_layout.addWidget(tcu_table)
        l.addLayout(tcu_layout)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.hmi_tab = table
        l.addWidget(table)
        self.tabs.addTab(w, "HMI CAN2")

    def create_emulator_tab(self, can_id, tab_name, title, default_payload, presets=None):
        if presets is None: presets = []
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel(title))

        # Add hex display label
        if can_id > 0x7FF:  # Extended ID
            hex_label = QLabel(f"0x{can_id:08X}: {self.current_hex.get(can_id, '00 00 00 00 00 00 00 00')}")
        else:  # Standard ID
            hex_label = QLabel(f"0x{can_id:03X}: {self.current_hex.get(can_id, '00 00 00 00 00 00 00 00')}")
        hex_label.setStyleSheet("font-family: Consolas; font-size: 11px; color: #666; padding: 2px;")
        self.hex_labels[can_id] = hex_label
        main.addWidget(hex_label)

        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tables[can_id] = table
        splitter.addWidget(table)

        emu = QWidget()
        el = QVBoxLayout(emu)
        el.addWidget(QLabel(f"<b>{tab_name} Emulator</b>"))

        btn = QPushButton("OFF to Click to Enable")
        input_field = QLineEdit(default_payload)
        input_field.setFixedWidth(340)
        setattr(self, f"input_{can_id:x}", input_field)
        btn.clicked.connect(lambda: self.toggle_emulator(can_id, btn, input_field))
        btn.setStyleSheet("background:#555;color:white;")
        el.addWidget(btn)

        hex_l = QHBoxLayout()
        hex_l.addWidget(QLabel("Payload:"))
        hex_l.addWidget(input_field)
        send_once = QPushButton("SEND ONCE")
        send_once.clicked.connect(lambda: self.send_raw(can_id, input_field.text()))
        hex_l.addWidget(send_once)
        el.addLayout(hex_l)

        if presets:
            p = QHBoxLayout()
            p.addWidget(QLabel("Presets:"))
            for label, pl in presets:
                b = QPushButton(label)
                b.clicked.connect(lambda _, x=pl: input_field.setText(x))
                p.addWidget(b)
            el.addLayout(p)

        el.addStretch()
        splitter.addWidget(emu)
        splitter.setSizes([1000, 400])
        self.tabs.addTab(w, tab_name)

    def create_battery_tab_with_emulator(self, name, idx, frame_ids):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.addWidget(QLabel(f"{name} – Live + Emulator"))
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        if idx == 1:  # Battery 1 table needs edit triggers for editable functionality
            table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed | QTableWidget.SelectedClicked)
            table.setSelectionBehavior(QTableWidget.SelectItems)
            table.setSelectionMode(QTableWidget.SingleSelection)
        self.battery_tabs[idx] = table
        splitter.addWidget(table)

        emu = QWidget()
        el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Battery 1 Full Emulator (400-406)</b>"))
        self.bat_inputs = {}
        defaults = {
            0x400: "9E 07 8A 02 4F 18 3A 5E",
            0x401: "DF 1A 0B 00 E0 1A 64 01",
            0x402: "3D 0E E2 04 A0 41 55 03",  # Alarms 1-8 example
            0x403: "00 3B 00 3C EE 0E F7 0E",
            0x404: "01 00 C8 0F 0F 01 00 00",  # Example realistic values
            0x405: "10 27 00 00 E8 03 00 3C",  # Nb_Cycles=10000, Ah=100.0, Time=60s
            0x406: "00 00 00 00 00 00 00 00",  # Alarms 9-16 clear
        }
        for cid in BAT1_EMULATOR_IDS:
            box = QGroupBox(f"0x{cid:03X}")
            bl = QVBoxLayout(box)

            # Add hex display label for this frame
            hex_label = QLabel(f"0x{cid:03X}: {self.current_hex.get(cid, '00 00 00 00 00 00 00 00')}")
            hex_label.setStyleSheet("font-family: Consolas; font-size: 10px; color: #666; padding: 1px;")
            self.hex_labels[cid] = hex_label
            bl.addWidget(hex_label)

            line = QLineEdit(defaults.get(cid, "00 00 00 00 00 00 00 00"))
            line.setFixedWidth(340)
            self.bat_inputs[cid] = line
            send_btn = QPushButton("SEND ONCE")
            send_btn.clicked.connect(lambda _, id=cid: self.send_raw(id, line.text()))
            bl.addWidget(line)
            bl.addWidget(send_btn)
            el.addWidget(box)

        self.bat_btn = QPushButton("OFF to Click to Enable Cycle")
        self.bat_btn.clicked.connect(self.toggle_bat1)
        self.bat_btn.setStyleSheet("background:#388E3C;color:white;")
        el.addWidget(self.bat_btn)
        el.addStretch()
        splitter.addWidget(emu)
        splitter.setSizes([1100, 500])
        self.tabs.addTab(w, name)

    def create_pcu_tab_with_emulator(self, name, frame_ids):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.addWidget(QLabel(f"{name} – Live + Emulator"))
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.pcu_tab = table
        splitter.addWidget(table)

        emu = QWidget()
        el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>PCU Full Emulator (720-724)</b>"))
        self.pcu_inputs = {}
        defaults = {
            0x720: "f0 04 9e 11 36 15 08 01",  # Motor Stat
            0x722: "4a 5e 30 64 43 4b 5e 49",  # PCU Cooling
            0x724: "E4 8A 28 1D E5 1A 00 00",  # PCU Power
        }
        for cid in PCU_FRAMES:
            box = QGroupBox(f"0x{cid:03X}")
            bl = QVBoxLayout(box)

            # Add hex display label for this frame
            hex_label = QLabel(f"0x{cid:03X}: {self.current_hex.get(cid, '00 00 00 00 00 00 00 00')}")
            hex_label.setStyleSheet("font-family: Consolas; font-size: 10px; color: #666; padding: 1px;")
            self.hex_labels[cid] = hex_label
            bl.addWidget(hex_label)

            line = QLineEdit(defaults.get(cid, "00 00 00 00 00 00 00 00"))
            line.setFixedWidth(340)
            self.pcu_inputs[cid] = line
            send_btn = QPushButton("SEND ONCE")
            send_btn.clicked.connect(lambda _, id=cid: self.send_raw(id, line.text()))
            bl.addWidget(line)
            bl.addWidget(send_btn)
            el.addWidget(box)

        self.pcu_btn = QPushButton("OFF to Click to Enable Cycle")
        self.pcu_btn.clicked.connect(self.toggle_pcu)
        self.pcu_btn.setStyleSheet("background:#388E3C;color:white;")
        el.addWidget(self.pcu_btn)
        el.addStretch()
        splitter.addWidget(emu)
        splitter.setSizes([1100, 500])
        self.tabs.addTab(w, name)

    def create_battery_tab(self, name, idx, frame_ids):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(name))

        # Add hex displays for all frames in this battery
        hex_layout = QHBoxLayout()
        for fid in frame_ids:
            hex_label = QLabel(f"0x{fid:03X}: {self.current_hex.get(fid, '00 00 00 00 00 00 00 00')}")
            hex_label.setStyleSheet("font-family: Consolas; font-size: 10px; color: #666; padding: 1px; margin-right: 10px;")
            self.hex_labels[fid] = hex_label
            hex_layout.addWidget(hex_label)
        l.addLayout(hex_layout)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.battery_tabs[idx] = table
        l.addWidget(table)
        self.tabs.addTab(w, name)

    # === Emulation Control ===
    def toggle_emulator(self, can_id, btn, input_field):
        EMULATOR_STATES[can_id] = not EMULATOR_STATES[can_id]
        if EMULATOR_STATES[can_id]:
            interval = get_emulator_interval(can_id)
            freq = int(1.0 / interval) if interval > 0 else 0
            btn.setText(f"ON – {hex(can_id)} @{freq}Hz")
            btn.setStyleSheet("background:#d32f2f;color:white;")
            self.start_timer(can_id, lambda: self.send_raw(can_id, input_field.text()), interval)
        else:
            btn.setText("OFF to Click to Enable")
            btn.setStyleSheet("background:#555;color:white;")
            self.stop_timer(can_id)

    def toggle_bat1(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = not EMULATOR_BAT1_ENABLED
        if EMULATOR_BAT1_ENABLED:
            self.bat_btn.setText("ON – Cycling 400-406 @10Hz")
            self.bat_btn.setStyleSheet("background:#2E7D32;color:white;")
            self.bat1_cycle_index = 0
            self.start_timer("battery", self.send_bat_cycle, 0.1)  # 100ms interval for battery frames
        else:
            self.bat_btn.setText("OFF to Click to Enable Cycle")
            self.bat_btn.setStyleSheet("background:#388E3C;color:white;")
            self.stop_timer("battery")

    def toggle_pcu(self):
        global EMULATOR_PCU_ENABLED
        EMULATOR_PCU_ENABLED = not EMULATOR_PCU_ENABLED
        if EMULATOR_PCU_ENABLED:
            self.pcu_btn.setText("ON – Cycling PCU Frames")
            self.pcu_btn.setStyleSheet("background:#2E7D32;color:white;")
            self.pcu_cycle_index = 0
            self.start_timer("pcu", self.send_pcu_cycle, 0.1)  # Use appropriate interval for PCU frames
        else:
            self.pcu_btn.setText("OFF to Click to Enable Cycle")
            self.pcu_btn.setStyleSheet("background:#388E3C;color:white;")
            self.stop_timer("pcu")

    def send_pcu_cycle(self):
        cid = PCU_FRAMES[self.pcu_cycle_index]
        self.send_raw(cid, self.pcu_inputs[cid].text())
        self.pcu_cycle_index = (self.pcu_cycle_index + 1) % len(PCU_FRAMES)

    def toggle_all_tcu_emulation(self):
        """Toggle continuous transmission of all TCU frames"""
        tcu_frames = [ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME]

        # Check if any TCU frame is currently enabled
        any_enabled = any(EMULATOR_STATES.get(fid, False) for fid in tcu_frames)

        if not any_enabled:
            # Start all TCU emulations
            for fid in tcu_frames:
                EMULATOR_STATES[fid] = True
                interval = get_emulator_interval(fid)  # Should be 0.5 for all TCU frames
                input_field = self.tcu_inputs[fid]
                self.start_timer(fid, lambda fid=fid, input=input_field: self.send_raw(fid, input.text()), interval)

            self.tcu_master_btn.setText("ON – ALL TCU @2Hz (500ms)")
            self.tcu_master_btn.setStyleSheet("background:#d32f2f;color:white;font-weight:bold;")
        else:
            # Stop all TCU emulations
            for fid in tcu_frames:
                EMULATOR_STATES[fid] = False
                self.stop_timer(fid)

            self.tcu_master_btn.setText("OFF to Click to Enable ALL TCU")
            self.tcu_master_btn.setStyleSheet("background:#555;color:white;font-weight:bold;")

    def start_timer(self, can_id, callback, interval_seconds=None):
        # Initialize emu_timers dictionary if it doesn't exist
        if not hasattr(self, "emu_timers"):
            self.emu_timers = {}

        # Stop existing timer for this CAN ID if it exists
        if can_id in self.emu_timers:
            self.emu_timers[can_id].stop()

        # Create new timer for this CAN ID
        self.emu_timers[can_id] = QTimer()
        self.emu_timers[can_id].timeout.connect(callback)
        if interval_seconds is None:
            interval_seconds = EMULATOR_INTERVAL_DEFAULT
        self.emu_timers[can_id].start(int(interval_seconds * 1000))

    def stop_timer(self, can_id):
        if hasattr(self, "emu_timers") and can_id in self.emu_timers:
            self.emu_timers[can_id].stop()
            del self.emu_timers[can_id]

    def stop_all_timers(self):
        if hasattr(self, "emu_timers"):
            for timer in self.emu_timers.values():
                timer.stop()
            self.emu_timers.clear()

    def send_bat_cycle(self):
        cid = BAT1_EMULATOR_IDS[self.bat1_cycle_index]
        self.send_raw(cid, self.bat_inputs[cid].text())
        self.bat1_cycle_index = (self.bat1_cycle_index + 1) % len(BAT1_EMULATOR_IDS)

    def send_raw(self, can_id, text):
        # Send to all connected CAN buses
        buses_to_send = []
        if self.bus1_connected:
            buses_to_send.append((self.bus1, 1))
        if self.bus2_connected:
            buses_to_send.append((self.bus2, 2))

        if not buses_to_send:
            return

        clean = ''.join(c for c in text.upper() if c in '0123456789ABCDEF ')
        clean = clean.replace(" ", "")
        if len(clean) != 16: return

        for bus, bus_num in buses_to_send:
            try:
                data = bytes.fromhex(clean)
                is_extended = (can_id > 0x7FF)
                msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=is_extended)
                bus.send(msg)
                self.process_message_for_gui(msg, bus_num)
            except Exception as e:
                print(f"Send failed on CAN{bus_num}:", e)

    # === Message Processing ===
    def process_message_for_gui(self, msg, can_bus=1):
        with self.lock:
            self.raw_log_lines.append(f"CAN{can_bus} | 0x{msg.arbitration_id:08X} | {msg.data.hex(' ').upper()}")
            if len(self.raw_log_lines) > 200:
                self.raw_log_lines.pop(0)

            # Update current hex data for this ID
            hex_data = msg.data.hex(' ').upper()
            self.current_hex[msg.arbitration_id] = hex_data

            # Update hex display label if it exists
            if msg.arbitration_id in self.hex_labels:
                if msg.arbitration_id > 0x7FF:  # Extended ID
                    self.hex_labels[msg.arbitration_id].setText(f"0x{msg.arbitration_id:08X}: {hex_data}")
                else:  # Standard ID
                    self.hex_labels[msg.arbitration_id].setText(f"0x{msg.arbitration_id:03X}: {hex_data}")

        fid = msg.arbitration_id

        if fid == ID_HV_CHARGER_STATUS:
            decoded_signals = self.decode_hv_charger_status(msg.data)
        elif fid == ID_HV_CHARGER_CMD:
            decoded_signals = self.decode_hv_charger_cmd(msg.data)
        elif fid == ID_DC12_COMM:
            decoded_signals = self.decode_dc12_comm(msg.data)
        elif fid == ID_DC12_STAT:
            decoded_signals = self.decode_dc12_stat(msg.data)
        elif fid == ID_CCU_STATUS:
            decoded_signals = self.decode_ccu_stat(msg.data)
        elif fid == ID_ZCU_PUMP:
            decoded_signals = self.decode_zcu_stat(msg.data)
        elif fid == ID_TEMP_FRAME:
            decoded_signals = self.decode_temperature_frame(msg.data)
        elif fid == ID_VOLT_FRAME:
            decoded_signals = self.decode_voltage_frame(msg.data)
        elif fid == ID_CURRENT_FRAME:
            decoded_signals = self.decode_current_frame(msg.data)
        elif fid == ID_DRIVE_FRAME:
            decoded_signals = self.decode_drive_frame(msg.data)
        elif fid == ID_SPDTQ_FRAME:
            decoded_signals = self.decode_spdtq_frame(msg.data)
        elif fid == ID_TCU_ENABLE_FRAME:
            decoded_signals = self.decode_tcu_enable_frame(msg.data)
        elif fid == ID_TCU_PRND_FRAME:
            decoded_signals = self.decode_tcu_prnd_frame(msg.data)
        elif fid == ID_TCU_THROTTLE_FRAME:
            decoded_signals = self.decode_tcu_throttle_frame(msg.data)
        elif fid == ID_TCU_TRIM_FRAME:
            decoded_signals = self.decode_tcu_trim_frame(msg.data)
        elif fid == ID_GPS_SPEED_FRAME:
            decoded_signals = self.decode_gps_speed_frame(msg.data)
        elif fid in PCU_FRAMES:
            decoded_signals = self.decode_pcu_frame(fid, msg.data)
        elif fid in [0x402,0x422,0x442,0x404,0x424,0x444,0x405,0x425,0x445,0x406,0x426,0x446]:
            decoded_signals = self.decode_battery_frame(fid, msg.data)
        else:
            dbc_id = self.HEX_TO_DBC_ID.get(fid)
            if dbc_id is not None:
                try:
                    decoded = self.db.decode_message(dbc_id, msg.data)
                    unit_map = {s.name: s.unit or "" for s in self.db.get_message_by_frame_id(dbc_id).signals}
                    with self.lock:
                        self.signals[fid].update({
                            name: {"v": value,
                                   "d": f"{value:.3f}" if isinstance(value,float) else str(value),
                                   "u": unit_map.get(name,""),
                                   "t": time.time()}
                            for name, value in decoded.items()
                        })
                    return
                except:
                    return
            else:
                return

        if 'decoded_signals' in locals():
            with self.lock:
                self.signals[fid].update({
                    name: {
                        "d": val["d"], 
                        "u": val["u"], 
                        "v": val.get("v", val["d"]),  # Store value if available, otherwise use display
                        "t": time.time()
                    }
                    for name, val in decoded_signals.items()
                })

    def can_listener1(self):
        while self.bus1_connected:
            try:
                msg = self.bus1.recv(timeout=0.1)
                if msg:
                    if getattr(msg, 'is_error_frame', False):
                        with self.lock:
                            self.error_count += 1
                    else:
                        self.process_message_for_gui(msg, can_bus=1)
            except:
                pass

    def can_listener2(self):
        while self.bus2_connected:
            try:
                msg = self.bus2.recv(timeout=0.1)
                if msg:
                    if getattr(msg, 'is_error_frame', False):
                        with self.lock:
                            self.error_count += 1
                    else:
                        print(f"CAN2 received: 0x{msg.arbitration_id:03X}")  # Debug print
                        self.process_message_for_gui(msg, can_bus=2)
            except Exception as e:
                print(f"CAN2 listener error: {e}")
                pass

    def update_gui(self):
        with self.lock:
            lines = self.raw_log_lines[-8:]

        # Regular tables
        for fid, table in self.tables.items():
            items = list(self.signals.get(fid, {}).items())
            table.setRowCount(len(items))
            for r, (name, d) in enumerate(items):
                # For editable frames, use modified value if available, otherwise use live CAN data
                editable_frames = [0x580, 0x600, 0x72E, ID_HV_CHARGER_STATUS, ID_DC12_STAT]
                if fid in editable_frames:  # PDU Stat, CCU Stat, ZCU Stat, HVC Stat, or DC12 Stat frame
                    modified_data = self.modified_signals.get(fid, {}).get(name)
                    if modified_data:
                        display_val = modified_data.get("d", d.get("d",""))
                        is_modified = True
                    else:
                        display_val = d.get("d","")
                        is_modified = False
                else:
                    display_val = d.get("d","")
                    is_modified = False

                for c, val in enumerate([name, display_val, d.get("u",""), f"{d.get('t',0):.3f}"]):
                    item = table.item(r, c)
                    if not item:
                        item = QTableWidgetItem(val)
                        table.setItem(r, c, item)
                        # Make the value column (column 1) editable for editable frames
                        if c == 1 and fid in editable_frames:
                            item.setFlags(item.flags() | Qt.ItemIsEditable)
                        # Highlight modified values
                        if is_modified and c == 1:
                            item.setBackground(Qt.yellow)
                    else:
                        # Only update if not currently being edited by user
                        if not table.isPersistentEditorOpen(item):
                            item.setText(val)
                            # Update background color
                            if is_modified and c == 1:
                                item.setBackground(Qt.yellow)
                            elif c == 1 and fid in editable_frames:
                                item.setBackground(Qt.white)

            if self.first_fill.get(fid, False):
                table.resizeColumnsToContents()
                self.first_fill[fid] = False

            # Connect item changed signal for editable frames
            editable_frames = [0x580, 0x600, 0x72E, ID_HV_CHARGER_STATUS, ID_DC12_STAT]
            if fid in editable_frames and not hasattr(table, '_item_changed_connected'):
                table.itemChanged.connect(lambda item, f=fid: self.on_table_item_changed(item, f))
                table._item_changed_connected = True

        # Battery tabs (merged view)
        for idx, frames in [(1,BAT1_FRAMES),(2,BAT2_FRAMES),(3,BAT3_FRAMES)]:
            table = self.battery_tabs[idx]
            all_sig = []
            for fid in frames:
                signals_for_frame = self.signals.get(fid, {})

                # For Battery 1 frames that haven't been received yet, add default signals
                if idx == 1 and not signals_for_frame:
                    if fid == 0x400:
                        signals_for_frame = {
                            "Pack_Voltage": {"d": "0", "v": 0, "u": "V"},
                            "Pack_Current": {"d": "0", "v": 0, "u": "A"},
                            "Pack_SOC": {"d": "0", "v": 0, "u": "%"},
                        }
                    elif fid == 0x401:
                        signals_for_frame = {
                            "Max_Cell_Voltage": {"d": "0", "v": 0, "u": "mV"},
                            "Min_Cell_Voltage": {"d": "0", "v": 0, "u": "mV"},
                            "Avg_Cell_Voltage": {"d": "0", "v": 0, "u": "mV"},
                        }
                    elif fid == 0x402:
                        signals_for_frame = {
                            "Alarm_1": {"d": "0", "v": 0, "u": ""},
                            "Alarm_2": {"d": "0", "v": 0, "u": ""},
                            "Alarm_3": {"d": "0", "v": 0, "u": ""},
                            "Alarm_4": {"d": "0", "v": 0, "u": ""},
                            "Alarm_5": {"d": "0", "v": 0, "u": ""},
                            "Alarm_6": {"d": "0", "v": 0, "u": ""},
                            "Alarm_7": {"d": "0", "v": 0, "u": ""},
                            "Alarm_8": {"d": "0", "v": 0, "u": ""},
                        }
                    elif fid == 0x403:
                        signals_for_frame = {
                            "Isol_Board_Powered": {"d": "No", "v": False, "u": ""},
                            "Open_Sw_Error": {"d": "No", "v": False, "u": ""},
                            "No_Closing_Sw_Error": {"d": "No", "v": False, "u": ""},
                            "V_Cell_Avg": {"d": "0", "v": 0, "u": "mV"},
                        }
                    elif fid == 0x404:
                        signals_for_frame = {
                            "Contactor_4_Aux": {"d": "Open", "v": False, "u": ""},
                            "Contactor_3_Aux": {"d": "Open", "v": False, "u": ""},
                            "Contactor_2_Aux": {"d": "Open", "v": False, "u": ""},
                            "Contactor_1_Aux": {"d": "Open", "v": False, "u": ""},
                            "Contactor_4_State": {"d": "Open", "v": False, "u": ""},
                            "Contactor_3_State_Precharge": {"d": "Open", "v": False, "u": ""},
                            "Contactor_2_State_Neg": {"d": "Open", "v": False, "u": ""},
                            "Contactor_1_State_Pos": {"d": "Open", "v": False, "u": ""},
                            "Is_Balancing_Active": {"d": "No", "v": False, "u": ""},
                        }
                    elif fid == 0x405:
                        signals_for_frame = {
                            "Nb_Cycles": {"d": "0", "v": 0, "u": ""},
                            "Ah_Discharged": {"d": "0.0", "v": 0.0, "u": "Ah"},
                            "Remaining_Time_Before_Opening": {"d": "0", "v": 0, "u": "s"},
                        }
                    elif fid == 0x406:
                        signals_for_frame = {
                            "Alarm_9": {"d": "0", "v": 0, "u": ""},
                            "Alarm_10": {"d": "0", "v": 0, "u": ""},
                            "Alarm_11": {"d": "0", "v": 0, "u": ""},
                            "Alarm_12": {"d": "0", "v": 0, "u": ""},
                            "Alarm_13": {"d": "0", "v": 0, "u": ""},
                            "Alarm_14": {"d": "0", "v": 0, "u": ""},
                            "Alarm_15": {"d": "0", "v": 0, "u": ""},
                            "Alarm_16": {"d": "0", "v": 0, "u": ""},
                        }

                for name, d in signals_for_frame.items():
                    # Use modified value if available, otherwise use live CAN data
                    modified_data = self.modified_signals.get(fid, {}).get(name)
                    if modified_data:
                        display_data = modified_data.copy()
                    else:
                        display_data = d.copy()
                    all_sig.append((name, display_data, fid))  # Include frame ID

            all_sig.sort(key=lambda x: x[0])  # Sort by signal name
            table.setRowCount(len(all_sig))
            for r, (name, d, fid) in enumerate(all_sig):
                # Check if this value is modified
                is_modified = self.modified_signals.get(fid, {}).get(name) is not None

                for c, val in enumerate([name, d.get("d",""), d.get("u",""), f"{d.get('t',0):.3f}"]):
                    item = table.item(r, c)
                    if not item:
                        item = QTableWidgetItem(val)
                        table.setItem(r, c, item)
                        # Make the value column (column 1) editable for Battery 1 (like PCU stat)
                        if idx == 1 and c == 1:
                            item.setFlags(item.flags() | Qt.ItemIsEditable)
                            # Store frame ID and signal name for later use
                            item.setData(Qt.UserRole, (fid, name))
                        # Highlight modified values
                        if is_modified and c == 1 and idx == 1:
                            item.setBackground(Qt.yellow)
                    else:
                        # Only update if not currently being edited by user
                        if not table.isPersistentEditorOpen(item):
                            item.setText(val)
                            # Ensure editable flags and data are set for existing items
                            if idx == 1 and c == 1:
                                item.setFlags(item.flags() | Qt.ItemIsEditable)
                                # Store frame ID and signal name for existing items too
                                item.setData(Qt.UserRole, (fid, name))
                            # Update background color
                            if is_modified and c == 1 and idx == 1:
                                item.setBackground(Qt.yellow)
                            elif c == 1 and idx == 1:
                                item.setBackground(Qt.white)

            if self.first_fill.get(f"BT{idx}", False):
                table.resizeColumnsToContents()
                self.first_fill[f"BT{idx}"] = False

            # Connect item changed signal for Battery 1 (like PCU stat)
            if idx == 1 and not hasattr(table, '_item_changed_connected'):
                table.itemChanged.connect(lambda item: self.on_battery_table_item_changed(item))
                table._item_changed_connected = True

        # PCU tab (merged view)
        if hasattr(self, 'pcu_tab'):
            table = self.pcu_tab
            all_sig = []
            for fid in PCU_FRAMES:
                for name, d in self.signals.get(fid, {}).items():
                    # Use modified value if available, otherwise use live CAN data
                    modified_data = self.modified_signals.get(fid, {}).get(name)
                    if modified_data:
                        display_data = modified_data.copy()
                    else:
                        display_data = d.copy()
                    all_sig.append((name, display_data, fid))  # Include frame ID

            all_sig.sort(key=lambda x: x[0])  # Sort by signal name
            table.setRowCount(len(all_sig))
            for r, (name, d, fid) in enumerate(all_sig):
                # Check if this value is modified
                is_modified = self.modified_signals.get(fid, {}).get(name) is not None

                for c, val in enumerate([name, d.get("d",""), d.get("u",""), f"{d.get('t',0):.3f}"]):
                    item = table.item(r, c)
                    if not item:
                        item = QTableWidgetItem(val)
                        table.setItem(r, c, item)
                        # Make the value column (column 1) editable for PCU frames
                        if c == 1:
                            item.setFlags(item.flags() | Qt.ItemIsEditable)
                            # Store frame ID and signal name for later use
                            item.setData(Qt.UserRole, (fid, name))
                        # Highlight modified values
                        if is_modified and c == 1:
                            item.setBackground(Qt.yellow)
                    else:
                        # Only update if not currently being edited by user
                        if not table.isPersistentEditorOpen(item):
                            item.setText(val)
                            # Update background color
                            if is_modified and c == 1:
                                item.setBackground(Qt.yellow)
                            elif c == 1:
                                item.setBackground(Qt.white)

            if self.first_fill.get("PCU", False):
                table.resizeColumnsToContents()
                self.first_fill["PCU"] = False

            # Connect item changed signal if not already connected
            if not hasattr(table, '_item_changed_connected'):
                table.itemChanged.connect(lambda item: self.on_pcu_table_item_changed(item))
                table._item_changed_connected = True

        # TCU tab (dedicated TCU parameters table)
        if hasattr(self, 'tcu_tab'):
            table = self.tcu_tab
            tcu_frames = [ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME]
            all_sig = []
            for fid in tcu_frames:
                # Add default signals for TCU frames if they don't exist
                if fid not in self.signals:
                    if fid == ID_TCU_ENABLE_FRAME:
                        self.signals[fid] = {
                            "TCU_ENABLE": {"d": "No", "u": "", "v": False, "t": 0}
                        }
                    elif fid == ID_TCU_PRND_FRAME:
                        self.signals[fid] = {
                            "TCU_PRND": {"d": "P", "u": "", "v": 1, "t": 0}
                        }
                    elif fid == ID_TCU_THROTTLE_FRAME:
                        self.signals[fid] = {
                            "TCU_Throttle": {"d": "0.0", "u": "%", "v": 0.0, "t": 0}
                        }
                    elif fid == ID_TCU_TRIM_FRAME:
                        self.signals[fid] = {
                            "TCU_Trim_Plus": {"d": "No", "u": "", "v": False, "t": 0},
                            "TCU_Trim_Minus": {"d": "No", "u": "", "v": False, "t": 0}
                        }
                    elif fid == ID_GPS_SPEED_FRAME:
                        self.signals[fid] = {
                            "GPS_Speed": {"d": "0", "u": "km/h", "v": 0, "t": 0}
                        }

                for name, d in self.signals.get(fid, {}).items():
                    # Use modified value if available, otherwise use live CAN data
                    modified_data = self.modified_signals.get(fid, {}).get(name)
                    if modified_data:
                        display_data = modified_data.copy()
                    else:
                        display_data = d.copy()
                    all_sig.append((name, display_data, fid))  # Include frame ID

            all_sig.sort(key=lambda x: x[0])  # Sort by signal name
            table.setRowCount(len(all_sig))
            for r, (name, d, fid) in enumerate(all_sig):
                # Check if this value is modified
                is_modified = self.modified_signals.get(fid, {}).get(name) is not None

                for c, val in enumerate([name, d.get("d",""), d.get("u",""), f"{d.get('t',0):.3f}"]):
                    item = table.item(r, c)
                    if not item:
                        item = QTableWidgetItem(val)
                        table.setItem(r, c, item)
                        # Make the value column (column 1) editable for TCU frames
                        if c == 1:
                            item.setFlags(item.flags() | Qt.ItemIsEditable)
                            # Store frame ID and signal name for later use
                            item.setData(Qt.UserRole, (fid, name))
                        # Highlight modified values
                        if is_modified and c == 1:
                            item.setBackground(Qt.yellow)
                    else:
                        # Only update if not currently being edited by user
                        if not table.isPersistentEditorOpen(item):
                            item.setText(val)
                            # Update background color
                            if is_modified and c == 1:
                                item.setBackground(Qt.yellow)
                            elif c == 1:
                                item.setBackground(Qt.white)

            if self.first_fill.get("TCU", False):
                table.resizeColumnsToContents()
                self.first_fill["TCU"] = False

            # Connect item changed signal if not already connected
            if not hasattr(table, '_tcu_item_changed_connected'):
                table.itemChanged.connect(lambda item: self.on_tcu_table_item_changed(item))
                table._tcu_item_changed_connected = True

        # HMI tab (combined temperature, voltage, current, drive, and speed/torque frames - TCU frames now have their own table)
        hmi_frames = [ID_TEMP_FRAME, ID_VOLT_FRAME, ID_CURRENT_FRAME, ID_DRIVE_FRAME, ID_SPDTQ_FRAME]
        tcu_frames = [ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME]
        editable_hmi_frames = [ID_DRIVE_FRAME]  # Only Drive frame is editable in main HMI table (TCU frames have their own table)
        table = self.hmi_tab
        # Collect signals with their frame IDs
        all_sig_with_fid = []
        for fid in hmi_frames:
            for name, d in self.signals.get(fid, {}).items():
                all_sig_with_fid.append((name, d, fid))
        all_sig_with_fid.sort(key=lambda x: x[0])  # Sort by signal name
        
        table.setRowCount(len(all_sig_with_fid))
        for r, (name, d, fid) in enumerate(all_sig_with_fid):
            # For editable frames (TCU frames and Drive frame), use modified value if available, otherwise use live CAN data
            is_editable_frame = fid in editable_hmi_frames
            if is_editable_frame:
                modified_data = self.modified_signals.get(fid, {}).get(name)
                if modified_data:
                    display_val = modified_data.get("d", d.get("d",""))
                    is_modified = True
                else:
                    display_val = d.get("d","")
                    is_modified = False
            else:
                display_val = d.get("d","")
                is_modified = False
            
            for c, val in enumerate([name, display_val, d.get("u",""), f"{d.get('t',0):.3f}"]):
                item = table.item(r, c)
                if not item:
                    item = QTableWidgetItem(val)
                    table.setItem(r, c, item)
                else:
                    # Only update if not currently being edited by user
                    if not table.isPersistentEditorOpen(item):
                        item.setText(val)
                
                # Store frame_id in item data for editable frames (always set, even if item exists)
                if is_editable_frame and c == 1:
                    item.setData(Qt.UserRole, fid)
                    # Make the value column (column 1) editable for editable frames
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                    # Update background color
                    if is_modified:
                        item.setBackground(Qt.yellow)
                    else:
                        item.setBackground(Qt.white)
                elif c == 1 and is_modified:
                    # Highlight modified values for non-TCU frames too
                    item.setBackground(Qt.yellow)
        if self.first_fill.get("HMI", False):
            table.resizeColumnsToContents()
            self.first_fill["HMI"] = False
        
        # Connect item changed signal for HMI table (TCU frames)
        if not hasattr(table, '_hmi_item_changed_connected'):
            table.itemChanged.connect(self.on_hmi_table_item_changed)
            table._hmi_item_changed_connected = True

        self.raw_log.clear()
        for l in lines:
            self.raw_log.append(l)

        # Update CAN1 status
        can1_status = "CONNECTED" if self.bus1_connected and self.error_count == 0 else f"NOISE: {self.error_count}"
        self.status_label1.setText(f"CAN1: {can1_status}")
        self.status_label1.setStyleSheet("color:green;" if self.bus1_connected and self.error_count == 0 else "color:orange;" if self.bus1_connected else "color:#d32f2f;")

        # Update CAN2 status
        can2_status = "CONNECTED" if self.bus2_connected and self.error_count == 0 else f"NOISE: {self.error_count}"
        self.status_label2.setText(f"CAN2: {can2_status}")
        self.status_label2.setStyleSheet("color:green;" if self.bus2_connected and self.error_count == 0 else "color:orange;" if self.bus2_connected else "color:#d32f2f;")

    def on_table_item_changed(self, item, frame_id):
        """Handle changes to table items for editable frames"""
        editable_frames = [0x580, 0x600, 0x72E, ID_HV_CHARGER_STATUS, ID_DC12_STAT]
        if item.column() != 1 or frame_id not in editable_frames:
            return

        # Get the signal name from the same row, name column
        name_item = item.tableWidget().item(item.row(), 0)
        if not name_item:
            return

        signal_name = name_item.text()
        new_value = item.text()

        if frame_id == 0x580:
            frame_name = "PDU Stat"
        elif frame_id == 0x600:
            frame_name = "CCU Stat"
        elif frame_id == 0x72E:
            frame_name = "ZCU Stat"
        elif frame_id == ID_HV_CHARGER_STATUS:
            frame_name = "HVC Stat"
        else:
            frame_name = "DC12 Stat"
        print(f"{frame_name} value changed: {signal_name} = {new_value}")

        # Store the modified value
        if frame_id not in self.modified_signals:
            self.modified_signals[frame_id] = {}
        
        # Get original signal data to preserve value type
        original_sig = self.signals.get(frame_id, {}).get(signal_name, {})
        
        # Try to parse the new value to the same type as original
        try:
            # Get original value type
            if "v" in original_sig:
                original_val = original_sig["v"]
                # Try to convert new_value to same type
                if isinstance(original_val, bool):
                    # Handle boolean values
                    parsed_val = new_value.lower() in ["yes", "true", "1", "on"]
                elif isinstance(original_val, float):
                    clean_val = new_value.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").replace("Celcius", "").replace("L/min", "").replace("W", "").strip()
                    parsed_val = float(clean_val) if clean_val else 0.0
                elif isinstance(original_val, int):
                    clean_val = new_value.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").replace("Celcius", "").replace("L/min", "").replace("W", "").strip()
                    parsed_val = int(float(clean_val)) if clean_val else 0
                else:
                    # Keep as string for enum types
                    parsed_val = new_value
            else:
                # Try to infer type from display value
                clean_val = new_value.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").replace("Celcius", "").replace("L/min", "").strip()
                if clean_val.lower() in ["yes", "no", "true", "false"]:
                    parsed_val = clean_val.lower() in ["yes", "true"]
                elif "." in clean_val:
                    parsed_val = float(clean_val)
                else:
                    parsed_val = int(clean_val) if clean_val else 0
        except (ValueError, AttributeError):
            # If parsing fails, try to use original value
            parsed_val = original_sig.get("v", 0)

        self.modified_signals[frame_id][signal_name] = {
            "d": new_value,  # Display value
            "v": parsed_val,  # Parsed value for encoding
            "u": original_sig.get("u", ""),  # Unit
            "t": time.time()
        }

        # Update hex payload for editable frames
        if frame_id == 0x580:
            self.update_pdu_hex_from_table(frame_id)
        elif frame_id == 0x600:
            self.update_ccu_hex_from_table(frame_id)
        elif frame_id == 0x72E:
            self.update_zcu_hex_from_table(frame_id)
        elif frame_id == ID_HV_CHARGER_STATUS:
            self.update_hvc_hex_from_table(frame_id)
        elif frame_id == ID_DC12_STAT:
            self.update_dc12_hex_from_table(frame_id)
        elif frame_id in [ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME]:
            self.update_tcu_hex_from_table(frame_id)

    def on_hmi_table_item_changed(self, item):
        """Handle changes to HMI table items for TCU frames"""
        if item.column() != 1:  # Only handle value column changes
            return

        # Get frame_id from item data
        frame_id = item.data(Qt.UserRole)
        editable_frames = [ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME, ID_DRIVE_FRAME]
        if frame_id is None or frame_id not in editable_frames:
            return

        # Get the signal name from the same row, name column
        name_item = item.tableWidget().item(item.row(), 0)
        if not name_item:
            return

        signal_name = name_item.text()
        new_value = item.text()

        frame_names = {
            ID_TCU_ENABLE_FRAME: "TCU Enable",
            ID_TCU_PRND_FRAME: "TCU PRND",
            ID_TCU_THROTTLE_FRAME: "TCU Throttle",
            ID_TCU_TRIM_FRAME: "TCU Trim",
            ID_GPS_SPEED_FRAME: "GPS Speed",
            ID_DRIVE_FRAME: "Drive Frame"
        }
        frame_name = frame_names.get(frame_id, "TCU")
        print(f"{frame_name} value changed: {signal_name} = {new_value}")

        # Store the modified value
        if frame_id not in self.modified_signals:
            self.modified_signals[frame_id] = {}
        
        # Get original signal data to preserve value type
        original_sig = self.signals.get(frame_id, {}).get(signal_name, {})
        
        # Try to parse the new value to the same type as original
        try:
            # Get original value type
            if "v" in original_sig:
                original_val = original_sig["v"]
                # Try to convert new_value to same type
                if isinstance(original_val, bool):
                    # Handle boolean values
                    parsed_val = new_value.lower() in ["yes", "true", "1", "on"]
                elif isinstance(original_val, float):
                    clean_val = new_value.replace("%", "").replace("km/h", "").replace("mph", "").strip()
                    parsed_val = float(clean_val) if clean_val else 0.0
                elif isinstance(original_val, int):
                    # For PRND, parse the string representation
                    if signal_name == "TCU_PRND":
                        prnd_val = 0
                        if "P" in new_value.upper(): prnd_val |= 0x01
                        if "R" in new_value.upper(): prnd_val |= 0x02
                        if "N" in new_value.upper(): prnd_val |= 0x04
                        if "D" in new_value.upper(): prnd_val |= 0x08
                        if "AUTO" in new_value.upper(): prnd_val |= 0x10
                        parsed_val = prnd_val
                    else:
                        clean_val = new_value.replace("%", "").replace("km/h", "").replace("mph", "").strip()
                        parsed_val = int(float(clean_val)) if clean_val else 0
                else:
                    # Keep as string for enum types
                    parsed_val = new_value
            else:
                # Try to infer type from display value
                clean_val = new_value.replace("%", "").strip()
                if clean_val.lower() in ["yes", "no", "true", "false"]:
                    parsed_val = clean_val.lower() in ["yes", "true"]
                elif "." in clean_val:
                    parsed_val = float(clean_val)
                else:
                    parsed_val = int(clean_val) if clean_val else 0
        except (ValueError, AttributeError):
            # If parsing fails, try to use original value
            parsed_val = original_sig.get("v", 0)

        self.modified_signals[frame_id][signal_name] = {
            "d": new_value,  # Display value
            "v": parsed_val,  # Parsed value for encoding
            "u": original_sig.get("u", ""),  # Unit
            "t": time.time()
        }

        # Update hex payload for TCU frame or Drive frame
        if frame_id == ID_DRIVE_FRAME:
            self.update_drive_hex_from_table(frame_id)
        else:
            self.update_tcu_hex_from_table(frame_id)

    def on_battery_table_item_changed(self, item):
        """Handle changes to Battery 1 table items (like PCU stat)"""
        if item.column() != 1:  # Only handle value column changes
            return

        # Get frame ID and signal name from stored data
        data = item.data(Qt.UserRole)
        if not data:
            return

        frame_id, signal_name = data
        new_value = item.text()

        print(f"Battery 1 value changed: Frame {frame_id:03X}, Signal {signal_name} = {new_value}")

        # Store the modified value
        if frame_id not in self.modified_signals:
            self.modified_signals[frame_id] = {}

        # Get original signal data to preserve value type
        original_sig = self.signals.get(frame_id, {}).get(signal_name, {})

        # Try to parse the new value to the same type as original
        try:
            # Get original value type
            if "v" in original_sig:
                original_val = original_sig["v"]
                # Try to convert new_value to same type
                if isinstance(original_val, bool):
                    # Handle boolean values
                    parsed_val = new_value.lower() in ["yes", "true", "1", "on", "active"]
                elif isinstance(original_val, float):
                    clean_val = new_value.replace("V", "").replace("A", "").replace("°C", "").replace("%", "").replace("Ah", "").strip()
                    parsed_val = float(clean_val) if clean_val else 0.0
                elif isinstance(original_val, int):
                    clean_val = new_value.replace("V", "").replace("A", "").replace("°C", "").replace("%", "").replace("Ah", "").strip()
                    parsed_val = int(float(clean_val)) if clean_val else 0
                else:
                    # Keep as string for enum types
                    parsed_val = new_value
            else:
                # Try to infer type from display value
                clean_val = new_value.replace("V", "").replace("A", "").replace("°C", "").replace("%", "").replace("Ah", "").strip()
                if clean_val.lower() in ["yes", "no", "true", "false", "active", "inactive", "on", "off"]:
                    parsed_val = clean_val.lower() in ["yes", "true", "active", "on"]
                elif "." in clean_val:
                    parsed_val = float(clean_val)
                else:
                    parsed_val = int(clean_val) if clean_val else 0
        except (ValueError, AttributeError):
            # If parsing fails, try to use original value
            parsed_val = original_sig.get("v", 0)

        self.modified_signals[frame_id][signal_name] = {
            "d": new_value,  # Display value
            "v": parsed_val,  # Parsed value for encoding
            "u": original_sig.get("u", ""),  # Unit
            "t": time.time()
        }

        # Update hex payload for Battery frame
        self.update_battery_hex_from_table(frame_id)

    def update_battery_hex_from_table(self, frame_id):
        """Update hex payload for Battery 1 frames when table values change"""
        if frame_id not in BAT1_FRAMES:
            return

        try:
            # Use cantools to encode the message
            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        if sig_name in ["Alarm_1", "Alarm_2", "Alarm_3", "Alarm_4", "Alarm_5", "Alarm_6", "Alarm_7", "Alarm_8",
                                        "Alarm_9", "Alarm_10", "Alarm_11", "Alarm_12", "Alarm_13", "Alarm_14", "Alarm_15", "Alarm_16"]:
                            signal_values[sig_name] = display_val.lower() in ["yes", "true", "1", "on", "active"]
                        else:
                            # Try numeric parsing
                            clean_val = display_val.replace("V", "").replace("A", "").replace("°C", "").replace("%", "").replace("Ah", "").strip()
                            if "." in clean_val:
                                signal_values[sig_name] = float(clean_val)
                            else:
                                signal_values[sig_name] = int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Encode the message using cantools
            encoded_data = self.db.encode_message(frame_id, signal_values)

            # Convert to hex string
            hex_string = encoded_data.hex(' ').upper()

            # Update the hex input field
            input_attr = f"bat_inputs[{frame_id}]"
            if hasattr(self, 'bat_inputs') and frame_id in self.bat_inputs:
                input_field = self.bat_inputs[frame_id]
                input_field.setText(hex_string)
                print(f"Updated Battery 1 hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id} (attribute: {input_attr})")

        except Exception as e:
            print(f"Error updating Battery 1 hex from table: {e}")
            import traceback
            traceback.print_exc()

    def update_ccu_hex_from_table(self, frame_id):
        """Update hex payload for CCU stat when table values change"""
        if frame_id != 0x600:
            return

        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        clean_val = display_val.replace("Celcius", "").replace("L/min", "").replace("A", "").replace("%", "").strip()
                        signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # CCU_COOL_IN: byte 0, scale 1, offset -40
            if "CCU_COOL_IN" in signal_values:
                cool_in = signal_values["CCU_COOL_IN"]
                b[0] = max(0, min(255, int(cool_in + 40)))

            # CCU_COOL_OUT: byte 1, scale 1, offset -40
            if "CCU_COOL_OUT" in signal_values:
                cool_out = signal_values["CCU_COOL_OUT"]
                b[1] = max(0, min(255, int(cool_out + 40)))

            # CCU_GLYCOL_FLOW: byte 2, scale 0.1, offset 0
            if "CCU_GLYCOL_FLOW" in signal_values:
                glycol_flow = signal_values["CCU_GLYCOL_FLOW"]
                b[2] = max(0, min(255, int(glycol_flow / 0.1)))

            # CCU_GLYCOL_THROTTLE: byte 3, scale 1, offset 0
            if "CCU_GLYCOL_THROTTLE" in signal_values:
                glycol_throttle = signal_values["CCU_GLYCOL_THROTTLE"]
                b[3] = max(0, min(255, int(glycol_throttle)))

            # CCU_12V_BAT: byte 4, scale 1, offset 0
            if "CCU_12V_BAT" in signal_values:
                bat_12v = signal_values["CCU_12V_BAT"]
                b[4] = max(0, min(255, int(bat_12v)))

            # CCU_ZCU_CURRENT: byte 5, scale 0.2, offset 0
            if "CCU_ZCU_CURRENT" in signal_values:
                zcu_current = signal_values["CCU_ZCU_CURRENT"]
                b[5] = max(0, min(255, int(zcu_current / 0.2)))

            # CCU_ZCU_TEMP: byte 6, scale 1, offset -40
            if "CCU_ZCU_TEMP" in signal_values:
                zcu_temp = signal_values["CCU_ZCU_TEMP"]
                b[6] = max(0, min(255, int(zcu_temp + 40)))

            # CCU_ERROR_CODES: byte 7, scale 1, offset 0
            if "CCU_ERROR_CODES" in signal_values:
                error_codes = signal_values["CCU_ERROR_CODES"]
                b[7] = max(0, min(255, int(error_codes)))

            # Convert to hex string
            hex_string = ' '.join(f"{x:02X}" for x in b)

            # Update the hex input field
            input_attr = f"input_{frame_id:x}"
            if hasattr(self, input_attr):
                input_field = getattr(self, input_attr)
                input_field.setText(hex_string)
                print(f"Updated CCU hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id} (attribute: {input_attr})")

        except Exception as e:
            print(f"Error updating CCU hex from table: {e}")
            import traceback
            traceback.print_exc()

    def update_zcu_hex_from_table(self, frame_id):
        """Update hex payload for ZCU stat when table values change"""
        if frame_id != 0x72E:
            return

        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        clean_val = display_val.replace("°C", "").replace("V", "").replace("A", "").replace("W", "").strip()
                        signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Current: byte 0, scale 0.2, offset 0
            if "Current" in signal_values:
                current = signal_values["Current"]
                b[0] = max(0, min(255, int(current / 0.2)))

            # Temp_CPU: byte 1, scale 1, offset -40 (decode subtracts 40, so encode adds 40)
            if "Temp_CPU" in signal_values:
                temp_cpu = signal_values["Temp_CPU"]
                b[1] = max(0, min(255, int(temp_cpu + 40)))

            # Temp_Mos: byte 2, scale 1, offset -40 (decode subtracts 40, so encode adds 40)
            if "Temp_Mos" in signal_values:
                temp_mos = signal_values["Temp_Mos"]
                b[2] = max(0, min(255, int(temp_mos + 40)))

            # Voltage: byte 3, scale 0.1, offset 0
            if "Voltage" in signal_values:
                voltage = signal_values["Voltage"]
                b[3] = max(0, min(255, int(voltage / 0.1)))

            # Power: bytes 4-5, 16-bit little-endian, scale 0.1, offset 0
            if "Power" in signal_values:
                power = signal_values["Power"]
                power_raw = max(0, min(65535, int(power / 0.1)))
                b[4] = power_raw & 0xFF
                b[5] = (power_raw >> 8) & 0xFF

            # Status: byte 6, scale 1, offset 0
            if "Status" in signal_values:
                status = signal_values["Status"]
                b[6] = max(0, min(255, int(status)))

            # Convert to hex string
            hex_string = ' '.join(f"{x:02X}" for x in b)

            # Update the hex input field
            input_attr = f"input_{frame_id:x}"
            if hasattr(self, input_attr):
                input_field = getattr(self, input_attr)
                input_field.setText(hex_string)
                print(f"Updated ZCU hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id} (attribute: {input_attr})")

        except Exception as e:
            print(f"Error updating ZCU hex from table: {e}")
            import traceback
            traceback.print_exc()

    def update_hvc_hex_from_table(self, frame_id):
        """Update hex payload for HVC stat when table values change"""
        if frame_id != ID_HV_CHARGER_STATUS:
            return

        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        if sig_name == "HV_Charger_Status":
                            signal_values[sig_name] = display_val.lower().startswith("state_a")
                        else:
                            clean_val = display_val.replace("°C", "").replace("V", "").replace("A", "").strip()
                            signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Voltage: bytes 0-1, big-endian 16-bit, scale 0.1
            if "HV_Charger_Voltage" in signal_values:
                voltage = signal_values["HV_Charger_Voltage"]
                voltage_raw = max(0, min(65535, int(voltage * 10.0)))
                b[0] = (voltage_raw >> 8) & 0xFF
                b[1] = voltage_raw & 0xFF

            # Current: bytes 2-3, big-endian 16-bit, scale 0.1
            if "HV_Charger_Current" in signal_values:
                current = signal_values["HV_Charger_Current"]
                current_raw = max(0, min(65535, int(current * 10.0)))
                b[2] = (current_raw >> 8) & 0xFF
                b[3] = current_raw & 0xFF

            # Status: byte 4, bit 0
            if "HV_Charger_Status" in signal_values:
                status_bit = signal_values["HV_Charger_Status"]
                if status_bit:
                    b[4] |= 0x01
                else:
                    b[4] &= ~0x01

            # Temperature: byte 5, offset -40
            if "HV_Charger_Temp" in signal_values:
                temp = signal_values["HV_Charger_Temp"]
                b[5] = max(0, min(255, int(temp + 40)))

            # Convert to hex string
            hex_string = ' '.join(f"{x:02X}" for x in b)

            # Update the hex input field
            input_attr = f"input_{frame_id:x}"
            if hasattr(self, input_attr):
                input_field = getattr(self, input_attr)
                input_field.setText(hex_string)
                print(f"Updated HVC hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id} (attribute: {input_attr})")

        except Exception as e:
            print(f"Error updating HVC hex from table: {e}")
            import traceback
            traceback.print_exc()

    def update_dc12_hex_from_table(self, frame_id):
        """Update hex payload for DC12 stat when table values change"""
        if frame_id != ID_DC12_STAT:
            return

        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        if sig_name == "Charger_Status":
                            signal_values[sig_name] = display_val.lower().startswith("state_a")
                        else:
                            clean_val = display_val.replace("°C", "").replace("V", "").replace("A", "").strip()
                            signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Status: byte 1
            if "Charger_Status" in signal_values:
                status_bit = signal_values["Charger_Status"]
                b[1] = 1 if status_bit else 0

            # Charging Current: byte 3, scale 0.1
            if "Charging_Current" in signal_values:
                current = signal_values["Charging_Current"]
                b[3] = max(0, min(255, int(current / 0.1)))

            # DC Bus Voltage: byte 5, scale 0.1
            if "DC_Bus_Voltage" in signal_values:
                voltage = signal_values["DC_Bus_Voltage"]
                b[5] = max(0, min(255, int(voltage / 0.1)))

            # Temperature: byte 7, offset -40
            if "Charger_Temperature" in signal_values:
                temp = signal_values["Charger_Temperature"]
                b[7] = max(0, min(255, int(temp + 40)))

            # Convert to hex string
            hex_string = ' '.join(f"{x:02X}" for x in b)

            # Update the hex input field
            input_attr = f"input_{frame_id:x}"
            if hasattr(self, input_attr):
                input_field = getattr(self, input_attr)
                input_field.setText(hex_string)
                print(f"Updated DC12 hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id} (attribute: {input_attr})")

        except Exception as e:
            print(f"Error updating DC12 hex from table: {e}")
            import traceback
            traceback.print_exc()

    def update_tcu_hex_from_table(self, frame_id):
        """Update hex payload for TCU frames when table values change"""
        tcu_frames = [ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME]
        if frame_id not in tcu_frames:
            return

        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        if sig_name in ["TCU_ENABLE", "TCU_Trim_Plus", "TCU_Trim_Minus"]:
                            signal_values[sig_name] = display_val.lower() in ["yes", "true", "1", "on"]
                        elif sig_name == "TCU_PRND":
                            prnd_val = 0
                            if "P" in display_val.upper(): prnd_val |= 0x01
                            if "R" in display_val.upper(): prnd_val |= 0x02
                            if "N" in display_val.upper(): prnd_val |= 0x04
                            if "D" in display_val.upper(): prnd_val |= 0x08
                            if "AUTO" in display_val.upper(): prnd_val |= 0x10
                            signal_values[sig_name] = prnd_val
                        elif sig_name == "GPS_Speed":
                            clean_val = display_val.replace("km/h", "").replace("mph", "").strip()
                            signal_values[sig_name] = int(float(clean_val)) if clean_val else 0
                        else:
                            clean_val = display_val.replace("%", "").strip()
                            signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            if frame_id == ID_TCU_ENABLE_FRAME:
                # TCU Enable: byte 4, bit 2
                if "TCU_ENABLE" in signal_values:
                    enable_bit = signal_values["TCU_ENABLE"]
                    if enable_bit:
                        b[4] |= 0x04
                    else:
                        b[4] &= ~0x04
                # Use default payload for other bytes
                default = bytes.fromhex("00 00 00 00 04 00 00 00".replace(" ", ""))
                for i in range(8):
                    if i != 4:
                        b[i] = default[i]

            elif frame_id == ID_TCU_PRND_FRAME:
                # TCU PRND: byte 0
                if "TCU_PRND" in signal_values:
                    b[0] = signal_values["TCU_PRND"] & 0xFF
                # Use default payload for other bytes
                default = bytes.fromhex("01 00 00 00 00 00 00 00".replace(" ", ""))
                for i in range(1, 8):
                    b[i] = default[i]

            elif frame_id == ID_TCU_THROTTLE_FRAME:
                # TCU Throttle: byte 1, 0-255 for 0-100%
                if "TCU_Throttle" in signal_values:
                    throttle_percent = signal_values["TCU_Throttle"]
                    throttle_raw = max(0, min(255, int((throttle_percent / 100.0) * 255.0)))
                    b[1] = throttle_raw
                # Use default payload for other bytes
                default = bytes.fromhex("00 10 00 00 00 00 00 00".replace(" ", ""))
                for i in range(8):
                    if i != 1:
                        b[i] = default[i]

            elif frame_id == ID_TCU_TRIM_FRAME:
                # TCU Trim: byte 0, bits 0-3
                trim_bits = 0
                if "TCU_Trim_Plus" in signal_values or "TCU_Trim_Minus" in signal_values:
                    if signal_values.get("TCU_Trim_Plus"):
                        trim_bits |= 0x01
                    if signal_values.get("TCU_Trim_Minus"):
                        trim_bits |= 0x02
                b[0] = trim_bits & 0x0F
                # Use default payload for other bytes
                default = bytes.fromhex("00 00 00 00 00 00 00 00".replace(" ", ""))
                for i in range(1, 8):
                    b[i] = default[i]

            elif frame_id == ID_GPS_SPEED_FRAME:
                # GPS Speed: bytes 4-5, 16-bit little-endian
                if "GPS_Speed" in signal_values:
                    gps_speed = signal_values["GPS_Speed"]
                    gps_speed_raw = max(0, min(65535, int(gps_speed)))
                    b[4] = gps_speed_raw & 0xFF
                    b[5] = (gps_speed_raw >> 8) & 0xFF
                # Use default payload for other bytes
                default = bytes.fromhex("00 00 00 00 00 11 00 00".replace(" ", ""))
                for i in range(8):
                    if i not in [4, 5]:
                        b[i] = default[i]

            # Convert to hex string
            hex_string = ' '.join(f"{x:02X}" for x in b)

            # Update the hex input field in TCU emulator
            if hasattr(self, 'tcu_inputs') and frame_id in self.tcu_inputs:
                input_field = self.tcu_inputs[frame_id]
                input_field.setText(hex_string)
                print(f"Updated TCU {frame_id:08X} hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for TCU frame {frame_id:08X}")

        except Exception as e:
            print(f"Error updating TCU hex from table: {e}")
            import traceback
            traceback.print_exc()

    def update_drive_hex_from_table(self, frame_id):
        """Update hex payload for Drive frame when table values change"""
        if frame_id != ID_DRIVE_FRAME:
            return

        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        if sig_name in ["LIMP_MODE", "LIMITED_RANGE", "TCU_VALIDATED", "TCU_REVERSE", "TCU_NEUTRAL", 
                                       "TCU_DRIVE", "TCU_ECO_SPORT", "TCU_DOCK", "TCU_ERROR_KILL",
                                       "PCU_VALIDATED", "PCU_REVERSE", "PCU_NEUTRAL", "PCU_DRIVE", "PCU_ECO_SPORT",
                                       "PCU_DOCK", "PCU_ENABLED", "PCU_ERROR_KILL"]:
                            signal_values[sig_name] = display_val.lower() in ["yes", "true", "1", "on"]
                        else:
                            clean_val = display_val.replace("%", "").strip()
                            signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Throttle: byte 0
            if "Throttle" in signal_values:
                throttle = signal_values["Throttle"]
                b[0] = max(0, min(255, int(throttle)))

            # Status: byte 1, bit field
            status = 0
            if signal_values.get("LIMP_MODE"):
                status |= 0x01
            if signal_values.get("LIMITED_RANGE"):
                status |= 0x02
            b[1] = status

            # TCU RND: byte 2, bit field
            tcu_rnd = 0
            if signal_values.get("TCU_VALIDATED"):
                tcu_rnd |= 0x01
            if signal_values.get("TCU_REVERSE"):
                tcu_rnd |= 0x02
            if signal_values.get("TCU_NEUTRAL"):
                tcu_rnd |= 0x04
            if signal_values.get("TCU_DRIVE"):
                tcu_rnd |= 0x08
            if signal_values.get("TCU_ECO_SPORT"):
                tcu_rnd |= 0x10
            if signal_values.get("TCU_DOCK"):
                tcu_rnd |= 0x20
            # TCU_ENABLED removed - duplicate of TCU_ENABLE
            if signal_values.get("TCU_ERROR_KILL"):
                tcu_rnd |= 0x80
            b[2] = tcu_rnd

            # PCU RND: byte 3, bit field
            pcu_rnd = 0
            if signal_values.get("PCU_VALIDATED"):
                pcu_rnd |= 0x01
            if signal_values.get("PCU_REVERSE"):
                pcu_rnd |= 0x02
            if signal_values.get("PCU_NEUTRAL"):
                pcu_rnd |= 0x04
            if signal_values.get("PCU_DRIVE"):
                pcu_rnd |= 0x08
            if signal_values.get("PCU_ECO_SPORT"):
                pcu_rnd |= 0x10
            if signal_values.get("PCU_DOCK"):
                pcu_rnd |= 0x20
            if signal_values.get("PCU_ENABLED"):
                pcu_rnd |= 0x40
            if signal_values.get("PCU_ERROR_KILL"):
                pcu_rnd |= 0x80
            b[3] = pcu_rnd

            # Trim: byte 4
            if "Trim" in signal_values:
                trim = signal_values["Trim"]
                b[4] = max(0, min(255, int(trim)))

            # Range: byte 5
            if "Range" in signal_values:
                range_val = signal_values["Range"]
                b[5] = max(0, min(255, int(range_val)))

            # Power: byte 6
            if "Power" in signal_values:
                power = signal_values["Power"]
                b[6] = max(0, min(255, int(power)))

            # SOC: byte 7
            if "SOC" in signal_values:
                soc = signal_values["SOC"]
                b[7] = max(0, min(255, int(soc)))

            # Convert to hex string
            hex_string = ' '.join(f"{x:02X}" for x in b)

            # Update the hex display label
            if frame_id in self.hex_labels:
                hex_label = self.hex_labels[frame_id]
                hex_label.setText(f"0x{frame_id:08X}: {hex_string}")
                print(f"Updated Drive frame hex payload: {hex_string}")
            else:
                print(f"Warning: No hex label found for Drive frame {frame_id:08X}")

        except Exception as e:
            print(f"Error updating Drive hex from table: {e}")
            import traceback
            traceback.print_exc()

    def update_pdu_hex_from_table(self, frame_id):
        """Update hex payload for PDU stat when table values change"""
        if frame_id != 0x580:
            return

        try:
            # Get DBC frame ID for encoding
            dbc_id = self.HEX_TO_DBC_ID.get(frame_id)
            if dbc_id is None:
                print(f"No DBC ID found for frame {frame_id}")
                return

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                # Check if this signal has been modified
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    # Use modified parsed value
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    # Use live value
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Fallback: try to parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        clean_val = display_val.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").strip()
                        if "." in clean_val:
                            signal_values[sig_name] = float(clean_val)
                        else:
                            signal_values[sig_name] = int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Encode the message using cantools
            encoded_data = self.db.encode_message(dbc_id, signal_values)
            
            # Convert to hex string
            hex_string = encoded_data.hex(' ').upper()

            # Update the hex input field
            input_attr = f"input_{frame_id:x}"
            if hasattr(self, input_attr):
                input_field = getattr(self, input_attr)
                input_field.setText(hex_string)
                print(f"Updated PDU hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id} (attribute: {input_attr})")

        except Exception as e:
            print(f"Error updating PDU hex from table: {e}")
            import traceback
            traceback.print_exc()

    def on_pcu_table_item_changed(self, item):
        """Handle changes to PCU table items"""
        if item.column() != 1:  # Only handle value column changes
            return

        # Get frame ID and signal name from stored data
        data = item.data(Qt.UserRole)
        if not data:
            return

        frame_id, signal_name = data
        new_value = item.text()

        print(f"PCU value changed: Frame {frame_id:03X}, Signal {signal_name} = {new_value}")

        # Store the modified value
        if frame_id not in self.modified_signals:
            self.modified_signals[frame_id] = {}
        
        # Get original signal data to preserve value type
        original_sig = self.signals.get(frame_id, {}).get(signal_name, {})
        
        # Try to parse the new value to the same type as original
        try:
            # Get original value type
            if "v" in original_sig:
                original_val = original_sig["v"]
                # Try to convert new_value to same type
                if isinstance(original_val, bool):
                    # Handle boolean values
                    parsed_val = new_value.lower() in ["yes", "true", "1", "on", "active"]
                elif isinstance(original_val, float):
                    clean_val = new_value.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").replace("RPM", "").replace("Nm", "").replace("h", "").replace("L/m", "").strip()
                    parsed_val = float(clean_val) if clean_val else 0.0
                elif isinstance(original_val, int):
                    clean_val = new_value.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").replace("RPM", "").replace("Nm", "").replace("h", "").replace("L/m", "").strip()
                    parsed_val = int(float(clean_val)) if clean_val else 0
                else:
                    # Keep as string for enum types
                    parsed_val = new_value
            else:
                # Try to infer type from display value
                clean_val = new_value.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").replace("RPM", "").replace("Nm", "").replace("h", "").replace("L/m", "").strip()
                if clean_val.lower() in ["yes", "no", "true", "false", "active", "inactive", "on", "off"]:
                    parsed_val = clean_val.lower() in ["yes", "true", "active", "on"]
                elif "." in clean_val:
                    parsed_val = float(clean_val)
                else:
                    parsed_val = int(clean_val) if clean_val else 0
        except (ValueError, AttributeError):
            # If parsing fails, try to use original value
            parsed_val = original_sig.get("v", 0)

        self.modified_signals[frame_id][signal_name] = {
            "d": new_value,  # Display value
            "v": parsed_val,  # Parsed value for encoding
            "u": original_sig.get("u", ""),  # Unit
            "t": time.time()
        }

        # Update hex payload for PCU frame
        self.update_pcu_hex_from_table(frame_id)

    def on_tcu_table_item_changed(self, item):
        """Handle changes to TCU table items"""
        if item.column() != 1:  # Only handle value column changes
            return

        # Get frame ID and signal name from stored data
        data = item.data(Qt.UserRole)
        if not data:
            return

        frame_id, signal_name = data
        new_value = item.text()

        print(f"TCU value changed: Frame {frame_id:08X}, Signal {signal_name} = {new_value}")

        # Store the modified value
        if frame_id not in self.modified_signals:
            self.modified_signals[frame_id] = {}

        # Get original signal data to preserve value type
        original_sig = self.signals.get(frame_id, {}).get(signal_name, {})

        # Try to parse the new value to the same type as original
        try:
            # Get original value type
            if "v" in original_sig:
                original_val = original_sig["v"]
                # Try to convert new_value to same type
                if isinstance(original_val, bool):
                    # Handle boolean values
                    parsed_val = new_value.lower() in ["yes", "true", "1", "on"]
                elif isinstance(original_val, float):
                    clean_val = new_value.replace("%", "").replace("km/h", "").replace("mph", "").strip()
                    parsed_val = float(clean_val) if clean_val else 0.0
                elif isinstance(original_val, int):
                    # For PRND, parse the string representation
                    if signal_name == "TCU_PRND":
                        prnd_val = 0
                        if "P" in new_value.upper(): prnd_val |= 0x01
                        if "R" in new_value.upper(): prnd_val |= 0x02
                        if "N" in new_value.upper(): prnd_val |= 0x04
                        if "D" in new_value.upper(): prnd_val |= 0x08
                        if "AUTO" in new_value.upper(): prnd_val |= 0x10
                        parsed_val = prnd_val
                    else:
                        clean_val = new_value.replace("%", "").replace("km/h", "").replace("mph", "").strip()
                        parsed_val = int(float(clean_val)) if clean_val else 0
                else:
                    # Keep as string for enum types
                    parsed_val = new_value
            else:
                # Try to infer type from display value
                clean_val = new_value.replace("%", "").strip()
                if clean_val.lower() in ["yes", "no", "true", "false"]:
                    parsed_val = clean_val.lower() in ["yes", "true"]
                elif "." in clean_val:
                    parsed_val = float(clean_val)
                else:
                    parsed_val = int(clean_val) if clean_val else 0
        except (ValueError, AttributeError):
            # If parsing fails, try to use original value
            parsed_val = original_sig.get("v", 0)

        self.modified_signals[frame_id][signal_name] = {
            "d": new_value,  # Display value
            "v": parsed_val,  # Parsed value for encoding
            "u": original_sig.get("u", ""),  # Unit
            "t": time.time()
        }

        # Update hex payload for TCU frame
        self.update_tcu_hex_from_table(frame_id)

    def update_pcu_hex_from_table(self, frame_id):
        """Update hex payload for PCU frames when table values change"""
        if frame_id not in PCU_FRAMES:
            return

        try:
            # For PCU frames, use custom encoding since we use custom decoding
            # This ensures signal names match between decode and encode
            if frame_id == 0x720:
                # Motor Status frame - use custom encoding
                self.update_pcu_motor_hex(frame_id)
            elif frame_id == 0x722:
                # PCU Cooling frame - use custom encoding
                self.update_pcu_cooling_hex(frame_id)
            elif frame_id == 0x724:
                # PCU Power frame - use custom encoding
                self.update_pcu_power_hex(frame_id)
            else:
                # Try DBC encoding for other frames
                dbc_id = self.HEX_TO_DBC_ID.get(frame_id)
                if dbc_id is not None:
                    # Use DBC encoding
                    # Collect all signal values (use modified if available, otherwise use live)
                    signal_values = {}
                    for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                        # Check if this signal has been modified
                        modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                        if modified and "v" in modified:
                            # Use modified parsed value
                            signal_values[sig_name] = modified["v"]
                        elif "v" in sig_data:
                            # Use live value
                            signal_values[sig_name] = sig_data["v"]
                        else:
                            # Fallback: try to parse display value
                            display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                            try:
                                clean_val = display_val.replace("°C", "").replace("V", "").replace("A", "").replace("%", "").replace("RPM", "").replace("Nm", "").replace("h", "").replace("L/m", "").strip()
                                if "." in clean_val:
                                    signal_values[sig_name] = float(clean_val)
                                else:
                                    signal_values[sig_name] = int(clean_val) if clean_val else 0
                            except (ValueError, AttributeError):
                                signal_values[sig_name] = 0

                    # Encode the message using cantools
                    try:
                        encoded_data = self.db.encode_message(dbc_id, signal_values)
                        
                        # Convert to hex string
                        hex_string = encoded_data.hex(' ').upper()

                        # Update the hex input field
                        # Check if it's in pcu_inputs dictionary
                        if hasattr(self, 'pcu_inputs') and frame_id in self.pcu_inputs:
                            # Don't update PCU input fields when PCU emulation is active
                            if not EMULATOR_PCU_ENABLED:
                                input_field = self.pcu_inputs[frame_id]
                                input_field.setText(hex_string)
                                print(f"Updated PCU frame {frame_id:03X} hex payload: {hex_string}")
                        else:
                            # Fallback: try attribute name (for other frames like PDU)
                            input_attr = f"input_{frame_id:x}"
                            if hasattr(self, input_attr):
                                input_field = getattr(self, input_attr)
                                input_field.setText(hex_string)
                                print(f"Updated frame {frame_id:03X} hex payload: {hex_string}")
                            else:
                                print(f"Warning: No input field found for frame {frame_id:03X}")
                    except Exception as encode_error:
                        print(f"Error encoding DBC message for frame {frame_id:03X} (DBC ID {dbc_id}): {encode_error}")
                        print(f"Signal values: {signal_values}")
                        import traceback
                        traceback.print_exc()

        except Exception as e:
            print(f"Error updating PCU hex from table for frame {frame_id:03X}: {e}")
            import traceback
            traceback.print_exc()

    def update_pcu_motor_hex(self, frame_id):
        """Custom encoder for PCU Motor Status frame (0x720)"""
        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        if sig_name in ["MOTOR_FAILURE", "INV_FAILURE", "POWER_FAILURE", "INTERNAL_FAILURE",
                                       "COOLING_FAILURE", "CANBUS_FAILURE", "FLASH_FAILURE", "TEMP_FAILURE",
                                       "JAKE_STATE", "BOOST_STATE", "TRIM_STATE", "IGN_STATE"]:
                            signal_values[sig_name] = display_val.lower() in ["yes", "true", "1", "on", "active"]
                        elif sig_name == "PRND":
                            # PRND is stored as raw byte value
                            signal_values[sig_name] = sig_data.get("v", 0)
                        else:
                            clean_val = display_val.replace("RPM", "").replace("Nm", "").replace("h", "").strip()
                            signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Motor Hours: bytes 0-1, 16-bit little-endian unsigned
            if "MOTOR_HOURS" in signal_values:
                motor_hours = max(0, min(65535, int(signal_values["MOTOR_HOURS"])))
                b[0] = motor_hours & 0xFF
                b[1] = (motor_hours >> 8) & 0xFF

            # Motor Torque: bytes 2-3, 16-bit little-endian signed, 1 bit per 0.1Nm
            if "MOTOR_TORQUE" in signal_values:
                torque = signal_values["MOTOR_TORQUE"]
                torque_raw = max(-32768, min(32767, int(torque / 0.1)))
                # Convert to unsigned 16-bit
                torque_unsigned = (torque_raw + 0x8000) % 0x10000
                b[2] = torque_unsigned & 0xFF
                b[3] = (torque_unsigned >> 8) & 0xFF

            # Motor Speed: bytes 4-5, 16-bit little-endian unsigned
            if "MOTOR_SPEED" in signal_values:
                motor_speed = max(0, min(65535, int(signal_values["MOTOR_SPEED"])))
                b[4] = motor_speed & 0xFF
                b[5] = (motor_speed >> 8) & 0xFF

            # PRND: byte 6, bit field
            if "PRND" in signal_values:
                prnd = signal_values["PRND"]
                # If PRND is a string, try to parse it, otherwise use the raw value
                if isinstance(prnd, str):
                    prnd_val = 0
                    if "P" in prnd.upper():
                        prnd_val |= 0x01
                    if "R" in prnd.upper():
                        prnd_val |= 0x02
                    if "N" in prnd.upper():
                        prnd_val |= 0x04
                    if "D" in prnd.upper():
                        prnd_val |= 0x08
                    b[6] = prnd_val
                else:
                    b[6] = prnd & 0xFF
            else:
                # Build PRND from individual states
                prnd = 0
                if signal_values.get("JAKE_STATE"):
                    prnd |= 0x10
                if signal_values.get("BOOST_STATE"):
                    prnd |= 0x20
                if signal_values.get("TRIM_STATE"):
                    prnd |= 0x40
                if signal_values.get("IGN_STATE"):
                    prnd |= 0x80
                b[6] = prnd

            # Failure: byte 7, bit field
            failure = 0
            if signal_values.get("MOTOR_FAILURE"):
                failure |= 0x01
            if signal_values.get("INV_FAILURE"):
                failure |= 0x02
            if signal_values.get("POWER_FAILURE"):
                failure |= 0x04
            if signal_values.get("INTERNAL_FAILURE"):
                failure |= 0x08
            if signal_values.get("COOLING_FAILURE"):
                failure |= 0x10
            if signal_values.get("CANBUS_FAILURE"):
                failure |= 0x20
            if signal_values.get("FLASH_FAILURE"):
                failure |= 0x40
            if signal_values.get("TEMP_FAILURE"):
                failure |= 0x80
            b[7] = failure

            # Convert to hex string
            hex_string = bytes(b).hex(' ').upper()

            # Update the hex input field
            if hasattr(self, 'pcu_inputs') and frame_id in self.pcu_inputs:
                # Don't update PCU input fields when PCU emulation is active
                if not EMULATOR_PCU_ENABLED:
                    input_field = self.pcu_inputs[frame_id]
                    input_field.setText(hex_string)
                    print(f"Updated PCU Motor frame {frame_id:03X} hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id:03X}")

        except Exception as e:
            print(f"Error encoding PCU Motor frame {frame_id:03X}: {e}")
            import traceback
            traceback.print_exc()

    def update_pcu_cooling_hex(self, frame_id):
        """Custom encoder for PCU Cooling frame (0x722)"""
        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        clean_val = display_val.replace("°C", "").replace("L/m", "").strip()
                        signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Cool_MT: byte 0, 8-bit with -40°C offset
            if "COOL_MT" in signal_values:
                cool_mt = signal_values["COOL_MT"]
                b[0] = max(0, min(255, int(cool_mt + 40)))

            # Cool_BT: byte 1, 8-bit with -40°C offset
            if "COOL_BT" in signal_values:
                cool_bt = signal_values["COOL_BT"]
                b[1] = max(0, min(255, int(cool_bt + 40)))

            # FlowSea: byte 2, 8-bit unsigned
            if "FLOW_SEA" in signal_values:
                flow_sea = signal_values["FLOW_SEA"]
                b[2] = max(0, min(255, int(flow_sea)))

            # FlowGlycol: byte 3, 8-bit unsigned, 0.1 L/m per bit
            if "FLOW_GLYCOL" in signal_values:
                flow_glycol = signal_values["FLOW_GLYCOL"]
                b[3] = max(0, min(255, int(flow_glycol / 0.1)))

            # Stator: byte 4, 8-bit with -40°C offset
            if "STATOR_TEMP" in signal_values:
                stator_temp = signal_values["STATOR_TEMP"]
                b[4] = max(0, min(255, int(stator_temp + 40)))

            # Inv: byte 5, 8-bit with -40°C offset
            if "INV_TEMP" in signal_values:
                inv_temp = signal_values["INV_TEMP"]
                b[5] = max(0, min(255, int(inv_temp + 40)))

            # Rotor: byte 6, 8-bit with -40°C offset
            if "ROTOR_TEMP" in signal_values:
                rotor_temp = signal_values["ROTOR_TEMP"]
                b[6] = max(0, min(255, int(rotor_temp + 40)))

            # Battery: byte 7, 8-bit with -40°C offset
            if "BATTERY_TEMP" in signal_values:
                battery_temp = signal_values["BATTERY_TEMP"]
                b[7] = max(0, min(255, int(battery_temp + 40)))

            # Convert to hex string
            hex_string = bytes(b).hex(' ').upper()

            # Update the hex input field
            if hasattr(self, 'pcu_inputs') and frame_id in self.pcu_inputs:
                # Don't update PCU input fields when PCU emulation is active
                if not EMULATOR_PCU_ENABLED:
                    input_field = self.pcu_inputs[frame_id]
                    input_field.setText(hex_string)
                    print(f"Updated PCU Cooling frame {frame_id:03X} hex payload: {hex_string}")
            else:
                print(f"Warning: No input field found for frame {frame_id:03X}")

        except Exception as e:
            print(f"Error encoding PCU Cooling frame {frame_id:03X}: {e}")
            import traceback
            traceback.print_exc()

    def update_pcu_power_hex(self, frame_id):
        """Custom encoder for PCU Power frame (0x724)"""
        try:
            b = [0] * 8

            # Collect all signal values (use modified if available, otherwise use live)
            signal_values = {}
            for sig_name, sig_data in self.signals.get(frame_id, {}).items():
                modified = self.modified_signals.get(frame_id, {}).get(sig_name)
                if modified and "v" in modified:
                    signal_values[sig_name] = modified["v"]
                elif "v" in sig_data:
                    signal_values[sig_name] = sig_data["v"]
                else:
                    # Parse display value
                    display_val = modified.get("d", "") if modified else sig_data.get("d", "")
                    try:
                        if sig_name in ["AUXILIARY_POWER", "MAINTENANCE_MODE", "ECO_MODE", "SPORT_MODE", 
                                       "REGEN_ENABLED", "INVERTER_DETECTED", "HV_DETECTED", "START_STOP"]:
                            signal_values[sig_name] = display_val.lower() in ["yes", "true", "1", "on"]
                        else:
                            clean_val = display_val.replace("V", "").replace("A", "").strip()
                            signal_values[sig_name] = float(clean_val) if "." in clean_val else int(clean_val) if clean_val else 0
                    except (ValueError, AttributeError):
                        signal_values[sig_name] = 0

            # Mode: byte 0, bit field
            mode = 0
            if signal_values.get("AUXILIARY_POWER"):
                mode |= 0x01
            if signal_values.get("MAINTENANCE_MODE"):
                mode |= 0x02
            if signal_values.get("ECO_MODE"):
                mode |= 0x04
            if signal_values.get("SPORT_MODE"):
                mode |= 0x08
            if signal_values.get("REGEN_ENABLED"):
                mode |= 0x10
            if signal_values.get("INVERTER_DETECTED"):
                mode |= 0x20
            if signal_values.get("HV_DETECTED"):
                mode |= 0x40
            if signal_values.get("START_STOP"):
                mode |= 0x80
            b[0] = mode

            # BattServ: byte 1, 1 bit per 0.1V
            if "BATT_SERV" in signal_values:
                battserv = signal_values["BATT_SERV"]
                b[1] = max(0, min(255, int(battserv / 0.1)))

            # Pump: byte 2, 1 bit per 0.1A
            if "PUMP_CURRENT" in signal_values:
                pump = signal_values["PUMP_CURRENT"]
                b[2] = max(0, min(255, int(pump / 0.1)))

            # Trim: byte 3, 1 bit per 1A
            if "TRIM_CURRENT" in signal_values:
                trim = signal_values["TRIM_CURRENT"]
                b[3] = max(0, min(255, int(trim)))

            # Inverter voltage: bytes 4-5, 16-bit little-endian, 1 bit per 0.1V
            if "INVERTER_VOLTAGE" in signal_values:
                inv_voltage = signal_values["INVERTER_VOLTAGE"]
                inv_voltage_raw = max(0, min(65535, int(inv_voltage / 0.1)))
                b[4] = inv_voltage_raw & 0xFF
                b[5] = (inv_voltage_raw >> 8) & 0xFF

            # Inverter current: bytes 6-7, 16-bit little-endian signed, 1 bit per 0.1A
            if "INVERTER_CURRENT" in signal_values:
                inv_current = signal_values["INVERTER_CURRENT"]
                inv_current_raw = max(-32768, min(32767, int(inv_current / 0.1)))
                # Convert to unsigned 16-bit
                inv_current_unsigned = (inv_current_raw + 0x8000) % 0x10000
                b[6] = inv_current_unsigned & 0xFF
                b[7] = (inv_current_unsigned >> 8) & 0xFF

            # Convert to hex string
            hex_string = bytes(b).hex(' ').upper()

            # Update the hex input field
            # Check if it's in pcu_inputs dictionary
            if hasattr(self, 'pcu_inputs') and frame_id in self.pcu_inputs:
                # Don't update PCU input fields when PCU emulation is active
                if not EMULATOR_PCU_ENABLED:
                    input_field = self.pcu_inputs[frame_id]
                    input_field.setText(hex_string)
                    print(f"Updated PCU Power frame {frame_id:03X} hex payload: {hex_string}")
            else:
                # Fallback: try attribute name
                input_attr = f"input_{frame_id:x}"
                if hasattr(self, input_attr):
                    input_field = getattr(self, input_attr)
                    input_field.setText(hex_string)
                    print(f"Updated PCU Power frame {frame_id:03X} hex payload: {hex_string}")
                else:
                    print(f"Warning: No input field found for frame {frame_id:03X}")

        except Exception as e:
            print(f"Error encoding PCU Power frame {frame_id:03X}: {e}")
            import traceback
            traceback.print_exc()

    def clear_modified_values(self):
        """Clear all user-modified table values for PDU stat, PCU, CCU stat, ZCU stat, HVC stat, and DC12 stat"""
        if 0x580 in self.modified_signals:
            self.modified_signals[0x580] = {}
            print("Cleared all modified PDU stat values")
        
        # Clear PCU modified values
        for fid in PCU_FRAMES:
            if fid in self.modified_signals:
                self.modified_signals[fid] = {}
        print("Cleared all modified PCU stat values")
        
        # Clear CCU stat modified values
        if 0x600 in self.modified_signals:
            self.modified_signals[0x600] = {}
            print("Cleared all modified CCU stat values")
        
        # Clear ZCU stat modified values
        if 0x72E in self.modified_signals:
            self.modified_signals[0x72E] = {}
            print("Cleared all modified ZCU stat values")
        
        # Clear HVC stat modified values
        if ID_HV_CHARGER_STATUS in self.modified_signals:
            self.modified_signals[ID_HV_CHARGER_STATUS] = {}
            print("Cleared all modified HVC stat values")
        
        # Clear DC12 stat modified values
        if ID_DC12_STAT in self.modified_signals:
            self.modified_signals[ID_DC12_STAT] = {}
            print("Cleared all modified DC12 stat values")
        
        # Clear TCU modified values
        tcu_frames = [ID_TCU_ENABLE_FRAME, ID_TCU_PRND_FRAME, ID_TCU_THROTTLE_FRAME, ID_TCU_TRIM_FRAME, ID_GPS_SPEED_FRAME]
        for fid in tcu_frames:
            if fid in self.modified_signals:
                self.modified_signals[fid] = {}
        print("Cleared all modified TCU values")
        
        # Force GUI update
        self.update_gui()

    def toggle_can1(self):
        if self.bus1_connected:
            self.disconnect_can1()
        else:
            self.connect_can1()

    def toggle_can2(self):
        if self.bus2_connected:
            self.disconnect_can2()
        else:
            self.connect_can2()

    def test_can2(self):
        """Send a test message on CAN2 and see if we receive it back"""
        if not self.bus2_connected:
            print("CAN2 not connected")
            return

        try:
            # Send a test message
            test_msg = can.Message(arbitration_id=0x123, data=[0xAA, 0xBB, 0xCC, 0xDD], is_extended_id=False)
            self.bus2.send(test_msg)
            print("Sent test message on CAN2: 0x123 AA BB CC DD")

            # Try to receive it back (if loopback is enabled or there's another device)
            try:
                recv_msg = self.bus2.recv(timeout=1.0)
                if recv_msg:
                    print(f"Received message on CAN2: 0x{recv_msg.arbitration_id:03X} {recv_msg.data.hex()}")
                else:
                    print("No message received on CAN2 (normal if no loopback or other devices)")
            except:
                print("No message received on CAN2")

        except Exception as e:
            print(f"CAN2 test failed: {e}")

    def connect_can1(self):
        try:
            self.bus1 = can.interface.Bus(channel=CHANNEL1, bustype=BUSTYPE1, bitrate=BITRATE)
            self.bus1_connected = True
            self.connect_btn1.setText("Disconnect CAN1")
            self.connect_btn1.setStyleSheet("background:#c62828;color:white;")
            self.status_label1.setText("CAN1: CONNECTED")
            self.status_label1.setStyleSheet("color:green;font-weight:bold;")
            threading.Thread(target=self.can_listener1, daemon=True).start()
        except Exception as e:
            self.status_label1.setText(f"CAN1: ERROR: {str(e)[:30]}")
            print("CAN1 Connect failed:", e)

    def connect_can2(self):
        try:
            print(f"Connecting to CAN2: channel={CHANNEL2}, bustype={BUSTYPE2}")  # Debug print
            self.bus2 = can.interface.Bus(channel=CHANNEL2, bustype=BUSTYPE2, bitrate=BITRATE)
            self.bus2_connected = True
            self.connect_btn2.setText("Disconnect CAN2")
            self.connect_btn2.setStyleSheet("background:#c62828;color:white;")
            self.status_label2.setText("CAN2: CONNECTED")
            self.status_label2.setStyleSheet("color:green;font-weight:bold;")
            print("CAN2 connected successfully, starting listener thread")  # Debug print
            threading.Thread(target=self.can_listener2, daemon=True).start()
        except Exception as e:
            # Try alternative channels
            alt_channels = ['PCAN_USBBUS3', 'PCAN_USBBUS4', 'PCAN_USBBUS5', 'PCAN_USBBUS6']
            for alt_channel in alt_channels:
                try:
                    print(f"Trying alternative CAN2 channel: {alt_channel}")
                    self.bus2 = can.interface.Bus(channel=alt_channel, bustype=BUSTYPE2, bitrate=BITRATE)
                    self.bus2_connected = True
                    self.connect_btn2.setText("Disconnect CAN2")
                    self.connect_btn2.setStyleSheet("background:#c62828;color:white;")
                    self.status_label2.setText(f"CAN2: CONNECTED ({alt_channel})")
                    self.status_label2.setStyleSheet("color:green;font-weight:bold;")
                    print(f"CAN2 connected successfully to {alt_channel}, starting listener thread")
                    threading.Thread(target=self.can_listener2, daemon=True).start()
                    return
                except:
                    continue

            self.status_label2.setText(f"CAN2: ERROR: {str(e)[:30]}")
            print("CAN2 Connect failed:", e)
            print("Available PCAN channels to try manually:")
            available = list_pcan_channels()
            if available:
                print("Available:", available)
            else:
                print("No PCAN channels detected")

    def disconnect_can1(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = False
        for cid in EMULATOR_STATES:
            EMULATOR_STATES[cid] = False
        self.stop_all_timers()
        if self.bus1:
            try:
                self.bus1.shutdown()
            except:
                pass
        self.bus1 = None
        self.bus1_connected = False
        self.connect_btn1.setText("Connect CAN1")
        self.connect_btn1.setStyleSheet("")
        self.status_label1.setText("CAN1: DISCONNECTED")
        self.status_label1.setStyleSheet("color:#d32f2f;")
        # Only clear data if both CANs are disconnected
        if not self.bus2_connected:
            with self.lock:
                for d in self.signals.values():
                    d.clear()
                self.raw_log_lines.clear()

    def disconnect_can2(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = False
        for cid in EMULATOR_STATES:
            EMULATOR_STATES[cid] = False
        self.stop_all_timers()
        if self.bus2:
            try:
                self.bus2.shutdown()
            except:
                pass
        self.bus2 = None
        self.bus2_connected = False
        self.connect_btn2.setText("Connect CAN2")
        self.connect_btn2.setStyleSheet("")
        self.status_label2.setText("CAN2: DISCONNECTED")
        self.status_label2.setStyleSheet("color:#d32f2f;")
        # Only clear data if both CANs are disconnected
        if not self.bus1_connected:
            with self.lock:
                for d in self.signals.values():
                    d.clear()
                self.raw_log_lines.clear()

    def closeEvent(self, event):
        if self.bus1_connected:
            self.disconnect_can1()
        if self.bus2_connected:
            self.disconnect_can2()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CANMonitor()
    win.showMaximized()
    sys.exit(app.exec_())