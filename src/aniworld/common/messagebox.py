import platform
import subprocess
import ctypes
import tkinter as tk
from tkinter import messagebox
import logging

from aniworld import globals as aniworld_globals


def show_messagebox(message, title="Message", box_type="info"):
    # box_type -> info, yesno, warning, error
    system = platform.system()
    
    if system == "Windows":
        msg_box_type = {
            "info": 0x40,
            "yesno": 0x04 | 0x20,
            "warning": 0x30,
            "error": 0x10,
        }.get(box_type, 0x40)
        
        response = ctypes.windll.user32.MessageBoxW(0, message, title, msg_box_type)
        if box_type == "yesno":
            return response == 6
        return True

    elif system == "Darwin":
        script = {
            "info": f'display dialog "{message}" with title "{title}" buttons "OK"',
            "yesno": f'display dialog "{message}" with title "{title}" buttons {{"Yes", "No"}}',
            "warning": f'display dialog "{message}" with title "{title}" buttons "OK" with icon caution',
            "error": f'display dialog "{message}" with title "{title}" buttons "OK" with icon stop',
        }.get(box_type, f'display dialog "{message}" with title "{title}" buttons "OK"')
        
        try:
            result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True)
            if box_type == "yesno":
                return "Yes" in result.stdout
            return True
        except Exception as e:
            logging.debug(f"Error showing messagebox on macOS: {e}")
            return False

    elif system == "Linux":
        try:
            if subprocess.run(["which", "zenity"], capture_output=True, text=True).returncode == 0:
                cmd = {
                    "info": ["zenity", "--info", "--text", message, "--title", title],
                    "yesno": ["zenity", "--question", "--text", message, "--title", title],
                    "warning": ["zenity", "--warning", "--text", message, "--title", title],
                    "error": ["zenity", "--error", "--text", message, "--title", title],
                }.get(box_type, ["zenity", "--info", "--text", message, "--title", title])
                
                result = subprocess.run(cmd)
                return result.returncode == 0 if box_type == "yesno" else True
            
            elif subprocess.run(["which", "kdialog"], capture_output=True, text=True).returncode == 0:
                cmd = {
                    "info": ["kdialog", "--msgbox", message, "--title", title],
                    "yesno": ["kdialog", "--yesno", message, "--title", title],
                    "warning": ["kdialog", "--sorry", message, "--title", title],
                    "error": ["kdialog", "--error", message, "--title", title],
                }.get(box_type, ["kdialog", "--msgbox", message, "--title", title])
                
                result = subprocess.run(cmd)
                return result.returncode == 0 if box_type == "yesno" else True
            
        except Exception as e:
            logging.debug(f"Error showing messagebox on Linux: {e}")
            return False

    root = tk.Tk()
    root.withdraw()
    if box_type == "yesno":
        return messagebox.askyesno(title, message)
    elif box_type == "warning":
        messagebox.showwarning(title, message)
    elif box_type == "error":
        messagebox.showerror(title, message)
    else:
        messagebox.showinfo(title, message)
    return True


if __name__ == "__main__":
    show_messagebox("Are you still there?", "Uhm...", "info")
