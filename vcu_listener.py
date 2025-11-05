# vcu_gui_final.py
import sys
import cantools
import can
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QLabel, QTextEdit, QTabWidget,
    QProgressBar, QPushButton
)
from PyQt5.QtCore import QTimer
import threading
import time
import traceback

# === CONFIG ===
DBC_FILE = 'DBC/vcu_updated.dbc'
BITRATE = 250000
CHANNEL = 'PCAN_USBBUS1'
BUSTYPE = 'pcan'

# === FRAME IDs ===
ID_727 = 0x727          # VCU → PCU
ID_587 = 0x587          # VCU → PDU
ID_107 = 0x107          # Pump Command
ID_607 = 0x607          # CCU/ZCU Command
ID_CMD_BMS = 0x4F0      # VCU → BMS
ID_PDU_STATUS = 0x580   # PDU Relay Status
ID_HMI_STATUS = 0x740   # HMI VCU Status
ID_PCU_COOL = 0x722     # PCU Cooling
ID_PCU_MOTOR = 0x720    # PCU Motor
ID_PCU_POWER = 0x724    # PCU Power
ID_CCU_STATUS = 0x600   # CCU Status
ID_TCU_CONTROL = 0x400  # TCU Control

# =============================================
class CANMonitor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VCU CAN Monitor – 12 Frames (CRASH-PROOF + 0x400 FIXED)")
        self.resize(2200, 1250)

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
        self.signals_107 = {}
        self.signals_607 = {}
        self.signals_cmd = {}
        self.signals_pdu = {}
        self.signals_hmi = {}
        self.signals_cool = {}
        self.signals_motor = {}
        self.signals_power = {}
        self.signals_ccu = {}
        self.signals_tcu = {}
        self.raw_log_lines = []
        self.error_count = 0
        self.last_error_print = 0
        self.unknown_count = 0
        self.last_table_update = 0

        self.lock = threading.Lock()
        self.init_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(100)

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

        # === TAB 1 – 0x727 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>VCU to PCU (0x727)</h2>"))
        self.table_727 = QTableWidget(); self.table_727.setColumnCount(4)
        self.table_727.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_727)
        self.throttle_bar = QProgressBar(); self.throttle_bar.setRange(0,100)
        self.throttle_bar.setFormat("Throttle: %p%")
        l.addWidget(self.throttle_bar)
        self.tabs.addTab(t,"0x727 – PCU")

        # === TAB 2 – 0x587 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>VCU to PDU (0x587)</h2>"))
        self.table_587 = QTableWidget(); self.table_587.setColumnCount(4)
        self.table_587.setHorizontalHeaderLabels(["Relay","Command","Raw","TS"])
        l.addWidget(self.table_587)
        self.tabs.addTab(t,"0x587 – PDU")

        # === TAB 3 – 0x107 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>Pump Command (0x107)</h2>"))
        self.table_107 = QTableWidget(); self.table_107.setColumnCount(4)
        self.table_107.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_107)
        self.pump_bar = QProgressBar(); self.pump_bar.setRange(0,100)
        self.pump_bar.setFormat("Pump: %p%")
        l.addWidget(self.pump_bar)
        self.tabs.addTab(t,"0x107 – Pump")

        # === TAB 4 – 0x607 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>CCU/ZCU Command (0x607)</h2>"))
        self.table_607 = QTableWidget(); self.table_607.setColumnCount(3)
        self.table_607.setHorizontalHeaderLabels(["Command","Status","TS"])
        l.addWidget(self.table_607)
        self.fresh_water_btn = QLabel("Fresh Water Pump: OFF")
        self.fresh_water_btn.setStyleSheet("font-weight:bold;color:red;")
        l.addWidget(self.fresh_water_btn)
        self.tabs.addTab(t,"0x607 – CCU/ZCU")

        # === TAB 5 – 0x4F0 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>VCU to BMS Command (0x4F0)</h2>"))
        self.table_cmd = QTableWidget(); self.table_cmd.setColumnCount(3)
        self.table_cmd.setHorizontalHeaderLabels(["Signal","State","TS"])
        l.addWidget(self.table_cmd)
        self.tabs.addTab(t,"0x4F0 – VCU Cmd")

        # === TAB 6 – 0x580 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>PDU Relay Status (0x580)</h2>"))
        self.table_pdu = QTableWidget(); self.table_pdu.setColumnCount(4)
        self.table_pdu.setHorizontalHeaderLabels(["Relay","CMD","STATUS","TS"])
        l.addWidget(self.table_pdu)
        self.tabs.addTab(t,"0x580 – PDU Relays")

        # === TAB 7 – 0x740 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>HMI VCU Status (0x740)</h2>"))
        hb = QHBoxLayout()
        self.soc_bar = QProgressBar(); self.soc_bar.setRange(0,100)
        self.soc_bar.setFormat("SOC: %p%")
        hb.addWidget(self.soc_bar)
        self.throttle_hmi_bar = QProgressBar(); self.throttle_hmi_bar.setRange(0,100)
        self.throttle_hmi_bar.setFormat("HMI Throttle: %p%")
        hb.addWidget(self.throttle_hmi_bar)
        l.addLayout(hb)
        self.beep_alert = QLabel("BEEPS: NONE")
        self.beep_alert.setStyleSheet("font-weight:bold;color:green;")
        l.addWidget(self.beep_alert)
        self.table_hmi = QTableWidget(); self.table_hmi.setColumnCount(4)
        self.table_hmi.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_hmi)
        self.tabs.addTab(t,"0x740 – HMI")

        # === TAB 8 – 0x722 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>PCU Cooling (0x722)</h2>"))
        self.flow_bar = QProgressBar(); self.flow_bar.setRange(0,255)
        self.flow_bar.setFormat("Water Flow: %v LPM")
        l.addWidget(self.flow_bar)
        self.table_cool = QTableWidget(); self.table_cool.setColumnCount(4)
        self.table_cool.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_cool)
        self.tabs.addTab(t,"0x722 – Cooling")

        # === TAB 9 – 0x720 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>PCU Motor (0x720)</h2>"))
        hb = QHBoxLayout()
        self.torque_bar = QProgressBar(); self.torque_bar.setRange(-1000,1000)
        self.torque_bar.setFormat("Torque: %v Nm"); self.torque_bar.setTextVisible(True)
        hb.addWidget(self.torque_bar)
        self.rpm_bar = QProgressBar(); self.rpm_bar.setRange(0,30000)
        self.rpm_bar.setFormat("RPM: %v")
        hb.addWidget(self.rpm_bar)
        l.addLayout(hb)
        self.motor_fault_alert = QLabel("PCU FAULTS: NONE")
        self.motor_fault_alert.setStyleSheet("font-weight:bold;color:green;")
        l.addWidget(self.motor_fault_alert)
        self.table_motor = QTableWidget(); self.table_motor.setColumnCount(4)
        self.table_motor.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_motor)
        self.tabs.addTab(t,"0x720 – Motor")

        # === TAB 10 – 0x724 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>PCU Power (0x724)</h2>"))
        hb = QHBoxLayout()
        self.hv_power_bar = QProgressBar(); self.hv_power_bar.setRange(-200,200)
        self.hv_power_bar.setFormat("HV Power: %v kW"); self.hv_power_bar.setTextVisible(True)
        hb.addWidget(self.hv_power_bar)
        self.current_bar = QProgressBar(); self.current_bar.setRange(-500,500)
        self.current_bar.setFormat("Current: %v A")
        hb.addWidget(self.current_bar)
        l.addLayout(hb)
        hb2 = QHBoxLayout()
        self.pump_pwm_bar = QProgressBar(); self.pump_pwm_bar.setRange(0,100)
        self.pump_pwm_bar.setFormat("Pump PWM: %p%")
        hb2.addWidget(self.pump_pwm_bar)
        self.trim_pos_bar = QProgressBar(); self.trim_pos_bar.setRange(0,100)
        self.trim_pos_bar.setFormat("Trim: %p%")
        hb2.addWidget(self.trim_pos_bar)
        l.addLayout(hb2)
        self.power_mode_alert = QLabel("PCU MODE: NORMAL")
        self.power_mode_alert.setStyleSheet("font-weight:bold;color:green;")
        l.addWidget(self.power_mode_alert)
        self.table_power = QTableWidget(); self.table_power.setColumnCount(4)
        self.table_power.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_power)
        self.tabs.addTab(t,"0x724 – Power")

        # === TAB 11 – 0x600 ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>CCU Status (0x600)</h2>"))
        hb = QHBoxLayout()
        self.glycol_flow_bar = QProgressBar(); self.glycol_flow_bar.setRange(0,255)
        self.glycol_flow_bar.setFormat("Glycol Flow: %v L/min")
        hb.addWidget(self.glycol_flow_bar)
        self.glycol_throttle_bar = QProgressBar(); self.glycol_throttle_bar.setRange(0,100)
        self.glycol_throttle_bar.setFormat("Glycol Throttle: %p%")
        hb.addWidget(self.glycol_throttle_bar)
        l.addLayout(hb)
        self.zcu_current_bar = QProgressBar(); self.zcu_current_bar.setRange(0,10)
        self.zcu_current_bar.setFormat("ZCU Current: %v A")
        l.addWidget(self.zcu_current_bar)
        self.ccu_error_alert = QLabel("CCU ERRORS: NONE")
        self.ccu_error_alert.setStyleSheet("font-weight:bold;color:green;")
        l.addWidget(self.ccu_error_alert)
        self.table_ccu = QTableWidget(); self.table_ccu.setColumnCount(4)
        self.table_ccu.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_ccu)
        self.tabs.addTab(t,"0x600 – CCU")

        # === TAB 12 – 0x400 (TCU) ===
        t = QWidget(); l = QVBoxLayout(t)
        l.addWidget(QLabel("<h2>TCU Control (0x400)</h2>"))
        hb = QHBoxLayout()
        self.tcu_throttle_bar = QProgressBar(); self.tcu_throttle_bar.setRange(-100,100)
        self.tcu_throttle_bar.setFormat("Throttle: %v%"); self.tcu_throttle_bar.setTextVisible(True)
        hb.addWidget(self.tcu_throttle_bar)
        self.tcu_analog_bar = QProgressBar(); self.tcu_analog_bar.setRange(0,5000)
        self.tcu_analog_bar.setFormat("Analog Pos: %v")
        hb.addWidget(self.tcu_analog_bar)
        l.addLayout(hb)

        self.tcu_relay_label = QLabel("Relay1: —, Relay2: —")
        self.tcu_relay_label.setStyleSheet("font-weight:bold;")
        l.addWidget(self.tcu_relay_label)

        self.tcu_status_alert = QLabel("TCU STATUS: NORMAL")
        self.tcu_status_alert.setStyleSheet("font-weight:bold;color:green;")
        l.addWidget(self.tcu_status_alert)

        self.table_tcu = QTableWidget(); self.table_tcu.setColumnCount(4)
        self.table_tcu.setHorizontalHeaderLabels(["Signal","Value","Unit","TS"])
        l.addWidget(self.table_tcu)
        self.tabs.addTab(t,"0x400 – TCU")

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
            print("CAN listener thread started")
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
                for d in (self.signals_727,self.signals_587,self.signals_107,
                          self.signals_607,self.signals_cmd,self.signals_pdu,
                          self.signals_hmi,self.signals_cool,self.signals_motor,
                          self.signals_power,self.signals_ccu,self.signals_tcu):
                    d.clear()
                self.raw_log_lines.clear()
                self.error_count = 0
                self.unknown_count = 0
        except Exception as e:
            print("CAN Disconnect Error:", e)

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------
    def safe_signal_value(self, value):
        if hasattr(value, 'name'):
            return value.name
        return value

    def int_or_zero(self, v):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return 0

    def get_unit(self, msg_name, sig_name):
        try:
            msg = self.db.get_message_by_name(msg_name)
            sig = next(s for s in msg.signals if s.name == sig_name)
            return sig.unit or ""
        except:
            return ""

    # -------------------------------------------------
    # Listener (CRASH-PROOF)
    # -------------------------------------------------
    def can_listener(self):
        while self.bus_connected:
            try:
                msg = self.bus.recv(timeout=0.5)
                if msg is None:
                    continue

                if msg.arbitration_id == 0x400A001:
                    continue

                if getattr(msg, 'is_error_frame', False):
                    with self.lock:
                        self.error_count += 1
                    now = time.time()
                    if now - self.last_error_print > 1.0:
                        print(f"[{now:.1f}] CAN ERROR FRAME #{self.error_count}")
                        self.last_error_print = now
                    continue

                raw = f"0x{msg.arbitration_id:03X} | {msg.data.hex().upper()} | {msg.timestamp:.3f}"
                with self.lock:
                    self.raw_log_lines.append(raw)
                    if len(self.raw_log_lines) > 200:
                        self.raw_log_lines = self.raw_log_lines[-200:]

                known_ids = {
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

                if msg.arbitration_id not in known_ids:
                    with self.lock:
                        self.unknown_count += 1
                    if self.unknown_count % 5000 == 0:
                        print(f"[INFO] {self.unknown_count} unknown messages ignored")
                    continue

                try:
                    decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                except Exception as e:
                    print(f"Decode failed for 0x{msg.arbitration_id:03X}: {e}")
                    continue

                with self.lock:
                    if msg.arbitration_id == ID_727:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("VCU_PCU_CONTROL_FRAME", n)
                            display = str(val)
                            if n == "VCU_PCU_THROTTLE":
                                display = f"{self.int_or_zero(val)}%"
                                self.throttle_bar.setValue(self.int_or_zero(val))
                            elif n == "VCU_PCU_PRND":
                                display = val
                            self.signals_727[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_587:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("VCU_PDU_COMMAND_FRAME", n)
                            display = "ON" if val else "OFF"
                            self.signals_587[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_107:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("PUMP_COMMAND_FRAME", n)
                            if n == "PUMP_THROTTLE":
                                display = f"{self.int_or_zero(val)}%"
                                self.pump_bar.setValue(self.int_or_zero(val))
                            elif n == "PUMP_FLOW":
                                display = f"{val:.1f}"
                            elif n == "PUMP_CMD_STATE":
                                display = {0:"STOPPED",1:"CW",2:"CCW"}.get(self.int_or_zero(val), f"UNKNOWN({val})")
                            else:
                                display = str(val)
                            self.signals_107[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_607:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("CCU_ZCU_COMMAND_FRAME", n)
                            display = "START" if val else "STOP"
                            if n == "CCU_CMD":
                                self.fresh_water_btn.setText(f"Fresh Water Pump: {display}")
                                self.fresh_water_btn.setStyleSheet("font-weight:bold;color:green;" if val else "font-weight:bold;color:red;")
                            self.signals_607[n] = {"value":val,"display":display,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_CMD_BMS:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            display = {0:"INIT",1:"SHUTDOWN",2:"CHARGE",3:"READY",
                                       4:"SLEEP",5:"OPERATIONAL",6:"ACTIVE",7:"FAILURE"
                                      }.get(self.int_or_zero(val), f"UNKNOWN({val})")
                            self.signals_cmd[n] = {"value":val,"display":display,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_PDU_STATUS:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            display = "ON" if val else "OFF"
                            if n == "PDU_MSG_COUNTER":
                                display = f"Counter: {val}"
                            self.signals_pdu[n] = {"value":val,"display":display,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_HMI_STATUS:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("HMI_VCU_STATUS", n)
                            if n == "HMI_VCU_GPS_SPEED":
                                display = f"{val:.1f}"
                            elif n == "HMI_VCU_POWER_CONSUMP":
                                display = f"{val:+.1f}"
                            elif n in ("HMI_VCU_SOC","HMI_VCU_THROTTLE"):
                                display = f"{self.int_or_zero(val)}"
                                if n == "HMI_VCU_SOC":
                                    self.soc_bar.setValue(self.int_or_zero(val))
                                else:
                                    self.throttle_hmi_bar.setValue(self.int_or_zero(val))
                            elif n == "HMI_VCU_12V_BAT":
                                display = f"{val:.1f}"
                            elif n.startswith("VCU_BEEP_"):
                                display = "BEEP" if val else "OK"
                            else:
                                display = str(val)
                            self.signals_hmi[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_PCU_COOL:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("PCU_COOLING_FRAME", n)
                            display = f"{val:.1f}"
                            if n == "PCU_WATERFLOW":
                                self.flow_bar.setValue(self.int_or_zero(val*10))
                            self.signals_cool[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_PCU_MOTOR:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("PCU_MOTOR_FRAME", n)
                            if n == "PCU_MOTOR_TORQUE":
                                display = f"{val:+.1f}"
                                self.torque_bar.setValue(self.int_or_zero(val*10))
                            elif n == "PCU_MOTOR_SPEED":
                                display = f"{self.int_or_zero(val)}"
                                self.rpm_bar.setValue(self.int_or_zero(val))
                            elif n == "PCU_DRIVE_SEL":
                                display = val
                            elif n.startswith("PCU_FAILURE_"):
                                display = "FAULT" if val else "OK"
                            else:
                                display = str(val)
                            self.signals_motor[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_PCU_POWER:
                        voltage = decoded.get("PCU_INVERTER_VOLTAGE",0)
                        current = decoded.get("PCU_INVERTER_CURRENT",0)
                        power_kw = voltage*current/1000.0 if voltage and current else 0
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("PCU_POWER_FRAME", n)
                            display = str(val)
                            if n == "PCU_INVERTER_CURRENT":
                                self.current_bar.setValue(self.int_or_zero(val))
                            elif n in ("PCU_PUMP_PWM","PCU_TRIM_POSITION"):
                                if n == "PCU_PUMP_PWM":
                                    self.pump_pwm_bar.setValue(self.int_or_zero(val))
                                else:
                                    self.trim_pos_bar.setValue(self.int_or_zero(val))
                            self.signals_power[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp,
                                                    "power_kw":power_kw if n=="PCU_INVERTER_CURRENT" else None}

                    elif msg.arbitration_id == ID_CCU_STATUS:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("CCU_STATUS_FRAME", n)
                            if n == "CCU_GLYCOL_FLOW":
                                display = f"{val:.1f}"
                                self.glycol_flow_bar.setValue(self.int_or_zero(val*10))
                            elif n == "CCU_GLYCOL_THROTTLE":
                                display = f"{self.int_or_zero(val)}"
                                self.glycol_throttle_bar.setValue(self.int_or_zero(val))
                            elif n == "CCU_ZCU_CURRENT":
                                display = f"{val:.1f}"
                                self.zcu_current_bar.setValue(self.int_or_zero(val*10))
                            elif n == "CCU_ERROR_CODES":
                                display = f"0x{self.int_or_zero(val):02X}"
                            else:
                                display = str(val)
                            self.signals_ccu[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

                    elif msg.arbitration_id == ID_TCU_CONTROL:
                        for n, v in decoded.items():
                            val = self.safe_signal_value(v)
                            unit = self.get_unit("TCU_CONTROL_FRAME", n)
                            display = str(val)
                            iv = self.int_or_zero(val)

                            if n == "TCU_ANALOG_POSITION":
                                display = f"{iv}"
                                self.tcu_analog_bar.setValue(iv)
                            elif n == "TCU_THROTTLE_POSITION":
                                display = f"{iv:+}"
                                self.tcu_throttle_bar.setValue(iv)
                            elif n == "TCU_RELAY1_STATE":
                                display = {0:"FREE",1:"OPEN",2:"CLOSE"}.get(iv, f"ERR{val}")
                            elif n == "TCU_RELAY2_STATE":
                                display = {0:"FREE",1:"OPEN",2:"CLOSE"}.get(iv, f"ERR{val}")
                            elif n == "TCU_STATUS":
                                bits = {0:"INC",1:"DEC",2:"MID",3:"FREE",4:"SETUP",7:"FLASH_FAIL"}
                                active = [bits[i] for i in range(8) if (iv & (1 << i))]
                                display = ", ".join(active) if active else "NORMAL"
                            else:
                                display = str(val)

                            self.signals_tcu[n] = {"value":val,"display":display,"unit":unit,"ts":msg.timestamp}

            except can.CanError as e:
                print(f"PCAN Error: {e}")
                time.sleep(0.1)
            except Exception as e:
                print(f"Listener error: {e}")
                time.sleep(0.1)

    # -------------------------------------------------
    # GUI update (THROTTLED)
    # -------------------------------------------------
    def update_gui(self):
        if not self.bus_connected:
            return

        now = time.time()
        if now - self.last_table_update < 0.1:
            return
        self.last_table_update = now

        with self.lock:
            s727 = list(self.signals_727.items())
            s587 = list(self.signals_587.items())
            s107 = list(self.signals_107.items())
            s607 = list(self.signals_607.items())
            s_cmd = list(self.signals_cmd.items())
            s_pdu = list(self.signals_pdu.items())
            s_hmi = list(self.signals_hmi.items())
            s_cool = list(self.signals_cool.items())
            s_motor = list(self.signals_motor.items())
            s_power = list(self.signals_power.items())
            s_ccu = list(self.signals_ccu.items())
            s_tcu = list(self.signals_tcu.items())
            raw = list(self.raw_log_lines[-8:])

        def fill(t, data, name_map=None):
            try:
                t.setRowCount(len(data))
                for r, (n, d) in enumerate(data):
                    name = name_map.get(n, n) if name_map else n
                    t.setItem(r,0,QTableWidgetItem(name))
                    t.setItem(r,1,QTableWidgetItem(d.get("display","")))
                    t.setItem(r,2,QTableWidgetItem(d.get("unit","")))
                    t.setItem(r,3,QTableWidgetItem(f"{d.get('ts',0):.3f}"))
                t.resizeColumnsToContents()
            except: pass

        fill(self.table_727, s727)
        fill(self.table_587, s587, {n:n.replace("VCU_PDU_","") for n in [x[0] for x in s587]})
        fill(self.table_107, s107)
        fill(self.table_607, s607)
        fill(self.table_cmd, s_cmd)
        fill(self.table_pdu, s_pdu)
        fill(self.table_hmi, s_hmi)
        fill(self.table_cool, s_cool)
        fill(self.table_motor, s_motor)
        fill(self.table_power, s_power)
        fill(self.table_ccu, s_ccu)
        fill(self.table_tcu, s_tcu)

        try:
            faults = [n.replace("PCU_FAILURE_","") for n,d in s_motor if n.startswith("PCU_FAILURE_") and d["value"]]
            self.motor_fault_alert.setText(f"PCU FAULTS: {', '.join(faults)}" if faults else "PCU FAULTS: NONE")
            self.motor_fault_alert.setStyleSheet("font-weight:bold;color:red;" if faults else "font-weight:bold;color:green;")

            beeps = [n.replace("VCU_BEEP_DIAG_","") for n,d in s_hmi if n.startswith("VCU_BEEP_") and d["value"]]
            self.beep_alert.setText(f"BEEPS: {', '.join(beeps)}" if beeps else "BEEPS: NONE")
            self.beep_alert.setStyleSheet("font-weight:bold;color:red;" if beeps else "font-weight:bold;color:green;")

            r1 = next((d["display"] for n,d in s_tcu if n=="TCU_RELAY1_STATE"),"—")
            r2 = next((d["display"] for n,d in s_tcu if n=="TCU_RELAY2_STATE"),"—")
            self.tcu_relay_label.setText(f"Relay1: {r1}, Relay2: {r2}")

            status = next((d["display"] for n,d in s_tcu if n=="TCU_STATUS"),"NORMAL")
            if "FLASH_FAIL" in status:
                self.tcu_status_alert.setText("TCU STATUS: FLASH FAILURE")
                self.tcu_status_alert.setStyleSheet("font-weight:bold;color:red;")
            elif "SETUP" in status:
                self.tcu_status_alert.setText("TCU STATUS: SETUP MODE")
                self.tcu_status_alert.setStyleSheet("font-weight:bold;color:orange;")
            else:
                self.tcu_status_alert.setText(f"TCU STATUS: {status}")
                self.tcu_status_alert.setStyleSheet("font-weight:bold;color:green;")

            err = next((self.int_or_zero(d["value"]) for n,d in s_ccu if n=="CCU_ERROR_CODES"),0)
            self.ccu_error_alert.setText(f"CCU ERRORS: 0x{err:02X}" if err else "CCU ERRORS: NONE")
            self.ccu_error_alert.setStyleSheet("font-weight:bold;color:red;" if err else "font-weight:bold;color:green;")
        except: pass

        try:
            self.raw_log.clear()
            for line in raw:
                self.raw_log.append(line)
        except: pass

        if self.error_count:
            self.status_label.setText(f"ERRORS: {self.error_count}")
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