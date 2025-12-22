#!/usr/bin/env python3
"""
Graphical CAN Monitor - Python GUI version of RetainVar Monitor

This script provides a graphical interface for CAN communication,
similar to the original C++ Borland Builder application.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import sys
import os

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from can_communication import (
        RetainVarMonitor, CANResult, BaudRate, CANMessage,
        MessageType, BoardData
    )
except ImportError as e:
    print(f"Error importing can_communication: {e}")
    print("Make sure can_communication.py is in the same directory")
    sys.exit(1)


class CANSettingsWindow:
    """Settings window for CAN configuration"""

    def __init__(self, root, callback):
        self.root = root
        self.callback = callback
        self.root.title("CAN Communication Settings")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        # Center the window
        self.center_window()

        self.create_widgets()

    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def create_widgets(self):
        """Create the settings window widgets"""
        # Title
        title_label = ttk.Label(self.root, text="CAN Communication Settings",
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=20)

        # CAN Interface selection
        ttk.Label(self.root, text="CAN Interface:").pack(anchor="w", padx=20)
        self.interface_var = tk.StringVar(value="PCAN_USBBUS1")
        interface_combo = ttk.Combobox(self.root, textvariable=self.interface_var,
                                     values=["PCAN_USBBUS1", "PCAN_USBBUS2", "PCAN_USBBUS3",
                                            "PCAN_USBBUS4", "can0", "can1", "can2", "can3"])
        interface_combo.pack(fill="x", padx=20, pady=(0, 10))

        # Baud rate selection
        ttk.Label(self.root, text="Baud Rate:").pack(anchor="w", padx=20)
        self.baud_var = tk.StringVar(value="250 kBit/s")
        baud_combo = ttk.Combobox(self.root, textvariable=self.baud_var,
                                values=["1 MBit/s", "500 kBit/s", "250 kBit/s",
                                       "125 kBit/s", "100 kBit/s", "50 kBit/s"])
        baud_combo.pack(fill="x", padx=20, pady=(0, 20))

        # Buttons
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", padx=20, pady=10)

        ttk.Button(button_frame, text="Connect", command=self.connect).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=self.root.quit).pack(side="right")

        # Status label
        self.status_var = tk.StringVar(value="Ready to connect...")
        status_label = ttk.Label(self.root, textvariable=self.status_var, foreground="blue")
        status_label.pack(pady=10)

    def connect(self):
        """Attempt to connect to CAN bus"""
        interface = self.interface_var.get()
        baud_text = self.baud_var.get()

        # Convert baud rate text to BaudRate enum
        baud_map = {
            "1 MBit/s": BaudRate.BAUD_1M,
            "500 kBit/s": BaudRate.BAUD_500K,
            "250 kBit/s": BaudRate.BAUD_250K,
            "125 kBit/s": BaudRate.BAUD_125K,
            "100 kBit/s": BaudRate.BAUD_100K,
            "50 kBit/s": BaudRate.BAUD_50K
        }

        baud_rate = baud_map.get(baud_text, BaudRate.BAUD_250K)

        self.status_var.set("Connecting...")
        self.root.update()

        # Call the callback with connection parameters
        success = self.callback(interface, baud_rate)
        if success:
            self.status_var.set("Connected successfully!")
            self.root.after(1000, self.root.destroy)  # Close after 1 second
        else:
            self.status_var.set("Connection failed. Check settings.")


class CANMonitorWindow:
    """Main CAN monitoring window"""

    def __init__(self, root, can_monitor):
        self.root = root
        self.monitor = can_monitor
        self.root.title("RetainVar Monitor - CAN Communication")
        self.root.geometry("1000x700")

        # Initialize status variable early to prevent attribute errors
        self.status_var = tk.StringVar(value="Initializing...")

        # Data
        self.message_count = 0
        self.received_messages = []
        self.monitoring_active = False
        self.last_message_time = time.time()
        self.can_id_map = {}  # Dictionary to track unique CAN IDs and their latest data
        self.max_unique_ids = 100  # Maximum number of unique IDs to track
        self.variable_values = {}  # Dictionary to store current variable values
        self.variable_read_timer = None  # Timer for automatic variable reading
        self.current_read_index = 0      # Current variable being read in sequence

        # Bind cleanup on window destroy
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.create_widgets()
        # Don't start monitoring yet - will be started after main loop begins

    def get_variable_size(self, var_index):
        """Get the size (in bytes) of a variable"""
        if not self.monitor.current_board:
            return 4  # Default

        try:
            address = self.monitor.current_board.get_variable_address(var_index)
            if var_index + 1 < len(self.monitor.current_board.table_addr):
                length = min(4, self.monitor.current_board.table_addr[var_index + 1] - address)
            else:
                length = 4  # Default for last variable
            return length
        except:
            return 4  # Default on error

    def format_value_hex(self, value, var_index=None):
        """Format a value as hexadecimal string based on variable size"""
        if isinstance(value, int):
            # Get variable size if index provided
            if var_index is not None:
                size_bytes = self.get_variable_size(var_index)
            else:
                size_bytes = 4  # Default

            # Format based on size
            if value < 0:
                # Handle negative values by showing their unsigned hex representation
                if size_bytes == 1:
                    return f"0x{value & 0xFF:02X}"
                elif size_bytes == 2:
                    return f"0x{value & 0xFFFF:04X}"
                else:  # 4 bytes or more
                    return f"0x{value & 0xFFFFFFFF:08X}"
            else:
                if size_bytes == 1:
                    return f"0x{value:02X}"
                elif size_bytes == 2:
                    return f"0x{value:04X}"
                else:  # 4 bytes or more
                    return f"0x{value:08X}"
        return str(value)

    def create_widgets(self):
        """Create the main monitoring window widgets"""
        # Create notebook (tabbed interface)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # CAN Bus tab
        self.create_canbus_tab()

        # Control tab
        self.create_control_tab()

        # About tab
        self.create_about_tab()

        # Status bar with message counter
        self.update_status_display()
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                              relief="sunken", anchor="w")
        status_bar.pack(fill="x", side="bottom")

        # Start status update timer
        self.status_update_timer()

    def update_status_display(self):
        """Update the status bar with current information"""
        time_since_last_msg = time.time() - self.last_message_time
        if time_since_last_msg < 5.0:
            status = f"Connected - Monitoring CAN bus... Messages: {self.message_count}"
        elif time_since_last_msg < 30.0:
            status = f"Connected - Monitoring CAN bus... Messages: {self.message_count} (Last: {time_since_last_msg:.1f}s ago)"
        else:
            status = f"Connected - Monitoring CAN bus... Messages: {self.message_count} (No messages for {time_since_last_msg:.0f}s)"
        self.status_var.set(status)

    def status_update_timer(self):
        """Update status display periodically"""
        if self.monitoring_active:
            self.update_status_display()
            self.root.after(1000, self.status_update_timer)  # Update every second

    def safe_status_update(self, message):
        """Safely update status from any thread"""
        try:
            if hasattr(self, 'root') and self.root:
                self.root.after(0, lambda: self.status_var.set(message))
        except Exception:
            # Ignore errors if GUI is not available
            pass

    def create_canbus_tab(self):
        """Create the CAN bus monitoring tab"""
        canbus_frame = ttk.Frame(self.notebook)
        self.notebook.add(canbus_frame, text="CAN Bus Monitor")

        # Message list
        list_frame = ttk.LabelFrame(canbus_frame, text="CAN Messages")
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Treeview for messages
        columns = ("Type", "ID", "Length", "Data", "Count", "Time")
        self.message_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=20)

        # Configure columns
        self.message_tree.heading("Type", text="Type")
        self.message_tree.heading("ID", text="ID")
        self.message_tree.heading("Length", text="Length")
        self.message_tree.heading("Data", text="Latest Data")
        self.message_tree.heading("Count", text="Rx Count")
        self.message_tree.heading("Time", text="Last Update")

        self.message_tree.column("Type", width=80)
        self.message_tree.column("ID", width=120)
        self.message_tree.column("Length", width=60)
        self.message_tree.column("Data", width=280)
        self.message_tree.column("Count", width=80)
        self.message_tree.column("Time", width=100)

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.message_tree.yview)
        h_scrollbar = ttk.Scrollbar(list_frame, orient="horizontal", command=self.message_tree.xview)
        self.message_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        self.message_tree.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")

        # Control buttons
        button_frame = ttk.Frame(canbus_frame)
        button_frame.pack(fill="x", padx=5, pady=5)

        ttk.Button(button_frame, text="Clear", command=self.clear_messages).pack(side="left", padx=(0, 5))
        ttk.Button(button_frame, text="Save Log", command=self.save_log).pack(side="left")

    def create_control_tab(self):
        """Create the variable control tab"""
        control_frame = ttk.Frame(self.notebook)
        self.notebook.add(control_frame, text="Variable Control")

        # Board selection
        board_frame = ttk.LabelFrame(control_frame, text="Board Selection")
        board_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(board_frame, text="Board Type:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.board_var = tk.StringVar(value="PCU")
        board_combo = ttk.Combobox(board_frame, textvariable=self.board_var,
                                 values=["PCU", "TCU", "BMS", "SCU", "FCU", "WLU", "OBD_DC_DC", "CCU", "GATE", "PDU", "ZCU", "VCU"])
        board_combo.grid(row=0, column=1, padx=5, pady=5)
        board_combo.bind("<<ComboboxSelected>>", self.on_board_changed)

        ttk.Button(board_frame, text="Select Board", command=self.select_board).grid(row=0, column=2, padx=5, pady=5)

        # Variable control
        var_frame = ttk.LabelFrame(control_frame, text="Variable Access")
        var_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(var_frame, text="CAN ID Base:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.can_id_base_var = tk.StringVar(value="0x300")
        can_id_entry = ttk.Entry(var_frame, textvariable=self.can_id_base_var, width=10)
        can_id_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(var_frame, text="Board Index:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.board_index_var = tk.StringVar(value="0")
        board_index_entry = ttk.Entry(var_frame, textvariable=self.board_index_var, width=10)
        board_index_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(var_frame, text="Variable Index:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.var_index_var = tk.StringVar(value="0")
        var_index_entry = ttk.Entry(var_frame, textvariable=self.var_index_var, width=10)
        var_index_entry.grid(row=2, column=1, padx=5, pady=5)

        ttk.Label(var_frame, text="Value:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.var_value_var = tk.StringVar()
        var_value_entry = ttk.Entry(var_frame, textvariable=self.var_value_var, width=20)
        var_value_entry.grid(row=3, column=1, padx=5, pady=5)

        # Buttons
        button_frame = ttk.Frame(var_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=10)

        ttk.Button(button_frame, text="Read", command=self.read_single_variable).pack(side="left", padx=(0, 5))
        ttk.Button(button_frame, text="Write", command=self.write_variable).pack(side="left", padx=(0, 5))

        # Variable list with values
        list_frame = ttk.LabelFrame(control_frame, text="Variable Monitor")
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.var_tree = ttk.Treeview(list_frame, columns=("Index", "Name", "Value"), show="headings", height=15)
        self.var_tree.heading("Index", text="Index")
        self.var_tree.heading("Name", text="Variable Name")
        self.var_tree.heading("Value", text="Value")
        self.var_tree.column("Index", width=60)
        self.var_tree.column("Name", width=200)
        self.var_tree.column("Value", width=120)

        var_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.var_tree.yview)
        self.var_tree.configure(yscrollcommand=var_scrollbar.set)

        self.var_tree.pack(side="left", fill="both", expand=True)
        var_scrollbar.pack(side="right", fill="y")

        # Initialize with PCU board
        self.select_board()

    def create_about_tab(self):
        """Create the about tab"""
        about_frame = ttk.Frame(self.notebook)
        self.notebook.add(about_frame, text="About")

        # Title
        title_label = ttk.Label(about_frame, text="RetainVar Monitor",
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=20)

        # Description
        desc_text = """Python implementation of CAN communication for marine propulsion systems.

