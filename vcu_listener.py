# vcu_can_tool_FINAL_100%_WORKING.py
# FULL BATTERY EMULATOR (0x400-0x406) + WORKS OFFLINE + ALL IMPORTS FIXED

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
ID_HV_CHARGER_STATUS = 0x18FF50E5
ID_HV_CHARGER_CMD = 0x1806E5F4
ID_DC12_COMM = 0x1800F5E5

BAT1_FRAMES = [0x400,0x401,0x402,0x403,0x404,0x405,0x406]
BAT2_FRAMES = [0x420,0x421,0x422,0x423,0x424,0x425,0x426]
BAT3_FRAMES = [0x440,0x441,0x442,0x443,0x444,0x445,0x446]

# ALL 7 FRAMES IN EMULATOR
BAT1_EMULATOR_IDS = [0x400, 0x401, 0x402, 0x403, 0x404, 0x405, 0x406]

EMULATOR_STATES = {k: False for k in [
    0x727,0x587,0x107,0x607,0x4F0,0x580,0x600,0x720,0x722,0x724,0x72E,
    ID_HV_CHARGER_STATUS, ID_HV_CHARGER_CMD, ID_DC12_COMM
]}
EMULATOR_INTERVAL = 0.1
EMULATOR_BAT1_ENABLED = False

BAT1_VIRTUAL_ID = "BATTERY_1"
BAT2_VIRTUAL_ID = "BATTERY_2"
BAT3_VIRTUAL_ID = "BATTERY_3"


def decode_battery_message(arbid, data):
    if len(data) < 8: return {}
    b = list(data)
    signals = {}
    frame = arbid & 0xFF

    if frame in [0x00, 0x01, 0x20, 0x21, 0x40, 0x41]:
        disch_lim = ((b[0] << 8) | b[1]) * 0.1
        chg_lim   = ((b[2] << 8) | b[3]) * 0.1
        soc       = ((b[4] << 8) | b[5]) * 0.01
        current   = (((b[6] << 8) | b[7]) ^ 0x8000) - 0x8000
        current  *= 0.1

        signals.update({
            "Discharge_Current_Limit": {"d": f"{disch_lim:.1f}", "u": "A"},
            "Charge_Current_Limit":    {"d": f"{chg_lim:.1f}",   "u": "A"},
            "SOC":                     {"d": f"{soc:.2f}",       "u": "%"},
            "Battery_Current":         {"d": f"{current:+.1f}", "u": "A"},
            "Battery_Connected":       {"d": "Yes" if b[7] & 0x01 else "No", "u": ""},
            "Battery_Balancing":       {"d": "Yes" if b[7] & 0x08 else "No", "u": ""},
        })

    elif frame in [0x02, 0x22, 0x42]:
        signals.update({
            "T_Cell_Min": {"d": f"{b[0] - 40:+}", "u": "°C"},
            "T_Cell_Max": {"d": f"{b[1] - 40:+}", "u": "°C"},
            "V_Cell_Min": {"d": f"{((b[2] << 8) | b[3]) * 0.001:.3f}", "u": "V"},
            "V_Cell_Max": {"d": f"{((b[4] << 8) | b[5]) * 0.001:.3f}", "u": "V"},
        })

    elif frame in [0x04, 0x24, 0x44]:
        v_avg = ((b[2] << 8) | b[3]) * 0.001
        signals.update({
            "Isolation_Board_Powered": {"d": "Yes" if b[0] & 1 else "No", "u": ""},
            "Contactor_Open_Error":    {"d": "Yes" if b[1] & 1 else "No", "u": ""},
            "Contactor_Close_Error":   {"d": "Yes" if b[1] & 2 else "No", "u": ""},
            "V_Cell_Average":          {"d": f"{v_avg:.3f}", "u": "V"},
            "Balancing_Active":        {"d": "Yes" if b[5] & 1 else "No", "u": ""},
        })

    elif frame in [0x05, 0x25, 0x45]:
        cycles = (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]
        ah = ((b[4] << 24) | (b[5] << 16) | (b[6] << 8) | b[7]) * 0.001
        signals.update({
            "Charge_Cycles":       {"d": str(cycles), "u": ""},
            "Ah_Discharged_Total": {"d": f"{ah:.1f}", "u": "Ah"},
        })

    elif frame in [0x06, 0x26, 0x46]:
        alarms = [f"Alarm_{i+9}" for i in range(8) if b[i] & 0x01]
        signals["Battery_Alarms"] = {"d": ", ".join(alarms) if alarms else "None", "u": ""}

    return signals


