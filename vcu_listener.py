# vcu_gui.py
import sys
import cantools
import can
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QTableWidget, QTableWidgetItem, QLabel, QTextEdit,
    QTabWidget, QFrame, QProgressBar
)
from PyQt5.QtCore import QTimer, Qt
from collections import defaultdict
import threading

# === CONFIG ===
DBC_FILE = 'DBC/vcu_full.dbc'
BITRATE = 250000
CHANNEL = 'PCAN_USBBUS1'
BUSTYPE = 'pcan'
# ==============

class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor - 3 Frames")
        self.resize(1200, 750)

        # Load DBC
        try:
            self.db = cantools.database.load_file(DBC_FILE)
            print(f"DBC loaded: {len(self.db.messages)} messages")
        except Exception as e:
            print(f"DBC Error: {e}")
            sys.exit(1)

        # CAN Bus
        try:
            self.bus = can.interface.Bus(channel=CHANNEL, bustype=BUSTYPE, bitrate=BITRATE)
            print(f"CAN bus initialized: {CHANNEL}")
        except Exception as e:
            print(f"CAN Error: {e}")
            sys.exit(1)

        # Data
        self.signals_727 = {}
        self.signals_20b = {}
        self.signals_587 = {}
        self.raw_log_lines = []

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

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # === TAB 1: 0x727 ===
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.addWidget(QLabel("<h2>VCU → PCU (0x727)</h2>"))
        self.table_727 = QTableWidget()
        self.table_727.setColumnCount(4)
        self.table_727.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        tab1_layout.addWidget(self.table_727)
        self.throttle_bar = QProgressBar()
        self.throttle_bar.setRange(0, 100)
        self.throttle_bar.setFormat("Throttle: %p%")
        self.throttle_bar.setTextVisible(True)
        tab1_layout.addWidget(self.throttle_bar)
        self.tabs.addTab(tab1, "0x727 - PCU")

        # === TAB 2: 0x20B ===
        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.addWidget(QLabel("<h2>VCU → BMS (0x20B)</h2>"))
        self.table_20b = QTableWidget()
        self.table_20b.setColumnCount(4)
        self.table_20b.setHorizontalHeaderLabels(["Signal", "Value", "Unit", "TS"])
        tab2_layout.addWidget(self.table_20b)
        self.tabs.addTab(tab2, "0x20B - BMS")

        # === TAB 3: 0x587 ===
        tab3 = QWidget()
        tab3_layout = QVBoxLayout(tab3)
        tab3_layout.addWidget(QLabel("<h2>VCU → PDU (0x587)</h2>"))
        self.table_587 = QTableWidget()
        self.table_587.setColumnCount(4)
        self.table_587.setHorizontalHeaderLabels(["Relay", "Command", "", "TS"])
        tab3_layout.addWidget(self.table_587)
        self.tabs.addTab(tab3, "0x587 - PDU")

        # === RAW LOG ===
        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setMaximumHeight(120)
        layout.addWidget(self.raw_log)

    def can_listener(self):
        while True:
            msg = self.bus.recv(timeout=1.0)
            if msg is None:
                continue

            raw = f"0x{msg.arbitration_id:03X} | {msg.data.hex().upper()} | {msg.timestamp:.3f}"
            self.raw_log_lines.append(raw)
            if len(self.raw_log_lines) > 50:
                self.raw_log_lines.pop(0)

            # Decode 0x727
            if msg.arbitration_id == 0x727:
                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                    for sig_name, value in decoded.items():
                        self.signals_727[sig_name] = {
                            "value": value,
                            "unit": self.get_unit("VCU_PCU_CONTROL_FRAME", sig_name),
                            "ts": msg.timestamp
                        }
                except: pass

            # Decode 0x20B
            elif msg.arbitration_id == 0x20B:
                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                    for sig_name, value in decoded.items():
                        self.signals_20b[sig_name] = {
                            "value": value,
                            "unit": self.get_unit("VCU_BMS_COMMAND_FRAME", sig_name),
                            "ts": msg.timestamp
                        }
                except: pass

            # Decode 0x587
            elif msg.arbitration_id == 0x587:
                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                    for sig_name, value in decoded.items():
                        self.signals_587[sig_name] = {
                            "value": value,
                            "unit": self.get_unit("VCU_PDU_COMMAND_FRAME", sig_name),
                            "ts": msg.timestamp
                        }
                except: pass

    def get_unit(self, msg_name, sig_name):
        try:
            msg = self.db.get_message_by_name(msg_name)
            sig = next(s for s in msg.signals if s.name == sig_name)
            return sig.unit or ""
        except:
            return ""

    def update_gui(self):
        # === 0x727 ===
        self.table_727.setRowCount(len(self.signals_727))
        row = 0
        for sig_name, data in self.signals_727.items():
            self.table_727.setItem(row, 0, QTableWidgetItem(sig_name))
            val = data["value"]
            if sig_name == "VCU_PCU_PRND":
                prnd_map = {1: "P", 2: "R", 4: "N", 8: "D"}
                val = prnd_map.get(val, f"0x{val:02X}")
            elif sig_name == "VCU_PCU_THROTTLE":
                val = f"{val}%"
                self.throttle_bar.setValue(data["value"] if data["value"] <= 100 else 0)
            self.table_727.setItem(row, 1, QTableWidgetItem(str(val)))
            self.table_727.setItem(row, 2, QTableWidgetItem(data["unit"]))
            self.table_727.setItem(row, 3, QTableWidgetItem(f"{data['ts']:.3f}"))
            row += 1
        self.table_727.resizeColumnsToContents()

        # === 0x20B ===
        self.table_20b.setRowCount(len(self.signals_20b))
        row = 0
        for sig_name, data in self.signals_20b.items():
            self.table_20b.setItem(row, 0, QTableWidgetItem(sig_name))
            val = data["value"]
            if sig_name == "VCU_BMS_CMD":
                val = ["NoCmd", "SwitchOn", "SwitchOff"].get(val, f"0x{val:02X}")
            elif sig_name == "VCU_BMS_STATE_REQUEST":
                states = ["NoRequest", "Idle", "HV_Active", "Charge", "Fault_Shutdown"]
                val = states[val] if val < len(states) else f"0x{val:02X}"
            self.table_20b.setItem(row, 1, QTableWidgetItem(str(val)))
            self.table_20b.setItem(row, 2, QTableWidgetItem(data["unit"]))
            self.table_20b.setItem(row, 3, QTableWidgetItem(f"{data['ts']:.3f}"))
            row += 1
        self.table_20b.resizeColumnsToContents()

        # === 0x587 ===
        self.table_587.setRowCount(len(self.signals_587))
        row = 0
        for sig_name, data in self.signals_587.items():
            self.table_587.setItem(row, 0, QTableWidgetItem(sig_name.replace("VCU_PDU_", "")))
            val = data["value"]
            if sig_name == "VCU_PDU_CMD":
                val = "Switch" if val else "NoCmd"
            else:
                val = "Close" if val else "Open"
            self.table_587.setItem(row, 1, QTableWidgetItem(val))
            self.table_587.setItem(row, 2, QTableWidgetItem(""))
            self.table_587.setItem(row, 3, QTableWidgetItem(f"{data['ts']:.3f}"))
            row += 1
        self.table_587.resizeColumnsToContents()

        # === RAW LOG ===
        self.raw_log.clear()
        for line in self.raw_log_lines[-8:]:
            self.raw_log.append(line)

    def closeEvent(self, event):
        self.bus.shutdown()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CANMonitor()
    window.show()
    sys.exit(app.exec_())