Features:
• CAN bus communication with multiple interface support
• Firmware programming capabilities
• Variable read/write operations
• Real-time message monitoring
• Support for multiple ECU types (PCU, TCU, BMS, etc.)

Converted from original C++ Borland Builder application."""

        desc_label = ttk.Label(about_frame, text=desc_text, justify="left")
        desc_label.pack(padx=20, pady=10)

        # Version info
        version_label = ttk.Label(about_frame, text="Version: Python 1.0.0",
                                 font=("Arial", 10, "italic"))
        version_label.pack(pady=10)

    def start_monitoring(self):
        """Start CAN message monitoring"""
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self.monitor_can_messages, daemon=True)
        self.monitor_thread.start()

    def monitor_can_messages(self):
        """Monitor CAN messages in a separate thread"""
        while self.monitoring_active:
            try:
                result, message, timestamp = self.monitor.can_comm.receive_message(0.1)
                if result == CANResult.ERR_OK and message:
                    self.root.after(0, self.add_message_to_list, message, timestamp)
                elif result != CANResult.ERR_QRCVEMPTY:
                    # Log any errors except "no message received"
                    print(f"CAN receive error: {result}")
                    self.safe_status_update(f"Receive error: {result}")
                    time.sleep(0.5)

            except Exception as e:
                print(f"Error monitoring CAN: {e}")
                self.safe_status_update(f"CAN Error: {e}")
                time.sleep(1)

    def add_message_to_list(self, message, timestamp):
        """Add or update a received message in the unique ID map"""
        self.message_count += 1
        self.last_message_time = time.time()

        # Update the CAN ID map
        can_id = message.id
        if can_id not in self.can_id_map:
            # New ID - add it
            self.can_id_map[can_id] = {
                'message': message,
                'timestamp': timestamp,
                'count': 1,
                'last_update': time.time()
            }
            # If we've exceeded the limit, remove the oldest entry
            if len(self.can_id_map) > self.max_unique_ids:
                oldest_id = min(self.can_id_map.keys(), key=lambda x: self.can_id_map[x]['last_update'])
                del self.can_id_map[oldest_id]
        else:
            # Existing ID - update it
            self.can_id_map[can_id]['message'] = message
            self.can_id_map[can_id]['timestamp'] = timestamp
            self.can_id_map[can_id]['count'] += 1
            self.can_id_map[can_id]['last_update'] = time.time()

        # Update the display
        self.update_message_display()

    def update_message_display(self):
        """Update the treeview with current unique CAN IDs and their latest data"""
        # Clear existing items
        for item in self.message_tree.get_children():
            self.message_tree.delete(item)

        # Sort IDs for consistent display
        sorted_ids = sorted(self.can_id_map.keys())

        # Add items to treeview
        for can_id in sorted_ids:
            data = self.can_id_map[can_id]
            message = data['message']
            timestamp = data['timestamp']
            count = data['count']

            # Format message type
            if message.msgtype == MessageType.MSGTYPE_EXTENDED:
                msg_type = "EXTENDED"
            elif message.msgtype == MessageType.MSGTYPE_RTR:
                msg_type = "RTR"
            else:
                msg_type = "STANDARD"

            # Format ID
            if message.msgtype == MessageType.MSGTYPE_EXTENDED:
                msg_id = f"{message.id:08X}h"
            else:
                msg_id = f"{message.id:03X}h"

            # Format data
            data_str = " ".join([f"{b:02X}" for b in message.data])

            # Format time (show time since last update)
            time_since_update = time.time() - data['last_update']
            if time_since_update < 1.0:
                time_str = "< 1s"
            elif time_since_update < 60.0:
                time_str = f"{time_since_update:.1f}s"
            else:
                time_str = f"{time_since_update/60.0:.1f}m"

            # Add to treeview
            self.message_tree.insert("", "end", values=(
                msg_type, msg_id, len(message.data), data_str,
                count, time_str
            ))

    def clear_messages(self):
        """Clear the message list and CAN ID map"""
        for item in self.message_tree.get_children():
            self.message_tree.delete(item)
        self.message_count = 0
        self.can_id_map.clear()
        self.last_message_time = time.time()

        # Also clear variable data and stop timer
        if self.variable_read_timer:
            self.root.after_cancel(self.variable_read_timer)
            self.variable_read_timer = None
        self.variable_values.clear()
        for item in self.var_tree.get_children():
            self.var_tree.delete(item)

    def save_log(self):
        """Save message log to file"""
        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write("CAN Message Log - Unique IDs\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(f"Total messages received: {self.message_count}\n")
                    f.write(f"Unique IDs tracked: {len(self.can_id_map)}\n\n")

                    # Sort IDs for consistent output
                    sorted_ids = sorted(self.can_id_map.keys())
                    for can_id in sorted_ids:
                        data = self.can_id_map[can_id]
                        message = data['message']
                        count = data['count']
                        last_update = data['last_update']

                        # Format message type
                        if message.msgtype == MessageType.MSGTYPE_EXTENDED:
                            msg_type = "EXTENDED"
                        else:
                            msg_type = "STANDARD"

                        # Format ID
                        if message.msgtype == MessageType.MSGTYPE_EXTENDED:
                            msg_id = f"{message.id:08X}h"
                        else:
                            msg_id = f"{message.id:03X}h"

                        # Format data
                        data_str = " ".join([f"{b:02X}" for b in message.data])

                        # Format timestamp
                        timestamp_str = time.strftime("%H:%M:%S", time.localtime(last_update))

                        f.write(f"{msg_type} {msg_id} {len(message.data)} {data_str} Count:{count} Last:{timestamp_str}\n")
                messagebox.showinfo("Success", f"Log saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save log: {e}")

    def on_board_changed(self, event):
        """Handle board type change"""
        pass  # Will be handled when Select Board is clicked

    def select_board(self):
        """Select and initialize board type"""
        board_type = self.board_var.get()
        if self.monitor.select_board(board_type):
            # Set CAN ID base to board default
            default_can_id = self.monitor.current_board.get_default_can_id_base()
            self.can_id_base_var.set(f"0x{default_can_id:03X}")

            # Stop any existing variable read timer
            if hasattr(self, 'variable_read_timer') and self.variable_read_timer:
                try:
                    self.root.after_cancel(self.variable_read_timer)
                except:
                    pass
                self.variable_read_timer = None

            # Clear variable list and values
            for item in self.var_tree.get_children():
                self.var_tree.delete(item)
            self.variable_values.clear()

            # Add variables for selected board
            variables = self.monitor.list_variables()
            for idx, name in variables:
                self.var_tree.insert("", "end", values=(idx, name, "Reading..."))
                self.variable_values[idx] = {"name": name, "value": "Reading...", "item_id": None}

            # Get item IDs for updating
            for item in self.var_tree.get_children():
                values = self.var_tree.item(item, 'values')
                idx = int(values[0])
                self.variable_values[idx]["item_id"] = item

            # Start variable reading immediately
            self.start_variable_reading()

            # Update status if status_var is available (might not be during initialization)
            if hasattr(self, 'status_var'):
                self.status_var.set(f"Selected board: {board_type}")
        else:
            messagebox.showerror("Error", f"Failed to select board: {board_type}")

    def start_variable_reading(self):
        """Start automatic variable reading every 5 seconds"""
        self.read_all_variables()

    def read_all_variables(self):
        """Read all variables sequentially using timer-based approach like C++ code"""
        if not self.variable_values:
            return

        # Start sequential reading using timer (like C++ TimerCANsendTimer)
        # CAN ID base and board index will be taken from board defaults
        self.current_read_index = 0
        self.send_next_read_request()

    def send_next_read_request(self):
        """Send next read request in sequence (like C++ TimerCANsendTimer)"""
        if self.current_read_index >= len(self.variable_values):
            # All requests sent, schedule next full read cycle
            self.variable_read_timer = self.root.after(5000, self.read_all_variables)
            return

        idx = list(self.variable_values.keys())[self.current_read_index]

        try:
            success, value = self.monitor.read_variable(idx, None, 0)  # Use board default for CAN ID base, keep board index 0
            if success:
                self.variable_values[idx]["value"] = self.format_value_hex(value, idx)
                print(f"DEBUG: Successfully read variable {idx} = {value}")
            else:
                # Don't overwrite existing values with "No Response" to prevent shifting
                print(f"DEBUG: No response for variable {idx}")
        except Exception as e:
            print(f"DEBUG: Exception reading variable {idx}: {e}")

        # Move to next variable
        self.current_read_index += 1

        # Schedule next request (small delay like C++ timer)
        self.root.after(50, self.send_next_read_request)

        # Update display after each successful read
        self.update_variable_display()

    def update_variable_display(self):
        """Update the variable treeview with current values (stable, no shifting)"""
        # Always maintain stable order by clearing and re-inserting in sorted order
        # This prevents shifting but ensures consistent positioning

        # Clear existing items
        for item in self.var_tree.get_children():
            self.var_tree.delete(item)

        # Re-insert all items in sorted order (stable positioning)
        sorted_var_ids = sorted(self.variable_values.keys())
        for var_idx in sorted_var_ids:
            var_data = self.variable_values[var_idx]
            self.var_tree.insert("", "end", values=(
                var_idx, var_data["name"], var_data["value"]
            ))

    def read_single_variable(self):
        """Read a single variable specified by index"""
        try:
            var_index = int(self.var_index_var.get())

            # Use UI values if they differ from defaults, otherwise use board defaults
            can_id_base_str = self.can_id_base_var.get()
            board_index_str = self.board_index_var.get()

            if self.monitor.current_board:
                default_can_id = self.monitor.current_board.get_default_can_id_base()

                # Check if UI values are different from board defaults
                try:
                    ui_can_id = int(can_id_base_str, 16) if can_id_base_str.startswith('0x') else int(can_id_base_str)
                    ui_board_index = int(board_index_str)

                    if ui_can_id != default_can_id:
                        # Use UI values
                        success, value = self.monitor.read_variable(var_index, ui_can_id, ui_board_index)
                    else:
                        # Use board defaults
                        success, value = self.monitor.read_variable(var_index, None, ui_board_index)
                except ValueError:
                    # Use board defaults if UI parsing fails
                    try:
                        ui_board_index = int(board_index_str)
                        success, value = self.monitor.read_variable(var_index, None, ui_board_index)
                    except ValueError:
                        success, value = self.monitor.read_variable(var_index, None, 0)
            else:
                # No board selected, use UI values
                can_id_base = int(can_id_base_str, 16) if can_id_base_str.startswith('0x') else int(can_id_base_str)
                board_index = int(board_index_str)
                success, value = self.monitor.read_variable(var_index, can_id_base, board_index)

            if success:
                self.var_value_var.set(self.format_value_hex(value, var_index))
                self.safe_status_update(f"Read variable {var_index}: {value}")
                # Also update in the table if it exists
                if var_index in self.variable_values:
                    self.variable_values[var_index]["value"] = self.format_value_hex(value, var_index)
                    self.update_variable_display()
            else:
                self.var_value_var.set("No Response")
                self.safe_status_update(f"No response for variable {var_index}")
        except ValueError:
            self.safe_status_update("Invalid variable index or parameters")
        except Exception as e:
            self.var_value_var.set(f"Error: {e}")
            self.safe_status_update(f"Read error: {e}")

    def on_closing(self):
        """Clean up when window is closing"""
        self.monitoring_active = False
        if self.variable_read_timer:
            try:
                self.root.after_cancel(self.variable_read_timer)
            except:
                pass  # Timer might already be cancelled
            self.variable_read_timer = None
        self.root.destroy()

    def read_variable(self):
        """Read a variable from the board"""
        try:
            var_index = int(self.var_index_var.get())
            success, value = self.monitor.read_variable(var_index)

            if success:
                self.var_value_var.set(self.format_value_hex(value, var_index))
                self.status_var.set(f"Read variable {var_index}: {value}")
            else:
                messagebox.showerror("Error", f"Failed to read variable {var_index}")
        except ValueError:
            messagebox.showerror("Error", "Invalid variable index")
        except Exception as e:
            messagebox.showerror("Error", f"Read error: {e}")

    def write_variable(self):
        """Write a variable to the board"""
        try:
            var_index = int(self.var_index_var.get())
            value_str = self.var_value_var.get()
            value = int(value_str, 16) if value_str.startswith('0x') else int(value_str)

            # Use UI values if they differ from defaults, otherwise use board defaults
            can_id_base_str = self.can_id_base_var.get()
            board_index_str = self.board_index_var.get()

            if self.monitor.current_board:
                default_can_id = self.monitor.current_board.get_default_can_id_base()

                # Check if UI values are different from board defaults
                try:
                    ui_can_id = int(can_id_base_str, 16) if can_id_base_str.startswith('0x') else int(can_id_base_str)
                    ui_board_index = int(board_index_str)

                    if ui_can_id != default_can_id:
                        # Use UI values
                        success = self.monitor.write_variable(var_index, value, ui_can_id, ui_board_index)
                    else:
                        # Use board defaults
                        success = self.monitor.write_variable(var_index, value, None, ui_board_index)
                except ValueError:
                    # Use board defaults if UI parsing fails
                    try:
                        ui_board_index = int(board_index_str)
                        success = self.monitor.write_variable(var_index, value, None, ui_board_index)
                    except ValueError:
                        success = self.monitor.write_variable(var_index, value, None, 0)
            else:
                # No board selected, use UI values
                can_id_base = int(can_id_base_str, 16) if can_id_base_str.startswith('0x') else int(can_id_base_str)
                board_index = int(board_index_str)
                success = self.monitor.write_variable(var_index, value, can_id_base, board_index)

            if success:
                self.safe_status_update(f"Wrote variable {var_index}: {value}")
                messagebox.showinfo("Success", f"Variable {var_index} written successfully")
                # Update the table if this variable is displayed
                if var_index in self.variable_values:
                    self.variable_values[var_index]["value"] = self.format_value_hex(value, var_index)
                    self.update_variable_display()
            else:
                messagebox.showerror("Error", f"Failed to write variable {var_index}")
        except ValueError:
            messagebox.showerror("Error", "Invalid variable index or value")
        except Exception as e:
            messagebox.showerror("Error", f"Write error: {e}")


class CANMonitorApp:
    """Main application class"""

    def __init__(self):
        self.root = None
        self.monitor = None

    def run(self):
        """Run the application"""
        print("Starting CAN Monitor GUI...")
        # Create settings window first
        settings_root = tk.Tk()
        settings_window = CANSettingsWindow(settings_root, self.on_connect)
        print("Settings window created, starting mainloop...")
        settings_root.mainloop()
        print("Settings window closed")

        # If connection successful, show main window
        if hasattr(self, 'monitor') and self.monitor:
            print("Starting main monitoring window...")
            # Create main monitoring window after settings window closes
            self.root = tk.Tk()
            self.monitor_window = CANMonitorWindow(self.root, self.monitor)
            # Start monitoring after a short delay to ensure main loop is running
            self.root.after(100, lambda: self.monitor_window.start_monitoring())
            # Variable reading is started by select_board when board is selected
            self.root.mainloop()
        else:
            print("No monitor created, exiting")

    def on_connect(self, interface, baud_rate):
        """Handle successful CAN connection"""
        try:
            self.monitor = RetainVarMonitor(interface, baud_rate)
            result = self.monitor.connect()

            if result == CANResult.ERR_OK:
                # Store connection parameters for later use
                self.interface = interface
                self.baud_rate = baud_rate
                return True
            else:
                messagebox.showerror("Connection Error",
                                   f"Failed to connect to CAN bus: {result}")
                return False
        except Exception as e:
            messagebox.showerror("Connection Error", f"Error: {e}")
            return False


def main():
    """Main entry point"""
    try:
        app = CANMonitorApp()
        app.run()
    except KeyboardInterrupt:
        print("Application interrupted by user")
    except Exception as e:
        print(f"Application error: {e}")
        messagebox.showerror("Application Error", f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
