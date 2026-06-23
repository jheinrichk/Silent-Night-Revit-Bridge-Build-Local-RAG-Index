# ============================================================
# OPENAI REVIT BRIDGE MAIN
# Unattended Continuous Loop Version V3.22 (Dynamic Waits + Batch QC Upload + Local RAG)
#
# Key fixes in V3.21:
#   - GUI Revit modal click sweeps removed; no Unjoin/OK/Cancel coordinate clicks are sent after RPS run.
#   - ChatGPT output wait, ChatGPT retry wait, and RPS output wait can now be cycle-specific.
#   - All non-critical short countdowns default to 3 seconds; ChatGPT input paste and file-picker Open retain longer waits.
#   - ChatGPT code copy retry is reduced to one retry with cycle-specific countdown.
#   - QC upload now batch-selects all eligible files in QC_Upload in one file picker operation, then deletes uploaded files.
#   - Adds a Revit API / Python RAG instruction block for future bridge prompts.
#
# Key fixes & improvements in V3.22:
#   - MAJOR: Safe Windows file dialog upload guard (ctypes + #32770 detection).
#     Prevents the bridge from continuing/pasting while the Open file picker is still
#     modal. Uses full quoted paths, Alt+N focus, Enter-to-confirm, and explicit
#     wait-for-dialog-open + wait-for-dialog-close before returning control to ChatGPT.
#     Greatly reduces stuck cycles and wrong-window paste bugs during QC PNG uploads.
#   - Dynamic per-cycle wait tuning (BRIDGE_RPS_WAIT_SECONDS / BRIDGE_CHATGPT_WAIT_SECONDS
#     / BRIDGE_RETRY_WAIT_SECONDS comments at top of generated scripts are now honored).
#   - RAG is now truly live/self-improving: every completed cycle becomes retrieval
#     context for subsequent cycles within the same long redline session.
#   - Batch QC upload supported in a single file picker dialog when possible.
#
# V3.21 / V3.20 behavior preserved unless noted above.
#   - Browser refresh calibration click runs before the Page Down and code-block Copy button sequence.
#   - Copy sequence is exactly: wait for output, browser refresh, wait, Page Down twice, wait, click calibrated copy coordinate, validate clipboard.
#   - Disables PyAutoGUI corner fail-safe for unattended folder-upload loops; use Ctrl+C in this terminal to stop.
#   - Removes all ChatGPT copy-button offset scanning.
#   - Treats chatgpt_response_click as the authoritative copy-button coordinate after Page Down.
#   - QC upload is now folder based: upload existing files from C:\RevitBridge\QC_Upload, then delete successfully uploaded files.
#   - If no PNG/export file exists in QC_Upload, skip only upload and still paste the Python/RPS output to ChatGPT.
#
# All previous V3.19 folder-upload and refresh-before-copy functionality preserved.
# ============================================================

import json
import ctypes
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import pyautogui
import pyperclip

# This bridge is intended to run unattended across browser, file picker and Revit windows.
# The terminal Ctrl+C remains the stop command. PyAutoGUI corner fail-safe can be
# triggered accidentally during file-picker/upload focus changes, so it is disabled here.
pyautogui.FAILSAFE = False


CONFIG_PATH = Path(__file__).with_name("bridge_config.json")


BRIDGE_RESPONSE_INSTRUCTION = (
    "MODE:REVIT_BRIDGE\n"
    "RETURN:FIRST_EXECUTABLE_REVIT_PYTHON_CODE_BLOCK_ONLY\n"
    "SCRIPT:IRONPYTHON_COMPATIBLE;NO_F_STRINGS;NO_TYPE_HINTS\n"
    "REQ:PRINT_RESULTS_ERRORS_NEXT_RECOMMENDED_STATE\n"
    "REQ:COPY_FINAL_OUTPUT_TO_WINDOWS_CLIPBOARD\n"
    "REQ:WRITE_FINAL_OUTPUT_TO_C:\\RevitBridge\\rps_last_output.txt\n"
    "REQ:QC_EXPORT_SHORT_FILENAME\n"
    "SAFETY:USER_EXPLICITLY_ALLOWED_TO_MODIFY_AND_EXPORT_FOR_THIS_REDLINE_WORKFLOW\n"
    "IF_MODIFY:USE_TRANSACTION;ROLLBACK_OR_REPORT_FAILURE\n"
    "OUTPUT:CODE_FIRST;NO_PROSE_BEFORE_CODE\n"
    "LOOP:CONTINUE_THROUGH_QAQC_AND_KEEP_DESIGNING_UNTIL_MAX_CYCLES_FIX_ERRORS_OR_USER_STOP\n"
    "STOP_ONLY_WHEN:NEXT_RECOMMENDED_STATE_IS_FIX_ERRORS_OR_MAX_CYCLES_OR_USER_STOPPED\n"
    "QAQC_COMPLETE_IS_STATUS_NOT_STOP:WHEN_QAQC_COMPLETE_CONTINUE_WITH_NEXT_DESIGN_CLEANUP_OR_REFINEMENT_CYCLE\n"
    "QAQC_VISUAL_RULE:DO_NOT_MARK_ITEM_COMPLETE_UNLESS_UPLOADED_QC_PNG_CLEARLY_SHOWS_THE_CHANGE_IN_THE_INTENDED_DETAIL_REGION\n"
    "QAQC_VISUAL_RULE:IF_CHANGE_IS_NOT_CLEARLY_VISIBLE_ADJUST_LOCATION_SIZE_DRAW_ORDER_OR_TARGET_AND_REPEAT_EXPORT_REVIEW\n"
    "QAQC_VISUAL_RULE:EXPORT_FOCUSED_QC_REGION_WHEN_FULL_SHEET_EXPORT_DOES_NOT_CLEARLY_SHOW_THE_WORK\n"
    "QAQC_VISUAL_RULE:USE_VISUAL_REVIEW_AND_OCR_WHEN_TEXT_IS_INVOLVED_SUCH_AS_OPTIONAL_DIA_RISER_LANDING_OR_NOTE_CALLOUTS\n"
    "QAQC_VISUAL_RULE:DO_NOT_SYNC_UNTIL_ALL_REDLINES_ARE_VISIBLY_CONFIRMED_IN_UPLOADED_QC_PNGS\n"
    "QAQC_SCALE_RULE:WHEN_MANIPULATING_OR_DRAFTING_INSIDE_A_VIEW_THAT_IS_PLACED_ON_A_SHEET_CONSIDER_VIEW_SCALE_SHEET_SCALE_AND_ANNOTATION_SCALE\n"
    "QAQC_SCALE_RULE:IDENTIFY_A_NEARBY_VISIBLE_REFERENCE_OBJECT_OR_REFERENCE_POINT_INSIDE_THE_TARGET_VIEW_WITHIN_THE_VIEW_CROP_AND_ANNOTATION_BOUNDARIES_AND_USE_IT_TO_POSITION_AND_SIZE_NEW_WORK\n"
    "QAQC_SCALE_RULE:REPORT_VIEW_NAME_VIEW_ID_VIEW_SCALE_REFERENCE_OBJECT_OR_REFERENCE_POINT_AND_CONFIRM_THE_WORK_IS_VISIBLE_IN_THE_SHEET_VIEWPORT_QC_EXPORT\n"
    "QAQC_SCALE_RULE:IF_VIEW_BASED_WORK_IS_NOT_CLEARLY_VISIBLE_ON_THE_SHEET_EXPORT_ADJUST_LOCATION_SIZE_DRAW_ORDER_OR_TARGET_RELATIVE_TO_THE_VISIBLE_REFERENCE_POINT_AND_REPEAT_QC\n"
    "QAQC_VISUAL_STATUS_VALUES:VISIBLE_CONFIRMED;NOT_VISIBLE_REQUIRES_ADJUSTMENT;WRONG_LOCATION_REQUIRES_ADJUSTMENT;TEXT_STILL_VISIBLE;OCR_UNCLEAR_EXPORT_HIGHER_RESOLUTION\n"
    "FORMAT_HARD_REQUIREMENT:THE_FIRST_CHARACTER_OF_THE_RESPONSE_MUST_BE_THE_FIRST_BACKTICK_OF_A_FENCED_PYTHON_CODE_BLOCK\n"
    "FORMAT_HARD_REQUIREMENT:START_EXACTLY_WITH_TRIPLE_BACKTICK_PYTHON_AND_END_EXACTLY_WITH_TRIPLE_BACKTICK\n"
    "FORMAT_HARD_REQUIREMENT:OPENING_FENCE_MUST_BE_EXACTLY_THREE_BACKTICKS_PLUS_PYTHON_NO_ID_NO_ATTRIBUTES\n"
    "FORMAT_HARD_REQUIREMENT:DO_NOT_OUTPUT_ANY_TEXT_BEFORE_OR_AFTER_THE_CODE_BLOCK\n"
    "MODEL_MAINTENANCE_RULE:WHEN_STARTING_OVER_OR_REDESIGNING_IDENTIFY_REMOVE_HIDE_OR_ARCHIVE_OBSOLETE_OVERLAPPING_PRIOR_AI_LOT8_SAMPLE_GEOMETRY_BEFORE_ADDING_NEW_WORK\n"
    "MODEL_MAINTENANCE_RULE:KEEP_THE_MODEL_COHERENT_BY_REPORTING_WHAT_WAS_REMOVED_KEPT_CREATED_AND_WHICH_CURRENT_DESIGN_ELEMENTS_REMAIN\n"
    "MODEL_MAINTENANCE_RULE:DO_NOT_LEAVE_OLD_AND_NEW_DESIGN_ITERATIONS_OVERLAPPED_UNLESS_EXPLICITLY_REQUESTED_FOR_COMPARISON\n"
    "MODEL_MAINTENANCE_RULE:CONTINUE_CLEANING_NONSENSICAL_WALLS_FLOORS_AND_SAMPLE_FRAGMENTS_UNLESS_THEY_ARE_EXPLICITLY_PART_OF_THE_CURRENT_DESIGN_INTENT\n"
    "DESIGN_RULE:LOT_8_EARTH_BERM_HOME_MUST_REMAIN_INHABITABLE_BY_PEOPLE_NOT_MERELY_ABSTRACT_FORM\n"
    "DESIGN_RULE:WHEN_CONTINUING_AFTER_QAQC_REFINE_ROOM_LOGIC_ENTRY_CIRCULATION_DAYLIGHT_STRUCTURE_DRAINAGE_AND_BUILDABLE_GEOMETRY\n"
    "REVIT_MODAL_GUARD_RULE:THE_BRIDGE_AUTOINJECTS_A_REVIT_API_DIALOGBOXSHOWING_GUARD_BEFORE_EACH_RPS_RUN_SO_DIALOGS_CAN_BE_OVERRIDDEN_BEFORE_THEY_BLOCK_THE_PYTHON_SHELL\n"
    "REVIT_MODAL_GUARD_RULE:FOR_MODEL_MODIFYING_SCRIPTS_USE_ai_apply_failure_handling_TRANSACTION_IF_AVAILABLE_AFTER_TRANSACTION_START_TO_DELETE_WARNINGS_AND_ROLL_BACK_SAFELY_ON_ERRORS\n"
    "REVIT_MODAL_GUARD_RULE:GUI_MODAL_DIALOG_COORDINATE_CLICKS_ARE_DISABLED_DO_NOT_EXPECT_THE_BRIDGE_TO_CLICK_UNJOIN_OK_OR_CANCEL_DIALOG_BUTTONS\n"
    "REVIT_MODAL_GUARD_RULE:RELY_ON_REVIT_API_DIALOGBOXSHOWING_GUARD_AND_FAILURE_PREPROCESSOR_WHEN_AVAILABLE_RISKY_GEOMETRY_DIALOGS_SHOULD_REPORT_FIX_ERRORS\n"
    "BRIDGE_TIMING_HINT_RULE:INCLUDE_TOP_OF_CODE_COMMENTS_WITH_INTEGER_SECONDS_FOR_THIS_CYCLE_WHEN_HELPFUL\n"
    "BRIDGE_TIMING_HINT_RULE:USE_COMMENT_FORMATS_EXACTLY_AS_HASH_SPACE_BRIDGE_RPS_WAIT_SECONDS_COLON_NUMBER_AND_HASH_SPACE_BRIDGE_CHATGPT_WAIT_SECONDS_COLON_NUMBER_AND_HASH_SPACE_BRIDGE_RETRY_WAIT_SECONDS_COLON_NUMBER\n"
    "BRIDGE_TIMING_HINT_RULE:CHOOSE_RPS_WAIT_SECONDS_BASED_ON_EXPECTED_REVIT_API_RUNTIME_FOR_THIS_SCRIPT_USUALLY_20_TO_120_SECONDS\n"
    "BRIDGE_TIMING_HINT_RULE:CHOOSE_CHATGPT_WAIT_SECONDS_BASED_ON_EXPECTED_COMPLEXITY_OF_NEXT_CODE_GENERATION_USUALLY_45_TO_180_SECONDS\n"
    "RAG_RULE:WHEN_REVIT_API_OR_IRONPYTHON_UNCERTAINTY_EXISTS_USE_STABLE_KNOWN_PATTERNS_FROM_REVIT_API_DOCS_PYREVIT_REVITPYTHONSHELL_REVITLOOKUP_AND_PRIOR_BRIDGE_OUTPUTS_BEFORE_SPECULATING\n"
    "RAG_RULE:PREFER_SMALL_IDEMPOTENT_REVIT_API_PATTERNS_THAT_CAN_BE_VERIFIED_BY_RPS_TEXT_AND_TARGETED_QC_EXPORTS"
)


