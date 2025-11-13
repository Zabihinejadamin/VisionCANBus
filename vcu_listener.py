# vcu_gui_final.py
# FULL WORKING – 11 FRAMES + 0x72E ZCU PUMP (6 signals) + 3 BATTERIES
# FIXED: Decode using DBC frame_id (1838), FULL DEBUG, NO CRASHES
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
ID_ZCU_PUMP = 0x72E  # ← ZCU PUMP STATUS

# === BATTERY FRAME IDs (Hex) ===
ID_BT1_DCL = 0x400  # 1024
ID_BT1_CURR = 0x401  # 1025
ID_BT1_TEMP = 0x403  # 1027
ID_BT1_FAIL = 0x406  # 1030
ID_BT1_RISO = 0x405  # 1029
ID_BT2_DCL = 0x420  # 1056
ID_BT2_CURR = 0x421  # 1057
ID_BT2_TEMP = 0x423  # 1059
ID_BT2_FAIL = 0x426  # 1062
ID_BT2_RISO = 0x505  # 1285
ID_BT3_DCL = 0x440  # 1088
ID_BT3_CURR = 0x441  # 1089
ID_BT3_TEMP = 0x443  # 1091
ID_BT3_FAIL = 0x446  # 1094
ID_BT3_RISO = 0x605  # 1541

