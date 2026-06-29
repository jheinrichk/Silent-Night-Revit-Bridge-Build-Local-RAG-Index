# ============================================================
# OPENAI REVIT BRIDGE CALIBRATION UI V3.12
# Countdown / Hide Window Version V3.11
# Includes:
#   ChatGPT input / submit
#   ChatGPT code block copy button
#   Revit Interactive Python Shell input / run / output
#   ChatGPT attach button
#   ChatGPT Add files / Upload from computer menu item
#   Windows file picker filename field / Open button
#   Browser refresh / reload button
#   Revit warning dialog OK button
#
# Also writes QC short upload naming defaults:
#   Revit export folder:
#     C:\RevitBridge\QC_Exports
#   Short upload staging folder:
#     C:\RevitBridge\QC_Upload
#   Short upload filename base:
#     qc_upload
#
# Purpose:
#   Calibrate mouse coordinates used by:
#     openai_revit_bridge_main.py
#     chatgpt_qc_export_upload_helper.py
#
# Required:
#   pip install pyautogui
#
# Stop:
#   Close the window.
# ============================================================

import json
import sys
import traceback
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

STARTUP_ERRORS = []

try:
    import pyautogui
except Exception as e:
    pyautogui = None
    STARTUP_ERRORS.append("pyautogui is required. Install with: python -m pip install pyautogui\n\n" + str(e))


SCRIPT_DIR = Path(__file__).resolve().parent
BRIDGE_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = BRIDGE_ROOT / "bridge_config.json"

COUNTDOWN_SECONDS_DEFAULT = 5


CALIBRATION_POINTS = [
    ("chatgpt_input", "ChatGPT input box"),
    ("chatgpt_submit", "ChatGPT submit button"),
    ("chatgpt_response_click", "ChatGPT code block Copy button / icon AFTER Page Down"),
    ("rps_input", "Revit Interactive Python Shell input area"),
    ("rps_run_button", "Revit Interactive Python Shell Run button"),
    ("rps_output_click", "Revit Interactive Python Shell output area"),
    ("chatgpt_attach", "ChatGPT attach / plus button"),
    ("chatgpt_add_files", "ChatGPT Add files / Upload from computer menu item"),
    ("file_picker_filename", "Windows file picker filename field"),
    ("file_picker_open", "Windows file picker Open button"),
    ("browser_refresh", "Browser refresh / reload button"),
    ("revit_warning_ok", "Revit warning dialog OK button"),
    ("revit_dialog_ok", "Revit modal dialog OK button"),
    ("revit_dialog_unjoin", "Revit modal dialog Unjoin button"),
    ("revit_dialog_cancel", "Revit modal dialog Cancel button")
]


DEFAULT_CONFIG = {
    "timing": {
        "chatgpt_output_wait_seconds": 60,
        "chatgpt_copy_retry_wait_seconds": 60,
        "chatgpt_copy_retry_attempts": 4,
        "chatgpt_page_down_count": 2,
        "chatgpt_page_down_pre_copy_wait_seconds": 4,
        "chatgpt_page_down_post_copy_wait_seconds": 4,
        "rps_output_wait_seconds": 11,
        "startup_delay_seconds": 3,
        "pause_between_actions": 0.5,
        "pause_after_copy_seconds": 7,
        "pause_after_paste_seconds": 7,
        "revit_warning_ok_click_wait_seconds": 0.8,
        "revit_dialog_click_wait_seconds": 0.8,
        "revit_dialog_sequence_passes": 2,
        "revit_dialog_before_output_wait_seconds": 4
    },
    "qc": {
        "export_folder": "C:\\RevitBridge\\QC_Exports",
        "upload_staging_folder": "C:\\RevitBridge\\QC_Upload",
        "upload_staging_basename": "qc_upload",
        "valid_export_extensions": [".png", ".pdf", ".jpg", ".jpeg"],
        "watch_interval_seconds": 2,
        "file_stability_checks": 3,
        "file_stability_interval_seconds": 1.0,
        "upload_wait_seconds": 4,
        "upload_step_wait_seconds": 4,
        "chatgpt_response_wait_seconds": 60
    },
    "bridge": {
        "max_cycles": 2222,
        "stop_on_syntax_error": True,
        "stop_on_fix_errors": True,
        "max_repeated_state_count": 8,
        "max_invalid_code_attempts": 2,
        "max_reprint_attempts": 1
    },
    "coordinates": {
        "chatgpt_input": [1000, 970],
        "chatgpt_submit": [1840, 970],
        "chatgpt_response_click": [950, 430],
        "rps_input": [850, 760],
        "rps_run_button": [950, 760],
        "rps_output_click": [850, 420],
        "chatgpt_attach": [720, 970],
        "chatgpt_add_files": [720, 860],
        "file_picker_filename": [760, 930],
        "file_picker_open": [1720, 930],
        "browser_refresh": [90, 50],
        "revit_warning_ok": [604, 350],
        "revit_dialog_ok": [604, 350],
        "revit_dialog_unjoin": [604, 350],
        "revit_dialog_cancel": [795, 350]
    },
    "hotkeys": {
        "copy": ["ctrl", "c"],
        "paste": ["ctrl", "v"],
        "select_all": ["ctrl", "a"],
        "chatgpt_submit": ["enter"],
        "rps_execute": ["f5"],
        "page_down": ["pagedown"]
    }
}