DEFAULT_CONFIG = {
    "timing": {
        "chatgpt_output_wait_seconds": 120,
        "chatgpt_copy_retry_wait_seconds": 90,
        "chatgpt_copy_retry_attempts": 2,
        "chatgpt_page_down_count": 2,
        "chatgpt_page_down_pre_copy_wait_seconds": 3,
        "chatgpt_page_down_post_copy_wait_seconds": 3,
        "browser_refresh_after_click_wait_seconds": 3,
        "chatgpt_reprint_wait_seconds": 90,
        "rps_output_wait_seconds": 60,
        "startup_delay_seconds": 3,
        "pause_between_actions": 0.5,
        "pause_after_copy_seconds": 3,
        "pause_after_paste_seconds": 3,
        "revit_warning_ok_click_wait_seconds": 0.0,
        "revit_dialog_click_wait_seconds": 0.0,
        "revit_dialog_sequence_passes": 0,
        "revit_dialog_before_output_wait_seconds": 0,
        "default_short_wait_seconds": 3,
        "chatgpt_input_paste_wait_seconds": 7,
        "chatgpt_wait_min_seconds": 45,
        "chatgpt_wait_max_seconds": 180,
        "rps_wait_min_seconds": 20,
        "rps_wait_max_seconds": 120,
        "retry_wait_min_seconds": 45,
        "retry_wait_max_seconds": 180
    },
    "qc": {
        "export_folder": "C:\\RevitBridge\\QC_Exports",
        "upload_staging_folder": "C:\\RevitBridge\\QC_Upload",
        "upload_staging_basename": "qc_upload",
        "valid_export_extensions": [".png", ".pdf", ".jpg", ".jpeg"],
        "file_stability_checks": 3,
        "file_stability_interval_seconds": 1.0,
        "upload_wait_seconds": 4,
        "upload_step_wait_seconds": 3,
        "activate_chatgpt_input_before_upload": True,
        "file_dialog_path_entry_attempts": 2,
        "file_picker_open_after_paste": True,
        "file_picker_open_wait_seconds": 7,
        "batch_upload_one_dialog": True,
        "upload_debug_log": "C:\\RevitBridge\\QC_Upload\\upload_debug_log.txt",
        "newest_file_fallback_max_age_seconds": 900
    },
    "bridge": {
        "max_cycles": 2222,
        "stop_on_syntax_error": True,
        "stop_on_fix_errors": True,
        "stop_on_completion_states": False,
        "stop_on_repeated_state": False,
        "revit_api_modal_guard_enabled": True,
        "max_repeated_state_count": 8,
        "max_invalid_code_attempts": 2,
        "max_reprint_attempts": 1
    },
    "rag": {
        "enabled": True,
        "rag_folder": "C:\\RevitBridge\\RAG",
        "retrieval_script": "C:\\RevitBridge\\RAG\\rag_retrieve.py",
        "cycle_log_file": "C:\\RevitBridge\\RAG\\cycles\\bridge_cycles.jsonl",
        "latest_context_file": "C:\\RevitBridge\\RAG\\latest_retrieved_context.txt",
        "max_context_chars": 6000,
        "top_k": 8,
        "include_on_initial_prompt": True,
        "include_on_followup_prompt": True,
        "log_cycles": True,
        "retrieval_timeout_seconds": 8
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


def load_config():
    if not CONFIG_PATH.exists():
        with open(str(CONFIG_PATH), "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    with open(str(CONFIG_PATH), "r") as f:
        config = json.load(f)

    original_coordinates = {}
    try:
        original_coordinates = dict(config.get("coordinates", {}))
    except Exception:
        original_coordinates = {}

    config = merge_defaults(config, json.loads(json.dumps(DEFAULT_CONFIG)))

    if "hotkeys" not in config:
        config["hotkeys"] = {}
    config["hotkeys"]["rps_execute"] = ["f5"]

    if "bridge" not in config:
        config["bridge"] = {}
    if int(config["bridge"].get("max_cycles", 0)) < 2222:
        config["bridge"]["max_cycles"] = 2222
    if "revit_api_modal_guard_enabled" not in config["bridge"]:
        config["bridge"]["revit_api_modal_guard_enabled"] = True
    if "stop_on_completion_states" not in config["bridge"]:
        config["bridge"]["stop_on_completion_states"] = False
    if "stop_on_repeated_state" not in config["bridge"]:
        config["bridge"]["stop_on_repeated_state"] = False

    if "timing" not in config:
        config["timing"] = {}

    for stale_key in [
        "chatgpt_copy_offset_scan_enabled",
        "chatgpt_copy_offset_scan_pixels",
        "chatgpt_copy_offset_scan_wait_seconds"
    ]:
        if stale_key in config["timing"]:
            del config["timing"][stale_key]
    # V3.21: remove GUI modal click sweeps and reduce short waits.
    config["timing"]["revit_warning_ok_click_wait_seconds"] = 0.0
    config["timing"]["revit_dialog_click_wait_seconds"] = 0.0
    config["timing"]["revit_dialog_sequence_passes"] = 0
    config["timing"]["revit_dialog_before_output_wait_seconds"] = 0
    config["timing"]["browser_refresh_after_click_wait_seconds"] = 3
    config["timing"]["chatgpt_page_down_pre_copy_wait_seconds"] = 3
    config["timing"]["chatgpt_page_down_post_copy_wait_seconds"] = 3
    config["timing"]["pause_after_copy_seconds"] = 3
    config["timing"]["pause_after_paste_seconds"] = 3
    config["timing"]["default_short_wait_seconds"] = 3

    # Dynamic waits are decided per cycle. These values are fallbacks only.
    if "chatgpt_output_wait_seconds" not in config["timing"]:
        config["timing"]["chatgpt_output_wait_seconds"] = 120
    if "rps_output_wait_seconds" not in config["timing"]:
        config["timing"]["rps_output_wait_seconds"] = 60
    if "chatgpt_copy_retry_wait_seconds" not in config["timing"]:
        config["timing"]["chatgpt_copy_retry_wait_seconds"] = 90
    config["timing"]["chatgpt_copy_retry_attempts"] = 2
    if "chatgpt_input_paste_wait_seconds" not in config["timing"]:
        config["timing"]["chatgpt_input_paste_wait_seconds"] = 7
    if "chatgpt_wait_min_seconds" not in config["timing"]:
        config["timing"]["chatgpt_wait_min_seconds"] = 45
    if "chatgpt_wait_max_seconds" not in config["timing"]:
        config["timing"]["chatgpt_wait_max_seconds"] = 180
    if "rps_wait_min_seconds" not in config["timing"]:
        config["timing"]["rps_wait_min_seconds"] = 20
    if "rps_wait_max_seconds" not in config["timing"]:
        config["timing"]["rps_wait_max_seconds"] = 120
    if "retry_wait_min_seconds" not in config["timing"]:
        config["timing"]["retry_wait_min_seconds"] = 45
    if "retry_wait_max_seconds" not in config["timing"]:
        config["timing"]["retry_wait_max_seconds"] = 180

    if "qc" not in config:
        config["qc"] = {}
    config["qc"]["upload_wait_seconds"] = int(config["qc"].get("upload_wait_seconds", 3) or 3)
    if config["qc"]["upload_wait_seconds"] != 3:
        config["qc"]["upload_wait_seconds"] = 3
    config["qc"]["upload_step_wait_seconds"] = int(config["qc"].get("upload_step_wait_seconds", 3) or 3)
    if config["qc"]["upload_step_wait_seconds"] != 3:
        config["qc"]["upload_step_wait_seconds"] = 3
    if "file_picker_open_wait_seconds" not in config["qc"]:
        config["qc"]["file_picker_open_wait_seconds"] = 7
    if "batch_upload_one_dialog" not in config["qc"]:
        config["qc"]["batch_upload_one_dialog"] = True

    if "coordinates" not in config:
        config["coordinates"] = {}

    # The calibration UI stores the ChatGPT code-block copy button as
    # chatgpt_response_click and labels it as the copy icon AFTER Page Down.
    # Treat that as authoritative for the copy-button click.
    if "chatgpt_response_click" in config["coordinates"]:
        config["coordinates"]["chatgpt_code_copy_button"] = config["coordinates"]["chatgpt_response_click"]
    elif "chatgpt_code_copy_button" not in config["coordinates"]:
        config["coordinates"]["chatgpt_code_copy_button"] = [950, 430]
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

    with open(str(CONFIG_PATH), "w") as f:
        json.dump(config, f, indent=2)

    return config


CONFIG = load_config()

TIMING = CONFIG.get("timing", {})
QC = CONFIG.get("qc", {})
BRIDGE = CONFIG.get("bridge", {})
RAG = CONFIG.get("rag", {})
COORDS = CONFIG.get("coordinates", {})
HOTKEYS = CONFIG.get("hotkeys", {})

CHATGPT_OUTPUT_WAIT_SECONDS = int(TIMING.get("chatgpt_output_wait_seconds", 120))
CHATGPT_COPY_RETRY_WAIT_SECONDS = int(TIMING.get("chatgpt_copy_retry_wait_seconds", 90))
CHATGPT_COPY_RETRY_ATTEMPTS = int(TIMING.get("chatgpt_copy_retry_attempts", 2))
CHATGPT_PAGE_DOWN_COUNT = int(TIMING.get("chatgpt_page_down_count", 2))
CHATGPT_PAGE_DOWN_PRE_COPY_WAIT_SECONDS = int(TIMING.get("chatgpt_page_down_pre_copy_wait_seconds", 4))
CHATGPT_PAGE_DOWN_POST_COPY_WAIT_SECONDS = int(TIMING.get("chatgpt_page_down_post_copy_wait_seconds", 4))
BROWSER_REFRESH_AFTER_CLICK_WAIT_SECONDS = int(TIMING.get("browser_refresh_after_click_wait_seconds", 3))
CHATGPT_REPRINT_WAIT_SECONDS = int(TIMING.get("chatgpt_reprint_wait_seconds", 60))
RPS_OUTPUT_WAIT_SECONDS = int(TIMING.get("rps_output_wait_seconds", 60))
STARTUP_DELAY_SECONDS = int(TIMING.get("startup_delay_seconds", 3))
PAUSE_BETWEEN_ACTIONS = float(TIMING.get("pause_between_actions", 0.5))
PAUSE_AFTER_COPY_SECONDS = int(TIMING.get("pause_after_copy_seconds", 3))
PAUSE_AFTER_PASTE_SECONDS = int(TIMING.get("pause_after_paste_seconds", 3))
REVIT_WARNING_OK_CLICK_WAIT_SECONDS = float(TIMING.get("revit_warning_ok_click_wait_seconds", 0.8))
REVIT_DIALOG_CLICK_WAIT_SECONDS = float(TIMING.get("revit_dialog_click_wait_seconds", 0.8))
REVIT_DIALOG_SEQUENCE_PASSES = int(TIMING.get("revit_dialog_sequence_passes", 2))
REVIT_DIALOG_BEFORE_OUTPUT_WAIT_SECONDS = int(TIMING.get("revit_dialog_before_output_wait_seconds", 0))
DEFAULT_SHORT_WAIT_SECONDS = int(TIMING.get("default_short_wait_seconds", 3))
CHATGPT_INPUT_PASTE_WAIT_SECONDS = int(TIMING.get("chatgpt_input_paste_wait_seconds", 7))
CHATGPT_WAIT_MIN_SECONDS = int(TIMING.get("chatgpt_wait_min_seconds", 45))
CHATGPT_WAIT_MAX_SECONDS = int(TIMING.get("chatgpt_wait_max_seconds", 180))
RPS_WAIT_MIN_SECONDS = int(TIMING.get("rps_wait_min_seconds", 20))
RPS_WAIT_MAX_SECONDS = int(TIMING.get("rps_wait_max_seconds", 120))
RETRY_WAIT_MIN_SECONDS = int(TIMING.get("retry_wait_min_seconds", 45))
RETRY_WAIT_MAX_SECONDS = int(TIMING.get("retry_wait_max_seconds", 180))

QC_EXPORT_FOLDER = QC.get("export_folder", r"C:\RevitBridge\\QC_Exports")
QC_UPLOAD_STAGING_FOLDER = QC.get("upload_staging_folder", r"C:\RevitBridge\\QC_Upload")
QC_UPLOAD_STAGING_BASENAME = QC.get("upload_staging_basename", "qc_upload")
QC_VALID_EXTENSIONS = QC.get("valid_export_extensions", [".png", ".pdf", ".jpg", ".jpeg"])
QC_FILE_STABILITY_CHECKS = int(QC.get("file_stability_checks", 3))
QC_FILE_STABILITY_INTERVAL_SECONDS = float(QC.get("file_stability_interval_seconds", 1.0))
QC_UPLOAD_WAIT_SECONDS = int(QC.get("upload_wait_seconds", 3))
QC_UPLOAD_STEP_WAIT_SECONDS = int(QC.get("upload_step_wait_seconds", 3))
QC_ACTIVATE_CHATGPT_INPUT_BEFORE_UPLOAD = bool(QC.get("activate_chatgpt_input_before_upload", True))
QC_FILE_DIALOG_PATH_ENTRY_ATTEMPTS = int(QC.get("file_dialog_path_entry_attempts", 2))
QC_FILE_PICKER_OPEN_AFTER_PASTE = bool(QC.get("file_picker_open_after_paste", True))
QC_FILE_PICKER_OPEN_WAIT_SECONDS = int(QC.get("file_picker_open_wait_seconds", 7))
QC_BATCH_UPLOAD_ONE_DIALOG = bool(QC.get("batch_upload_one_dialog", True))
QC_UPLOAD_DEBUG_LOG = QC.get("upload_debug_log", r"C:\RevitBridge\\QC_Upload\\upload_debug_log.txt")
QC_NEWEST_FILE_FALLBACK_MAX_AGE_SECONDS = int(QC.get("newest_file_fallback_max_age_seconds", 900))

MAX_CYCLES = int(BRIDGE.get("max_cycles", 40))
REVIT_API_MODAL_GUARD_ENABLED = bool(BRIDGE.get("revit_api_modal_guard_enabled", True))
STOP_ON_SYNTAX_ERROR = bool(BRIDGE.get("stop_on_syntax_error", True))
STOP_ON_FIX_ERRORS = bool(BRIDGE.get("stop_on_fix_errors", True))
STOP_ON_COMPLETION_STATES = bool(BRIDGE.get("stop_on_completion_states", False))
STOP_ON_REPEATED_STATE = bool(BRIDGE.get("stop_on_repeated_state", False))
MAX_REPEATED_STATE_COUNT = int(BRIDGE.get("max_repeated_state_count", 8))
MAX_INVALID_CODE_ATTEMPTS = int(BRIDGE.get("max_invalid_code_attempts", 2))
MAX_REPRINT_ATTEMPTS = int(BRIDGE.get("max_reprint_attempts", 1))

RAG_ENABLED = bool(RAG.get("enabled", True))
RAG_FOLDER = RAG.get("rag_folder", r"C:\RevitBridge\RAG")
RAG_RETRIEVAL_SCRIPT = RAG.get("retrieval_script", r"C:\RevitBridge\RAG\rag_retrieve.py")
RAG_CYCLE_LOG_FILE = RAG.get("cycle_log_file", r"C:\RevitBridge\RAG\cycles\bridge_cycles.jsonl")
RAG_LATEST_CONTEXT_FILE = RAG.get("latest_context_file", r"C:\RevitBridge\RAG\latest_retrieved_context.txt")
RAG_MAX_CONTEXT_CHARS = int(RAG.get("max_context_chars", 6000))
RAG_TOP_K = int(RAG.get("top_k", 8))
RAG_INCLUDE_ON_INITIAL_PROMPT = bool(RAG.get("include_on_initial_prompt", True))
RAG_INCLUDE_ON_FOLLOWUP_PROMPT = bool(RAG.get("include_on_followup_prompt", True))
RAG_LOG_CYCLES = bool(RAG.get("log_cycles", True))
RAG_RETRIEVAL_TIMEOUT_SECONDS = int(RAG.get("retrieval_timeout_seconds", 8))

CLEAR_CLIPBOARD_BEFORE_COPY = True
PRINT_CLIPBOARD_PREVIEW = True
CLIPBOARD_PREVIEW_CHARS = 800
VERBOSE = True


def hotkey_value(name, fallback):
    value = HOTKEYS.get(name)
    if not value:
        return fallback
    return tuple(value)


COPY_HOTKEY = hotkey_value("copy", ("ctrl", "c"))
PASTE_HOTKEY = hotkey_value("paste", ("ctrl", "v"))
SELECT_ALL_HOTKEY = hotkey_value("select_all", ("ctrl", "a"))
CHATGPT_SUBMIT_HOTKEY = hotkey_value("chatgpt_submit", ("enter",))
RPS_EXECUTE_HOTKEY = hotkey_value("rps_execute", ("f5",))
PAGE_DOWN_HOTKEY = hotkey_value("page_down", ("pagedown",))


def log(message):
    if VERBOSE:
        print(message)


def pause(seconds=None):
    if seconds is None:
        seconds = PAUSE_BETWEEN_ACTIONS
    time.sleep(seconds)


def countdown(seconds, label):
    log("")
    log("{}: waiting {} seconds...".format(label, seconds))
    for remaining in range(seconds, 0, -1):
        if remaining % 10 == 0 or remaining <= 5:
            log("  {} seconds remaining".format(remaining))
        time.sleep(1)
    log("{}: wait complete.".format(label))


def step_wait(label):
    countdown(QC_UPLOAD_STEP_WAIT_SECONDS, label)

# ============================================================
# V3.22 MINIMAL PATCH: SAFE WINDOWS FILE DIALOG UPLOAD GUARD
# Prevents the bridge from continuing/pasting into ChatGPT while
# the Windows Open dialog is still active. Uses full quoted paths.
# ============================================================

try:
    _AI_USER32 = ctypes.windll.user32
    _AI_EnumWindows = _AI_USER32.EnumWindows
    _AI_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    _AI_IsWindowVisible = _AI_USER32.IsWindowVisible
    _AI_GetWindowTextW = _AI_USER32.GetWindowTextW
    _AI_GetWindowTextLengthW = _AI_USER32.GetWindowTextLengthW
    _AI_GetClassNameW = _AI_USER32.GetClassNameW
    _AI_SetForegroundWindow = _AI_USER32.SetForegroundWindow
    _AI_ShowWindow = _AI_USER32.ShowWindow
    _AI_SW_RESTORE = 9
except Exception:
    _AI_USER32 = None


def _ai_get_window_text(hwnd):
    try:
        length = _AI_GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        _AI_GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""


def _ai_get_class_name(hwnd):
    try:
        buff = ctypes.create_unicode_buffer(256)
        _AI_GetClassNameW(hwnd, buff, 256)
        return buff.value
    except Exception:
        return ""


def _ai_enum_visible_file_dialogs():
    dialogs = []
    if _AI_USER32 is None:
        return dialogs

    def callback(hwnd, lparam):
        try:
            if _AI_IsWindowVisible(hwnd):
                cls = _ai_get_class_name(hwnd)
                title = _ai_get_window_text(hwnd)
                if cls == "#32770":
                    tl = (title or "").lower()
                    if ("open" in tl) or ("upload" in tl) or ("choose" in tl) or ("file" in tl):
                        dialogs.append((hwnd, title, cls))
        except Exception:
            pass
        return True

    try:
        _AI_EnumWindows(_AI_EnumWindowsProc(callback), 0)
    except Exception:
        pass
    return dialogs


def windows_file_dialog_is_open():
    return len(_ai_enum_visible_file_dialogs()) > 0


def bring_windows_file_dialog_to_front():
    dialogs = _ai_enum_visible_file_dialogs()
    if not dialogs:
        return False
    hwnd = dialogs[0][0]
    try:
        _AI_ShowWindow(hwnd, _AI_SW_RESTORE)
        _AI_SetForegroundWindow(hwnd)
        time.sleep(0.35)
        return True
    except Exception:
        return False


def wait_for_windows_file_dialog_open(timeout_seconds):
    start = time.time()
    while time.time() - start < timeout_seconds:
        if windows_file_dialog_is_open():
            append_upload_debug("Windows Open dialog detected.")
            return True
        time.sleep(0.25)
    append_upload_debug("Windows Open dialog was not detected within timeout.")
    return False


def wait_for_windows_file_dialog_close(timeout_seconds):
    start = time.time()
    while time.time() - start < timeout_seconds:
        if not windows_file_dialog_is_open():
            append_upload_debug("Windows Open dialog closed.")
            return True
        time.sleep(0.25)
    append_upload_debug("Windows Open dialog is still open after timeout.")
    return False



def clamp_seconds(value, min_seconds, max_seconds, fallback):
    try:
        n = int(value)
    except Exception:
        n = int(fallback)
    if n < int(min_seconds):
        n = int(min_seconds)
    if n > int(max_seconds):
        n = int(max_seconds)
    return n


def extract_bridge_wait_hint(text, names, fallback, min_seconds, max_seconds):
    s = str(text or "")
    for name in names:
        pattern = r"(?im)^\s*#?\s*" + re.escape(name) + r"\s*:?\s*(\d+)\s*$"
        m = re.search(pattern, s)
        if m:
            return clamp_seconds(m.group(1), min_seconds, max_seconds, fallback)
    return clamp_seconds(fallback, min_seconds, max_seconds, fallback)


def complexity_score(text):
    s = str(text or "")
    u = s.upper()
    score = len(s) // 1800
    weighted_tokens = [
        ("EXPORTIMAGE", 5),
        ("IMAGEEXPORTOPTIONS", 5),
        ("FILTEREDELEMENTCOLLECTOR", 3),
        ("TRANSACTION(", 4),
        ("DOC.DELETE", 4),
        ("ELEMENTTRANSFORMUTILS", 5),
        ("FAMILYINSTANCE", 4),
        ("TEXTNOTE.CREATE", 3),
        ("VIEWPORT", 3),
        ("VIEWSHEET", 3),
        ("REVISION", 3),
        ("DIMENSION", 3),
        ("ROOM", 2),
        ("WALL", 2),
        ("FLOOR", 2),
        ("ROOF", 3),
        ("DIRECTSHAPE", 5),
        ("SOLID", 4),
        ("BOOLEAN", 5),
        ("LOOP", 2),
        ("QAQC", 2),
        ("OCR", 4),
        ("REDLINE", 2),
        ("UPLOAD", 2),
        ("PNG", 2)
    ]
    for token, weight in weighted_tokens:
        if token in u:
            score += weight
    return score


def decide_chatgpt_wait_seconds(prompt_text, cycle_number=None, reason=None):
    hinted = extract_bridge_wait_hint(
        prompt_text,
        ["BRIDGE_CHATGPT_WAIT_SECONDS", "CHATGPT_WAIT_SECONDS", "NEXT_CHATGPT_WAIT_SECONDS"],
        CHATGPT_OUTPUT_WAIT_SECONDS,
        CHATGPT_WAIT_MIN_SECONDS,
        CHATGPT_WAIT_MAX_SECONDS
    )
    if hinted != clamp_seconds(CHATGPT_OUTPUT_WAIT_SECONDS, CHATGPT_WAIT_MIN_SECONDS, CHATGPT_WAIT_MAX_SECONDS, CHATGPT_OUTPUT_WAIT_SECONDS):
        return hinted
    score = complexity_score(prompt_text)
    if score >= 25:
        return clamp_seconds(180, CHATGPT_WAIT_MIN_SECONDS, CHATGPT_WAIT_MAX_SECONDS, CHATGPT_OUTPUT_WAIT_SECONDS)
    if score >= 16:
        return clamp_seconds(150, CHATGPT_WAIT_MIN_SECONDS, CHATGPT_WAIT_MAX_SECONDS, CHATGPT_OUTPUT_WAIT_SECONDS)
    if score >= 9:
        return clamp_seconds(120, CHATGPT_WAIT_MIN_SECONDS, CHATGPT_WAIT_MAX_SECONDS, CHATGPT_OUTPUT_WAIT_SECONDS)
    if score >= 4:
        return clamp_seconds(90, CHATGPT_WAIT_MIN_SECONDS, CHATGPT_WAIT_MAX_SECONDS, CHATGPT_OUTPUT_WAIT_SECONDS)
    return clamp_seconds(60, CHATGPT_WAIT_MIN_SECONDS, CHATGPT_WAIT_MAX_SECONDS, CHATGPT_OUTPUT_WAIT_SECONDS)


def decide_rps_wait_seconds(code_text, cycle_number=None):
    hinted = extract_bridge_wait_hint(
        code_text,
        ["BRIDGE_RPS_WAIT_SECONDS", "RPS_WAIT_SECONDS", "IPS_WAIT_SECONDS", "REVIT_RUN_WAIT_SECONDS"],
        RPS_OUTPUT_WAIT_SECONDS,
        RPS_WAIT_MIN_SECONDS,
        RPS_WAIT_MAX_SECONDS
    )
    if hinted != clamp_seconds(RPS_OUTPUT_WAIT_SECONDS, RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS, RPS_OUTPUT_WAIT_SECONDS):
        return hinted
    score = complexity_score(code_text)
    if score >= 28:
        return clamp_seconds(120, RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS, RPS_OUTPUT_WAIT_SECONDS)
    if score >= 18:
        return clamp_seconds(90, RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS, RPS_OUTPUT_WAIT_SECONDS)
    if score >= 10:
        return clamp_seconds(60, RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS, RPS_OUTPUT_WAIT_SECONDS)
    if score >= 5:
        return clamp_seconds(45, RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS, RPS_OUTPUT_WAIT_SECONDS)
    return clamp_seconds(25, RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS, RPS_OUTPUT_WAIT_SECONDS)


def decide_retry_wait_seconds(context_text, cycle_number=None):
    hinted = extract_bridge_wait_hint(
        context_text,
        ["BRIDGE_RETRY_WAIT_SECONDS", "CHATGPT_RETRY_WAIT_SECONDS", "RETRY_WAIT_SECONDS"],
        CHATGPT_COPY_RETRY_WAIT_SECONDS,
        RETRY_WAIT_MIN_SECONDS,
        RETRY_WAIT_MAX_SECONDS
    )
    if hinted != clamp_seconds(CHATGPT_COPY_RETRY_WAIT_SECONDS, RETRY_WAIT_MIN_SECONDS, RETRY_WAIT_MAX_SECONDS, CHATGPT_COPY_RETRY_WAIT_SECONDS):
        return hinted
    score = complexity_score(context_text)
    if score >= 18:
        return clamp_seconds(150, RETRY_WAIT_MIN_SECONDS, RETRY_WAIT_MAX_SECONDS, CHATGPT_COPY_RETRY_WAIT_SECONDS)
    if score >= 10:
        return clamp_seconds(120, RETRY_WAIT_MIN_SECONDS, RETRY_WAIT_MAX_SECONDS, CHATGPT_COPY_RETRY_WAIT_SECONDS)
    return clamp_seconds(75, RETRY_WAIT_MIN_SECONDS, RETRY_WAIT_MAX_SECONDS, CHATGPT_COPY_RETRY_WAIT_SECONDS)



def coord(name):
    value = COORDS.get(name)
    if not value or len(value) != 2:
        raise RuntimeError("Missing coordinate in bridge_config.json: {}".format(name))
    return int(value[0]), int(value[1])


def has_coord(name):
    value = COORDS.get(name)
    return value is not None and len(value) == 2

def chatgpt_code_copy_coord_name():
    # Calibration UI labels chatgpt_response_click as the code-block Copy button
    # AFTER the configured Page Down sequence. Treat it as authoritative.
    if has_coord("chatgpt_response_click"):
        return "chatgpt_response_click"
    return "chatgpt_code_copy_button"


def click_chatgpt_code_copy_button():
    name = chatgpt_code_copy_coord_name()
    click_at_name(name, "ChatGPT code copy button")


def click_at_xy(x, y, label=None):
    if label:
        log("Clicking: {} at {}, {}".format(label, x, y))
    try:
        pyautogui.moveTo(x, y, duration=0.15)
        pause(0.10)
    except Exception:
        pass
    pyautogui.click(x, y)
    pause()


def click_at_name(name, label=None):
    x, y = coord(name)
    click_at_xy(x, y, label)


def click_revit_warning_ok_if_calibrated(reason=None):
    if not has_coord("revit_warning_ok"):
        log("Revit warning OK coordinate is not calibrated; skipping warning OK click.")
        return False
    try:
        label = "Revit warning OK"
        if reason:
            label = label + " after " + str(reason)
        click_at_name("revit_warning_ok", label)
        time.sleep(REVIT_WARNING_OK_CLICK_WAIT_SECONDS)
        return True
    except Exception as ex:
        log("Revit warning OK click failed: {}".format(ex))
        return False


def active_window_title():
    try:
        win = pyautogui.getActiveWindow()
        if win is not None:
            return str(win.title)
    except Exception:
        pass
    return ""


def click_revit_dialog_coord_if_calibrated(name, label, reason=None):
    if not has_coord(name):
        log("{} coordinate is not calibrated; skipping.".format(label))
        return False
    try:
        final_label = label
        if reason:
            final_label = final_label + " after " + str(reason)
        click_at_name(name, final_label)
        time.sleep(REVIT_DIALOG_CLICK_WAIT_SECONDS)
        return True
    except Exception as ex:
        log("{} click failed: {}".format(label, ex))
        return False


def handle_revit_modal_dialogs(context=None):
    reason = context if context else "Revit run"
    title = active_window_title()
    log("GUI Revit modal click sweep disabled for {}. Active window title: {}".format(reason, title))
    log("No Unjoin, OK, warning OK, disconnect, or Cancel coordinate clicks are sent by the bridge.")
    log("Relying on the Revit API modal guard wrapper and transaction failure preprocessor only.")
    return False


def refresh_browser_if_calibrated(reason=None):
    if not has_coord("browser_refresh"):
        log("Browser refresh coordinate is not calibrated; skipping browser refresh.")
        return False
    try:
        label = "Browser refresh"
        if reason:
            label = label + " for " + str(reason)
        click_at_name("browser_refresh", label)
        return True
    except Exception as ex:
        log("Browser refresh click failed: {}".format(ex))
        return False


def hotkey(keys, label=None):
    if label:
        log("Hotkey: {}".format(label))
    pyautogui.hotkey(*keys)
    pause()


def press_hotkey_or_key(keys, label=None):
    if label:
        log("Pressing: {}".format(label))
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)
    pause()


def press_key(key, label=None):
    if label:
        log("Pressing: {}".format(label))
    pyautogui.press(key)
    pause()


def make_clipboard_sentinel(label):
    safe_label = str(label).replace(" ", "_")
    return "__REVIT_BRIDGE_CLIPBOARD_SENTINEL__" + safe_label + "__" + str(int(time.time() * 1000)) + "__"


def set_clipboard_sentinel(label):
    sentinel = make_clipboard_sentinel(label)
    pyperclip.copy(sentinel)
    pause(0.15)
    return sentinel


def is_clipboard_sentinel(text):
    return str(text or "").startswith("__REVIT_BRIDGE_CLIPBOARD_SENTINEL__")


def clear_clipboard():
    pyperclip.copy("")
    pause(0.15)


def get_clipboard_text():
    text = pyperclip.paste()
    if text is None:
        return ""
    return text


def paste_text(text, label=None, post_wait_seconds=None):
    if label:
        log("Pasting: {}".format(label))
    pyperclip.copy(text)
    pause()
    hotkey(PASTE_HOTKEY, "paste")
    if post_wait_seconds is None:
        post_wait_seconds = PAUSE_AFTER_PASTE_SECONDS
    countdown(int(post_wait_seconds), "Post paste wait")


def clear_focused_text_field(label):
    log("Clearing focused field: {}".format(label))
    hotkey(SELECT_ALL_HOTKEY, "select all in " + label)
    press_key("backspace", "clear " + label)


def copy_current_selection(label=None):
    if label:
        log("Copying selected text: {}".format(label))
    sentinel = ""
    if CLEAR_CLIPBOARD_BEFORE_COPY:
        sentinel = set_clipboard_sentinel(label or "selection_copy")
    hotkey(COPY_HOTKEY, "copy")
    countdown(PAUSE_AFTER_COPY_SECONDS, "Post copy wait")
    copied = get_clipboard_text()
    if not copied.strip():
        log("WARNING: Clipboard is empty after copy attempt.")
    if sentinel and copied == sentinel:
        log("WARNING: Clipboard sentinel unchanged after copy attempt; copy likely failed.")
        return ""
    if is_clipboard_sentinel(copied):
        log("WARNING: Clipboard still contains bridge sentinel; copy likely failed.")
        return ""
    return copied


def select_all_and_copy(label=None):
    if label:
        log("Select all and copy: {}".format(label))
    hotkey(SELECT_ALL_HOTKEY, "select all")
    pause()
    return copy_current_selection(label)


def preview_text(text, title):
    if not PRINT_CLIPBOARD_PREVIEW:
        return
    log("")
    log(title)
    if not text:
        log("[EMPTY]")
        return
    normalized = text.replace("\r\n", "\n")
    if len(normalized) > CLIPBOARD_PREVIEW_CHARS:
        log(normalized[:CLIPBOARD_PREVIEW_CHARS])
        log("...[preview truncated]")
    else:
        log(normalized)


def basic_looks_like_revit_python(text):
    s = (text or "").strip()
    if not s:
        return False

    upper = s.upper()

    rejection_tokens = [
        "MODE:REVIT_BRIDGE",
        "CURRENT_BRIDGE_EXECUTION_COUNT:",
        "VISUAL_QAQC_REQUIRED:",
        "RUN ANOTHER CYCLE",
        "TYPE Y TO CONTINUE",
        "REPRINT_PREVIOUS_REVIT_PYTHON_CODE_BLOCK_ONLY"
    ]
    for token in rejection_tokens:
        if token in upper:
            return False

    if "RPS_OUTPUT:" in upper and "FROM AUTODESK.REVIT.DB" not in upper and "CLR.ADDREFERENCE" not in upper:
        return False
    if "SYNTAX ERROR:" in upper and "FROM AUTODESK.REVIT.DB" not in upper and "CLR.ADDREFERENCE" not in upper:
        return False
    if is_clipboard_sentinel(s):
        return False

    has_revit = False
    tokens = [
        "__REVIT__",
        "AUTODESK.REVIT.DB",
        "CLR.ADDREFERENCE(\"REVITAPI\")",
        "CLR.ADDREFERENCE('REVITAPI')",
        "FILTEREDELEMENTCOLLECTOR",
        "TRANSACTION(",
        "VIEWSHEET",
        "VIEWPORT",
        "TEXTNOTE",
        "IMAGEEXPORTOPTIONS",
        "UIDOC = __REVIT__",
        "DOC = UIDOC.DOCUMENT"
    ]

    for token in tokens:
        if token in upper:
            has_revit = True
            break

    has_python = False
    python_tokens = ["IMPORT ", "FROM ", "DEF ", "TRY:", "CLASS "]
    for token in python_tokens:
        if token in upper:
            has_python = True
            break

    has_output = False
    if "NEXT_RECOMMENDED_STATE" in upper:
        has_output = True
    elif "RESULTS" in upper and "ERRORS" in upper:
        has_output = True

    return has_revit and has_python and has_output


def extract_revit_python_code(text):
    s = (text or "").strip()
    if not s:
        return ""

    if is_clipboard_sentinel(s):
        return ""

    normalized = s.replace("\r\n", "\n").replace("\r", "\n")

    python_blocks = re.findall(r"```\s*(?:python|py|ironpython)(?:[^\n`]*)?\n(.*?)```", normalized, re.DOTALL | re.IGNORECASE)
    if python_blocks:
        for block in reversed(python_blocks):
            candidate = block.strip()
            if basic_looks_like_revit_python(candidate):
                return candidate

    any_blocks = re.findall(r"```[^\n`]*\n(.*?)```", normalized, re.DOTALL)
    if any_blocks:
        for block in reversed(any_blocks):
            candidate = block.strip()
            if basic_looks_like_revit_python(candidate):
                return candidate

    if basic_looks_like_revit_python(normalized):
        return normalized

    lines = normalized.split("\n")
    start_index = None

    starters = [
        "# -*- coding",
        "import ",
        "from ",
        "try:",
        "def ",
        "class ",
        "uidoc = __revit__",
        "doc = __revit__",
        "clr.AddReference"
    ]

    for i, line in enumerate(lines):
        stripped = line.strip()
        for starter in starters:
            if stripped.startswith(starter):
                start_index = i
                break
        if start_index is not None:
            break

    if start_index is not None:
        candidate = "\n".join(lines[start_index:]).strip()
        # Trim accidental transcript after a shell prompt if present.
        prompt_index = candidate.find("\n>>>")
        if prompt_index > 0:
            candidate = candidate[:prompt_index].strip()
        if basic_looks_like_revit_python(candidate):
            return candidate

    return ""



def truncate_for_rag(text, max_chars):
    s = str(text or "")
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    head = int(max_chars * 0.65)
    tail = max_chars - head - 80
    if tail < 0:
        tail = 0
    return s[:head] + "\n\n...[RAG query truncated]...\n\n" + s[-tail:]


def ensure_rag_folder():
    try:
        if RAG_FOLDER and not os.path.isdir(RAG_FOLDER):
            os.makedirs(RAG_FOLDER)
        cycle_folder = os.path.dirname(RAG_CYCLE_LOG_FILE)
        if cycle_folder and not os.path.isdir(cycle_folder):
            os.makedirs(cycle_folder)
        return True
    except Exception as ex:
        log("RAG folder setup failed: {}".format(ex))
        return False


def run_rag_retrieval(query_text):
    if not RAG_ENABLED:
        return ""
    if not RAG_RETRIEVAL_SCRIPT or not os.path.exists(RAG_RETRIEVAL_SCRIPT):
        return ""
    query = truncate_for_rag(query_text, 12000)
    cmd = [sys.executable, RAG_RETRIEVAL_SCRIPT, "--query", query, "--top-k", str(RAG_TOP_K), "--max-chars", str(RAG_MAX_CONTEXT_CHARS)]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = proc.communicate(timeout=RAG_RETRIEVAL_TIMEOUT_SECONDS)
        except TypeError:
            out, err = proc.communicate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            return ""
        try:
            if not isinstance(out, str):
                out = out.decode("utf-8", "replace")
        except Exception:
            out = str(out)
        context = out.strip()
        if context:
            try:
                ensure_rag_folder()
                folder = os.path.dirname(RAG_LATEST_CONTEXT_FILE)
                if folder and not os.path.isdir(folder):
                    os.makedirs(folder)
                f = open(RAG_LATEST_CONTEXT_FILE, "w")
                f.write(context)
                f.close()
            except Exception:
                pass
        return context
    except Exception as ex:
        log("RAG retrieval skipped after exception: {}".format(ex))
        return ""


def build_rag_enriched_data(user_prompt):
    if not RAG_ENABLED:
        return user_prompt
    if "LOCAL REVIT RAG CONTEXT:" in str(user_prompt):
        return user_prompt
    context = run_rag_retrieval(user_prompt)
    if not context:
        return user_prompt
    return (
        "LOCAL REVIT RAG CONTEXT:\n"
        "Use only if relevant. Prefer the current RPS output and current QC PNGs over stale memories.\n"
        "Do not cite this context in code; use it to avoid repeated Revit API mistakes.\n"
        + context[:RAG_MAX_CONTEXT_CHARS]
        + "\n\nDATA:\n"
        + str(user_prompt)
    )


def write_rag_cycle_record(cycle_number, chatgpt_code, rps_output, state):
    if not RAG_ENABLED or not RAG_LOG_CYCLES:
        return False
    try:
        ensure_rag_folder()
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cycle_number": cycle_number,
            "next_recommended_state": state,
            "code_preview": truncate_for_rag(chatgpt_code, 12000),
            "rps_output_preview": truncate_for_rag(rps_output, 16000)
        }
        f = open(RAG_CYCLE_LOG_FILE, "a")
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.close()
        return True
    except Exception as ex:
        log("RAG cycle logging failed: {}".format(ex))
        return False


def build_chatgpt_prompt(user_prompt):
    enriched = build_rag_enriched_data(user_prompt)
    if enriched != user_prompt:
        return BRIDGE_RESPONSE_INSTRUCTION + "\n\n" + enriched
    return BRIDGE_RESPONSE_INSTRUCTION + "\n\nDATA:\n" + user_prompt


def click_chatgpt_input_and_clear():
    click_at_name("chatgpt_input", "ChatGPT input")
    clear_focused_text_field("ChatGPT input")


def submit_prompt_to_chatgpt(user_prompt, wait_label, wait_seconds=None):
    log("")
    log("Submitting prompt to ChatGPT...")
    final_prompt = build_chatgpt_prompt(user_prompt)
    click_chatgpt_input_and_clear()
    paste_text(final_prompt, "ChatGPT bridge prompt", CHATGPT_INPUT_PASTE_WAIT_SECONDS)
    if has_coord("chatgpt_submit"):
        click_at_name("chatgpt_submit", "ChatGPT submit button")
    else:
        hotkey(CHATGPT_SUBMIT_HOTKEY, "submit ChatGPT prompt")
    if wait_seconds is None:
        wait_seconds = decide_chatgpt_wait_seconds(user_prompt, None, wait_label)
    log("Cycle-specific ChatGPT output wait selected: {} seconds".format(int(wait_seconds)))
    countdown(int(wait_seconds), wait_label)


def page_down_chatgpt_before_copy():
    if CHATGPT_PAGE_DOWN_COUNT <= 0:
        return

    log("")
    log("Paging down ChatGPT output before copy button click.")
    for i in range(CHATGPT_PAGE_DOWN_COUNT):
        press_hotkey_or_key(PAGE_DOWN_HOTKEY, "ChatGPT page down {} of {}".format(i + 1, CHATGPT_PAGE_DOWN_COUNT))

    countdown(CHATGPT_PAGE_DOWN_PRE_COPY_WAIT_SECONDS, "Wait before ChatGPT copy button click")


def copy_chatgpt_code_once():
    log("")
    log("Copying ChatGPT code using fixed calibrated code copy button after Page Down sequence.")
    log("The code copy button is used only in this ChatGPT-output-to-RPS-code-copy step.")
    log("It is not used while returning RPS output back to the ChatGPT input.")

    if refresh_browser_if_calibrated("code block restore before copy"):
        countdown(BROWSER_REFRESH_AFTER_CLICK_WAIT_SECONDS, "Browser refresh reload wait before Page Down and copy")

    page_down_chatgpt_before_copy()

    sentinel = ""
    if CLEAR_CLIPBOARD_BEFORE_COPY:
        sentinel = set_clipboard_sentinel("chatgpt_code_button")

    click_chatgpt_code_copy_button()

    countdown(CHATGPT_PAGE_DOWN_POST_COPY_WAIT_SECONDS, "Wait after ChatGPT copy button click")
    countdown(PAUSE_AFTER_COPY_SECONDS, "Post copy wait")

    copied_raw = get_clipboard_text()

    if sentinel and copied_raw == sentinel:
        log("Clipboard sentinel unchanged after calibrated copy-button click.")
        return ""

    if is_clipboard_sentinel(copied_raw):
        log("Clipboard still contains bridge sentinel after calibrated copy-button click.")
        return ""

    preview_text(copied_raw, "Raw copied from ChatGPT preview:")

    copied_code = extract_revit_python_code(copied_raw)
    preview_text(copied_code, "Extracted Revit Python preview:")

    if basic_looks_like_revit_python(copied_code):
        log("Valid Revit Python copied from fixed calibrated ChatGPT copy button.")
        return copied_code

    return ""


def copy_chatgpt_code_with_retry(retry_wait_seconds=None):
    attempts = int(CHATGPT_COPY_RETRY_ATTEMPTS)
    if attempts < 2:
        attempts = 2
    if attempts > 2:
        attempts = 2
    if retry_wait_seconds is None:
        retry_wait_seconds = CHATGPT_COPY_RETRY_WAIT_SECONDS
    retry_wait_seconds = clamp_seconds(retry_wait_seconds, RETRY_WAIT_MIN_SECONDS, RETRY_WAIT_MAX_SECONDS, CHATGPT_COPY_RETRY_WAIT_SECONDS)

    for attempt in range(1, attempts + 1):
        copied = copy_chatgpt_code_once()

        if basic_looks_like_revit_python(copied):
            log("ChatGPT code accepted on copy attempt {}.".format(attempt))
            return copied

        log("")
        log("ChatGPT copied text does not look like executable Revit Python.")
        log("Copy attempt {} of {} failed.".format(attempt, attempts))

        if attempt < attempts:
            countdown(retry_wait_seconds, "Single retry wait before copying ChatGPT output again")

    log("")
    log("ERROR: ChatGPT code was not ready or not valid after the one configured retry.")
    return ""


def request_reprint_previous_python_output(reason):
    log("")
    log("ChatGPT output did not copy as valid fenced Revit Python.")
    log("Requesting reprint of previous Python code block before counting failure.")
    log("Reason: {}".format(reason))

    rescue_prompt = (
        "REPRINT_PREVIOUS_REVIT_PYTHON_CODE_BLOCK_ONLY\n"
        "The previous response did not render or copy as a valid fenced Python code block.\n"
        "Do not create a new answer, explanation, summary or list.\n"
        "Reprint the previous executable IronPython-compatible Revit Python script only.\n"
        "The first character of your response must be the first backtick of this exact opening fence:\n"
        "```python\n"
        "The final characters of your response must be this exact closing fence:\n"
        "```\n"
        "Do not write any code-fence attributes such as id after the word python.\n"
        "Do not include any text before or after the fenced code block.\n"
        "Do not apologize.\n"
        "Do not explain.\n"
        "Do not use plain-text code outside the fenced code block."
    )

    for attempt in range(1, MAX_REPRINT_ATTEMPTS + 1):
        log("")
        log("Reprint request attempt {} of {}.".format(attempt, MAX_REPRINT_ATTEMPTS))
        submit_prompt_to_chatgpt(rescue_prompt, "ChatGPT previous-code reprint output wait", decide_chatgpt_wait_seconds(rescue_prompt, None, "reprint"))
        copied = copy_chatgpt_code_with_retry(decide_retry_wait_seconds(rescue_prompt, None))

        if basic_looks_like_revit_python(copied):
            log("Previous Python code reprint copied successfully.")
            return copied

        log("Previous Python code reprint still did not copy as valid Revit Python.")

    return ""


def build_revit_api_modal_guard_wrapper(code_text):
    user_code_literal = repr(code_text or "")
    wrapper_template = """
# ============================================================
# AUTO-INJECTED REVIT API MODAL GUARD
# Registers before user code executes so Revit dialogs can be
# overridden before they block the Python shell.
# The original ChatGPT RPS code is executed by exec() below.
# ============================================================
import os
import traceback

_AI_USER_CODE = __AI_USER_CODE_LITERAL__
_AI_MODAL_GUARD_LOG = []
_AI_MODAL_GUARD_FILE = r"C:\\RevitBridge\\revit_modal_guard_last_log.txt"
_AI_RPS_OUTPUT_FILE = r"C:\\RevitBridge\\rps_last_output.txt"
_AI_DIALOG_HANDLER_ATTACHED = False


def _ai_modal_guard_write_log():
    try:
        folder = os.path.dirname(_AI_MODAL_GUARD_FILE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        f = open(_AI_MODAL_GUARD_FILE, "w")
        f.write("\\n".join(_AI_MODAL_GUARD_LOG))
        f.close()
    except Exception:
        pass


def _ai_modal_guard_copy_clipboard(text):
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import Clipboard
        try:
            Clipboard.SetText(text)
        except Exception:
            Clipboard.SetDataObject(text, True)
    except Exception:
        pass


def _ai_modal_guard_publish_failure(text):
    try:
        folder = os.path.dirname(_AI_RPS_OUTPUT_FILE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        f = open(_AI_RPS_OUTPUT_FILE, "w")
        f.write(text)
        f.close()
    except Exception:
        pass
    _ai_modal_guard_copy_clipboard(text)
    print(text)


def _ai_dialog_text(args):
    dialog_id = ""
    message = ""
    title = ""
    try:
        dialog_id = str(args.DialogId)
    except Exception:
        pass
    try:
        message = str(args.Message)
    except Exception:
        pass
    try:
        title = str(args.Title)
    except Exception:
        pass
    return dialog_id, title, message


def _ai_pick_dialog_result(dialog_id, title, message):
    txt = (str(dialog_id) + "\\n" + str(title) + "\\n" + str(message)).lower()

    if "unjoin" in txt:
        return 1001, "COMMAND_LINK_1_UNJOIN"

    if "join" in txt and "element" in txt:
        return 1001, "COMMAND_LINK_1_JOIN_GEOMETRY_DECISION"

    if "slightly off axis" in txt:
        return 1, "OK_OFF_AXIS_WARNING"

    if "identical instances" in txt:
        return 1, "OK_IDENTICAL_INSTANCE_WARNING"

    if "room is not enclosed" in txt or "area is not enclosed" in txt:
        return 1, "OK_ROOM_OR_AREA_WARNING"

    if "warning" in txt and "error" not in txt and "serious" not in txt:
        return 1, "OK_GENERAL_WARNING"

    if "cannot" in txt or "can't" in txt or "failed" in txt or "error" in txt or "serious" in txt:
        return 8, "CANCEL_RISKY_GEOMETRY_DIALOG"

    if "revit" in txt or dialog_id:
        return 1, "OK_DEFAULT_REVIT_DIALOG"

    return 8, "CANCEL_UNKNOWN_DIALOG"


def _ai_dialog_handler(sender, args):
    try:
        dialog_id, title, message = _ai_dialog_text(args)
        result, reason = _ai_pick_dialog_result(dialog_id, title, message)
        _AI_MODAL_GUARD_LOG.append("DIALOG | id=" + dialog_id + " | title=" + title + " | decision=" + reason + " | result=" + str(result) + " | message=" + message[:500])
        try:
            args.OverrideResult(result)
        except Exception as ex:
            _AI_MODAL_GUARD_LOG.append("OVERRIDE_FAILED | " + str(ex))
    except Exception as ex:
        _AI_MODAL_GUARD_LOG.append("HANDLER_FAILED | " + str(ex))


try:
    from Autodesk.Revit.DB import IFailuresPreprocessor
    from Autodesk.Revit.DB import FailureProcessingResult
    from Autodesk.Revit.DB import FailureSeverity

    class AiBridgeFailuresPreprocessor(IFailuresPreprocessor):
        def PreprocessFailures(self, failuresAccessor):
            try:
                messages = failuresAccessor.GetFailureMessages()
                for fm in messages:
                    try:
                        desc = ""
                        try:
                            desc = str(fm.GetDescriptionText())
                        except Exception:
                            pass
                        sev = fm.GetSeverity()
                        _AI_MODAL_GUARD_LOG.append("FAILURE | severity=" + str(sev) + " | " + desc[:500])
                        if sev == FailureSeverity.Warning:
                            try:
                                failuresAccessor.DeleteWarning(fm)
                                _AI_MODAL_GUARD_LOG.append("FAILURE_DECISION | deleted warning")
                            except Exception as exdel:
                                _AI_MODAL_GUARD_LOG.append("FAILURE_DELETE_WARNING_FAILED | " + str(exdel))
                    except Exception as exfm:
                        _AI_MODAL_GUARD_LOG.append("FAILURE_MESSAGE_LOOP_FAILED | " + str(exfm))
                return FailureProcessingResult.Continue
            except Exception as ex:
                _AI_MODAL_GUARD_LOG.append("FAILURE_PREPROCESSOR_FAILED | " + str(ex))
                try:
                    return FailureProcessingResult.ProceedWithRollBack
                except Exception:
                    return FailureProcessingResult.Continue

    def ai_apply_failure_handling(transaction):
        try:
            opts = transaction.GetFailureHandlingOptions()
            opts.SetFailuresPreprocessor(AiBridgeFailuresPreprocessor())
            try:
                opts.SetClearAfterRollback(True)
            except Exception:
                pass
            transaction.SetFailureHandlingOptions(opts)
            _AI_MODAL_GUARD_LOG.append("FAILURE_HANDLING_ATTACHED | transaction=" + str(transaction.GetName()))
            return True
        except Exception as ex:
            _AI_MODAL_GUARD_LOG.append("FAILURE_HANDLING_ATTACH_FAILED | " + str(ex))
            return False
except Exception as ex:
    _AI_MODAL_GUARD_LOG.append("FAILURE_HANDLING_HELPER_UNAVAILABLE | " + str(ex))


try:
    try:
        _ai_uiapp = __revit__
    except Exception:
        _ai_uiapp = None
    if _ai_uiapp is not None:
        try:
            _ai_uiapp.DialogBoxShowing += _ai_dialog_handler
            _AI_DIALOG_HANDLER_ATTACHED = True
            _AI_MODAL_GUARD_LOG.append("DIALOG_GUARD_ATTACHED")
        except Exception as ex:
            _AI_MODAL_GUARD_LOG.append("DIALOG_GUARD_ATTACH_FAILED | " + str(ex))
    else:
        _AI_MODAL_GUARD_LOG.append("DIALOG_GUARD_ATTACH_FAILED | __revit__ unavailable")

    exec(_AI_USER_CODE, globals(), globals())

except Exception:
    err_text = "RESULTS:\\nAuto-injected Revit API modal guard wrapper caught an unhandled exception before the user script could publish output.\\n\\nERRORS:\\n" + traceback.format_exc() + "\\nMODAL_GUARD_LOG:\\n" + "\\n".join(_AI_MODAL_GUARD_LOG) + "\\n\\nNEXT_RECOMMENDED_STATE:\\nFIX_ERRORS"
    _ai_modal_guard_publish_failure(err_text)

finally:
    try:
        if _AI_DIALOG_HANDLER_ATTACHED:
            _ai_uiapp.DialogBoxShowing -= _ai_dialog_handler
            _AI_MODAL_GUARD_LOG.append("DIALOG_GUARD_DETACHED")
    except Exception as ex:
        _AI_MODAL_GUARD_LOG.append("DIALOG_GUARD_DETACH_FAILED | " + str(ex))
    _ai_modal_guard_write_log()
"""
    return wrapper_template.replace("__AI_USER_CODE_LITERAL__", user_code_literal)


def prepare_code_for_rps_execution(code_text):
    if not REVIT_API_MODAL_GUARD_ENABLED:
        return code_text
    return build_revit_api_modal_guard_wrapper(code_text)

def paste_code_into_rps(code_text, rps_wait_seconds=None):
    log("")
    log("Pasting copied ChatGPT code into Revit Interactive Python Shell...")

    rps_code_text = prepare_code_for_rps_execution(code_text)
    if REVIT_API_MODAL_GUARD_ENABLED:
        log("Auto-injected Revit API modal guard wrapper is enabled for this RPS run.")

    click_at_name("rps_input", "RPS input")
    clear_focused_text_field("RPS input")
    paste_text(rps_code_text, "code into RPS", DEFAULT_SHORT_WAIT_SECONDS)

    log("Executing code in RPS...")

    if has_coord("rps_run_button"):
        click_at_name("rps_run_button", "RPS Run button")
    else:
        hotkey(RPS_EXECUTE_HOTKEY, "execute RPS code")

    if rps_wait_seconds is None:
        rps_wait_seconds = decide_rps_wait_seconds(code_text, None)
    rps_wait_seconds = clamp_seconds(rps_wait_seconds, RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS, RPS_OUTPUT_WAIT_SECONDS)
    log("Cycle-specific RPS/IPS output wait selected: {} seconds".format(int(rps_wait_seconds)))
    countdown(int(rps_wait_seconds), "RPS output wait before copy")


def copy_rps_output_from_calibrated_area():
    log("")
    log("Copying RPS output from calibrated area.")
    click_at_name("rps_output_click", "RPS output area")
    copied = select_all_and_copy("RPS output area")
    preview_text(copied, "Copied from RPS preview:")
    return copied


def extract_next_recommended_state(text):
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("NEXT_RECOMMENDED_STATE"):
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return "UNKNOWN"


def rps_has_syntax_error(text):
    upper = (text or "").upper()
    if "SYNTAX ERROR" in upper:
        return True
    if "TRACEBACK" in upper and "ERRORS:" not in upper:
        return True
    return False


def state_is_completion(state):
    s = (state or "").strip().upper()
    if s == "DONE":
        return True
    if s == "REDLINES_COMPLETE":
        return True
    if s == "QAQC_COMPLETE":
        return True
    if s == "ALL_REDLINES_COMPLETE":
        return True
    if s == "A019_REDLINES_COMPLETE":
        return True
    if s == "COMPLETE":
        return True
    return False


def state_is_fix_errors(state):
    s = (state or "").strip().upper()
    if s == "FIX_ERRORS":
        return True
    if s.startswith("FIX_"):
        return True
    return False


def clean_path_value(value):
    s = (value or "").strip()
    s = s.strip('"')
    s = s.strip("'")
    s = s.replace("\r", "")
    s = s.replace("\n", "")
    return s


def value_after_label(lines, label):
    target = label.upper()
    for i, line in enumerate(lines):
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith(target):
            parts = stripped.split(":", 1)
            if len(parts) == 2 and parts[1].strip():
                return clean_path_value(parts[1].strip())
            if i + 1 < len(lines):
                return clean_path_value(lines[i + 1].strip())
    return ""


def extract_qc_export_path(text):
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    priority_labels = [
        "QC_EXPORT_ACTUAL_PATH:",
        "QC_EXPORT_REPORTED_PATH:",
        "QC_EXPORT_UPLOAD_PATH:",
        "QC EXPORT:"
    ]

    for label in priority_labels:
        value = value_after_label(lines, label)
        if value:
            upper_value = value.upper()
            if upper_value.startswith("EXPORT_FAILED") or upper_value.startswith("EXPORT_SKIPPED"):
                continue
            return clean_path_value(value)

    short_name = value_after_label(lines, "QC_EXPORT_SHORT_FILENAME:")
    if short_name:
        short_name = os.path.basename(short_name)
        for folder in [QC_EXPORT_FOLDER, QC_UPLOAD_STAGING_FOLDER]:
            candidate = os.path.join(folder, short_name)
            if os.path.exists(candidate):
                return candidate
        return os.path.join(QC_EXPORT_FOLDER, short_name)

    matches = re.findall(r"([A-Za-z]:\\[^\r\n]+?\.(?:png|jpg|jpeg|pdf))", text, re.IGNORECASE)
    if matches:
        return clean_path_value(matches[-1])

    return ""


def newest_matching_file(folder, base_name, extension):
    if not folder or not os.path.isdir(folder):
        return ""

    candidates = []

    try:
        names = os.listdir(folder)
    except Exception:
        return ""

    for name in names:
        path = os.path.join(folder, name)

        if not os.path.isfile(path):
            continue

        if extension and not name.lower().endswith(extension.lower()):
            continue

        if name.startswith(base_name):
            candidates.append(path)

    if len(candidates) == 0:
        short_prefix = base_name[:20]
        for name in names:
            path = os.path.join(folder, name)

            if not os.path.isfile(path):
                continue

            if extension and not name.lower().endswith(extension.lower()):
                continue

            if name.startswith(short_prefix):
                candidates.append(path)

    newest = ""
    newest_time = -1.0

    for path in candidates:
        try:
            mt = os.path.getmtime(path)
        except Exception:
            mt = 0.0

        if mt > newest_time:
            newest_time = mt
            newest = path

    return newest


def newest_recent_qc_file(max_age_seconds=None):
    folders = [QC_EXPORT_FOLDER, QC_UPLOAD_STAGING_FOLDER]
    newest = ""
    newest_time = -1.0
    now = time.time()

    for folder in folders:
        if not os.path.isdir(folder):
            continue

        try:
            names = os.listdir(folder)
        except Exception:
            continue

        for name in names:
            ext = os.path.splitext(name)[1].lower()
            valid = False
            for good_ext in QC_VALID_EXTENSIONS:
                if ext == good_ext.lower():
                    valid = True
                    break

            if not valid:
                continue

            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue

            try:
                mt = os.path.getmtime(path)
            except Exception:
                mt = 0.0

            if max_age_seconds is not None and max_age_seconds > 0:
                if now - mt > max_age_seconds:
                    continue

            if mt > newest_time:
                newest_time = mt
                newest = path

    return newest


def resolve_actual_qc_export_path(reported_path):
    reported_path = clean_path_value(reported_path)

    if not reported_path:
        return ""

    if os.path.exists(reported_path):
        return reported_path

    if not os.path.dirname(reported_path):
        for folder_candidate in [QC_EXPORT_FOLDER, QC_UPLOAD_STAGING_FOLDER]:
            candidate_path = os.path.join(folder_candidate, reported_path)
            if os.path.exists(candidate_path):
                return candidate_path

    folder = os.path.dirname(reported_path)
    name = os.path.basename(reported_path)
    base_name, extension = os.path.splitext(name)

    actual = newest_matching_file(folder, base_name, extension)

    if actual and os.path.exists(actual):
        log("")
        log("Resolved Revit long export filename:")
        log("  Reported: {}".format(reported_path))
        log("  Actual:   {}".format(actual))
        return actual

    if not folder or not os.path.isdir(folder):
        for folder_candidate in [QC_EXPORT_FOLDER, QC_UPLOAD_STAGING_FOLDER]:
            actual = newest_matching_file(folder_candidate, base_name, extension)
            if actual and os.path.exists(actual):
                log("")
                log("Resolved QC export filename from default folders:")
                log("  Reported: {}".format(reported_path))
                log("  Actual:   {}".format(actual))
                return actual

    return ""


def wait_for_file_stable(path):
    if not path:
        return False

    if not os.path.exists(path):
        log("QC file does not exist yet: {}".format(path))
        return False

    last_size = -1
    stable_count = 0

    while stable_count < QC_FILE_STABILITY_CHECKS:
        try:
            size = os.path.getsize(path)
        except Exception:
            return False

        if size == last_size and size > 0:
            stable_count += 1
            log("  stable check {}/{} size={}".format(stable_count, QC_FILE_STABILITY_CHECKS, size))
        else:
            stable_count = 0
            last_size = size
            log("  size changing or first read size={}".format(size))

        time.sleep(QC_FILE_STABILITY_INTERVAL_SECONDS)

    return True


def stage_qc_export_for_short_upload(actual_path):
    if not actual_path or not os.path.exists(actual_path):
        return ""

    if not os.path.isdir(QC_UPLOAD_STAGING_FOLDER):
        os.makedirs(QC_UPLOAD_STAGING_FOLDER)

    ext = os.path.splitext(actual_path)[1].lower()
    if not ext:
        ext = ".png"

    staged_path = os.path.join(QC_UPLOAD_STAGING_FOLDER, QC_UPLOAD_STAGING_BASENAME + ext)

    try:
        if os.path.exists(staged_path):
            os.remove(staged_path)
    except Exception:
        pass

    shutil.copy2(actual_path, staged_path)

    log("")
    log("Staged QC export to short upload path:")
    log("  Source: {}".format(actual_path))
    log("  Staged: {}".format(staged_path))

    return staged_path


def append_upload_debug(message):
    try:
        folder = os.path.dirname(QC_UPLOAD_DEBUG_LOG)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(QC_UPLOAD_DEBUG_LOG, "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  " + str(message) + "\n")
    except Exception:
        pass


def focus_chatgpt_before_upload():
    if not QC_ACTIVATE_CHATGPT_INPUT_BEFORE_UPLOAD:
        append_upload_debug("ChatGPT pre-upload activation skipped by config.")
        return

    append_upload_debug("Activating ChatGPT window/input before upload.")
    try:
        if has_coord("chatgpt_input"):
            click_at_name("chatgpt_input", "activate ChatGPT input before upload")
            step_wait("Upload pre-step activate ChatGPT input")
        else:
            append_upload_debug("chatgpt_input coordinate missing; deliberately not clicking the ChatGPT code copy button or response area during upload activation.")
            log("WARNING: chatgpt_input coordinate missing; upload activation will not use the ChatGPT code copy button as a fallback.")
    except Exception as ex:
        append_upload_debug("ChatGPT pre-upload activation failed: " + str(ex))


def paste_path_into_file_picker_and_open(file_path, attempt_number):
    append_upload_debug("File dialog path entry attempt {} for {}".format(attempt_number, file_path))

    if not windows_file_dialog_is_open():
        append_upload_debug("FAILED: Windows Open dialog is not active before single-file path paste.")
        return False

    bring_windows_file_dialog_to_front()

    focused = focus_file_name_box()
    if not focused:
        append_upload_debug("Could not focus file name field on attempt {}".format(attempt_number))
        return False

    step_wait("Upload step filename focused attempt {}".format(attempt_number))

    try:
        # Full quoted path prevents stale filenames such as upload_debug_log.txt
        # and works regardless of the current folder shown in the dialog.
        pyperclip.copy(quote_file_dialog_path(file_path))
        pause()
        hotkey(SELECT_ALL_HOTKEY, "select all in file picker filename")
        hotkey(PASTE_HOTKEY, "paste quoted full QC filepath")
    except Exception as ex:
        append_upload_debug("Paste path failed on attempt {}: {}".format(attempt_number, str(ex)))
        return False

    step_wait("Upload step full path pasted attempt {}".format(attempt_number))

    try:
        # Press Enter instead of relying on possibly stale Open button coordinates.
        press_key("enter", "Enter to open QC file")
        append_upload_debug("Enter open command sent on attempt {}".format(attempt_number))
    except Exception as ex:
        append_upload_debug("Open command failed on attempt {}: {}".format(attempt_number, str(ex)))
        return False

    if not wait_for_windows_file_dialog_close(QC_FILE_PICKER_OPEN_WAIT_SECONDS + 18):
        append_upload_debug("FAILED: Windows Open dialog remained open after single-file path submit.")
        return False

    return True


def focus_file_name_box():
    log("Focusing Windows file dialog filename field using Alt+N and calibrated coordinate fallback.")

    focused = False

    try:
        pyautogui.hotkey("alt", "n")
        pause()
        focused = True
        append_upload_debug("Alt+N sent to file picker filename field.")
    except Exception as ex:
        append_upload_debug("Alt+N failed: " + str(ex))

    if has_coord("file_picker_filename"):
        try:
            click_at_name("file_picker_filename", "file picker filename field")
            focused = True
            append_upload_debug("Clicked calibrated file_picker_filename coordinate.")
        except Exception as ex:
            append_upload_debug("file_picker_filename coordinate click failed: " + str(ex))

    return focused


def quote_file_dialog_path(path):
    return '"{}"'.format(str(path).replace('"', ''))


def build_batch_file_dialog_text(file_paths):
    return " ".join([quote_file_dialog_path(p) for p in file_paths])


def paste_paths_into_file_picker_and_open(file_paths, attempt_number):
    append_upload_debug("Batch file dialog path entry attempt {} for {} file(s)".format(attempt_number, len(file_paths)))

    if not windows_file_dialog_is_open():
        append_upload_debug("FAILED: Windows Open dialog is not active before batch path paste.")
        return False

    bring_windows_file_dialog_to_front()

    focused = focus_file_name_box()
    if not focused:
        append_upload_debug("Could not focus file name field on batch attempt {}".format(attempt_number))
        return False

    step_wait("Upload step filename focused batch attempt {}".format(attempt_number))

    try:
        # Use full quoted paths for every file. This prevents the stale
        # upload_debug_log.txt value from being opened accidentally.
        pyperclip.copy(build_batch_file_dialog_text(file_paths))
        pause()
        hotkey(SELECT_ALL_HOTKEY, "select all in file picker filename")
        hotkey(PASTE_HOTKEY, "paste quoted full QC filepaths")
    except Exception as ex:
        append_upload_debug("Batch paste paths failed on attempt {}: {}".format(attempt_number, str(ex)))
        return False

    step_wait("Upload step full batch paths pasted attempt {}".format(attempt_number))

    try:
        # Press Enter instead of relying on possibly stale Open button coordinates.
        press_key("enter", "Enter to open batch QC files")
        append_upload_debug("Batch Enter open command sent on attempt {}".format(attempt_number))
    except Exception as ex:
        append_upload_debug("Batch open command failed on attempt {}: {}".format(attempt_number, str(ex)))
        return False

    if not wait_for_windows_file_dialog_close(QC_FILE_PICKER_OPEN_WAIT_SECONDS + 18):
        append_upload_debug("FAILED: Windows Open dialog remained open after batch path submit.")
        return False

    return True


def upload_files_to_chatgpt(file_paths):
    clean_paths = []
    for path in file_paths:
        if path and os.path.exists(path):
            clean_paths.append(path)

    if not clean_paths:
        return "NO_QC_UPLOAD_PATHS"

    if not has_coord("chatgpt_attach"):
        return "UPLOAD_SKIPPED_MISSING_COORD_chatgpt_attach"

    log("")
    log("Starting batch QC upload sequence.")
    log("QC upload files: {}".format(len(clean_paths)))
    append_upload_debug("")
    append_upload_debug("START batch upload sequence for {} file(s)".format(len(clean_paths)))

    try:
        focus_chatgpt_before_upload()

        step_wait("Upload step 1 before attach click")
        click_at_name("chatgpt_attach", "ChatGPT attach / plus button")
        append_upload_debug("Clicked ChatGPT attach / plus button.")

        step_wait("Upload step 2 wait for attach menu")

        if has_coord("chatgpt_add_files"):
            click_at_name("chatgpt_add_files", "ChatGPT Add files / Upload from computer")
            append_upload_debug("Clicked ChatGPT Add files coordinate.")
            if not wait_for_windows_file_dialog_open(QC_FILE_PICKER_OPEN_WAIT_SECONDS + 8):
                append_upload_debug("FAILED: Windows Open dialog did not appear after Add files click.")
                return "UPLOAD_FAILED_FILE_DIALOG_DID_NOT_OPEN"
        else:
            append_upload_debug("Missing chatgpt_add_files coordinate. Trying file dialog path entry anyway.")
            log("WARNING: Missing chatgpt_add_files coordinate. Trying file dialog anyway.")
            if not wait_for_windows_file_dialog_open(QC_FILE_PICKER_OPEN_WAIT_SECONDS + 8):
                append_upload_debug("FAILED: Windows Open dialog did not appear in fallback wait.")
                return "UPLOAD_FAILED_FILE_DIALOG_DID_NOT_OPEN"

        path_open_sent = False
        attempts = max(1, QC_FILE_DIALOG_PATH_ENTRY_ATTEMPTS)
        for attempt in range(1, attempts + 1):
            if paste_paths_into_file_picker_and_open(clean_paths, attempt):
                path_open_sent = True
                break
            step_wait("Upload file dialog retry wait {}".format(attempt))

        if not path_open_sent:
            append_upload_debug("FAILED: could not send batch file paths/open command.")
            return "UPLOAD_FAILED_COULD_NOT_SEND_BATCH_FILEPATH_OPEN"

        countdown(QC_UPLOAD_WAIT_SECONDS, "QC upload processing wait")

        if windows_file_dialog_is_open():
            append_upload_debug("FAILED: Windows Open dialog is still open after upload wait; refusing to continue.")
            return "UPLOAD_FAILED_FILE_DIALOG_STILL_OPEN"

        try:
            if has_coord("chatgpt_input"):
                click_at_name("chatgpt_input", "ChatGPT input after batch upload")
                append_upload_debug("Clicked ChatGPT input after batch upload.")
        except Exception as ex:
            append_upload_debug("Click ChatGPT input after batch upload failed: " + str(ex))

        step_wait("Upload step after returning to input")
        append_upload_debug("BATCH UPLOAD COMPLETE reported for {} file(s)".format(len(clean_paths)))

        return "UPLOADED_BATCH: " + " | ".join(clean_paths)

    except Exception as ex:
        try:
            pyautogui.press("esc")
        except Exception:
            pass
        append_upload_debug("BATCH UPLOAD FAILED AND ESC SENT: " + str(ex))
        return "UPLOAD_BATCH_FAILED_AND_ESC_SENT: " + str(ex)


def upload_file_to_chatgpt(file_path):
    if not file_path:
        return "NO_QC_UPLOAD_PATH"

    if not os.path.exists(file_path):
        return "QC_UPLOAD_FILE_NOT_FOUND: " + file_path

    if not has_coord("chatgpt_attach"):
        return "UPLOAD_SKIPPED_MISSING_COORD_chatgpt_attach"

    log("")
    log("Starting QC upload sequence.")
    log("QC upload file: {}".format(file_path))
    append_upload_debug("")
    append_upload_debug("START upload sequence for {}".format(file_path))

    try:
        focus_chatgpt_before_upload()

        step_wait("Upload step 1 before attach click")
        click_at_name("chatgpt_attach", "ChatGPT attach / plus button")
        append_upload_debug("Clicked ChatGPT attach / plus button.")

        step_wait("Upload step 2 wait for attach menu")

        if has_coord("chatgpt_add_files"):
            click_at_name("chatgpt_add_files", "ChatGPT Add files / Upload from computer")
            append_upload_debug("Clicked ChatGPT Add files coordinate.")
            if not wait_for_windows_file_dialog_open(QC_FILE_PICKER_OPEN_WAIT_SECONDS + 8):
                append_upload_debug("FAILED: Windows Open dialog did not appear after Add files click.")
                return "UPLOAD_FAILED_FILE_DIALOG_DID_NOT_OPEN"
        else:
            append_upload_debug("Missing chatgpt_add_files coordinate. Trying file dialog path entry anyway.")
            log("WARNING: Missing chatgpt_add_files coordinate. Trying file dialog anyway.")
            if not wait_for_windows_file_dialog_open(QC_FILE_PICKER_OPEN_WAIT_SECONDS + 8):
                append_upload_debug("FAILED: Windows Open dialog did not appear in fallback wait.")
                return "UPLOAD_FAILED_FILE_DIALOG_DID_NOT_OPEN"

        path_open_sent = False
        attempts = max(1, QC_FILE_DIALOG_PATH_ENTRY_ATTEMPTS)
        for attempt in range(1, attempts + 1):
            if paste_path_into_file_picker_and_open(file_path, attempt):
                path_open_sent = True
                break
            step_wait("Upload file dialog retry wait {}".format(attempt))

        if not path_open_sent:
            append_upload_debug("FAILED: could not send file path/open command.")
            return "UPLOAD_FAILED_COULD_NOT_SEND_FILEPATH_OPEN"

        step_wait("Upload step after file open command")
        countdown(QC_UPLOAD_WAIT_SECONDS, "QC upload processing wait")

        if windows_file_dialog_is_open():
            append_upload_debug("FAILED: Windows Open dialog is still open after upload wait; refusing to continue.")
            return "UPLOAD_FAILED_FILE_DIALOG_STILL_OPEN"

        try:
            if has_coord("chatgpt_input"):
                click_at_name("chatgpt_input", "ChatGPT input after upload")
                append_upload_debug("Clicked ChatGPT input after upload.")
        except Exception as ex:
            append_upload_debug("Click ChatGPT input after upload failed: " + str(ex))

        step_wait("Upload step after returning to input")
        append_upload_debug("UPLOAD COMPLETE reported for {}".format(file_path))

        return "UPLOADED: " + file_path

    except Exception as ex:
        try:
            pyautogui.press("esc")
        except Exception:
            pass
        append_upload_debug("UPLOAD FAILED AND ESC SENT: " + str(ex))
        return "UPLOAD_FAILED_AND_ESC_SENT: " + str(ex)



def valid_qc_upload_extension(path):
    ext = os.path.splitext(path)[1].lower()
    for good_ext in QC_VALID_EXTENSIONS:
        if ext == good_ext.lower():
            return True
    return False


def list_qc_upload_folder_files():
    files = []
    folder = QC_UPLOAD_STAGING_FOLDER
    if not os.path.isdir(folder):
        return files

    try:
        names = os.listdir(folder)
    except Exception as ex:
        log("Could not list QC upload folder: {}".format(ex))
        return files

    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        if not valid_qc_upload_extension(path):
            continue
        try:
            mt = os.path.getmtime(path)
        except Exception:
            mt = 0.0
        files.append((mt, path))

    files.sort(key=lambda item: item[0])
    return [item[1] for item in files]


def delete_file_quietly(path, label=None):
    if not path:
        return False
    try:
        if os.path.exists(path):
            os.remove(path)
            if label:
                log("Deleted {}: {}".format(label, path))
            return True
    except Exception as ex:
        log("Could not delete file {}: {}".format(path, ex))
    return False


def clear_qc_upload_folder_before_rps():
    folder = QC_UPLOAD_STAGING_FOLDER
    if not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception as ex:
            log("Could not create QC upload folder before RPS run: {}".format(ex))
            return

    removed = 0
    for path in list_qc_upload_folder_files():
        if delete_file_quietly(path, "stale QC upload file before RPS run"):
            removed += 1

    if removed:
        log("Cleared {} stale QC upload file(s) before RPS run.".format(removed))
    else:
        log("QC upload folder is clear before RPS run.")


def upload_existing_qc_upload_folder_files():
    files = list_qc_upload_folder_files()
    if not files:
        return "", "", "", "NO_QC_UPLOAD_FILES_FOUND_IN_FOLDER"

    stable_files = []
    failed_paths = []
    statuses = []

    log("")
    log("QC folder-based batch upload mode: found {} file(s) in {}".format(len(files), QC_UPLOAD_STAGING_FOLDER))

    for path in files:
        if wait_for_file_stable(path):
            stable_files.append(path)
        else:
            statuses.append("FILE_NOT_STABLE: " + path)
            failed_paths.append(path)

    uploaded_paths = []
    deleted_paths = []

    if stable_files:
        if QC_BATCH_UPLOAD_ONE_DIALOG:
            status = upload_files_to_chatgpt(stable_files)
            statuses.append(status)
            if str(status).startswith("UPLOADED_BATCH:"):
                for path in stable_files:
                    uploaded_paths.append(path)
                    if delete_file_quietly(path, "uploaded QC file"):
                        deleted_paths.append(path)
                    else:
                        failed_paths.append(path)
            else:
                for path in stable_files:
                    failed_paths.append(path)
        else:
            for path in stable_files:
                status = upload_file_to_chatgpt(path)
                statuses.append(status)
                if str(status).startswith("UPLOADED:"):
                    uploaded_paths.append(path)
                    if delete_file_quietly(path, "uploaded QC file"):
                        deleted_paths.append(path)
                    else:
                        failed_paths.append(path)
                else:
                    failed_paths.append(path)

    actual_qc_path = "\n".join(files)
    uploaded_qc_path = "\n".join(uploaded_paths)
    if uploaded_paths:
        reported_qc_path = uploaded_paths[0]
    else:
        reported_qc_path = files[0]

    qc_upload_status = "FOLDER_BATCH_UPLOAD_RESULTS:\n" + "\n".join(statuses)
    if deleted_paths:
        qc_upload_status += "\nDELETED_AFTER_UPLOAD:\n" + "\n".join(deleted_paths)
    if failed_paths:
        qc_upload_status += "\nREMAINING_NOT_DELETED:\n" + "\n".join(failed_paths)

    return reported_qc_path, actual_qc_path, uploaded_qc_path, qc_upload_status


def build_rps_return_data(cycle_number, rps_output, state, reported_qc_path, actual_qc_path, staged_qc_path, qc_upload_status):
    if str(qc_upload_status).startswith("NO_QC_UPLOAD_FILES_FOUND_IN_FOLDER"):
        visual_qaqc = (
            "No QC PNG/export file was found in the QC upload folder for this cycle. "
            "Proceed using the Python/RPS text output only. If visual QAQC is needed, the next Revit Python script should create/export the intended view PNG directly into the QC upload folder."
        )
    else:
        visual_qaqc = (
            "Review the uploaded QC image visually and use OCR if text is involved. "
            "Do not mark the item complete unless the change is clearly visible in the correct detail or sheet region. "
            "If the change is not clearly visible, return a Revit Python script to adjust the location, size, draw order, masking, text target or export crop and repeat QC. "
            "When work is inside a view placed on a sheet, consider view scale and identify a nearby visible reference point inside the target view and within crop / annotation boundaries. "
            "Use that reference point to position and size the work, then verify it shows properly on the sheet viewport QC export."
        )

    return (
        "CURRENT_BRIDGE_EXECUTION_COUNT:\n{}\n\n"
        "CURRENT_NEXT_RECOMMENDED_STATE:\n{}\n\n"
        "QC_EXPORT_REPORTED_PATH:\n{}\n\n"
        "QC_EXPORT_ACTUAL_PATH:\n{}\n\n"
        "QC_EXPORT_UPLOAD_PATH:\n{}\n\n"
        "QC_UPLOAD_STATUS:\n{}\n\n"
        "VISUAL_QAQC_REQUIRED:\n{}\n\n"
        "RPS_OUTPUT:\n{}"
    ).format(cycle_number, state, reported_qc_path, actual_qc_path, staged_qc_path, qc_upload_status, visual_qaqc, rps_output)


def return_rps_output_to_chatgpt(cycle_number, rps_output, state):
    log("")
    log("Returning compact Revit Python Shell output data to ChatGPT...")
    log("This return path always pastes Python/RPS output back to ChatGPT, whether or not QC files exist.")
    log("QC upload is folder based only. The bridge checks QC_Upload and does not choose Revit export views.")

    reported_qc_path = ""
    actual_qc_path = ""
    staged_qc_path = ""
    qc_upload_status = "NO_QC_UPLOAD_FILES_FOUND_IN_FOLDER"

    try:
        reported_qc_path, actual_qc_path, staged_qc_path, qc_upload_status = upload_existing_qc_upload_folder_files()
    except Exception as ex:
        qc_upload_status = "QC_FOLDER_UPLOAD_EXCEPTION: " + str(ex)
        log(qc_upload_status)

    message = build_rps_return_data(
        cycle_number,
        rps_output,
        state,
        reported_qc_path,
        actual_qc_path,
        staged_qc_path,
        qc_upload_status
    )

    click_chatgpt_input_and_clear()
    paste_text(build_chatgpt_prompt(message), "compact RPS output data back to ChatGPT", CHATGPT_INPUT_PASTE_WAIT_SECONDS)

    if has_coord("chatgpt_submit"):
        click_at_name("chatgpt_submit", "ChatGPT submit button")
    else:
        hotkey(CHATGPT_SUBMIT_HOTKEY, "submit RPS output to ChatGPT")

    followup_wait = decide_chatgpt_wait_seconds(message, cycle_number, "follow up output")
    log("Cycle-specific ChatGPT follow-up wait selected: {} seconds".format(int(followup_wait)))
    countdown(followup_wait, "ChatGPT follow up output wait")

def get_initial_prompt():
    print("")
    print("Paste or type the initial redline prompt to send to ChatGPT.")
    print("The bridge will then continue unattended until complete or stopped.")
    print("Finish input by typing a line containing only:")
    print("END")
    print("")

    lines = []

    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)

    text = "\n".join(lines).strip()

    if not text:
        text = (
            "Continue with the A-019 redlines. "
            "You are explicitly allowed to modify the Revit model to complete the redlines and export QC PNGs. "
            "Use transactions for all modifications. "
            "When drafting or manipulating inside a view placed on a sheet, consider view scale and use a nearby visible reference object or reference point inside that same view and within crop / annotation boundaries to position and size work. "
            "Verify view-based work appears properly in the sheet viewport QC export. "
            "Before adding new Lot 8 geometry, remove or archive obsolete overlapping AI Lot 8 sample and prior-iteration geometry so the model stays coherent. "
            "Report what current design elements remain, what was removed, and what was created. "
            "After QAQC is visible and confirmed, keep going into the next design cleanup/refinement cycle instead of stopping. "
            "Continue cleaning nonsensical walls, floors and sample fragments unless they are clearly part of the intended design. "
            "Keep Lot 8 as an inhabitable earth berm home for people with logical rooms, entry circulation, daylight, structure, drainage and buildable geometry. "
            "Continue cycles until the configured max cycle count, FIX_ERRORS or user stop."
        )

    return text


