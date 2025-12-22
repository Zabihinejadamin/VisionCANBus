#!/usr/bin/env python3
"""
Simple GUI test to verify tkinter works
"""

import tkinter as tk
from tkinter import ttk, messagebox

def test_gui():
    """Test basic GUI functionality"""
    root = tk.Tk()
    root.title("GUI Test")
    root.geometry("300x200")

    label = ttk.Label(root, text="GUI Test Window")
    label.pack(pady=20)

    def on_click():
        messagebox.showinfo("Test", "GUI is working!")
        root.quit()

    button = ttk.Button(root, text="Test GUI", command=on_click)
    button.pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    test_gui()