def merge_defaults(config, defaults):
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
        elif isinstance(value, dict) and isinstance(config.get(key), dict):
            merge_defaults(config[key], value)
    return config


def force_updated_defaults(config):
    if "hotkeys" not in config:
        config["hotkeys"] = {}

    config["hotkeys"]["rps_execute"] = ["f5"]

    if "qc" not in config:
        config["qc"] = {}

    if "export_folder" not in config["qc"]:
        config["qc"]["export_folder"] = "C:\\RevitBridge\\QC_Exports"

    if "upload_staging_folder" not in config["qc"]:
        config["qc"]["upload_staging_folder"] = "C:\\RevitBridge\\QC_Upload"

    if "upload_staging_basename" not in config["qc"]:
        config["qc"]["upload_staging_basename"] = "qc_upload"

    if "upload_step_wait_seconds" not in config["qc"]:
        config["qc"]["upload_step_wait_seconds"] = 4

    if "timing" not in config:
        config["timing"] = {}

    if "pause_after_copy_seconds" not in config["timing"]:
        config["timing"]["pause_after_copy_seconds"] = 11

    if "pause_after_paste_seconds" not in config["timing"]:
        config["timing"]["pause_after_paste_seconds"] = 11

    if "chatgpt_page_down_count" not in config["timing"]:
        config["timing"]["chatgpt_page_down_count"] = 2

    if "chatgpt_page_down_pre_copy_wait_seconds" not in config["timing"]:
        config["timing"]["chatgpt_page_down_pre_copy_wait_seconds"] = 4

    if "chatgpt_page_down_post_copy_wait_seconds" not in config["timing"]:
        config["timing"]["chatgpt_page_down_post_copy_wait_seconds"] = 4

    if "revit_warning_ok_click_wait_seconds" not in config["timing"]:
        config["timing"]["revit_warning_ok_click_wait_seconds"] = 0.8

    if "bridge" not in config:
        config["bridge"] = {}

    if int(config["bridge"].get("max_cycles", 0)) < 2222:
        config["bridge"]["max_cycles"] = 2222

    if "coordinates" not in config:
        config["coordinates"] = {}

    if "browser_refresh" not in config["coordinates"]:
        config["coordinates"]["browser_refresh"] = [90, 50]

    if "revit_warning_ok" not in config["coordinates"]:
        config["coordinates"]["revit_warning_ok"] = [604, 350]
    if "revit_dialog_ok" not in config["coordinates"]:
        config["coordinates"]["revit_dialog_ok"] = [604, 350]
    if "revit_dialog_unjoin" not in config["coordinates"]:
        config["coordinates"]["revit_dialog_unjoin"] = [604, 350]
    if "revit_dialog_cancel" not in config["coordinates"]:
        config["coordinates"]["revit_dialog_cancel"] = [795, 350]

    return config


def load_config():
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    with open(str(CONFIG_PATH), "r", encoding="utf-8-sig") as f:
        config = json.load(f)

    config = merge_defaults(config, json.loads(json.dumps(DEFAULT_CONFIG)))
    config = force_updated_defaults(config)
    save_config(config)
    return config