def decode_dc12_message(data):
    if len(data) < 8: return {}
    b = list(data)
    signals = {}

    # Byte 1: start/stop (1 = start, 0 = stop)
    start_stop = "Start" if b[1] == 1 else "Stop"
    signals["Start_Stop"] = {"d": start_stop, "u": ""}

    # Byte 2: voltage setpoint (V) 1 bit per 0.1V
    voltage_setpoint = b[2] * 0.1
    signals["Voltage_Setpoint"] = {"d": f"{voltage_setpoint:.1f}", "u": "V"}

    # Byte 4: max current (A) 1 bit per 0.1A
    max_current = b[4] * 0.1
    signals["Max_Current"] = {"d": f"{max_current:.1f}", "u": "A"}

    # Byte 5: Active signal (0: not active, 1: active)
    active = "Active" if b[5] == 1 else "Not Active"
    signals["Charger_Active"] = {"d": active, "u": ""}

    return signals


class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Tool – FULL BATTERY EMULATOR (0x400-0x406)")
        self.resize(3000, 1600)
        self.bus = None
        self.bus_connected = False
        self.tables = {}
        self.battery_tabs = {}
        self.lock = threading.Lock()
        self.raw_log_lines = []
        self.first_fill = {}
        self.bat1_cycle_index = 0

        try:
            self.db = cantools.database.load_file(DBC_FILE)
        except:
            self.db = cantools.database.Database()

        all_ids = [ID_727,ID_587,ID_107,ID_607,ID_CMD_BMS,ID_PDU_STATUS,ID_HMI_STATUS,
                   ID_PCU_COOL,ID_PCU_MOTOR,ID_PCU_POWER,ID_CCU_STATUS,ID_ZCU_PUMP,
                   ID_HV_CHARGER_STATUS,ID_HV_CHARGER_CMD,ID_DC12_COMM]
        all_ids += BAT1_FRAMES + BAT2_FRAMES + BAT3_FRAMES
        all_ids += [BAT1_VIRTUAL_ID, BAT2_VIRTUAL_ID, BAT3_VIRTUAL_ID]

        self.signals = {i: {} for i in set(all_ids)}
        self.first_fill = {k: True for k in self.signals}

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
        self.connect_btn = QPushButton("Connect CAN")
        self.connect_btn.setFixedHeight(36)
        self.connect_btn.clicked.connect(self.toggle_can)
        top.addWidget(self.connect_btn)
        self.status_label = QLabel("DISCONNECTED")
        self.status_label.setStyleSheet("color:#d32f2f; font-weight:bold;")
        top.addWidget(self.status_label)
        top.addStretch()
        layout.addLayout(top)

        self.setStyleSheet("* { font-family: Segoe UI; font-size: 11px; }")
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.create_emulator_tab(0x727, "0x727 – VCU→PCU", "VCU to PCU", "44 40 00 14 F8 11 64 00")
        self.create_emulator_tab(0x587, "0x587 – PDU Cmd", "PDU", "01 01 00 00 01 00 07 04")
        self.create_emulator_tab(0x107, "0x107 – Pump", "Pump", "00 00 00 00 00 00 00 00")
        self.create_emulator_tab(0x607, "0x607 – CCU/ZCU", "CCU/ZCU", "01 00 00 00 00 00 00 00")
        self.create_emulator_tab(0x4F0, "0x4F0 – BMS Cmd", "BMS", "00 01 00 01 00 00 00 00")
        self.create_emulator_tab(0x580, "0x580 – PDU Status", "PDU", "99 00 00 99 04 00 00 F3")
        self.create_emulator_tab(0x600, "0x600 – CCU", "CCU", "3A 39 50 54 8D 00 3C 00")
        self.create_emulator_tab(0x720, "0x720 – Motor", "Motor", "07 00 00 00 00 00 84 00")
        self.create_emulator_tab(0x722, "0x722 – Cooling", "Cooling", "39 38 00 3C 39 3B 28 39")
        self.create_emulator_tab(0x724, "0x724 – Power", "Power", "E4 8A 28 1D E5 1A 3A 5E")
        self.create_emulator_tab(0x72E, "0x72E – ZCU Pump", "ZCU", "28 00 00 00 00 3C 08 00")
        self.create_emulator_tab(ID_HV_CHARGER_STATUS, "HVC Status", "Charger Status", "1B 01 00 80 00 00 43 00")
        self.create_emulator_tab(ID_HV_CHARGER_CMD, "HVC CMD", "Charger CMD", "1D 88 00 96 01 00 00 00")
        self.create_emulator_tab(ID_DC12_COMM, "DC12 Comm", "DC12 Charger Communication", "00 01 90 00 F4 01 00 00")
        self.create_tab(ID_HMI_STATUS, "0x740 – HMI", "HMI", ["Signal","Value","Unit","TS"])

        self.create_battery_tab_with_emulator("Battery 1", 1, BAT1_FRAMES)
        self.create_battery_tab("Battery 2", 2, BAT2_FRAMES)
        self.create_battery_tab("Battery 3", 3, BAT3_FRAMES)

        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(QLabel("Raw Log:"))
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
        if presets is None: presets = []
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
        btn = QPushButton("OFF → Click to Enable")
        input_field = QLineEdit(default_payload)
        input_field.setFixedWidth(340)
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
        splitter.setSizes([1000,400])
        self.tabs.addTab(w, tab_name)

    def create_battery_tab_with_emulator(self, name, idx, frame_ids):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.addWidget(QLabel(f"{name} – Live + FULL Emulator (7 frames)"))
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
        el.addWidget(QLabel("<b>Battery 1 Emulator – ALL 7 FRAMES</b>"))
        self.bat_inputs = {}
        defaults = {
            0x400: "9E 07 8A 02 4F 18 3A 5E",
            0x401: "DF 1A 0B 00 E0 1A 64 01",
            0x402: "1E 28 0F A0 13 88 00 00",
            0x403: "00 3B 00 3C EE 0E F7 0E",
            0x404: "01 00 DC 05 00 01 00 00",
            0x405: "00 00 01 2C 00 00 13 88",
            0x406: "00 00 00 00 00 00 00 00",
        }
        for cid in BAT1_EMULATOR_IDS:
            box = QGroupBox(f"0x{cid:03X}")
            bl = QVBoxLayout(box)
            line = QLineEdit(defaults.get(cid, "00 00 00 00 00 00 00 00"))
            line.setFixedWidth(380)
            self.bat_inputs[cid] = line
            send_btn = QPushButton("SEND ONCE")
            send_btn.clicked.connect(lambda _, id=cid: self.send_raw(id, line.text()))
            bl.addWidget(line)
            bl.addWidget(send_btn)
            el.addWidget(box)

        self.bat_btn = QPushButton("OFF → Click to Enable Full Cycle")
        self.bat_btn.clicked.connect(self.toggle_bat1)
        self.bat_btn.setStyleSheet("background:#388E3C;color:white;font-weight:bold;")
        el.addWidget(self.bat_btn)
        el.addStretch()
        splitter.addWidget(emu)
        splitter.setSizes([1200,600])
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

    def toggle_emulator(self, can_id, btn, input_field):
        EMULATOR_STATES[can_id] = not EMULATOR_STATES[can_id]
        if EMULATOR_STATES[can_id]:
            btn.setText(f"ON – {hex(can_id)} @10Hz")
            btn.setStyleSheet("background:#d32f2f;color:white;")
            self.start_timer(lambda: self.send_raw(can_id, input_field.text()))
        else:
            btn.setText("OFF → Click to Enable")
            btn.setStyleSheet("background:#555;color:white;")

    def toggle_bat1(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = not EMULATOR_BAT1_ENABLED
        if EMULATOR_BAT1_ENABLED:
            self.bat_btn.setText("ON – Sending All 7 Frames @10Hz")
            self.bat_btn.setStyleSheet("background:#2E7D32;color:white;")
            self.bat1_cycle_index = 0
            self.start_timer(self.send_bat_cycle)
        else:
            self.bat_btn.setText("OFF → Click to Enable Full Cycle")
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
        self.bat1_cycle_index = (self.bat1_cycle_index + 1) % len(BAT1_EMULATOR_IDS)

    def send_raw(self, can_id, text):
        clean = ''.join(c for c in text.upper() if c in '0123456789ABCDEF ')
        clean = clean.replace(" ", "")
        if len(clean) != 16:
            return
        try:
            data = bytes.fromhex(clean)
            msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=False, timestamp=time.time())
            if self.bus_connected:
                self.bus.send(msg)
            self.process_message_for_gui(msg)
        except Exception as e:
            print("Send error:", e)

    def process_message_for_gui(self, msg):
        with self.lock:
            self.raw_log_lines.append(f"0x{msg.arbitration_id:08X} | {msg.data.hex(' ').upper()}")
            if len(self.raw_log_lines) > 200:
                self.raw_log_lines.pop(0)

        arb = msg.arbitration_id
        if arb in BAT1_FRAMES:
            virtual_id = BAT1_VIRTUAL_ID
        elif arb in BAT2_FRAMES:
            virtual_id = BAT2_VIRTUAL_ID
        elif arb in BAT3_FRAMES:
            virtual_id = BAT3_VIRTUAL_ID
        else:
            virtual_id = None

        if virtual_id:
            decoded = decode_battery_message(arb, msg.data)
            if decoded:
                with self.lock:
                    self.signals[virtual_id].update({
                        k: {"d": v["d"], "u": v.get("u", ""), "t": time.time()}
                        for k, v in decoded.items()
                    })
            return

        # Handle DC12 comm messages
        if arb == ID_DC12_COMM:
            decoded = decode_dc12_message(msg.data)
            if decoded:
                with self.lock:
                    self.signals[arb].update({
                        k: {"d": v["d"], "u": v.get("u", ""), "t": time.time()}
                        for k, v in decoded.items()
                    })
            return

        dbc_id = self.HEX_TO_DBC_ID.get(arb)
        if dbc_id:
            try:
                decoded = self.db.decode_message(dbc_id, msg.data)
                with self.lock:
                    for n, v in decoded.items():
                        self.signals[arb][n] = {"d": str(v), "u": "", "t": time.time()}
            except:
                pass

    def update_gui(self):
        with self.lock:
            lines = self.raw_log_lines[-8:]

        for fid, table in self.tables.items():
            items = list(self.signals.get(fid, {}).items())
            table.setRowCount(len(items))
            for r, (name, d) in enumerate(items):
                for c, val in enumerate([name, d.get("d",""), d.get("u",""), f"{d.get('t',0):.1f}"]):
                    item = table.item(r, c)
                    if not item:
                        table.setItem(r, c, QTableWidgetItem(val))
                    else:
                        item.setText(val)
            if self.first_fill.get(fid, False):
                table.resizeColumnsToContents()
                self.first_fill[fid] = False

        for idx, virtual_id in [(1, BAT1_VIRTUAL_ID), (2, BAT2_VIRTUAL_ID), (3, BAT3_VIRTUAL_ID)]:
            table = self.battery_tabs[idx]
            items = list(self.signals.get(virtual_id, {}).items())
            table.setRowCount(len(items))
            for r, (name, d) in enumerate(items):
                for c, val in enumerate([name, d.get("d",""), d.get("u",""), f"{d.get('t',0):.1f}"]):
                    item = table.item(r, c)
                    if not item:
                        table.setItem(r, c, QTableWidgetItem(val))
                    else:
                        item.setText(val)
            if self.first_fill.get(virtual_id, False):
                table.resizeColumnsToContents()
                self.first_fill[virtual_id] = False

        self.raw_log.clear()
        for l in lines:
            self.raw_log.append(l)

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
            self.status_label.setStyleSheet("color:green;")
            threading.Thread(target=self.can_listener, daemon=True).start()
        except Exception as e:
            self.status_label.setText(f"ERR: {e}")

    def disconnect_can(self):
        global EMULATOR_BAT1_ENABLED
        EMULATOR_BAT1_ENABLED = False
        for k in EMULATOR_STATES:
            EMULATOR_STATES[k] = False
        if hasattr(self, "emu_timer"):
            self.emu_timer.stop()
        if self.bus:
            try:
                self.bus.shutdown()
            except:
                pass
        self.bus_connected = False
        self.connect_btn.setText("Connect CAN")
        self.status_label.setText("DISCONNECTED")
        self.status_label.setStyleSheet("color:#d32f2f;")
        with self.lock:
            for d in self.signals.values():
                d.clear()
            self.raw_log_lines.clear()

    def can_listener(self):
        while self.bus_connected:
            try:
                msg = self.bus.recv(timeout=0.1)
                if msg and not getattr(msg, 'is_error_frame', False):
                    self.process_message_for_gui(msg)
            except:
                pass

    HEX_TO_DBC_ID = {0x727:1831, 0x587:1415, 0x740:1856, 0x580:1408, 0x600:1536,
                     0x720:1824, 0x722:1826, 0x724:1828, 0x72E:1838}

    def closeEvent(self, e):
        self.disconnect_can()
        e.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CANMonitor()
    win.show()
    sys.exit(app.exec_())