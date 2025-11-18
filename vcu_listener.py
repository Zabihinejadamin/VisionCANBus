# vcu_gui_ULTIMATE_ALL_EMULATORS.py
# THE FINAL VERSION – EVERY KEY FRAME HAS ITS OWN EMULATOR IN THE SAME TAB

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
CHANNEL = 'PCAN_USBBUS1'
BUSTYPE = 'pcan'

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

BAT1_FRAMES = [0x400, 0x401, 0x403, 0x405, 0x406]
BAT2_FRAMES = [0x420, 0x421, 0x423, 0x425, 0x426]
BAT3_FRAMES = [0x440, 0x441, 0x443, 0x445, 0x446]
BAT1_EMULATOR_IDS = [0x400, 0x401, 0x403]

# Emulator states
EMULATOR_107_ENABLED = EMULATOR_607_ENABLED = EMULATOR_4F0_ENABLED = False
EMULATOR_580_ENABLED = EMULATOR_600_ENABLED = EMULATOR_720_ENABLED = False
EMULATOR_722_ENABLED = EMULATOR_724_ENABLED = EMULATOR_BAT1_ENABLED = False
EMULATOR_INTERVAL = 0.1


class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN TOOL – ULTIMATE EDITION (ALL EMULATORS)")
        self.resize(2800, 1400)

        self.bus = None
        self.bus_connected = False
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

        all_ids = [ID_727, ID_587, ID_107, ID_607, ID_CMD_BMS, ID_PDU_STATUS, ID_HMI_STATUS,
                   ID_PCU_COOL, ID_PCU_MOTOR, ID_PCU_POWER, ID_CCU_STATUS, ID_ZCU_PUMP]
        all_ids += BAT1_FRAMES + BAT2_FRAMES + BAT3_FRAMES
        self.signals = {id_: {} for id_ in set(all_ids)}
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

        top = QHBoxLayout()
        self.connect_btn = QPushButton("CONNECT CAN")
        self.connect_btn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;padding:10px;")
        self.connect_btn.clicked.connect(self.toggle_can)
        top.addWidget(self.connect_btn)
        self.status_label = QLabel("DISCONNECTED")
        self.status_label.setStyleSheet("color:red;font-weight:bold;")
        top.addWidget(self.status_label)
        top.addStretch()
        layout.addLayout(top)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { padding: 10px 18px; font-weight: bold; }")
        layout.addWidget(self.tabs)

        self.create_tab(ID_727, "0x727 – PCU", "VCU to PCU", ["Signal","Value","Unit","TS"])
        self.create_tab(ID_587, "0x587 – PDU", "VCU to PDU", ["Relay","Command","Raw","TS"])

        # === NEW EMULATORS ===
        self.create_pump_tab_with_emulator()      # 0x107
        self.create_ccu_cmd_tab_with_emulator()   # 0x607
        self.create_bms_cmd_tab_with_emulator()   # 0x4F0
        self.create_pdu_tab_with_emulator()       # 0x580
        self.create_tab(ID_HMI_STATUS, "0x740 – HMI", "HMI VCU Status", ["Signal","Value","Unit","TS"])
        self.create_cooling_tab_with_emulator()   # 0x722
        self.create_motor_tab_with_emulator()     # 0x720
        self.create_power_tab_with_emulator()     # 0x724
        self.create_ccu_tab_with_emulator()       # 0x600

        self.create_battery_tab_with_emulator("Battery 1", 1, BAT1_FRAMES)
        self.create_battery_tab("Battery 2", 2, BAT2_FRAMES)
        self.create_battery_tab("Battery 3", 3, BAT3_FRAMES)
        self.create_tab(ID_ZCU_PUMP, "0x72E – ZCU Pump", "ZCU Pump Status", ["Signal","Value","Unit","TS"])

        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(QLabel("Raw CAN Log (last 8 frames):"))
        layout.addWidget(self.raw_log)

    def create_tab(self, fid, name, title, headers):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(f"<h2>{title}</h2>"))
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        self.tables[fid] = table
        l.addWidget(table)
        self.tabs.addTab(w, name)

    # === 0x107 – PUMP ===
    def create_pump_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x107 – Pump Command + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_107] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Pump Emulator (0x107)</b>"))
        ctrl = QHBoxLayout(); self.pump_btn = QPushButton("OFF → Click to Enable")
        self.pump_btn.setStyleSheet("background:#795548;color:white;font-weight:bold;")
        self.pump_btn.clicked.connect(lambda: self.toggle_emulator(ID_107, self.pump_btn, self.pump_input))
        ctrl.addWidget(self.pump_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.pump_input = QLineEdit("01 32 00 00 00 00 00 00")
        self.pump_input.setFixedWidth(340); hex_l.addWidget(self.pump_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_107, self.pump_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l)
        presets = QHBoxLayout(); presets.addWidget(QLabel("Presets:"))
        for name, payload in [("OFF","00 00 00 00 00 00 00 00"), ("30%","01 1E 00 00 00 00 00 00"), ("100%","01 64 00 00 00 00 00 00")]:
            b = QPushButton(name); b.clicked.connect(lambda _, p=payload: self.pump_input.setText(p)); presets.addWidget(b)
        el.addLayout(presets); el.addStretch(); splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x107 – Pump")

    # === 0x607 – CCU/ZCU CMD ===
    def create_ccu_cmd_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x607 – CCU/ZCU Command + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_607] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>CCU/ZCU Cmd Emulator (0x607)</b>"))
        ctrl = QHBoxLayout(); self.ccu_cmd_btn = QPushButton("OFF → Click to Enable")
        self.ccu_cmd_btn.setStyleSheet("background:#607D8B;color:white;font-weight:bold;")
        self.ccu_cmd_btn.clicked.connect(lambda: self.toggle_emulator(ID_607, self.ccu_cmd_btn, self.ccu_cmd_input))
        ctrl.addWidget(self.ccu_cmd_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.ccu_cmd_input = QLineEdit("01 00 00 00 00 00 00 00")
        self.ccu_cmd_input.setFixedWidth(340); hex_l.addWidget(self.ccu_cmd_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_607, self.ccu_cmd_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l); el.addStretch()
        splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x607 – CCU/ZCU")

    # === 0x4F0 – BMS CMD ===
    def create_bms_cmd_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x4F0 – VCU to BMS Cmd + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_CMD_BMS] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>BMS Command Emulator (0x4F0)</b>"))
        ctrl = QHBoxLayout(); self.bms_cmd_btn = QPushButton("OFF → Click to Enable")
        self.bms_cmd_btn.setStyleSheet("background:#E91E63;color:white;font-weight:bold;")
        self.bms_cmd_btn.clicked.connect(lambda: self.toggle_emulator(ID_CMD_BMS, self.bms_cmd_btn, self.bms_cmd_input))
        ctrl.addWidget(self.bms_cmd_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.bms_cmd_input = QLineEdit("01 00 00 00 00 00 00 00")
        self.bms_cmd_input.setFixedWidth(340); hex_l.addWidget(self.bms_cmd_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_CMD_BMS, self.bms_cmd_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l)
        presets = QHBoxLayout(); presets.addWidget(QLabel("Presets:"))
        for name, payload in [("Idle","00 00 00 00 00 00 00 00"), ("Precharge","02 00 00 00 00 00 00 00"), ("Close Contactors","01 00 00 00 00 00 00 00")]:
            b = QPushButton(name); b.clicked.connect(lambda _, p=payload: self.bms_cmd_input.setText(p)); presets.addWidget(b)
        el.addLayout(presets); el.addStretch(); splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x4F0 – VCU Cmd")

    # === 0x580 – PDU RELAYS ===
    def create_pdu_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x580 – PDU Relay Status + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_PDU_STATUS] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>PDU Emulator (0x580)</b>"))
        ctrl = QHBoxLayout(); self.pdu_btn = QPushButton("OFF → Click to Enable")
        self.pdu_btn.setStyleSheet("background:#FF9800;color:white;font-weight:bold;")
        self.pdu_btn.clicked.connect(lambda: self.toggle_emulator(ID_PDU_STATUS, self.pdu_btn, self.pdu_input))
        ctrl.addWidget(self.pdu_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.pdu_input = QLineEdit("FF FF FF FF FF FF FF FF")
        self.pdu_input.setFixedWidth(340); hex_l.addWidget(self.pdu_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_PDU_STATUS, self.pdu_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l)
        presets = QHBoxLayout(); presets.addWidget(QLabel("Presets:"))
        for name, payload in [("All OFF","00 00 00 00 00 00 00 00"), ("Main+Pre","03 00 00 00 00 00 00 00"), ("All ON","FF FF FF FF FF FF FF FF")]:
            b = QPushButton(name); b.clicked.connect(lambda _, p=payload: self.pdu_input.setText(p)); presets.addWidget(b)
        el.addLayout(presets); el.addStretch(); splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x580 – PDU Relays")

    # === 0x722 – COOLING ===
    def create_cooling_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x722 – PCU Cooling + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_PCU_COOL] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Cooling Emulator (0x722)</b>"))
        ctrl = QHBoxLayout(); self.cool_btn = QPushButton("OFF → Click to Enable")
        self.cool_btn.setStyleSheet("background:#00BCD4;color:white;font-weight:bold;")
        self.cool_btn.clicked.connect(lambda: self.toggle_emulator(ID_PCU_COOL, self.cool_btn, self.cool_input))
        ctrl.addWidget(self.cool_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.cool_input = QLineEdit("00 00 00 00 00 00 00 00")
        self.cool_input.setFixedWidth(340); hex_l.addWidget(self.cool_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_PCU_COOL, self.cool_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l); el.addStretch()
        splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x722 – Cooling")

    # === 0x720 – MOTOR ===
    def create_motor_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x720 – Motor Status + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_PCU_MOTOR] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Motor Emulator (0x720)</b>"))
        ctrl = QHBoxLayout(); self.motor_btn = QPushButton("OFF → Click to Enable")
        self.motor_btn.setStyleSheet("background:#FF5722;color:white;font-weight:bold;")
        self.motor_btn.clicked.connect(lambda: self.toggle_emulator(ID_PCU_MOTOR, self.motor_btn, self.motor_input))
        ctrl.addWidget(self.motor_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.motor_input = QLineEdit("00 00 00 00 00 00 00 00")
        self.motor_input.setFixedWidth(340); hex_l.addWidget(self.motor_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_PCU_MOTOR, self.motor_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l); el.addStretch()
        splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x720 – Motor")

    # === 0x724 – POWER ===
    def create_power_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x724 – PCU Power + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_PCU_POWER] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Power Emulator (0x724)</b>"))
        ctrl = QHBoxLayout(); self.power_btn = QPushButton("OFF → Click to Enable")
        self.power_btn.setStyleSheet("background:#2196F3;color:white;font-weight:bold;")
        self.power_btn.clicked.connect(lambda: self.toggle_emulator(ID_PCU_POWER, self.power_btn, self.power_input))
        ctrl.addWidget(self.power_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.power_input = QLineEdit("00 00 00 00 00 00 00 00")
        self.power_input.setFixedWidth(340); hex_l.addWidget(self.power_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_PCU_POWER, self.power_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l); el.addStretch()
        splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x724 – Power")

    # === 0x600 – CCU STATUS ===
    def create_ccu_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x600 – CCU Status + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.tables[ID_CCU_STATUS] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>CCU Emulator (0x600)</b>"))
        ctrl = QHBoxLayout(); self.ccu_btn = QPushButton("OFF → Click to Enable")
        self.ccu_btn.setStyleSheet("background:#9C27B0;color:white;font-weight:bold;")
        self.ccu_btn.clicked.connect(lambda: self.toggle_emulator(ID_CCU_STATUS, self.ccu_btn, self.ccu_input))
        ctrl.addWidget(self.ccu_btn); ctrl.addStretch(); el.addLayout(ctrl)
        hex_l = QHBoxLayout(); hex_l.addWidget(QLabel("Payload:")); self.ccu_input = QLineEdit("00 00 21 00 52 AE 56 00")
        self.ccu_input.setFixedWidth(340); hex_l.addWidget(self.ccu_input)
        send_once = QPushButton("SEND ONCE"); send_once.clicked.connect(lambda: self.send_raw(ID_CCU_STATUS, self.ccu_input.text()))
        hex_l.addWidget(send_once); el.addLayout(hex_l); el.addStretch()
        splitter.addWidget(emu); splitter.setSizes([900,400])
        self.tabs.addTab(w, "0x600 – CCU")

    # === BATTERY 1 – PER-ID EMULATOR ===
    def create_battery_tab_with_emulator(self, name, idx, frame_ids):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.addWidget(QLabel(f"<h2>{name} – Live Data + Independent Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.battery_tabs[idx] = table; splitter.addWidget(table)
        emu = QWidget(); el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Battery 1 Emulator – Independent Payloads</b>"))
        self.bat_inputs = {}
        default_payloads = {0x400: "01 00 64 00 C8 00 C8 00", 0x401: "02 0A 14 1E 28 32 3C 46", 0x403: "03 00 50 00 3C 00 00 00"}
        for can_id in BAT1_EMULATOR_IDS:
            box = QGroupBox(f"0x{can_id:03X}")
            box_layout = QVBoxLayout(box)
            payload_l = QHBoxLayout(); payload_l.addWidget(QLabel("Payload:"))
            line = QLineEdit(default_payloads.get(can_id, "00 00 00 00 00 00 00 00"))
            line.setFixedWidth(340); self.bat_inputs[can_id] = line; payload_l.addWidget(line)
            send_btn = QPushButton("SEND ONCE"); send_btn.clicked.connect(lambda checked, cid=can_id: self.send_bat_single(cid))
            payload_l.addWidget(send_btn); box_layout.addLayout(payload_l); el.addWidget(box)
        ctrl = QHBoxLayout(); self.bat_btn = QPushButton("OFF → Click to Enable Cycle")
        self.bat_btn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;")
        self.bat_btn.clicked.connect(self.toggle_bat1); ctrl.addWidget(self.bat_btn); ctrl.addStretch(); el.addLayout(ctrl)
        presets = QHBoxLayout(); presets.addWidget(QLabel("Quick SOC (0x400): "))
        for soc, payload in [("100%","01 00 64 00 C8 00 C8 00"), ("75%","01 00 4B 00 B0 00 B0 00"), ("50%","01 00 32 00 90 00 90 00"), ("25%","01 00 19 00 60 00 60 00"), ("0%","01 00 00 00 40 00 40 00")]:
            b = QPushButton(soc); b.clicked.connect(lambda _, p=payload: self.bat_inputs[0x400].setText(p)); presets.addWidget(b)
        el.addLayout(presets); el.addStretch(); splitter.addWidget(emu); splitter.setSizes([1000,500])
        self.tabs.addTab(w, name)

    def create_battery_tab(self, name, idx, frame_ids):
        w = QWidget(); l = QVBoxLayout(w); l.addWidget(QLabel(f"<h2>{name}</h2>"))
        table = QTableWidget(); table.setColumnCount(4); table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        self.battery_tabs[idx] = table; l.addWidget(table); self.tabs.addTab(w, name)

    # === DBC MAPPING ===
    HEX_TO_DBC_ID = {
        0x727: 1831, 0x587: 1415, 0x107: 263, 0x607: 1543, 0x4F0: 1264,
        0x580: 1408, 0x740: 1856, 0x722: 1826, 0x720: 1824, 0x724: 1828,
        0x600: 1536, 0x72E: 1838,
        0x400: 1024, 0x401: 1025, 0x403: 1027, 0x405: 1029, 0x406: 1030,
        0x420: 1056, 0x421: 1057, 0x423: 1059, 0x425: 1061, 0x426: 1062,
        0x440: 1088, 0x441: 1089, 0x443: 1091, 0x445: 1093, 0x446: 1094,
    }

    # === EMULATOR CONTROL ===
    def toggle_emulator(self, can_id, btn, input_field):
        global EMULATOR_107_ENABLED, EMULATOR_607_ENABLED, EMULATOR_4F0_ENABLED
        global EMULATOR_580_ENABLED, EMULATOR_600_ENABLED, EMULATOR_720_ENABLED, EMULATOR_722_ENABLED, EMULATOR_724_ENABLED

        if can_id == 0x107:   state = EMULATOR_107_ENABLED = not EMULATOR_107_ENABLED
        elif can_id == 0x607: state = EMULATOR_607_ENABLED = not EMULATOR_607_ENABLED
        elif can_id == 0x4F0: state = EMULATOR_4F0_ENABLED = not EMULATOR_4F0_ENABLED
        elif can_id == 0x580: state = EMULATOR_580_ENABLED = not EMULATOR_580_ENABLED
        elif can_id == 0x600: state = EMULATOR_600_ENABLED = not EMULATOR_600_ENABLED
        elif can_id == 0x720: state = EMULATOR_720_ENABLED = not EMULATOR_720_ENABLED
        elif can_id == 0x722: state = EMULATOR_722_ENABLED = not EMULATOR_722_ENABLED
        elif can_id == 0x724: state = EMULATOR_724_ENABLED = not EMULATOR_724_ENABLED
        else: return

        if state:
            btn.setText(f"ON – {hex(can_id)} @ 10Hz")
            btn.setStyleSheet("background:#E91E63;color:white;font-weight:bold;")
            self.start_timer(lambda: self.send_raw(can_id, input_field.text()))
        else:
            btn.setText("OFF → Click to Enable")
            color_map = {0x107:"#795548", 0x607:"#607D8B", 0x4F0:"#E91E63", 0x580:"#FF9800", 0x600:"#9C27B0", 0x720:"#FF5722", 0x722:"#00BCD4", 0x724:"#2196F3"}
            btn.setStyleSheet(f"background:{color_map.get(can_id,'#555')};color:white;font-weight:bold;")

    def toggle_bat1(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = not EMULATOR_BAT1_ENABLED
        if EMULATOR_BAT1_ENABLED:
            self.bat_btn.setText("ON – Cycling 400→401→403")
            self.bat_btn.setStyleSheet("background:#66BB6A;color:white;font-weight:bold;")
            self.bat1_cycle_index = 0
            self.start_timer(self.send_bat_cycle)
        else:
            self.bat_btn.setText("OFF → Click to Enable Cycle")
            self.bat_btn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;")

    def start_timer(self, callback):
        if hasattr(self, "emu_timer"): self.emu_timer.stop()
        self.emu_timer = QTimer()
        self.emu_timer.timeout.connect(callback)
        self.emu_timer.start(int(EMULATOR_INTERVAL * 1000))

    def send_bat_single(self, can_id):
        self.send_raw(can_id, self.bat_inputs[can_id].text())

    def send_bat_cycle(self):
        can_id = BAT1_EMULATOR_IDS[self.bat1_cycle_index]
        self.send_raw(can_id, self.bat_inputs[can_id].text())
        self.bat1_cycle_index = (self.bat1_cycle_index + 1) % 3

    def send_raw(self, can_id, text):
        if not self.bus_connected: return
        clean = ''.join(c for c in text.upper() if c in '0123456789ABCDEF ')
        clean = clean.replace(" ", "")
        if len(clean) != 16:
            print("Invalid payload (must be 8 bytes)")
            return
        try:
            data = bytes.fromhex(clean)
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            self.bus.send(msg)
            print(f"SENT → {hex(can_id)} | {data.hex(' ').upper()}")
            self.process_message_for_gui(msg)
        except Exception as e:
            print("Send failed:", e)

    def process_message_for_gui(self, msg):
        with self.lock:
            self.raw_log_lines.append(f"0x{msg.arbitration_id:03X} | {msg.data.hex(' ').upper()}")
            if len(self.raw_log_lines) > 200: self.raw_log_lines.pop(0)
        dbc_id = self.HEX_TO_DBC_ID.get(msg.arbitration_id)
        if not dbc_id: return
        try:
            decoded = self.db.decode_message(dbc_id, msg.data)
            unit_map = {s.name: s.unit or "" for s in self.db.get_message_by_frame_id(dbc_id).signals}
            with self.lock:
                self.signals[msg.arbitration_id].update({
                    name: {"v": value, "d": f"{value:.2f}" if isinstance(value,float) else str(value),
                           "u": unit_map.get(name,""), "t": getattr(msg,'timestamp',time.time())}
                    for name, value in decoded.items()
                })
        except: pass

    def can_listener(self):
        while self.bus_connected:
            try:
                msg = self.bus.recv(timeout=0.1)
                if msg and not getattr(msg, 'is_error_frame', False):
                    self.process_message_for_gui(msg)
                elif msg and getattr(msg, 'is_error_frame', False):
                    with self.lock: self.error_count += 1
            except: pass

    def update_gui(self):
        with self.lock:
            lines = self.raw_log_lines[-8:]
        for fid, table in self.tables.items():
            items = list(self.signals.get(fid, {}).items())
            table.setRowCount(len(items))
            for r, (name, d) in enumerate(items):
                table.setItem(r, 0, QTableWidgetItem(name))
                table.setItem(r, 1, QTableWidgetItem(d.get("d","")))
                table.setItem(r, 2, QTableWidgetItem(d.get("u","")))
                table.setItem(r, 3, QTableWidgetItem(f"{d.get('t',0):.3f}"))
            if self.first_fill.get(fid, False):
                table.resizeColumnsToContents()
                self.first_fill[fid] = False

        for idx, frames in [(1,BAT1_FRAMES),(2,BAT2_FRAMES),(3,BAT3_FRAMES)]:
            table = self.battery_tabs[idx]
            all_sig = [item for fid in frames for item in self.signals.get(fid, {}).items()]
            table.setRowCount(len(all_sig))
            for r, (name, d) in enumerate(all_sig):
                table.setItem(r, 0, QTableWidgetItem(name))
                table.setItem(r, 1, QTableWidgetItem(d.get("d","")))
                table.setItem(r, 2, QTableWidgetItem(d.get("u","")))
                table.setItem(r, 3, QTableWidgetItem(f"{d.get('t',0):.3f}"))
            if self.first_fill.get(f"BT{idx}", False):
                table.resizeColumnsToContents()
                self.first_fill[f"BT{idx}"] = False

        self.raw_log.clear()
        for l in lines: self.raw_log.append(l)
        self.status_label.setText("CONNECTED" if not self.error_count else f"NOISE: {self.error_count}")
        self.status_label.setStyleSheet("color:green;font-weight:bold;" if not self.error_count else "color:orange;font-weight:bold;")

    def toggle_can(self):
        if self.bus_connected: self.disconnect_can()
        else: self.connect_can()

    def connect_can(self):
        try:
            self.bus = can.interface.Bus(channel=CHANNEL, bustype=BUSTYPE, bitrate=BITRATE)
            self.bus_connected = True
            self.connect_btn.setText("DISCONNECT CAN")
            self.connect_btn.setStyleSheet("background:#f44336;color:white;font-weight:bold;")
            self.status_label.setText("CONNECTED")
            self.status_label.setStyleSheet("color:green;font-weight:bold;")
            threading.Thread(target=self.can_listener, daemon=True).start()
        except Exception as e:
            print("Connect error:", e)

    def disconnect_can(self):
        globals_dict = globals()
        for name in [k for k in globals_dict.keys() if k.startswith("EMULATOR_") and k.endswith("_ENABLED")]:
            globals_dict[name] = False
        if hasattr(self, "emu_timer"): self.emu_timer.stop()
        if self.bus:
            try: self.bus.shutdown()
            except: pass
            self.bus = None
        self.bus_connected = False
        self.connect_btn.setText("CONNECT CAN")
        self.connect_btn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;")
        self.status_label.setText("DISCONNECTED")
        with self.lock:
            for d in self.signals.values(): d.clear()
            self.raw_log_lines.clear()

    def closeEvent(self, event):
        self.disconnect_can()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CANMonitor()
    win.show()
    sys.exit(app.exec_())