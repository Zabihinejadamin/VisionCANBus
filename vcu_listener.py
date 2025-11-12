# vcu_gui_final.py
# Full working version – all signals show, no blank tabs
import sys
import cantools
import can
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QLabel, QTextEdit, QTabWidget,
    QProgressBar, QPushButton, QGridLayout
)
from PyQt5.QtCore import QTimer, Qt
import threading
import time
import traceback

# === CONFIG ===
DBC_FILE = 'DBC/vcu_updated.dbc'
BITRATE = 250000
CHANNEL = 'PCAN_USBBUS1'
BUSTYPE = 'pcan'

# === CAN IDs (Hex) ===
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

# === BATTERY FRAME IDs (Hex) ===
ID_BT1_DCL   = 0x400  # 1024
ID_BT1_CURR  = 0x401  # 1025
ID_BT1_TEMP  = 0x403  # 1027
ID_BT1_FAIL  = 0x406  # 1030
ID_BT1_RISO  = 0x405  # 1029

ID_BT2_DCL   = 0x420  # 1056
ID_BT2_CURR  = 0x421  # 1057
ID_BT2_TEMP  = 0x423  # 1059
ID_BT2_FAIL  = 0x426  # 1062
ID_BT2_RISO  = 0x505  # 1285

ID_BT3_DCL   = 0x440  # 1088
ID_BT3_CURR  = 0x441  # 1089
ID_BT3_TEMP  = 0x443  # 1091
ID_BT3_FAIL  = 0x446  # 1094
ID_BT3_RISO  = 0x605  # 1541

