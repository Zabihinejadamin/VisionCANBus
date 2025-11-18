# vcu_gui_FINAL_WITH_PER_ID_BATTERY_EMULATOR.py
# FULLY WORKING – INDEPENDENT PAYLOADS FOR 0x400, 0x401, 0x403

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

EMULATOR_600_ENABLED = False
EMULATOR_720_ENABLED = False
EMULATOR_BAT1_ENABLED = False
EMULATOR_INTERVAL = 0.1


class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor – FINAL + Per-ID Battery Emulator")
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
        self.tabs.setStyleSheet("QTabBar::tab { padding: 8px 16px; } QTabBar::tab:selected { background: #e0e0e0; }")
        layout.addWidget(self.tabs)

        self.create_tab(ID_727, "0x727 – PCU", "VCU to PCU", ["Signal","Value","Unit","TS"])
        self.create_tab(ID_587, "0x587 – PDU", "VCU to PDU", ["Relay","Command","Raw","TS"])
        self.create_tab(ID_107, "0x107 – Pump", "Pump Command", ["Signal","Value","Unit","TS"])
        self.create_tab(ID_607, "0x607 – CCU/ZCU", "CCU/ZCU Command", ["Command","Status","TS"])
        self.create_tab(ID_CMD_BMS, "0x4F0 – VCU Cmd", "VCU to BMS", ["Signal","State","TS"])
        self.create_tab(ID_PDU_STATUS, "0x580 – PDU Relays", "PDU Relay Status", ["Relay","CMD","STATUS","TS"])
        self.create_tab(ID_HMI_STATUS, "0x740 – HMI", "HMI VCU Status", ["Signal","Value","Unit","TS"])
        self.create_tab(ID_PCU_COOL, "0x722 – Cooling", "PCU Cooling", ["Signal","Value","Unit","TS"])
        self.create_tab(ID_PCU_POWER, "0x724 – Power", "PCU Power", ["Signal","Value","Unit","TS"])

        self.create_motor_tab_with_emulator()
        self.create_ccu_tab_with_emulator()
        self.create_battery_tab_with_emulator("Battery 1", 1, BAT1_FRAMES)  # ← NEW PER-ID EMULATOR
        self.create_battery_tab("Battery 2", 2, BAT2_FRAMES)
        self.create_battery_tab("Battery 3", 3, BAT3_FRAMES)
        self.create_tab(ID_ZCU_PUMP, "0x72E – ZCU Pump", "ZCU Pump Status", ["Signal","Value","Unit","TS"])

        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(QLabel("Raw CAN Log:"))
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

    def create_motor_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x720 – Motor Status + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        self.tables[ID_PCU_MOTOR] = table
        splitter.addWidget(table)
        emu = QWidget()
        el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Motor Emulator (0x720)</b>"))
        ctrl = QHBoxLayout()
        self.motor_btn = QPushButton("OFF → Click to Enable")
        self.motor_btn.setStyleSheet("background:#FF5722;color:white;font-weight:bold;")
        self.motor_btn.clicked.connect(lambda: self.toggle_emulator(ID_PCU_MOTOR, self.motor_btn, self.motor_input))
        ctrl.addWidget(self.motor_btn)
        ctrl.addStretch()
        el.addLayout(ctrl)
        hex_l = QHBoxLayout()
        hex_l.addWidget(QLabel("Payload:"))
        self.motor_input = QLineEdit("00 00 00 00 00 00 00 00")
        self.motor_input.setFixedWidth(320)
        hex_l.addWidget(self.motor_input)
        send_once = QPushButton("SEND ONCE")
        send_once.clicked.connect(lambda: self.send_raw(ID_PCU_MOTOR, self.motor_input.text()))
        hex_l.addWidget(send_once)
        el.addLayout(hex_l)
        el.addStretch()
        splitter.addWidget(emu)
        splitter.setSizes([900, 400])
        self.tabs.addTab(w, "0x720 – Motor")

    def create_ccu_tab_with_emulator(self):
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel("<h2>0x600 – CCU Status + Emulator</h2>"))
        splitter = QSplitter(Qt.Horizontal)
        main.addWidget(splitter)
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        self.tables[ID_CCU_STATUS] = table
        splitter.addWidget(table)
        emu = QWidget()
        el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>CCU Emulator (0x600)</b>"))
        ctrl = QHBoxLayout()
        self.ccu_btn = QPushButton("OFF → Click to Enable")
        self.ccu_btn.setStyleSheet("background:#9C27B0;color:white;font-weight:bold;")
        self.ccu_btn.clicked.connect(lambda: self.toggle_emulator(ID_CCU_STATUS, self.ccu_btn, self.ccu_input))
        ctrl.addWidget(self.ccu_btn)
        ctrl.addStretch()
        el.addLayout(ctrl)
        hex_l = QHBoxLayout()
        hex_l.addWidget(QLabel("Payload:"))
        self.ccu_input = QLineEdit("00 00 21 00 52 AE 56 00")
        self.ccu_input.setFixedWidth(320)
        hex_l.addWidget(self.ccu_input)
        send_once = QPushButton("SEND ONCE")
        send_once.clicked.connect(lambda: self.send_raw(ID_CCU_STATUS, self.ccu_input.text()))
        hex_l.addWidget(send_once)
        el.addLayout(hex_l)
        el.addStretch()
        splitter.addWidget(emu)
        splitter.setSizes([900, 400])
        self.tabs.addTab(w, "0x600 – CCU")

    # === NEW: PER-ID BATTERY EMULATOR ===
    def create_battery_tab_with_emulator(self, name, idx, frame_ids):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.addWidget(QLabel(f"<h2>{name} – Live Data + Independent Emulator</h2>"))

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        self.battery_tabs[idx] = table
        splitter.addWidget(table)

        emu = QWidget()
        el = QVBoxLayout(emu)
        el.addWidget(QLabel("<b>Battery 1 Emulator – Independent Payloads</b>"))

        self.bat_inputs = {}  # {0x400: QLineEdit, 0x401: QLineEdit, 0x403: QLineEdit}

        default_payloads = {
            0x400: "01 00 64 00 C8 00 C8 00",   # SOC 100%
            0x401: "02 0A 14 1E 28 32 3C 46",   # Cell voltages
            0x403: "03 00 50 00 3C 00 00 00",   # Status / temp
        }

        for can_id in BAT1_EMULATOR_IDS:
            box = QGroupBox(f"0x{can_id:03X}")
            box_layout = QVBoxLayout(box)

            payload_l = QHBoxLayout()
            payload_l.addWidget(QLabel("Payload:"))
            line = QLineEdit(default_payloads.get(can_id, "00 00 00 00 00 00 00 00"))
            line.setFixedWidth(340)
            self.bat_inputs[can_id] = line
            payload_l.addWidget(line)

            send_btn = QPushButton("SEND ONCE")
            send_btn.clicked.connect(lambda checked, cid=can_id: self.send_bat_single(cid))
            payload_l.addWidget(send_btn)

            box_layout.addLayout(payload_l)
            el.addWidget(box)

        # Cycle button
        ctrl = QHBoxLayout()
        self.bat_btn = QPushButton("OFF → Click to Enable Cycle")
        self.bat_btn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;")
        self.bat_btn.clicked.connect(self.toggle_bat1)
        ctrl.addWidget(self.bat_btn)
        ctrl.addStretch()
        el.addLayout(ctrl)

        # Quick SOC presets (only affects 0x400)
        presets = QHBoxLayout()
        presets.addWidget(QLabel("Quick SOC (0x400): "))
        for soc, payload in [("100%","01 00 64 00 C8 00 C8 00"), ("75%","01 00 4B 00 B0 00 B0 00"),
                            ("50%","01 00 32 00 90 00 90 00"), ("25%","01 00 19 00 60 00 60 00"), ("0%","01 00 00 00 40 00 40 00")]:
            b = QPushButton(soc)
            b.clicked.connect(lambda _, p=payload: self.bat_inputs[0x400].setText(p))
            presets.addWidget(b)
        el.addLayout(presets)

        el.addStretch()
        splitter.addWidget(emu)
        splitter.setSizes([1000, 500])
        self.tabs.addTab(w, name)

    def create_battery_tab(self, name, idx, frame_ids):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(f"<h2>{name}</h2>"))
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        self.battery_tabs[idx] = table
        l.addWidget(table)
        self.tabs.addTab(w, name)

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
        global EMULATOR_600_ENABLED, EMULATOR_720_ENABLED
        if can_id == 0x600: EMULATOR_600_ENABLED = not EMULATOR_600_ENABLED; state = EMULATOR_600_ENABLED
        elif can_id == 0x720: EMULATOR_720_ENABLED = not EMULATOR_720_ENABLED; state = EMULATOR_720_ENABLED
        else: return

        if state:
            btn.setText(f"ON – {hex(can_id)} @ 10Hz")
            btn.setStyleSheet("background:#E91E63;color:white;font-weight:bold;")
            self.start_timer(lambda: self.send_raw(can_id, input_field.text()))
        else:
            btn.setText("OFF → Click to Enable")
            color = "#9C27B0" if can_id == 0x600 else "#FF5722"
            btn.setStyleSheet(f"background:{color};color:white;font-weight:bold;")

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
        payload = self.bat_inputs[can_id].text()
        self.send_raw(can_id, payload)

    def send_bat_cycle(self):
        can_id = BAT1_EMULATOR_IDS[self.bat1_cycle_index]
        payload = self.bat_inputs[can_id].text()
        self.send_raw(can_id, payload)
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
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False, timestamp=time.time())
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
                    name: {"v": value,
                           "d": f"{value:.2f}" if isinstance(value, float) else str(value),
                           "u": unit_map.get(name, ""),
                           "t": getattr(msg, 'timestamp', time.time())}
                    for name, value in decoded.items()
                })
        except: pass

    def can_listener(self):
        while self.bus_connected:
            try:
                msg = self.bus.recv(timeout=0.1)
                if not msg: continue
                if getattr(msg, 'is_error_frame', False):
                    with self.lock: self.error_count += 1
                    continue
                self.process_message_for_gui(msg)
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
            all_sig = []
            for fid in frames:
                all_sig.extend(self.signals.get(fid, {}).items())
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
        global EMULATOR_600_ENABLED, EMULATOR_720_ENABLED, EMULATOR_BAT1_ENABLED
        EMULATOR_600_ENABLED = EMULATOR_720_ENABLED = EMULATOR_BAT1_ENABLED = False
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