def save_config(config):
    with open(str(CONFIG_PATH), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


class CalibrationUI(object):
    def __init__(self, root):
        self.root = root
        self.root.title("OpenAI Revit Bridge Calibration UI")
        self.root.geometry("1080x880")
        self.root.attributes("-topmost", True)

        self.config = load_config()
        self.coords = self.config.get("coordinates", {})
        self.config["coordinates"] = self.coords

        self.countdown_remaining = 0
        self.pending_key = None
        self.pending_label = None

        self.hide_during_capture = tk.BooleanVar(value=True)
        self.countdown_seconds = tk.IntVar(value=COUNTDOWN_SECONDS_DEFAULT)

        title = tk.Label(
            root,
            text="OpenAI Revit Bridge Calibration",
            font=("Segoe UI", 16, "bold")
        )
        title.pack(pady=10)

        intro = (
            "Use countdown capture. Click a Capture button, move your mouse to the target, then wait.\n"
            "The UI can hide during countdown so it does not block Edge, Revit or the file picker."
        )
        tk.Label(root, text=intro, justify="center", wraplength=940).pack(pady=4)

        options = tk.Frame(root)
        options.pack(pady=6)

        tk.Label(options, text="Countdown seconds:").grid(row=0, column=0, padx=6)

        tk.Spinbox(
            options,
            from_=2,
            to=20,
            width=5,
            textvariable=self.countdown_seconds
        ).grid(row=0, column=1, padx=6)

        tk.Checkbutton(
            options,
            text="Hide window during countdown capture",
            variable=self.hide_during_capture
        ).grid(row=0, column=2, padx=12)

        self.position_label = tk.Label(root, text="", font=("Consolas", 12))
        self.position_label.pack(pady=6)

        self.status_label = tk.Label(
            root,
            text="Ready.",
            font=("Segoe UI", 11, "bold"),
            fg="blue"
        )
        self.status_label.pack(pady=4)

        frame = tk.Frame(root)
        frame.pack(fill="both", expand=True, padx=20, pady=10)

        header_font = ("Segoe UI", 10, "bold")

        tk.Label(frame, text="Target", anchor="w", width=62, font=header_font).grid(
            row=0,
            column=0,
            sticky="w",
            pady=4
        )

        tk.Label(frame, text="Current X,Y", width=18, font=header_font).grid(
            row=0,
            column=1,
            pady=4
        )

        tk.Label(frame, text="Capture", width=38, font=header_font).grid(
            row=0,
            column=2,
            pady=4
        )

        self.value_labels = {}

        for row, item in enumerate(CALIBRATION_POINTS, start=1):
            key = item[0]
            label = item[1]

            tk.Label(frame, text=label, anchor="w", width=62).grid(
                row=row,
                column=0,
                sticky="w",
                pady=4
            )

            val = self.coords.get(key, ["", ""])

            val_label = tk.Label(
                frame,
                text="{}, {}".format(val[0], val[1]),
                width=18,
                font=("Consolas", 10)
            )
            val_label.grid(row=row, column=1, padx=8)

            self.value_labels[key] = val_label

            btn_frame = tk.Frame(frame)
            btn_frame.grid(row=row, column=2, padx=8, pady=2)

            tk.Button(
                btn_frame,
                text="Capture in countdown",
                width=22,
                command=lambda k=key, l=label: self.start_countdown_capture(k, l)
            ).grid(row=0, column=0, padx=4)

            tk.Button(
                btn_frame,
                text="Capture now",
                width=12,
                command=lambda k=key, l=label: self.capture_now(k, l)
            ).grid(row=0, column=1, padx=4)

        bottom = tk.Frame(root)
        bottom.pack(pady=12)

        tk.Button(
            bottom,
            text="Save Config",
            width=18,
            command=self.save
        ).grid(row=0, column=0, padx=8)

        tk.Button(
            bottom,
            text="Show Mouse Position",
            width=20,
            command=self.show_mouse_position
        ).grid(row=0, column=1, padx=8)

        tk.Button(
            bottom,
            text="Show QC Paths",
            width=18,
            command=self.show_qc_paths
        ).grid(row=0, column=2, padx=8)

        tk.Button(
            bottom,
            text="Close",
            width=18,
            command=root.destroy
        ).grid(row=0, column=3, padx=8)

        notes = (
            "Important calibration notes:\n"
            "1. ChatGPT attach / plus button is only the first click.\n"
            "2. ChatGPT Add files / Upload from computer menu item is the second click after the attach menu opens.\n"
            "3. File picker filename field can usually be focused by Alt+N, but calibrate it as backup.\n"
            "4. File picker Open button is backup only. The bridge should press Enter after pasting the full path.\n"
            "5. IPS execute hotkey is forced to F5 because Enter may only add a new line.\n"
            "6. Revit may create long PNG export names. The bridge should copy them to the simple upload name qc_upload.png.\n"
            "7. Revit warning OK default is X=604, Y=350 based on the provided warning dialog screenshot. Recalibrate if the dialog opens elsewhere.\n"
            "8. Browser refresh is only calibrated here; the main bridge will not use it unless a recovery function calls it."
        )
        tk.Label(root, text=notes, fg="gray25", wraplength=940, justify="left").pack(pady=4)

        self.root.after(100, self.update_mouse_label)

    def update_mouse_label(self):
        x, y = pyautogui.position()
        self.position_label.config(text="Current mouse position: X={}, Y={}".format(x, y))
        self.root.after(100, self.update_mouse_label)

    def start_countdown_capture(self, key, label):
        self.pending_key = key
        self.pending_label = label
        self.countdown_remaining = int(self.countdown_seconds.get())

        self.status_label.config(
            text="Move mouse to target: {}. Capturing in {} seconds.".format(
                label,
                self.countdown_remaining
            ),
            fg="red"
        )

        if self.hide_during_capture.get():
            self.root.after(600, self.root.withdraw)

        self.root.after(1000, self.countdown_tick)

    def countdown_tick(self):
        self.countdown_remaining -= 1

        if self.countdown_remaining > 0:
            if self.root.state() != "withdrawn":
                self.status_label.config(
                    text="Move mouse to target: {}. Capturing in {} seconds.".format(
                        self.pending_label,
                        self.countdown_remaining
                    ),
                    fg="red"
                )

            self.root.after(1000, self.countdown_tick)
            return

        x, y = pyautogui.position()

        self.coords[self.pending_key] = [int(x), int(y)]
        self.config["coordinates"] = self.coords
        save_config(self.config)

        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)

        self.value_labels[self.pending_key].config(text="{}, {}".format(x, y))

        self.status_label.config(
            text="Captured {} at X={}, Y={}".format(self.pending_label, x, y),
            fg="green"
        )

        self.pending_key = None
        self.pending_label = None

    def capture_now(self, key, label):
        x, y = pyautogui.position()

        self.coords[key] = [int(x), int(y)]
        self.config["coordinates"] = self.coords
        save_config(self.config)

        self.value_labels[key].config(text="{}, {}".format(x, y))

        self.status_label.config(
            text="Captured {} at X={}, Y={}".format(label, x, y),
            fg="green"
        )

    def save(self):
        self.config["coordinates"] = self.coords
        self.config = force_updated_defaults(self.config)
        save_config(self.config)
        messagebox.showinfo("Saved", "Calibration saved to:\n{}".format(CONFIG_PATH))

    def show_mouse_position(self):
        x, y = pyautogui.position()
        messagebox.showinfo("Mouse Position", "X={}, Y={}".format(x, y))

    def show_qc_paths(self):
        qc = self.config.get("qc", {})
        export_folder = qc.get("export_folder", "")
        upload_folder = qc.get("upload_staging_folder", "")
        upload_name = qc.get("upload_staging_basename", "qc_upload")
        messagebox.showinfo(
            "QC Paths",
            "Revit export folder:\n{}\n\nShort upload folder:\n{}\n\nShort upload filename:\n{}.png".format(
                export_folder,
                upload_folder,
                upload_name
            )
        )


def show_startup_error(title, text):
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, text)
        root.destroy()
    except Exception:
        pass

    try:
        print("")
        print(title)
        print(text)
        print("")
        input("Press Enter to close...")
    except Exception:
        pass


def main():
    try:
        if STARTUP_ERRORS:
            show_startup_error(
                "Calibration UI startup error",
                "\n\n".join(STARTUP_ERRORS)
            )
            return

        root = tk.Tk()
        CalibrationUI(root)
        root.mainloop()
    except Exception:
        msg = traceback.format_exc()
        show_startup_error("Calibration UI crashed", msg)


if __name__ == "__main__":
    main()