def main_loop(initial_prompt):
    repeated_state = ""
    repeated_state_count = 0
    invalid_code_count = 0

    submit_prompt_to_chatgpt(initial_prompt, "ChatGPT initial output wait", decide_chatgpt_wait_seconds(initial_prompt, 0, "initial prompt"))

    for cycle_number in range(1, MAX_CYCLES + 1):
        log("")
        log("============================================================")
        log("STARTING UNATTENDED BRIDGE CYCLE {}".format(cycle_number))
        log("============================================================")

        chatgpt_code = copy_chatgpt_code_with_retry(decide_retry_wait_seconds(initial_prompt, cycle_number))

        if not chatgpt_code.strip():
            chatgpt_code = request_reprint_previous_python_output(
                "Initial copy returned empty or invalid code before timeout / invalid-code failure."
            )

        if not chatgpt_code.strip():
            invalid_code_count += 1
            log("Invalid or empty ChatGPT code count: {}".format(invalid_code_count))
            if invalid_code_count >= MAX_INVALID_CODE_ATTEMPTS:
                log("Stopping: maximum invalid code attempts reached.")
                break
            retry_prompt = "The prior response did not render or copy as a valid fenced Python code block. Return the first executable IronPython-compatible Revit Python code block only. The first character must be the first backtick of ```python and there must be no text before or after the fenced code block. Do not add any code-fence attributes such as id after python."
            submit_prompt_to_chatgpt(
                retry_prompt,
                "ChatGPT retry output wait",
                decide_chatgpt_wait_seconds(retry_prompt, cycle_number, "invalid code retry")
            )
            continue

        invalid_code_count = 0

        clear_qc_upload_folder_before_rps()
        paste_code_into_rps(chatgpt_code, decide_rps_wait_seconds(chatgpt_code, cycle_number))

        rps_output = copy_rps_output_from_calibrated_area()
        if not rps_output.strip():
            rps_output = "[No output copied from Revit Interactive Python Shell.]"

        state = extract_next_recommended_state(rps_output)
        write_rag_cycle_record(cycle_number, chatgpt_code, rps_output, state)

        log("")
        log("Cycle {} NEXT_RECOMMENDED_STATE: {}".format(cycle_number, state))

        if state == repeated_state:
            repeated_state_count += 1
        else:
            repeated_state = state
            repeated_state_count = 1

        if rps_has_syntax_error(rps_output):
            log("")
            log("Detected syntax error or raw traceback in RPS output.")
            if STOP_ON_SYNTAX_ERROR:
                log("Stopping for safety. Fix copy target or RPS input clearing before continuing.")
                break

        if state_is_completion(state):
            log("")
            log("Completion status reached: {}".format(state))
            if STOP_ON_COMPLETION_STATES:
                log("Configured to stop on completion states. Bridge stopping.")
                break
            log("Configured to continue after completion states. Returning output to ChatGPT for the next design cleanup/refinement cycle.")

        if STOP_ON_FIX_ERRORS and state_is_fix_errors(state):
            log("")
            log("Fix error state reached: {}".format(state))
            log("Bridge stopping.")
            break

        if STOP_ON_REPEATED_STATE and repeated_state_count >= MAX_REPEATED_STATE_COUNT:
            log("")
            log("Stopping: same NEXT_RECOMMENDED_STATE repeated {} times.".format(repeated_state_count))
            break

        return_rps_output_to_chatgpt(cycle_number, rps_output, state)

    log("")
    log("============================================================")
    log("UNATTENDED BRIDGE LOOP STOPPED")
    log("============================================================")
    log("Max cycles allowed: {}".format(MAX_CYCLES))
    log("Last repeated state: {}".format(repeated_state))
    log("Repeated state count: {}".format(repeated_state_count))


