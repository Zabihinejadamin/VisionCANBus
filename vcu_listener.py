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

# ALL BATTERY FRAMES (now complete)
BAT1_FRAMES = [0x400, 0x401, 0x402, 0x403, 0x404, 0x405, 0x406]
BAT2_FRAMES = [0x420, 0x421, 0x422, 0x423, 0x424, 0x425, 0x426]
BAT3_FRAMES = [0x440, 0x441, 0x442, 0x443, 0x444, 0x445, 0x446]

# Emulator uses all frames for Battery 1
BAT1_EMULATOR_IDS = [0x400, 0x401, 0x402, 0x403, 0x404, 0x405, 0x406]

EMULATOR_STATES = {k: False for k in [
    0x727,0x587,0x107,0x607,0x4F0,0x580,0x600,0x720,0x722,0x724,0x72E,
    ID_HV_CHARGER_STATUS, ID_HV_CHARGER_CMD, ID_DC12_COMM, ID_DC12_STAT,
    ID_TEMP_FRAME
]}

# Refresh intervals for different frame types (in seconds)
EMULATOR_INTERVALS = {
    0x600: 0.05,  # 50ms for CCU status
    0x720: 0.05,  # 50ms for motor status
    # Battery frames and temperature frame use 100ms (0.1 seconds)
    0x400: 0.1, 0x401: 0.1, 0x402: 0.1, 0x403: 0.1, 0x404: 0.1, 0x405: 0.1, 0x406: 0.1,
    0x420: 0.1, 0x421: 0.1, 0x422: 0.1, 0x423: 0.1, 0x424: 0.1, 0x425: 0.1, 0x426: 0.1,
    0x440: 0.1, 0x441: 0.1, 0x442: 0.1, 0x443: 0.1, 0x444: 0.1, 0x445: 0.1, 0x446: 0.1,
    ID_TEMP_FRAME: 0.1,  # 100ms for temperature frame (0x111)
}

# Default interval for other frames (100ms)
EMULATOR_INTERVAL_DEFAULT = 0.1