# =============================================
class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor – 3 Batteries + 11 Frames")
        self.resize(2600, 1400)
        self.bus = None
        self.bus_connected = False

        # === GUI CONTAINERS ===
        self.tables = {}
        self.bars = {}
        self.alerts = {}
        self.battery_tabs = {}

        # Load DBC
        try:
            self.db = cantools.database.load_file(DBC_FILE)
            print(f"DBC loaded: {len(self.db.messages)} messages")
        except Exception as e:
            print(f"DBC Error (non-fatal): {e}")
            self.db = cantools.database.Database()

        # === DATA CONTAINERS (ALL HEX IDs) ===
        self.signals = {
            ID_727: {}, ID_587: {}, ID_107: {}, ID_607: {}, ID_CMD_BMS: {},
            ID_PDU_STATUS: {}, ID_HMI_STATUS: {}, ID_PCU_COOL: {}, ID_PCU_MOTOR: {},
            ID_PCU_POWER: {}, ID_CCU_STATUS: {},
            # Batteries
            0x400: {}, 0x401: {}, 0x403: {}, 0x406: {}, 0x405: {},
            0x420: {}, 0x421: {}, 0x423: {}, 0x426: {}, 0x505: {},
            0x440: {}, 0x441: {}, 0x443: {}, 0x446: {}, 0x605: {},
        }

        self.raw_log_lines = []
        self.error_count = 0
        self.unknown_count = 0
        self.last_gui_update = 0
        self.lock = threading.Lock()

        # GUI state
        self.first_fill = {k: True for k in self.signals}
        self.first_fill.update({f"BT{i}": True for i in [1, 2, 3]})

        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(100)  # 10 Hz
        self.thread = None

    # -------------------------------------------------
    # UI
    # -------------------------------------------------
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top bar
        top = QHBoxLayout()
        self.connect_btn = QPushButton("CONNECT CAN")
        self.connect_btn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;padding:8px;")
        self.connect_btn.clicked.connect(self.toggle_can)
        top.addWidget(self.connect_btn)

        self.status_label = QLabel("DISCONNECTED")
        self.status_label.setStyleSheet("color:red;font-weight:bold;")
        top.addWidget(self.status_label)
        top.addStretch()
        layout.addLayout(top)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # === Regular Frames ===
        self.create_tab(ID_727, "0x727 – PCU", "VCU to PCU", ["Signal","Value","Unit","TS"], ["VCU_PCU_THROTTLE"])
        self.create_tab(ID_587, "0x587 – PDU", "VCU to PDU", ["Relay","Command","Raw","TS"], None)
        self.create_tab(ID_107, "0x107 – Pump", "Pump Command", ["Signal","Value","Unit","TS"], ["PUMP_THROTTLE"])
        self.create_tab(ID_607, "0x607 – CCU/ZCU", "CCU/ZCU Command", ["Command","Status","TS"], None)
        self.create_tab(ID_CMD_BMS, "0x4F0 – VCU Cmd", "VCU to BMS", ["Signal","State","TS"], None)
        self.create_tab(ID_PDU_STATUS, "0x580 – PDU Relays", "PDU Relay Status", ["Relay","CMD","STATUS","TS"], None)
        self.create_tab(ID_HMI_STATUS, "0x740 – HMI", "HMI VCU Status", ["Signal","Value","Unit","TS"], ["HMI_VCU_SOC", "HMI_VCU_THROTTLE"])
        self.create_tab(ID_PCU_COOL, "0x722 – Cooling", "PCU Cooling", ["Signal","Value","Unit","TS"], ["PCU_WATERFLOW"])
        self.create_tab(ID_PCU_MOTOR, "0x720 – Motor", "PCU Motor", ["Signal","Value","Unit","TS"], ["PCU_MOTOR_TORQUE", "PCU_MOTOR_SPEED"])
        self.create_tab(ID_PCU_POWER, "0x724 – Power", "PCU Power", ["Signal","Value","Unit","TS"], ["PCU_INVERTER_CURRENT", "PCU_PUMP_PWM", "PCU_TRIM_POSITION"])
        self.create_tab(ID_CCU_STATUS, "0x600 – CCU", "CCU Status", ["Signal","Value","Unit","TS"], ["CCU_GLYCOL_FLOW", "CCU_GLYLYCOL_THROTTLE", "CCU_ZCU_CURRENT"])

        # === Battery Tabs ===
        self.create_battery_tab("Battery 1", 1, [0x400, 0x401, 0x403, 0x406, 0x405])
        self.create_battery_tab("Battery 2", 2, [0x420, 0x421, 0x423, 0x426, 0x505])
        self.create_battery_tab("Battery 3", 3, [0x440, 0x441, 0x443, 0x446, 0x605])

        # Raw log
        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(self.raw_log)

    def create_tab(self, fid, name, title, headers, progress_signals):
        t = QWidget()
        l = QVBoxLayout(t)
        l.addWidget(QLabel(f"<h2>{title}</h2>"))

        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        self.tables[fid] = table
        l.addWidget(table)

        if progress_signals:
            hb = QHBoxLayout()
            for sig in progress_signals:
                bar = QProgressBar()
                bar.setTextVisible(True)
                bar.setFormat(f"{sig}: %p%")
                self.bars[(fid, sig)] = bar
                hb.addWidget(bar)
            l.addLayout(hb)

        self.tabs.addTab(t, name)

    def create_battery_tab(self, name, idx, frame_ids):
        t = QWidget()
        l = QVBoxLayout(t)
        l.addWidget(QLabel(f"<h2>{name} – All Signals</h2>"))

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        self.battery_tabs[idx] = table
        l.addWidget(table)

        # Progress bars
        grid = QGridLayout()
        bars = [
            ("SOC (%)", f"BT{idx}_SOC", 100.0),
            ("Current (A)", f"BT{idx}_CURR", 6552),
            ("Voltage (V)", f"BT{idx}_VOLT", 655.3),
            ("Temp (°C)", f"BT{idx}_TEMP", 127),
            ("DCL (A)", f"BT{idx}_DCL", 6553.5),
            ("CCL (A)", f"BT{idx}_CCL", 6553.5),
            ("Balanced", f"BT{idx}_RISO", 180),
        ]
        row = 0
        for label, sig, max_val in bars:
            bar = QProgressBar()
            bar.setMaximum(100)
            bar.setTextVisible(True)
            bar.setFormat(f"{sig}: %p%")
            self.bars[(f"BT{idx}", sig)] = bar
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(bar, row, 1)
            row += 1
        l.addLayout(grid)

        # Alerts
        state_label = QLabel("STATE: —")
        bal_label = QLabel("BALANCING: —")
        fail_label = QLabel("FAILURE: —")
        state_label.setStyleSheet("font-weight:bold;")
        bal_label.setStyleSheet("font-weight:bold;")
        fail_label.setStyleSheet("font-weight:bold;")
        self.alerts[(f"BT{idx}", "state")] = state_label
        self.alerts[(f"BT{idx}", "bal")] = bal_label
        self.alerts[(f"BT{idx}", "fail")] = fail_label
        l.addWidget(state_label)
        l.addWidget(bal_label)
        l.addWidget(fail_label)

        self.tabs.addTab(t, name)

    # -------------------------------------------------
    # CAN Control
    # -------------------------------------------------
    def toggle_can(self):
        if not self.bus_connected:
            self.connect_can()
        else:
            self.disconnect_can()

    def connect_can(self):
        try:
            self.bus = can.interface.Bus(channel=CHANNEL, bustype=BUSTYPE, bitrate=BITRATE)
            self.bus_connected = True
            self.connect_btn.setText("DISCONNECT CAN")
            self.connect_btn.setStyleSheet("background:#f44336;color:white;font-weight:bold;padding:8px;")
            self.status_label.setText("CONNECTED")
            self.status_label.setStyleSheet("color:green;font-weight:bold;")
            self.thread = threading.Thread(target=self.can_listener, daemon=True)
            self.thread.start()
            print("CAN listener started")
        except Exception as e:
            print("CAN Connect Error:", e)
            traceback.print_exc()
            self.status_label.setText("CONNECT FAILED")
            self.status_label.setStyleSheet("color:red;font-weight:bold;")

    def disconnect_can(self):
        try:
            if self.bus:
                self.bus.shutdown()
                self.bus = None
            self.bus_connected = False
            self.connect_btn.setText("CONNECT CAN")
            self.connect_btn.setStyleSheet("background:#4CAF50;color:white;font-weight:bold;padding:8px;")
            self.status_label.setText("DISCONNECTED")
            self.status_label.setStyleSheet("color:red;font-weight:bold;")
            with self.lock:
                for d in self.signals.values():
                    d.clear()
                self.raw_log_lines.clear()
                self.error_count = 0
                self.unknown_count = 0
        except Exception as e:
            print("CAN Disconnect Error:", e)

    # -------------------------------------------------
    # CAN Listener
    # -------------------------------------------------
    def can_listener(self):
        known = {
            0x727: "VCU_PCU_CONTROL_FRAME",
            0x587: "VCU_PDU_COMMAND_FRAME",
            0x107: "PUMP_COMMAND_FRAME",
            0x607: "CCU_ZCU_COMMAND_FRAME",
            0x4F0: "VCU_BMS_COMMAND_FRAME",
            0x580: "PDU_RELAY_STATUS",
            0x740: "HMI_VCU_STATUS",
            0x722: "PCU_COOLING_FRAME",
            0x720: "PCU_MOTOR_FRAME",
            0x724: "PCU_POWER_FRAME",
            0x600: "CCU_STATUS_FRAME",
            # Batteries
            0x400: "BT1_DCL_CCL_SOC",
            0x401: "BT1_CURR_VOLT_STATE_BAL",
            0x403: "BT1_TEMP",
            0x406: "BT1_FAILURE",
            0x405: "BT1_RISO",
            0x420: "BT2_DCL_CCL_SOC",
            0x421: "BT2_CURR_VOLT_STATE_BAL",
            0x423: "BT2_TEMP",
            0x426: "BT2_FAILURE",
            0x505: "BT2_RISO",
            0x440: "BT3_DCL_CCL_SOC",
            0x441: "BT3_CURR_VOLT_STATE_BAL",
            0x443: "BT3_TEMP",
            0x446: "BT3_FAILURE",
            0x605: "BT3_RISO",
        }

        while self.bus_connected:
            try:
                msg = self.bus.recv(timeout=0.1)
                if not msg: continue
                if msg.arbitration_id == 0x400A001: continue
                if getattr(msg, 'is_error_frame', False):
                    with self.lock: self.error_count += 1
                    continue

                raw = f"0x{msg.arbitration_id:03X} | {msg.data.hex().upper()} | {msg.timestamp:.3f}"
                with self.lock:
                    self.raw_log_lines.append(raw)
                    if len(self.raw_log_lines) > 200:
                        self.raw_log_lines.pop(0)

                if msg.arbitration_id not in known:
                    with self.lock: self.unknown_count += 1
                    continue

                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                except Exception as e:
                    print(f"Decode failed for 0x{msg.arbitration_id:03X}: {e}")
                    continue

                with self.lock:
                    self.signals[msg.arbitration_id].update({
                        name: {"v": val, "d": str(val), "u": "", "t": msg.timestamp}
                        for name, val in decoded.items()
                    })
                    # Force GUI update on first signal of new frame
                    if len(self.signals[msg.arbitration_id]) == len(decoded):
                        self.last_gui_update = 0

            except can.CanError:
                time.sleep(0.05)
            except Exception as e:
                print(f"[FATAL] {e}")
                time.sleep(0.1)

    # -------------------------------------------------
    # GUI Update
    # -------------------------------------------------
    def update_gui(self):
        if not self.bus_connected: return
        now = time.time()
        if now - self.last_gui_update < 0.1: return
        self.last_gui_update = now

        with self.lock:
            data = {k: list(v.items()) for k, v in self.signals.items()}
            raw = self.raw_log_lines[-8:]

        # Update regular tables
        for fid in [ID_727, ID_587, ID_107, ID_607, ID_CMD_BMS, ID_PDU_STATUS,
                    ID_HMI_STATUS, ID_PCU_COOL, ID_PCU_MOTOR, ID_PCU_POWER, ID_CCU_STATUS]:
            table = self.tables.get(fid)
            if not table: continue
            items = data.get(fid, [])
            try:
                table.setRowCount(len(items))
                for r, (name, d) in enumerate(items):
                    table.setItem(r, 0, QTableWidgetItem(name))
                    table.setItem(r, 1, QTableWidgetItem(d.get("d", "")))
                    table.setItem(r, 2, QTableWidgetItem(d.get("u", "")))
                    table.setItem(r, 3, QTableWidgetItem(f"{d.get('t',0):.3f}"))
                if self.first_fill[fid]:
                    table.resizeColumnsToContents()
                    self.first_fill[fid] = False
            except: pass

        # Update battery tabs
        for idx in [1, 2, 3]:
            table = self.battery_tabs.get(idx)
            if not table: continue
            frame_ids = {
                1: [0x400, 0x401, 0x403, 0x406, 0x405],
                2: [0x420, 0x421, 0x423, 0x426, 0x505],
                3: [0x440, 0x441, 0x443, 0x446, 0x605],
            }[idx]
            all_signals = []
            for fid in frame_ids:
                all_signals.extend(data.get(fid, []))
            try:
                table.setRowCount(len(all_signals))
                for r, (name, d) in enumerate(all_signals):
                    table.setItem(r, 0, QTableWidgetItem(name))
                    table.setItem(r, 1, QTableWidgetItem(d.get("d", "")))
                    table.setItem(r, 2, QTableWidgetItem(d.get("u", "")))
                    table.setItem(r, 3, QTableWidgetItem(f"{d.get('t',0):.3f}"))
                if self.first_fill.get(f"BT{idx}", True):
                    table.resizeColumnsToContents()
                    self.first_fill[f"BT{idx}"] = False
            except: pass

        # Update progress bars & alerts
        try:
            for idx, prefix in [(1, "BT1"), (2, "BT2"), (3, "BT3")]:
                dcl_id  = {1:0x400, 2:0x420, 3:0x440}[idx]
                curr_id = {1:0x401, 2:0x421, 3:0x441}[idx]
                temp_id = {1:0x403, 2:0x423, 3:0x443}[idx]
                fail_id = {1:0x406, 2:0x426, 3:0x446}[idx]
                riso_id = {1:0x405, 2:0x505, 3:0x605}[idx]

                # SOC
                soc = next((d["v"] for n,d in data.get(dcl_id, []) if n == f"{prefix}_SOC"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_SOC"))
                if bar: bar.setValue(int(soc))

                # Current
                curr = next((d["v"] for n,d in data.get(curr_id, []) if n == f"{prefix}_CURR"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_CURR"))
                if bar:
                    pct = int((curr + 3276) / 6552 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_CURR: {curr:+.0f}A")

                # Voltage
                volt = next((d["v"] for n,d in data.get(curr_id, []) if n == f"{prefix}_VOLT"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_VOLT"))
                if bar:
                    pct = int(volt / 655.3 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_VOLT: {volt:.1f}V")

                # Temp
                temp = next((d["v"] for n,d in data.get(temp_id, []) if n == f"{prefix}_TEMP"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_TEMP"))
                if bar:
                    pct = int((temp + 40) / 127 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_TEMP: {temp:.0f}°C")

                # DCL/CCL
                dcl = next((d["v"] for n,d in data.get(dcl_id, []) if n == f"{prefix}_DCL"), 0)
                ccl = next((d["v"] for n,d in data.get(dcl_id, []) if n == f"{prefix}_CCL"), 0)
                for sig, val in [(f"{prefix}_DCL", dcl), (f"{prefix}_CCL", ccl)]:
                    bar = self.bars.get((f"BT{idx}", sig))
                    if bar:
                        pct = int(val / 6553.5 * 100)
                        bar.setValue(max(0, min(100, pct)))
                        bar.setFormat(f"{sig}: {val:.0f}A")

                # RISO
                riso = next((d["v"] for n,d in data.get(riso_id, []) if n == f"{prefix}_RISO"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_RISO"))
                if bar:
                    pct = int(riso / 180 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_RISO: {riso} cells")

                # Alerts
                state = next((d["v"] for n,d in data.get(curr_id, []) if n == f"{prefix}_STATE"), 0)
                bal   = next((d["v"] for n,d in data.get(curr_id, []) if n == f"{prefix}_BALANCING"), 0)
                fail  = next((d["v"] for n,d in data.get(fail_id, []) if n == f"{prefix}_FAILURE"), 0)

                self.alerts[(f"BT{idx}", "state")].setText(f"STATE: {'ACTIVE' if state else 'IDLE'}")
                self.alerts[(f"BT{idx}", "state")].setStyleSheet("font-weight:bold;color:green;" if state else "font-weight:bold;color:orange;")

                self.alerts[(f"BT{idx}", "bal")].setText(f"BALANCING: {bal}/15")
                self.alerts[(f"BT{idx}", "bal")].setStyleSheet("font-weight:bold;color:red;" if bal > 0 else "font-weight:bold;color:green;")

                self.alerts[(f"BT{idx}", "fail")].setText(f"FAILURE: 0x{fail:02X}")
                self.alerts[(f"BT{idx}", "fail")].setStyleSheet("font-weight:bold;color:red;" if fail != 0 else "font-weight:bold;color:green;")

        except Exception as e:
            print("GUI update error:", e)

        # Raw log
        try:
            self.raw_log.clear()
            for line in raw:
                self.raw_log.append(line)
        except: pass

        # Status
        if self.error_count:
            self.status_label.setText(f"NOISE: {self.error_count}")
            self.status_label.setStyleSheet("color:orange;font-weight:bold;")
        else:
            self.status_label.setText("CONNECTED")
            self.status_label.setStyleSheet("color:green;font-weight:bold;")

    def closeEvent(self, event):
        self.disconnect_can()
        event.accept()

# =============================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CANMonitor()
    win.show()
    sys.exit(app.exec_())