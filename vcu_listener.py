# vcu_gui_final.py
import sys
import cantools
import can
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QTableWidget, QTableWidgetItem, QLabel, QTextEdit,
    QTabWidget, QProgressBar, QPushButton
)
from PyQt5.QtCore import QTimer, Qt
import threading
import time
import traceback

# === CONFIG ===
DBC_FILE = 'DBC/vcu_full.dbc'
BITRATE = 250000
CHANNEL = 'PCAN_USBBUS1'
BUSTYPE = 'pcan'

# === FRAME IDs FROM DBC ===
ID_727 = 0x727   # 1831
ID_587 = 0x587   # 1415
ID_200 = 0x200   # 512 (BMS Status)
ID_107 = 0x107   # 263 (Pump Command)
ID_607 = 0x607   # 1543 (CCU/ZCU Command)
# ==============

class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor - 5 Frames (CONNECT/DISCONNECT)")
        self.resize(1400, 850)

        # CAN Bus (initially None)
        self.bus = None
        self.bus_connected = False

        # Load DBC
        try:
            self.db = cantools.database.load_file(DBC_FILE)
            print(f"DBC loaded: {len(self.db.messages)} messages")
        except Exception as e:
            print(f"DBC Error: {e}")
            traceback.print_exc()
            sys.exit(1)

        # Data containers
        self.signals_727 = {}
        self.signals_587 = {}
        self.signals_200 = {}
        self.signals_107 = {}
        self.signals_607 = {}
        self.raw_log_lines = []
        self.error_count = 0
        self.last_error_print = 0

        # Thread lock
        self.lock = threading.Lock()

        # GUI
        self.init_ui()

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(100)

        # CAN Thread (starts only when connected)
        self.thread = None

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # === TOP BAR: CONNECT BUTTON + STATUS ===
        top_bar = QHBoxLayout()
        self.connect_btn = QPushButton("CONNECT CAN")
        self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.connect_btn.clicked.connect(self.toggle_can)
        top_bar.addWidget(self.connect_btn)

        self.status_label = QLabel("DISCONNECTED")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        top_bar.addWidget(self.status_label)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # === TAB 1: 0x727 ===
        tab1 = QWidget()
        l = QVBoxLayout(tab1)
        l.addWidget(QLabel("<h2>VCU to PCU (0x727)</h2>"))
        self.table_727 = QTableWidget()
        self.table_727.setColumnCount(4)
        self.table_727.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        l.addWidget(self.table_727)
        self.throttle_bar = QProgressBar()
        self.throttle_bar.setRange(0, 100)
        self.throttle_bar.setFormat("Throttle: %p%")
        l.addWidget(self.throttle_bar)
        self.tabs.addTab(tab1, "0x727 - PCU")

        # === TAB 2: 0x587 ===
        tab2 = QWidget()
        l = QVBoxLayout(tab2)
        l.addWidget(QLabel("<h2>VCU to PDU (0x587)</h2>"))
        self.table_587 = QTableWidget()
        self.table_587.setColumnCount(4)
        self.table_587.setHorizontalHeaderLabels(["Relay", "Command", "Raw", "TS"])
        l.addWidget(self.table_587)
        self.tabs.addTab(tab2, "0x587 - PDU")

        # === TAB 3: 0x200 BMS STATUS ===
        tab3 = QWidget()
        l = QVBoxLayout(tab3)
        l.addWidget(QLabel("<h2>BMS to VCU Status (0x200)</h2>"))
        self.table_200 = QTableWidget()
        self.table_200.setColumnCount(4)
        self.table_200.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        l.addWidget(self.table_200)
        self.tabs.addTab(tab3, "0x200 - BMS")

        # === TAB 4: 0x107 PUMP COMMAND ===
        tab4 = QWidget()
        l = QVBoxLayout(tab4)
        l.addWidget(QLabel("<h2>Pump Command (0x107)</h2>"))
        self.table_107 = QTableWidget()
        self.table_107.setColumnCount(4)
        self.table_107.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        l.addWidget(self.table_107)
        self.pump_bar = QProgressBar()
        self.pump_bar.setRange(0, 100)
        self.pump_bar.setFormat("Pump: %p%")
        l.addWidget(self.pump_bar)
        self.tabs.addTab(tab4, "0x107 - Pump")

        # === TAB 5: 0x607 CCU/ZCU COMMAND ===
        tab5 = QWidget()
        l = QVBoxLayout(tab5)
        l.addWidget(QLabel("<h2>CCU/ZCU Command (0x607)</h2>"))
        self.table_607 = QTableWidget()
        self.table_607.setColumnCount(3)
        self.table_607.setHorizontalHeaderLabels(["Command", "Status", "TS"])
        l.addWidget(self.table_607)
        self.fresh_water_btn = QLabel("Fresh Water Pump: OFF")
        self.fresh_water_btn.setStyleSheet("font-weight: bold; color: red;")
        l.addWidget(self.fresh_water_btn)
        self.tabs.addTab(tab5, "0x607 - CCU/ZCU")

        # === RAW LOG ===
        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(self.raw_log)

    def toggle_can(self):
        if not self.bus_connected:
            self.connect_can()
        else:
            self.disconnect_can()

    def connect_can(self):
        try:
            self.bus = can.interface.Bus(channel=CHANNEL, bustype=BUSTYPE, bitrate=BITRATE)
            print(f"CAN bus initialized: {CHANNEL}")
            self.bus_connected = True
            self.connect_btn.setText("DISCONNECT CAN")
            self.connect_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px;")
            self.status_label.setText("CONNECTED")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")

            # Start listener thread
            self.thread = threading.Thread(target=self.can_listener, daemon=True)
            self.thread.start()

        except Exception as e:
            print(f"CAN Connect Error: {e}")
            traceback.print_exc()
            self.status_label.setText("CONNECT FAILED")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def disconnect_can(self):
        try:
            if self.bus:
                self.bus.shutdown()
                self.bus = None
            self.bus_connected = False
            self.connect_btn.setText("CONNECT CAN")
            self.connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
            self.status_label.setText("DISCONNECTED")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

            # Clear all data
            with self.lock:
                self.signals_727.clear()
                self.signals_587.clear()
                self.signals_200.clear()
                self.signals_107.clear()
                self.signals_607.clear()
                self.raw_log_lines.clear()
                self.error_count = 0

        except Exception as e:
            print(f"CAN Disconnect Error: {e}")

    def can_listener(self):
        while self.bus_connected:
            try:
                msg = self.bus.recv(timeout=1.0)
                if msg is None:
                    continue

                # === IGNORE 0x400A001 ===
                if msg.arbitration_id == 0x400A001:
                    continue

                # === IGNORE ERROR FRAMES ===
                if getattr(msg, 'is_error_frame', False):
                    self.error_count += 1
                    now = time.time()
                    if now - self.last_error_print > 1.0:
                        print(f"[{now:.1f}] CAN ERROR FRAME #{self.error_count} (ignored)")
                        self.last_error_print = now
                    continue

                if self.error_count > 0:
                    self.error_count = 0

                raw = f"0x{msg.arbitration_id:03X} | {msg.data.hex().upper()} | {msg.timestamp:.3f}"

                with self.lock:
                    self.raw_log_lines.append(raw)
                    if len(self.raw_log_lines) > 200:
                        self.raw_log_lines = self.raw_log_lines[-200:]

                # === DECODE ===
                try:
                    if msg.arbitration_id == ID_727:
                        decoded = self.db.decode_message(ID_727, msg.data)
                        with self.lock:
                            for n, v in decoded.items():
                                self.signals_727[n] = {"value": v, "unit": self.get_unit("VCU_PCU_CONTROL_FRAME", n), "ts": msg.timestamp}

                    elif msg.arbitration_id == ID_587:
                        decoded = self.db.decode_message(ID_587, msg.data)
                        with self.lock:
                            for n, v in decoded.items():
                                self.signals_587[n] = {"value": v, "unit": self.get_unit("VCU_PDU_COMMAND_FRAME", n), "ts": msg.timestamp}

                    elif msg.arbitration_id == ID_200:
                        decoded = self.db.decode_message(ID_200, msg.data)
                        with self.lock:
                            for n, v in decoded.items():
                                unit = self.get_unit("BMS_STATUS_FRAME", n)
                                display = f"{v:.1f}" if isinstance(v, float) else str(v)
                                self.signals_200[n] = {"value": v, "display": display, "unit": unit, "ts": msg.timestamp}

                    elif msg.arbitration_id == ID_107:
                        decoded = self.db.decode_message(ID_107, msg.data)
                        with self.lock:
                            for n, v in decoded.items():
                                if n == "PUMP_THROTTLE":
                                    display = f"{v}%"
                                    self.pump_bar.setValue(int(v) if 0 <= v <= 100 else 0)
                                elif n == "PUMP_FLOW":
                                    display = f"{v:.1f}"
                                elif n == "PUMP_CMD_STATE":
                                    display = self.decode_pump_state(v)
                                else:
                                    display = str(v)
                                self.signals_107[n] = {"value": v, "display": display, "unit": self.get_unit("PUMP_COMMAND_FRAME", n), "ts": msg.timestamp}

                    elif msg.arbitration_id == ID_607:
                        decoded = self.db.decode_message(ID_607, msg.data)
                        with self.lock:
                            for n, v in decoded.items():
                                if n == "CCU_CMD":
                                    status = "START" if (v & 0x01) else "STOP"
                                    self.fresh_water_btn.setText(f"Fresh Water Pump: {status}")
                                    self.fresh_water_btn.setStyleSheet("font-weight: bold; color: green;" if status == "START" else "font-weight: bold; color: red;")
                                self.signals_607[n] = {"value": v, "display": self.decode_ccu_cmd(v), "ts": msg.timestamp}

                except Exception as e:
                    print("Decode error:", e)

            except Exception as e:
                if self.bus_connected:
                    print("Listener error:", e)
                time.sleep(0.1)

    def decode_pump_state(self, byte):
        if byte == 0x00: return "STOPPED"
        return "CW" if (byte & 0x01) else "CCW" if (byte & 0x02) else "UNKNOWN"

    def decode_ccu_cmd(self, byte):
        return "Fresh Water Pump START" if (byte & 0x01) else "Fresh Water Pump STOP"

    def get_unit(self, msg_name, sig_name):
        try:
            msg = self.db.get_message_by_name(msg_name)
            sig = next(s for s in msg.signals if s.name == sig_name)
            return sig.unit or ""
        except:
            return ""

    def update_gui(self):
        if not self.bus_connected:
            return

        with self.lock:
            s727 = list(self.signals_727.items())
            s587 = list(self.signals_587.items())
            s200 = list(self.signals_200.items())
            s107 = list(self.signals_107.items())
            s607 = list(self.signals_607.items())
            raw = list(self.raw_log_lines[-8:])

        # === 0x727 ===
        try:
            self.table_727.setRowCount(len(s727))
            for r, (n, d) in enumerate(s727):
                self.table_727.setItem(r, 0, QTableWidgetItem(n))
                val = d.get("value")
                if n == "VCU_PCU_PRND":
                    try: val = self.db.get_message_by_frame_id(ID_727).get_signal_value_table(n).get(val, f"0x{val:02X}")
                    except: pass
                elif n == "VCU_PCU_THROTTLE":
                    try:
                        v = int(d.get("value", 0))
                        val = f"{v}%"
                        self.throttle_bar.setValue(v if 0 <= v <= 100 else 0)
                    except: val = str(d.get("value", ""))
                self.table_727.setItem(r, 1, QTableWidgetItem(str(val)))
                self.table_727.setItem(r, 2, QTableWidgetItem(d.get("unit", "")))
                self.table_727.setItem(r, 3, QTableWidgetItem(f"{d.get('ts', 0):.3f}"))
            self.table_727.resizeColumnsToContents()
        except Exception as e: pass

        # === 0x587 ===
        try:
            self.table_587.setRowCount(len(s587))
            for r, (n, d) in enumerate(s587):
                raw = d.get("value")
                cmd = ""
                try: cmd = self.db.get_message_by_frame_id(ID_587).get_signal_value_table(n).get(raw, f"0x{raw:02X}")
                except: cmd = str(raw)
                self.table_587.setItem(r, 0, QTableWidgetItem(n.replace("VCU_PDU_", "")))
                self.table_587.setItem(r, 1, QTableWidgetItem(cmd))
                item = QTableWidgetItem(f"{raw}")
                item.setTextAlignment(Qt.AlignCenter)
                self.table_587.setItem(r, 2, item)
                self.table_587.setItem(r, 3, QTableWidgetItem(f"{d.get('ts', 0):.3f}"))
            self.table_587.resizeColumnsToContents()
        except Exception as e: pass

        # === 0x200 BMS STATUS ===
        try:
            self.table_200.setRowCount(len(s200))
            for r, (n, d) in enumerate(s200):
                self.table_200.setItem(r, 0, QTableWidgetItem(n.replace("BMS_", "")))
                self.table_200.setItem(r, 1, QTableWidgetItem(d.get("display", str(d.get("value", "")))))
                self.table_200.setItem(r, 2, QTableWidgetItem(d.get("unit", "")))
                self.table_200.setItem(r, 3, QTableWidgetItem(f"{d.get('ts', 0):.3f}"))
            self.table_200.resizeColumnsToContents()
        except Exception as e: pass

        # === 0x107 PUMP COMMAND ===
        try:
            self.table_107.setRowCount(len(s107))
            for r, (n, d) in enumerate(s107):
                self.table_107.setItem(r, 0, QTableWidgetItem(n.replace("PUMP_", "")))
                self.table_107.setItem(r, 1, QTableWidgetItem(d.get("display", str(d.get("value", "")))))
                self.table_107.setItem(r, 2, QTableWidgetItem(d.get("unit", "")))
                self.table_107.setItem(r, 3, QTableWidgetItem(f"{d.get('ts', 0):.3f}"))
            self.table_107.resizeColumnsToContents()
        except Exception as e: pass

        # === 0x607 CCU/ZCU COMMAND ===
        try:
            self.table_607.setRowCount(len(s607))
            for r, (n, d) in enumerate(s607):
                self.table_607.setItem(r, 0, QTableWidgetItem(n))
                self.table_607.setItem(r, 1, QTableWidgetItem(d.get("display", "")))
                self.table_607.setItem(r, 2, QTableWidgetItem(f"{d.get('ts', 0):.3f}"))
            self.table_607.resizeColumnsToContents()
        except Exception as e: pass

        # === RAW LOG ===
        try:
            self.raw_log.clear()
            for line in raw:
                self.raw_log.append(line)
        except Exception as e: pass

        # Status
        if self.error_count > 0:
            self.status_label.setText(f"ERRORS: {self.error_count}")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.status_label.setText("CONNECTED")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")

    def closeEvent(self, event):
        self.disconnect_can()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CANMonitor()
    window.show()
    sys.exit(app.exec_())