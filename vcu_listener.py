# vcu_gui_final.py
import sys
import cantools
import can
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QLabel, QTextEdit, QTabWidget,
    QProgressBar, QPushButton
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

# === FRAME IDs ===
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
ID_TCU_CONTROL = 0x400

# =============================================
class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor – 12 Frames (NO FREEZE + 0x400)")
        self.resize(2200, 1250)
        self.bus = None
        self.bus_connected = False

        # Load DBC
        try:
            self.db = cantools.database.load_file(DBC_FILE)
            print(f"DBC loaded: {len(self.db.messages)} messages")
        except Exception as e:
            print(f"DBC Error (non-fatal): {e}")
            self.db = cantools.database.Database()

        # Data containers
        self.signals = {
            ID_727: {}, ID_587: {}, ID_107: {}, ID_607: {},
            ID_CMD_BMS: {}, ID_PDU_STATUS: {}, ID_HMI_STATUS: {},
            ID_PCU_COOL: {}, ID_PCU_MOTOR: {}, ID_PCU_POWER: {},
            ID_CCU_STATUS: {}, ID_TCU_CONTROL: {}
        }
        self.raw_log_lines = []
        self.error_count = 0
        self.last_error_print = 0
        self.unknown_count = 0
        self.last_gui_update = 0
        self.lock = threading.Lock()

        # GUI state
        self.first_fill = {k: True for k in self.signals}
        self.column_widths = {}

        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(100)  # 10 Hz max
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

        # Create tabs with tables
        self.tables = {}
        self.bars = {}
        self.alerts = {}

        tab_info = [
            (ID_727, "0x727 – PCU", "VCU to PCU (0x727)", ["Signal","Value","Unit","TS"], ["VCU_PCU_THROTTLE"]),
            (ID_587, "0x587 – PDU", "VCU to PDU (0x587)", ["Relay","Command","Raw","TS"], None),
            (ID_107, "0x107 – Pump", "Pump Command (0x107)", ["Signal","Value","Unit","TS"], ["PUMP_THROTTLE"]),
            (ID_607, "0x607 – CCU/ZCU", "CCU/ZCU Command (0x607)", ["Command","Status","TS"], None),
            (ID_CMD_BMS, "0x4F0 – VCU Cmd", "VCU to BMS Command (0x4F0)", ["Signal","State","TS"], None),
            (ID_PDU_STATUS, "0x580 – PDU Relays", "PDU Relay Status (0x580)", ["Relay","CMD","STATUS","TS"], None),
            (ID_HMI_STATUS, "0x740 – HMI", "HMI VCU Status (0x740)", ["Signal","Value","Unit","TS"], ["HMI_VCU_SOC", "HMI_VCU_THROTTLE"]),
            (ID_PCU_COOL, "0x722 – Cooling", "PCU Cooling (0x722)", ["Signal","Value","Unit","TS"], ["PCU_WATERFLOW"]),
            (ID_PCU_MOTOR, "0x720 – Motor", "PCU Motor (0x720)", ["Signal","Value","Unit","TS"], ["PCU_MOTOR_TORQUE", "PCU_MOTOR_SPEED"]),
            (ID_PCU_POWER, "0x724 – Power", "PCU Power (0x724)", ["Signal","Value","Unit","TS"], ["PCU_INVERTER_CURRENT", "PCU_PUMP_PWM", "PCU_TRIM_POSITION"]),
            (ID_CCU_STATUS, "0x600 – CCU", "CCU Status (0x600)", ["Signal","Value","Unit","TS"], ["CCU_GLYCOL_FLOW", "CCU_GLYCOL_THROTTLE", "CCU_ZCU_CURRENT"]),
            (ID_TCU_CONTROL, "0x400 – TCU", "TCU Control (0x400)", ["Signal","Value","Unit","TS"], ["TCU_THROTTLE_POSITION", "TCU_ANALOG_POSITION"]),
        ]

        for fid, tab_name, title, headers, progress_signals in tab_info:
            t = QWidget()
            l = QVBoxLayout(t)
            l.addWidget(QLabel(f"<h2>{title}</h2>"))

            table = QTableWidget()
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)
            self.tables[fid] = table
            l.addWidget(table)

            # Progress bars
            if progress_signals:
                hb = QHBoxLayout()
                for sig in progress_signals:
                    bar = QProgressBar()
                    bar.setTextVisible(True)
                    self.bars[(fid, sig)] = bar
                    hb.addWidget(bar)
                l.addLayout(hb)

            # Alerts
            if fid == ID_PCU_MOTOR:
                alert = QLabel("PCU FAULTS: NONE")
                alert.setStyleSheet("font-weight:bold;color:green;")
                self.alerts["motor_fault"] = alert
                l.addWidget(alert)
            elif fid == ID_HMI_STATUS:
                alert = QLabel("BEEPS: NONE")
                alert.setStyleSheet("font-weight:bold;color:green;")
                self.alerts["beep"] = alert
                l.addWidget(alert)
            elif fid == ID_TCU_CONTROL:
                relay_label = QLabel("Relay1: —, Relay2: —")
                relay_label.setStyleSheet("font-weight:bold;")
                self.alerts["tcu_relay"] = relay_label
                l.addWidget(relay_label)
                status_alert = QLabel("TCU STATUS: NORMAL")
                status_alert.setStyleSheet("font-weight:bold;color:green;")
                self.alerts["tcu_status"] = status_alert
                l.addWidget(status_alert)
            elif fid == ID_CCU_STATUS:
                alert = QLabel("CCU ERRORS: NONE")
                alert.setStyleSheet("font-weight:bold;color:green;")
                self.alerts["ccu_error"] = alert
                l.addWidget(alert)

            self.tabs.addTab(t, tab_name)

        # Raw log
        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(self.raw_log)

    # -------------------------------------------------
    # CAN control
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
    # Helpers
    # -------------------------------------------------
    def int_or_zero(self, v):
        try: return int(float(v))
        except: return 0

    def get_unit(self, msg_name, sig_name):
        try:
            msg = self.db.get_message_by_name(msg_name)
            sig = next(s for s in msg.signals if s.name == sig_name)
            return sig.unit or ""
        except: return ""

    # -------------------------------------------------
    # Manual TCU decode
    # -------------------------------------------------
    def manual_decode_tcu(self, msg):
        try:
            data = msg.data
            if len(data) < 8: return
            analog = int.from_bytes(data[0:2], 'little')
            relay1 = data[2] & 0x03
            relay2 = (data[2] >> 2) & 0x03
            throttle = data[4]
            if throttle > 127: throttle -= 256
            status = data[5]

            bits = {0:"INC",1:"DEC",2:"MID",3:"FREE",4:"SETUP",7:"FLASH_FAIL"}
            active = [bits.get(i, f"BIT{i}") for i in range(8) if status & (1 << i)]
            status_str = ", ".join(active) if active else "NORMAL"

            with self.lock:
                self.signals[ID_TCU_CONTROL].update({
                    "TCU_ANALOG_POSITION": {"v": analog, "d": str(analog), "u": "", "t": msg.timestamp},
                    "TCU_RELAY1_STATE": {"v": relay1, "d": {0:"FREE",1:"OPEN",2:"CLOSE"}.get(relay1, f"ERR{relay1}"), "u": "", "t": msg.timestamp},
                    "TCU_RELAY2_STATE": {"v": relay2, "d": {0:"FREE",1:"OPEN",2:"CLOSE"}.get(relay2, f"ERR{relay2}"), "u": "", "t": msg.timestamp},
                    "TCU_STATUS": {"v": status, "d": status_str, "u": "", "t": msg.timestamp},
                    "TCU_THROTTLE_POSITION": {"v": throttle, "d": f"{throttle:+}", "u": "%", "t": msg.timestamp},
                })
        except Exception as e:
            print(f"TCU decode error: {e}")

    # -------------------------------------------------
    # Listener
    # -------------------------------------------------
    def can_listener(self):
        known = {
            ID_727: "VCU_PCU_CONTROL_FRAME",
            ID_587: "VCU_PDU_COMMAND_FRAME",
            ID_107: "PUMP_COMMAND_FRAME",
            ID_607: "CCU_ZCU_COMMAND_FRAME",
            ID_CMD_BMS: "VCU_BMS_COMMAND_FRAME",
            ID_PDU_STATUS: "PDU_RELAY_STATUS",
            ID_HMI_STATUS: "HMI_VCU_STATUS",
            ID_PCU_COOL: "PCU_COOLING_FRAME",
            ID_PCU_MOTOR: "PCU_MOTOR_FRAME",
            ID_PCU_POWER: "PCU_POWER_FRAME",
            ID_CCU_STATUS: "CCU_STATUS_FRAME",
            ID_TCU_CONTROL: "TCU_CONTROL_FRAME",
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
                except:
                    if msg.arbitration_id == ID_TCU_CONTROL:
                        self.manual_decode_tcu(msg)
                    continue

                with self.lock:
                    self.signals[msg.arbitration_id].update({
                        name: {"v": val, "d": str(val), "u": "", "t": msg.timestamp}
                        for name, val in decoded.items()
                    })

            except can.CanError:
                time.sleep(0.05)
            except Exception as e:
                print(f"[FATAL] {e}")
                time.sleep(0.1)

    # -------------------------------------------------
    # GUI update (10 Hz, no freeze)
    # -------------------------------------------------
    def update_gui(self):
        if not self.bus_connected: return
        now = time.time()
        if now - self.last_gui_update < 0.1: return
        self.last_gui_update = now

        with self.lock:
            data = {k: list(v.items()) for k, v in self.signals.items()}
            raw = self.raw_log_lines[-8:]

        # Update tables
        for fid, items in data.items():
            table = self.tables[fid]
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

        # Update bars & alerts
        try:
            # Example: throttle
            if (ID_727, "VCU_PCU_THROTTLE") in self.bars:
                val = next((d["v"] for n,d in data[ID_727] if n=="VCU_PCU_THROTTLE"), 0)
                self.bars[(ID_727, "VCU_PCU_THROTTLE")].setValue(self.int_or_zero(val))

            # TCU status
            status = next((d["d"] for n,d in data[ID_TCU_CONTROL] if n=="TCU_STATUS"), "NORMAL")
            self.alerts["tcu_status"].setText(f"TCU STATUS: {status}")
            self.alerts["tcu_status"].setStyleSheet(
                "font-weight:bold;color:red;" if "FLASH_FAIL" in status
                else "font-weight:bold;color:orange;" if "SETUP" in status
                else "font-weight:bold;color:green;"
            )
        except: pass

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = CANMonitor()
    win.show()
    sys.exit(app.exec_())