# =============================================
class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor – 3 Batteries + 11 Frames + ZCU Pump")
        self.resize(2800, 1400)
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
            print(f"\nDBC LOADED: {len(self.db.messages)} messages")
            for m in self.db.messages:
                print(f"  → {m.frame_id} | {m.name} | {m.length} bytes")
        except Exception as e:
            print(f"DBC LOAD ERROR: {e}")
            self.db = cantools.database.Database()

        # === DATA CONTAINERS (HEX IDs) ===
        self.signals = {
            ID_727: {}, ID_587: {}, ID_107: {}, ID_607: {}, ID_CMD_BMS: {},
            ID_PDU_STATUS: {}, ID_HMI_STATUS: {}, ID_PCU_COOL: {}, ID_PCU_MOTOR: {}, ID_PCU_POWER: {}, ID_CCU_STATUS: {},
            ID_ZCU_PUMP: {},  # ← ZCU PUMP
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
        self.create_tab(ID_CCU_STATUS, "0x600 – CCU", "CCU Status", ["Signal","Value","Unit","TS"], ["CCU_GLYCOL_FLOW", "CCU_GLYCOL_THROTTLE", "CCU_ZCU_CURRENT"])

        # === ZCU Pump Status ===
        self.create_tab(ID_ZCU_PUMP, "0x72E – ZCU Pump", "ZCU Pump Status",
                        ["Signal","Value","Unit","TS"],
                        ["Current", "Temp_CPU", "Temp_Mos", "Voltage", "Power"])

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

        # === ZCU PUMP SPECIAL ===
        if fid == ID_ZCU_PUMP:
            grid = QGridLayout()
            alerts = [
                ("PUMP DIR", "zcu_dir"),
                ("CAN BUS", "zcu_can"),
                ("PUMP MODE", "zcu_mode"),
            ]
            row = 0
            for label, key in alerts:
                lbl = QLabel(f"{label}: —")
                lbl.setStyleSheet("font-weight:bold;")
                self.alerts[(fid, key)] = lbl
                grid.addWidget(QLabel(label + ":"), row, 0)
                grid.addWidget(lbl, row, 1)
                row += 1
            l.addLayout(grid)

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
            print("\nCAN LISTENER STARTED\n")
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
    # CAN Listener (WITH FULL DEBUG)
    # -------------------------------------------------
    def can_listener(self):
        # === HEX → DBC FRAME ID MAPPING (MUST MATCH DBC) ===
        HEX_TO_DBC_ID = {
            0x727: 1831, 0x587: 1415, 0x107: 263, 0x607: 1543, 0x4F0: 1264,
            0x580: 1408, 0x740: 1856, 0x722: 1826, 0x720: 1824, 0x724: 1828, 0x600: 1536,
            0x72E: 1838,  # ← CRITICAL: MUST BE 1838 IN DBC
            # Batteries
            0x400: 1024, 0x401: 1025, 0x403: 1027, 0x406: 1030, 0x405: 1029,
            0x420: 1056, 0x421: 1057, 0x423: 1059, 0x426: 1062, 0x505: 1285,
            0x440: 1088, 0x441: 1089, 0x443: 1091, 0x446: 1094, 0x605: 1541,
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

                dbc_id = HEX_TO_DBC_ID.get(msg.arbitration_id)
                if dbc_id is None:
                    with self.lock: self.unknown_count += 1
                    continue

                print(f"\n[DECODE] 0x{msg.arbitration_id:03X} → DBC {dbc_id} | {msg.data.hex().upper()}")

                try:
                    decoded = self.db.decode_message(dbc_id, msg.data)
                    print(f"  → SUCCESS: {len(decoded)} signals")
                    for name, val in decoded.items():
                        print(f"    • {name} = {val}")
                except Exception as e:
                    print(f"  → FAILED: {e}")
                    try:
                        m = self.db.get_message_by_frame_id(dbc_id)
                        print(f"  → DBC HAS: {m.name} | Signals: {[s.name for s in m.signals]}")
                    except:
                        print(f"  → NO MESSAGE ID {dbc_id} IN DBC!")
                    continue

                # Get unit from DBC
                try:
                    msg_obj = self.db.get_message_by_frame_id(dbc_id)
                    unit_map = {s.name: s.unit for s in msg_obj.signals}
                except:
                    unit_map = {}

                with self.lock:
                    self.signals[msg.arbitration_id].update({
                        name: {
                            "v": val,
                            "d": f"{val:.2f}" if isinstance(val, float) else str(val),
                            "u": unit_map.get(name, ""),
                            "t": msg.timestamp
                        }
                        for name, val in decoded.items()
                    })
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
        for fid in [ID_727, ID_587, ID_107, ID_607, ID_CMD_BMS, ID_PDU_STATUS, ID_HMI_STATUS, ID_PCU_COOL, ID_PCU_MOTOR, ID_PCU_POWER, ID_CCU_STATUS, ID_ZCU_PUMP]:
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
            # === ZCU PUMP UPDATE ===
            fid = ID_ZCU_PUMP
            curr = next((d["v"] for n,d in data.get(fid, []) if n == "Current"), 0)
            bar = self.bars.get((fid, "Current"))
            if bar:
                pct = int(curr / 50.8 * 100)
                bar.setValue(max(0, min(100, pct)))
                bar.setFormat(f"Current: {curr:.1f}A")

            temp_cpu = next((d["v"] for n,d in data.get(fid, []) if n == "Temp_CPU"), 0)
            bar = self.bars.get((fid, "Temp_CPU"))
            if bar:
                pct = int((temp_cpu + 40) / 255 * 100)
                bar.setValue(max(0, min(100, pct)))
                bar.setFormat(f"Temp_CPU: {temp_cpu:.0f}°C")

            temp_mos = next((d["v"] for n,d in data.get(fid, []) if n == "Temp_Mos"), 0)
            bar = self.bars.get((fid, "Temp_Mos"))
            if bar:
                pct = int((temp_mos + 40) / 255 * 100)
                bar.setValue(max(0, min(100, pct)))
                bar.setFormat(f"Temp_Mos: {temp_mos:.0f}°C")

            volt = next((d["v"] for n,d in data.get(fid, []) if n == "Voltage"), 0)
            bar = self.bars.get((fid, "Voltage"))
            if bar:
                pct = int(volt / 25.5 * 100)
                bar.setValue(max(0, min(100, pct)))
                bar.setFormat(f"Voltage: {volt:.1f}V")

            power = next((d["v"] for n,d in data.get(fid, []) if n == "Power"), 0)
            bar = self.bars.get((fid, "Power"))
            if bar:
                pct = int(power / 6553.5 * 100)
                bar.setValue(max(0, min(100, pct)))
                bar.setFormat(f"Power: {power:.1f}W")

            status = next((d["v"] for n,d in data.get(fid, []) if n == "Status"), 0)
            dir_text = "Clockwise" if (status & 0x01) == 0 else "Counter-Clockwise"
            self.alerts[(fid, "zcu_dir")].setText(dir_text)
            self.alerts[(fid, "zcu_dir")].setStyleSheet("font-weight:bold;color:green;")

            can_text = "OK" if (status & 0x02) == 0 else "TIMEOUT"
            color = "green" if (status & 0x02) == 0 else "red"
            self.alerts[(fid, "zcu_can")].setText(can_text)
            self.alerts[(fid, "zcu_can")].setStyleSheet(f"font-weight:bold;color:{color};")

            mode = (status >> 3) & 0x03
            mode_text = ["Unknown", "Nominal", "Derated", "Critical"][mode]
            color = ["gray", "green", "orange", "red"][mode]
            self.alerts[(fid, "zcu_mode")].setText(mode_text)
            self.alerts[(fid, "zcu_mode")].setStyleSheet(f"font-weight:bold;color:{color};")

            # === BATTERIES (unchanged) ===
            for idx, prefix in [(1, "BT1"), (2, "BT2"), (3, "BT3")]:
                dcl_id = {1:0x400, 2:0x420, 3:0x440}[idx]
                curr_id = {1:0x401, 2:0x421, 3:0x441}[idx]
                temp_id = {1:0x403, 2:0x423, 3:0x443}[idx]
                fail_id = {1:0x406, 2:0x426, 3:0x446}[idx]
                riso_id = {1:0x405, 2:0x505, 3:0x605}[idx]

                soc = next((d["v"] for n,d in data.get(dcl_id, []) if n == f"{prefix}_SOC"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_SOC"))
                if bar: bar.setValue(int(soc))

                curr = next((d["v"] for n,d in data.get(curr_id, []) if n == f"{prefix}_CURR"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_CURR"))
                if bar:
                    pct = int((curr + 3276) / 6552 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_CURR: {curr:+.0f}A")

                volt = next((d["v"] for n,d in data.get(curr_id, []) if n == f"{prefix}_VOLT"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_VOLT"))
                if bar:
                    pct = int(volt / 655.3 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_VOLT: {volt:.1f}V")

                temp = next((d["v"] for n,d in data.get(temp_id, []) if n == f"{prefix}_TEMP"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_TEMP"))
                if bar:
                    pct = int((temp + 40) / 127 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_TEMP: {temp:.0f}°C")

                dcl = next((d["v"] for n,d in data.get(dcl_id, []) if n == f"{prefix}_DCL"), 0)
                ccl = next((d["v"] for n,d in data.get(dcl_id, []) if n == f"{prefix}_CCL"), 0)
                for sig, val in [(f"{prefix}_DCL", dcl), (f"{prefix}_CCL", ccl)]:
                    bar = self.bars.get((f"BT{idx}", sig))
                    if bar:
                        pct = int(val / 6553.5 * 100)
                        bar.setValue(max(0, min(100, pct)))
                        bar.setFormat(f"{sig}: {val:.0f}A")

                riso = next((d["v"] for n,d in data.get(riso_id, []) if n == f"{prefix}_RISO"), 0)
                bar = self.bars.get((f"BT{idx}", f"{prefix}_RISO"))
                if bar:
                    pct = int(riso / 180 * 100)
                    bar.setValue(max(0, min(100, pct)))
                    bar.setFormat(f"{prefix}_RISO: {riso} cells")

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