def main():
    print("")
    print("============================================================")
    print("OPENAI REVIT BRIDGE MAIN")
    print("Unattended Continuous Loop Version V3.22 (Dynamic Waits + Batch QC Upload + Local RAG)")
    print("============================================================")
    print("PyAutoGUI FAILSAFE: disabled for unattended upload loop; use Ctrl+C in this terminal to stop.")
    print("")
    print("Stop command:")
    print("  Ctrl + C in this terminal window")
    print("")
    print("Config:")
    print("  {}".format(CONFIG_PATH))
    print("")
    print("Timing:")
    print("  ChatGPT output wait: {} seconds".format(CHATGPT_OUTPUT_WAIT_SECONDS))
    print("  RPS output wait: {} seconds".format(RPS_OUTPUT_WAIT_SECONDS))
    print("  Pause after copy: {} seconds".format(PAUSE_AFTER_COPY_SECONDS))
    print("  Pause after paste: {} seconds".format(PAUSE_AFTER_PASTE_SECONDS))
    print("  Page down before copy: {}".format(CHATGPT_PAGE_DOWN_COUNT))
    print("  Browser refresh before copy wait: {} seconds".format(BROWSER_REFRESH_AFTER_CLICK_WAIT_SECONDS))
    print("  ChatGPT reprint wait: {} seconds".format(CHATGPT_REPRINT_WAIT_SECONDS))
    print("  Default short wait: {} seconds".format(DEFAULT_SHORT_WAIT_SECONDS))
    print("  ChatGPT input paste wait: {} seconds".format(CHATGPT_INPUT_PASTE_WAIT_SECONDS))
    print("  Dynamic ChatGPT wait range: {}-{} seconds".format(CHATGPT_WAIT_MIN_SECONDS, CHATGPT_WAIT_MAX_SECONDS))
    print("  Dynamic RPS/IPS wait range: {}-{} seconds".format(RPS_WAIT_MIN_SECONDS, RPS_WAIT_MAX_SECONDS))
    print("  GUI Revit modal Unjoin/OK/Cancel clicks: DISABLED")
    print("")
    print("QC folders:")
    print("  Revit export folder: {}".format(QC_EXPORT_FOLDER))
    print("  Folder-based upload source: {}".format(QC_UPLOAD_STAGING_FOLDER))
    print("  Revit scripts should export/copy intended QC files directly into this folder.")
    print("  All eligible QC files are batch-selected in one upload dialog when possible.")
    print("  Successfully uploaded files are deleted after upload.")
    print("  Upload debug log: {}".format(QC_UPLOAD_DEBUG_LOG))
    print("")
    print("Local Revit RAG:")
    print("  Enabled: {}".format(RAG_ENABLED))
    print("  Folder: {}".format(RAG_FOLDER))
    print("  Retrieval script: {}".format(RAG_RETRIEVAL_SCRIPT))
    print("  Cycle log: {}".format(RAG_CYCLE_LOG_FILE))
    print("  Max injected chars: {}".format(RAG_MAX_CONTEXT_CHARS))
    print("")
    print("Loop safety:")
    print("  Max cycles: {}".format(MAX_CYCLES))
    print("  Revit API modal guard wrapper: {}".format("ENABLED" if REVIT_API_MODAL_GUARD_ENABLED else "DISABLED"))
    print("  Stop on syntax error: {}".format(STOP_ON_SYNTAX_ERROR))
    print("  Stop on FIX_ERRORS: {}".format(STOP_ON_FIX_ERRORS))
    print("  Stop on completion states: {}".format(STOP_ON_COMPLETION_STATES))
    print("  Stop on repeated state: {}".format(STOP_ON_REPEATED_STATE))
    print("  Max reprint attempts before invalid-code count: {}".format(MAX_REPRINT_ATTEMPTS))
    print("  ChatGPT code copy button calibrated: {}".format(has_coord("chatgpt_code_copy_button") or has_coord("chatgpt_response_click")))
    print("  Browser refresh calibrated: {}".format(has_coord("browser_refresh")))
    print("")

    print("Starting in {} seconds...".format(STARTUP_DELAY_SECONDS))
    time.sleep(STARTUP_DELAY_SECONDS)

    try:
        initial_prompt = get_initial_prompt()
        main_loop(initial_prompt)
    except KeyboardInterrupt:
        print("")
        print("Bridge stopped by Ctrl + C.")
        sys.exit(0)


def wait_before_exit(message):
    print("")
    print(message)
    try:
        input("Press Enter to close this bridge window...")
    except Exception:
        try:
            raw_input("Press Enter to close this bridge window...")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
        wait_before_exit("Bridge finished or stopped normally.")
    except KeyboardInterrupt:
        print("")
        print("Bridge stopped by Ctrl + C.")
        wait_before_exit("Bridge interrupted by user.")
    except SystemExit:
        wait_before_exit("Bridge exited.")
    except Exception:
        print("")
        print("Bridge crashed with an unhandled exception:")
        print(traceback.format_exc())
        wait_before_exit("Bridge crashed. Review the traceback above.")