EMULATOR_BAT1_ENABLED = False


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
                   ID_TEMP_FRAME]
        all_ids += BAT1_FRAMES + BAT2_FRAMES + BAT3_FRAMES

        self.signals = {id_: {} for id_ in set(all_ids)}
        self.current_hex = {id_: "00 00 00 00 00 00 00 00" for id_ in set(all_ids)}
        self.hex_labels = {}
        self.first_fill = {k: True for k in self.signals}
        self.first_fill.update({f"BT{i}": True for i in [1,2,3]})

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
        self.create_emulator_tab(0x580, "0x580 – PDU Stat", "PDU Relays", "99 00 00 99 04 00 00 F3",
                                 [("All OFF","00 00 00 00 00 00 00 00"), ("Main+Pre","03 00 00 00 00 00 00 00"), ("All ON","FF FF FF FF FF FF FF FF")])
        self.create_emulator_tab(0x600, "0x600 – CCU", "CCU Stat", "3A 39 50 54 8D 00 3C 00")
        self.create_emulator_tab(0x720, "0x720 – Motor", "Motor Stat", "07 00 00 00 00 00 84 00")
        self.create_emulator_tab(0x722, "0x722 – Cooling", "PCU Cooling", "39 38 00 3C 39 3B 28 39")
        self.create_emulator_tab(0x724, "0x724 – Power", "PCU Power", "E4 8A 28 1D E5 1A 3A 5E")
        self.create_emulator_tab(0x72E, "0x72E – ZCU Pump", "ZCU Pump Stat", "28 00 00 00 00 3C 08 00",
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
        self.create_tab(ID_TEMP_FRAME, "0x111 – Temp Frame", "Temperature Frame (HMI)", ["Signal","Value","Unit","TS"])
        self.create_battery_tab_with_emulator("Battery 1", 1, BAT1_FRAMES)
        self.create_battery_tab("Battery 2", 2, BAT2_FRAMES)
        self.create_battery_tab("Battery 3", 3, BAT3_FRAMES)

        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        self.raw_log.setStyleSheet("font-family: Consolas; font-size: 10px;")
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
                signals[name] = {"d": f"0x{b[i]:02X}", "u": ""}

        elif frame_id in (0x404, 0x424, 0x444):
            # Byte 0
            signals["Isol_Board_Powered"] = {"d": "Yes" if b[0] & 0x01 else "No", "u": ""}
            # Byte 1
            signals["Open_Sw_Error"] = {"d": "Yes" if b[1] & 0x01 else "No", "u": ""}
            signals["No_Closing_Sw_Error"] = {"d": "Yes" if (b[1] & 0x02) else "No", "u": ""}
            # Byte 2-3: V_Cell_Avg
            v_avg = (b[2] << 8) | b[3]
            signals["V_Cell_Avg"] = {"d": f"{v_avg}", "u": "mV"}
            # Byte 4: Contactor states
            aux = b[4] & 0x0F
            main = (b[4] >> 4) & 0x0F
            signals["Contactor_4_Aux"] = {"d": "Closed" if aux & 0x01 else "Open", "u": ""}
            signals["Contactor_3_Aux"] = {"d": "Closed" if aux & 0x02 else "Open", "u": ""}
            signals["Contactor_2_Aux"] = {"d": "Closed" if aux & 0x04 else "Open", "u": ""}
            signals["Contactor_1_Aux"] = {"d": "Closed" if aux & 0x08 else "Open", "u": ""}
            signals["Contactor_4_State"] = {"d": "Closed" if main & 0x01 else "Open", "u": ""}
            signals["Contactor_3_State_Precharge"] = {"d": "Closed" if main & 0x02 else "Open", "u": ""}
            signals["Contactor_2_State_Neg"] = {"d": "Closed" if main & 0x04 else "Open", "u": ""}
            signals["Contactor_1_State_Pos"] = {"d": "Closed" if main & 0x08 else "Open", "u": ""}
            # Byte 5
            signals["Is_Balancing_Active"] = {"d": "Yes" if b[5] & 0x01 else "No", "u": ""}

        elif frame_id in (0x405, 0x425, 0x445):
            nb_cycles = (b[3] << 24) | (b[2] << 16) | (b[1] << 8) | b[0]
            ah_discharged = (b[7] << 24) | (b[6] << 16) | (b[5] << 8) | b[4]
            signals["Nb_Cycles"] = {"d": str(nb_cycles), "u": ""}
            signals["Ah_Discharged"] = {"d": f"{ah_discharged / 10.0:.1f}", "u": "Ah"}
            signals["Remaining_Time_Before_Opening"] = {"d": str(b[7]), "u": "s"}

        elif frame_id in (0x406, 0x426, 0x446):  # Alarms 9-16
            alarms = ["Alarm_9","Alarm_10","Alarm_11","Alarm_12","Alarm_13","Alarm_14","Alarm_15","Alarm_16"]
            for i, name in enumerate(alarms):
                signals[name] = {"d": f"0x{b[i]:02X}", "u": ""}

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
        status = "State_A (Charging)" if (b[4] & 0x01) else "State_C (Ready/Finished)"
        temp = b[5] - 40
        return {
            "HV_Charger_Voltage": {"d": f"{voltage:.1f}", "u": "V"},
            "HV_Charger_Current": {"d": f"{current:.1f}", "u": "A"},
            "HV_Charger_Status": {"d": status, "u": ""},
            "HV_Charger_Temp": {"d": f"{temp:+.0f}", "u": "°C"},
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
        status = "State_A" if b[1] == 1 else "State_C"
        current = b[3] * 0.1  # Charging current in A, 1 bit per 0.1A
        voltage = b[5] * 0.1  # DC bus voltage in V, 1 bit per 0.1V
        temperature = b[7] - 40  # Temperature in °C, offset by -40
        return {
            "Charger_Status": {"d": status, "u": ""},
            "Charging_Current": {"d": f"{current:.1f}", "u": "A"},
            "DC_Bus_Voltage": {"d": f"{voltage:.1f}", "u": "V"},
            "Charger_Temperature": {"d": f"{temperature:+}", "u": "°C"},
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

    HEX_TO_DBC_ID = {
        0x727:1831, 0x587:1415, 0x107:263, 0x607:1543, 0x4F0:1264, 0x580:1408, 0x740:1856,
        0x722:1826, 0x720:1824, 0x724:1828, 0x600:1536, 0x72E:1838,
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
        elif fid == ID_TEMP_FRAME:
            decoded_signals = self.decode_temperature_frame(msg.data)
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
                    name: {"d": val["d"], "u": val["u"], "t": time.time()}
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
                        self.process_message_for_gui(msg, can_bus=2)
            except:
                pass

    def update_gui(self):
        with self.lock:
            lines = self.raw_log_lines[-8:]

        # Regular tables
        for fid, table in self.tables.items():
            items = list(self.signals.get(fid, {}).items())
            table.setRowCount(len(items))
            for r, (name, d) in enumerate(items):
                for c, val in enumerate([name, d.get("d",""), d.get("u",""), f"{d.get('t',0):.3f}"]):
                    item = table.item(r, c)
                    if not item:
                        table.setItem(r, c, QTableWidgetItem(val))
                    else:
                        item.setText(val)
            if self.first_fill.get(fid, False):
                table.resizeColumnsToContents()
                self.first_fill[fid] = False

        # Battery tabs (merged view)
        for idx, frames in [(1,BAT1_FRAMES),(2,BAT2_FRAMES),(3,BAT3_FRAMES)]:
            table = self.battery_tabs[idx]
            all_sig = [item for fid in frames for item in self.signals.get(fid, {}).items()]
            table.setRowCount(len(all_sig))
            for r, (name, d) in enumerate(all_sig):
                for c, val in enumerate([name, d.get("d",""), d.get("u",""), f"{d.get('t',0):.3f}"]):
                    item = table.item(r, c)
                    if not item:
                        table.setItem(r, c, QTableWidgetItem(val))
                    else:
                        item.setText(val)
            if self.first_fill.get(f"BT{idx}", False):
                table.resizeColumnsToContents()
                self.first_fill[f"BT{idx}"] = False

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
            self.bus2 = can.interface.Bus(channel=CHANNEL2, bustype=BUSTYPE2, bitrate=BITRATE)
            self.bus2_connected = True
            self.connect_btn2.setText("Disconnect CAN2")
            self.connect_btn2.setStyleSheet("background:#c62828;color:white;")
            self.status_label2.setText("CAN2: CONNECTED")
            self.status_label2.setStyleSheet("color:green;font-weight:bold;")
            threading.Thread(target=self.can_listener2, daemon=True).start()
        except Exception as e:
            self.status_label2.setText(f"CAN2: ERROR: {str(e)[:30]}")
            print("CAN2 Connect failed:", e)

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
    win.show()
    sys.exit(app.exec_())