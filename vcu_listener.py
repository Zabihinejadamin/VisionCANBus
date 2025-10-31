# vcu_gui_final.py
import sys
import cantools
import can
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout,
    QWidget, QTableWidget, QTableWidgetItem, QLabel, QTextEdit,
    QTabWidget, QProgressBar
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
ID_20B = 0x20B   # 523
ID_587 = 0x587   # 1415
ID_200 = 0x200   # 512 (BMS Status)
# ==============

class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor - 4 Frames (BULLETPROOF)")
        self.resize(1300, 800)

        # Load DBC
        try:
            self.db = cantools.database.load_file(DBC_FILE)
            print(f"DBC loaded: {len(self.db.messages)} messages")
        except Exception as e:
            print(f"DBC Error: {e}")
            traceback.print_exc()
            sys.exit(1)

        # CAN Bus
        try:
            self.bus = can.interface.Bus(channel=CHANNEL, bustype=BUSTYPE, bitrate=BITRATE)
            print(f"CAN bus initialized: {CHANNEL}")
        except Exception as e:
            print(f"CAN Error: {e}")
            traceback.print_exc()
            sys.exit(1)

        # Data containers
        self.signals_727 = {}
        self.signals_20b = {}
        self.signals_587 = {}
        self.signals_200 = {}
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

        # CAN Thread
        self.thread = threading.Thread(target=self.can_listener, daemon=True)
        self.thread.start()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Status
        self.status_label = QLabel("Running...")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.status_label)

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

        # === TAB 2: 0x20B ===
        tab2 = QWidget()
        l = QVBoxLayout(tab2)
        l.addWidget(QLabel("<h2>VCU to BMS (0x20B)</h2>"))
        self.table_20b = QTableWidget()
        self.table_20b.setColumnCount(4)
        self.table_20b.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        l.addWidget(self.table_20b)
        self.tabs.addTab(tab2, "0x20B - BMS")

        # === TAB 3: 0x587 ===
        tab3 = QWidget()
        l = QVBoxLayout(tab3)
        l.addWidget(QLabel("<h2>VCU to PDU (0x587)</h2>"))
        self.table_587 = QTableWidget()
        self.table_587.setColumnCount(4)
        self.table_587.setHorizontalHeaderLabels(["Relay", "Command", "Raw", "TS"])
        l.addWidget(self.table_587)
        self.tabs.addTab(tab3, "0x587 - PDU")

        # === TAB 4: 0x200 BMS STATUS ===
        tab4 = QWidget()
        l = QVBoxLayout(tab4)
        l.addWidget(QLabel("<h2>BMS to VCU Status (0x200)</h2>"))
        self.table_200 = QTableWidget()
        self.table_200.setColumnCount(4)
        self.table_200.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        l.addWidget(self.table_200)
        self.tabs.addTab(tab4, "0x200 - BMS Status")

        # === RAW LOG ===
        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(self.raw_log)

    def can_listener(self):
        while True:
            try:
                msg = self.bus.recv(timeout=1.0)
                if msg is None:
                    continue

                # === IGNORE 0x400A001 (PCAN FIRMWARE NOISE) ===
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

                # Reset error count
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

                    elif msg.arbitration_id == ID_20B:
                        decoded = self.db.decode_message(ID_20B, msg.data)
                        with self.lock:
                            for n, v in decoded.items():
                                self.signals_20b[n] = {"value": v, "unit": self.get_unit("VCU_BMS_COMMAND_FRAME", n), "ts": msg.timestamp}

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
                                # Format nicely
                                if isinstance(v, float):
                                    value_str = f"{v:.1f}"
                                else:
                                    value_str = str(v)
                                self.signals_200[n] = {"value": v, "display": value_str, "unit": unit, "ts": msg.timestamp}

                except Exception as e:
                    print("Decode error:", e)
                    traceback.print_exc()

            except Exception as e:
                print("Listener error:", e)
                time.sleep(0.1)

    def get_unit(self, msg_name, sig_name):
        try:
            msg = self.db.get_message_by_name(msg_name)
            sig = next(s for s in msg.signals if s.name == sig_name)
            return sig.unit or ""
        except:
            return ""

    def update_gui(self):
        with self.lock:
            s727 = list(self.signals_727.items())
            s20b = list(self.signals_20b.items())
            s587 = list(self.signals_587.items())
            s200 = list(self.signals_200.items())
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
        except Exception as e: print("GUI 727 error:", e)

        # === 0x20B ===
        try:
            self.table_20b.setRowCount(len(s20b))
            for r, (n, d) in enumerate(s20b):
                self.table_20b.setItem(r, 0, QTableWidgetItem(n))
                val = d.get("value")
                if n in ["VCU_BMS_CMD", "VCU_BMS_STATE_REQUEST"]:
                    try: val = self.db.get_message_by_frame_id(ID_20B).get_signal_value_table(n).get(val, f"0x{val:02X}")
                    except: pass
                self.table_20b.setItem(r, 1, QTableWidgetItem(str(val)))
                self.table_20b.setItem(r, 2, QTableWidgetItem(d.get("unit", "")))
                self.table_20b.setItem(r, 3, QTableWidgetItem(f"{d.get('ts', 0):.3f}"))
            self.table_20b.resizeColumnsToContents()
        except Exception as e: print("GUI 20B error:", e)

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
        except Exception as e: print("GUI 587 error:", e)

        # === 0x200 BMS STATUS ===
        try:
            self.table_200.setRowCount(len(s200))
            for r, (n, d) in enumerate(s200):
                self.table_200.setItem(r, 0, QTableWidgetItem(n.replace("BMS_", "")))
                self.table_200.setItem(r, 1, QTableWidgetItem(d.get("display", str(d.get("value", "")))))
                self.table_200.setItem(r, 2, QTableWidgetItem(d.get("unit", "")))
                self.table_200.setItem(r, 3, QTableWidgetItem(f"{d.get('ts', 0):.3f}"))
            self.table_200.resizeColumnsToContents()
        except Exception as e: print("GUI 200 error:", e)

        # === RAW LOG ===
        try:
            self.raw_log.clear()
            for line in raw:
                self.raw_log.append(line)
        except Exception as e: print("Raw log error:", e)

        # Status
        if self.error_count > 0:
            self.status_label.setText(f"ERRORS: {self.error_count} (ignored)")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.status_label.setText("Running...")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")

    def closeEvent(self, event):
        try: self.bus.shutdown()
        except: pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CANMonitor()
    window.show()
    sys.exit(app.exec_())