# vcu_can_tool_FINAL_PERFECT.py
# 12 emulators + clean UI + CONNECT BUTTON WORKS + NO INDENTATION ERRORS

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

EMULATOR_STATES = {k: False for k in [0x727,0x587,0x107,0x607,0x4F0,0x580,0x600,0x720,0x722,0x724,0x72E]}
EMULATOR_INTERVAL = 0.1
EMULATOR_BAT1_ENABLED = False


class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Tool – FINAL PERFECT VERSION")
        self.resize(3000, 1600)

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

        all_ids = [ID_727,ID_587,ID_107,ID_607,ID_CMD_BMS,ID_PDU_STATUS,ID_HMI_STATUS,
                   ID_PCU_COOL,ID_PCU_MOTOR,ID_PCU_POWER,ID_CCU_STATUS,ID_ZCU_PUMP]
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
        layout.setContentsMargins(10,10,10,10)
        layout.setSpacing(8)

        # Top bar — CONNECT BUTTON WORKS!
        top = QHBoxLayout()
        self.connect_btn = QPushButton("Connect CAN")
        self.connect_btn.setFixedHeight(36)
        self.connect_btn.clicked.connect(self.toggle_can)  # FIXED
        top.addWidget(self.connect_btn)

        self.status_label = QLabel("DISCONNECTED")
        self.status_label.setStyleSheet("color:#d32f2f; font-weight:bold;")
        top.addWidget(self.status_label)
        top.addStretch()
        layout.addLayout(top)

        self.setStyleSheet("""
            * { font-family: Segoe UI, Arial; font-size: 11px; }
            QLineEdit, QPushButton, QTabBar::tab { font-size: 11px; }
            QTableWidget { font-size: 11px; }
        """)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # All emulator tabs
        self.create_emulator_tab(0x727, "0x727 – VCU→PCU", "VCU to PCU Command", "44 40 00 14 F8 11 64 00",
                                [("Standby","00 00 00 00 00 00 00 00"), ("Drive","01 00 00 00 00 00 00 00"), ("Reset","03 00 00 00 00 00 00 00")])
        self.create_emulator_tab(0x587, "0x587 – PDU Cmd", "PDU Command", "01 01 00 00 01 00 07 04",
                                [("All OFF","00 00 00 00 00 00 00 00"), ("Precharge","01 00 00 00 00 00 00 00"), ("Main+Pre","03 00 00 00 00 00 00 00")])
        self.create_emulator_tab(0x107, "0x107 – Pump", "Pump Command", "00 00 00 00 00 00 00 00",
                                [("OFF","00 00 00 00 00 00 00 00"), ("50%","01 32 00 00 00 00 00 00"), ("100%","01 64 00 00 00 00 00 00")])
        self.create_emulator_tab(0x607, "0x607 – CCU/ZCU Cmd", "CCU/ZCU Command", "01 00 00 00 00 00 00 00")
        self.create_emulator_tab(0x4F0, "0x4F0 – VCU→BMS", "VCU to BMS", "00 01 00 01 00 00 00 00",
                                [("Idle","00 00 00 00 00 00 00 00"), ("Precharge","02 00 00 00 00 00 00 00"), ("Close","01 00 00 00 00 00 00 00")])
        self.create_emulator_tab(0x580, "0x580 – PDU Status", "PDU Relays", "99 00 00 99 04 00 00 F3",
                                [("All OFF","00 00 00 00 00 00 00 00"), ("Main+Pre","03 00 00 00 00 00 00 00"), ("All ON","FF FF FF FF FF FF FF FF")])
        self.create_emulator_tab(0x600, "0x600 – CCU", "CCU Status", "3A 39 50 54 8D 00 3C 00")
        self.create_emulator_tab(0x720, "0x720 – Motor", "Motor Status", "07 00 00 00 00 00 84 00")
        self.create_emulator_tab(0x722, "0x722 – Cooling", "PCU Cooling", "39 38 00 3C 39 3B 28 39")
        self.create_emulator_tab(0x724, "0x724 – Power", "PCU Power", "E4 8A 28 1D E5 1A 3A 5E")
        self.create_emulator_tab(0x72E, "0x72E – ZCU Pump", "ZCU Pump Status", "28 00 00 00 00 3C 08 00",
                                [("OFF","00 00 00 00 00 00 00 00"), ("50%","01 32 00 00 00 00 00 00"), ("100%","01 64 00 00 00 00 00 00")])

        self.create_tab(ID_HMI_STATUS, "0x740 – HMI", "HMI Status", ["Signal","Value","Unit","TS"])

        self.create_battery_tab_with_emulator("Battery 1", 1, BAT1_FRAMES)
        self.create_battery_tab("Battery 2", 2, BAT2_FRAMES)
        self.create_battery_tab("Battery 3", 3, BAT3_FRAMES)

        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        self.raw_log.setStyleSheet("font-family: Consolas; font-size: 10px;")
        layout.addWidget(QLabel("Raw CAN Log (last 8 frames):"))
        layout.addWidget(self.raw_log)

    def create_tab(self, fid, name, title, headers):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(title))
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tables[fid] = table
        l.addWidget(table)
        self.tabs.addTab(w, name)

    def create_emulator_tab(self, can_id, tab_name, title, default_payload, presets=None):
        if presets is None:
            presets = []
        w = QWidget()
        main = QVBoxLayout(w)
        main.addWidget(QLabel(title))
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

        ctrl = QHBoxLayout()
        btn = QPushButton("OFF → Click to Enable")
        btn.clicked.connect(lambda: self.toggle_emulator(can_id, btn, input_field))
        btn.setStyleSheet("background:#555;color:white;")
        ctrl.addWidget(btn)
        ctrl.addStretch()
        el.addLayout(ctrl)

        hex_l = QHBoxLayout()
        hex_l.addWidget(QLabel("Payload:"))
        input_field = QLineEdit(default_payload)
        input_field.setFixedWidth(340)
        setattr(self, f"input_{can_id:x}", input_field)
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
        el.addWidget(QLabel("<b>Battery 1 Emulator</b>"))
        self.bat_inputs = {}
        defaults = {0x400: "9E 07 8A 02 4F 18 3A 5E", 0x401: "DF 1A 0B 00 E0 1A 64 01", 0x403: "00 3B 00 3C EE 0E F7 0E"}
        for cid in BAT1_EMULATOR_IDS:
            box = QGroupBox(f"0x{cid:03X}")
            bl = QVBoxLayout(box)
            pl = QHBoxLayout()
            pl.addWidget(QLabel("Payload:"))
            line = QLineEdit(defaults.get(cid, "00 00 00 00 00 00 00 00"))
            line.setFixedWidth(340)
            self.bat_inputs[cid] = line
            pl.addWidget(line)
            sb = QPushButton("SEND ONCE")
            sb.clicked.connect(lambda _, id=cid: self.send_raw(id, line.text()))
            pl.addWidget(sb)
            bl.addLayout(pl)
            el.addWidget(box)

        ctrl = QHBoxLayout()
        self.bat_btn = QPushButton("OFF → Click to Enable Cycle")
        self.bat_btn.setStyleSheet("background:#388E3C;color:white;")
        self.bat_btn.clicked.connect(self.toggle_bat1)
        ctrl.addWidget(self.bat_btn)
        ctrl.addStretch()
        el.addLayout(ctrl)

        soc_l = QHBoxLayout()
        soc_l.addWidget(QLabel("Quick SOC:"))
        for soc, pl in [("100%","01 00 64 00 C8 00 C8 00"), ("50%","01 00 32 00 90 00 90 00"), ("0%","01 00 00 00 40 00 40 00")]:
            b = QPushButton(soc)
            b.clicked.connect(lambda _, p=pl: self.bat_inputs[0x400].setText(p))
            soc_l.addWidget(b)
        el.addLayout(soc_l)
        el.addStretch()

        splitter.addWidget(emu)
        splitter.setSizes([1100, 500])
        self.tabs.addTab(w, name)

    def create_battery_tab(self, name, idx, frame_ids):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel(name))
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.battery_tabs[idx] = table
        l.addWidget(table)
        self.tabs.addTab(w, name)

    HEX_TO_DBC_ID = {
        0x727:1831, 0x587:1415, 0x107:263, 0x607:1543, 0x4F0:1264, 0x580:1408, 0x740:1856,
        0x722:1826, 0x720:1824, 0x724:1828, 0x600:1536, 0x72E:1838,
        0x400:1024, 0x401:1025, 0x403:1027, 0x405:1029, 0x406:1030,
        0x420:1056, 0x421:1057, 0x423:1059, 0x425:1061, 0x426:1062,
        0x440:1088, 0x441:1089, 0x443:1091, 0x445:1093, 0x446:1094
    }

    def toggle_emulator(self, can_id, btn, input_field):
        EMULATOR_STATES[can_id] = not EMULATOR_STATES[can_id]
        if EMULATOR_STATES[can_id]:
            btn.setText(f"ON – {hex(can_id)} @10Hz")
            btn.setStyleSheet("background:#d32f2f;color:white;")
            self.start_timer(lambda: self.send_raw(can_id, input_field.text()))
        else:
            btn.setText("OFF → Click to Enable")
            colors = {0x72E:"#2E7D32", 0x727:"#D50000", 0x587:"#FF6D00", 0x107:"#6D4C41", 0x607:"#455A64",
                      0x4F0:"#880E4F", 0x580:"#E65100", 0x600:"#6A1B9A", 0x720:"#D84315", 0x722:"#00695C", 0x724:"#1E88E5"}
            btn.setStyleSheet(f"background:{colors.get(can_id,'#555')};color:white;")

    def toggle_bat1(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = not EMULATOR_BAT1_ENABLED
        if EMULATOR_BAT1_ENABLED:
            self.bat_btn.setText("ON – Cycling 400→401→403")
            self.bat_btn.setStyleSheet("background:#2E7D32;color:white;")
            self.bat1_cycle_index = 0
            self.start_timer(self.send_bat_cycle)
        else:
            self.bat_btn.setText("OFF → Click to Enable Cycle")
            self.bat_btn.setStyleSheet("background:#388E3C;color:white;")

    def start_timer(self, callback):
        if hasattr(self, "emu_timer"):
            self.emu_timer.stop()
        self.emu_timer = QTimer()
        self.emu_timer.timeout.connect(callback)
        self.emu_timer.start(int(EMULATOR_INTERVAL * 1000))

    def send_bat_cycle(self):
        cid = BAT1_EMULATOR_IDS[self.bat1_cycle_index]
        self.send_raw(cid, self.bat_inputs[cid].text())
        self.bat1_cycle_index = (self.bat1_cycle_index + 1) % 3

    def send_raw(self, can_id, text):
        if not self.bus_connected:
            return
        clean = ''.join(c for c in text.upper() if c in '0123456789ABCDEF ')
        clean = clean.replace(" ", "")
        if len(clean) != 16:
            return
        try:
            data = bytes.fromhex(clean)
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False)
            self.bus.send(msg)
            self.process_message_for_gui(msg)
        except Exception as e:
            print("Send failed:", e)

    def process_message_for_gui(self, msg):
        with self.lock:
            self.raw_log_lines.append(f"0x{msg.arbitration_id:03X} | {msg.data.hex(' ').upper()}")
            if len(self.raw_log_lines) > 200:
                self.raw_log_lines.pop(0)

        dbc_id = self.HEX_TO_DBC_ID.get(msg.arbitration_id)
        if not dbc_id:
            return
        try:
            decoded = self.db.decode_message(dbc_id, msg.data)
            unit_map = {s.name: s.unit or "" for s in self.db.get_message_by_frame_id(dbc_id).signals}
            with self.lock:
                self.signals[msg.arbitration_id].update({
                    name: {"v": value, "d": f"{value:.3f}" if isinstance(value,float) else str(value),
                           "u": unit_map.get(name,""), "t": time.time()}
                    for name, value in decoded.items()
                })
        except:
            pass

    def can_listener(self):
        while self.bus_connected:
            try:
                msg = self.bus.recv(timeout=0.1)
                if msg:
                    if getattr(msg, 'is_error_frame', False):
                        with self.lock: self.error_count += 1
                    else:
                        self.process_message_for_gui(msg)
            except:
                pass

    def update_gui(self):
        with self.lock:
            lines = self.raw_log_lines[-8:]

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

        self.status_label.setText("CONNECTED" if self.bus_connected and self.error_count == 0 else f"NOISE: {self.error_count}")
        self.status_label.setStyleSheet("color:green;" if self.error_count == 0 else "color:orange;")

    def toggle_can(self):
        if self.bus_connected:
            self.disconnect_can()
        else:
            self.connect_can()

    def connect_can(self):
        try:
            self.bus = can.interface.Bus(channel=CHANNEL, bustype=BUSTYPE, bitrate=BITRATE)
            self.bus_connected = True
            self.connect_btn.setText("Disconnect CAN")
            self.connect_btn.setStyleSheet("background:#c62828;color:white;")
            self.status_label.setText("CONNECTED")
            self.status_label.setStyleSheet("color:green;font-weight:bold;")
            threading.Thread(target=self.can_listener, daemon=True).start()
        except Exception as e:
            self.status_label.setText(f"ERROR: {str(e)[:50]}")
            print("Connect failed:", e)

    def disconnect_can(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = False
        for cid in EMULATOR_STATES:
            EMULATOR_STATES[cid] = False
        if hasattr(self, "emu_timer"):
            self.emu_timer.stop()
        if self.bus:
            try: self.bus.shutdown()
            except: pass
            self.bus = None
        self.bus_connected = False
        self.connect_btn.setText("Connect CAN")
        self.connect_btn.setStyleSheet("")
        self.status_label.setText("DISCONNECTED")
        self.status_label.setStyleSheet("color:#d32f2f;")
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