# ============================================================
# REVIT PYTHON SHELL QC EXPORT SNIPPET
# ============================================================
#
# This is not the main bridge runner.
# This is a Revit-side snippet ChatGPT can adapt into generated Revit code.
# It exports the exact target view by name to the QC folder.
#
# ============================================================

import os
import re
import time
import traceback

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    View,
    ImageExportOptions,
    ImageFileType,
    ExportRange,
    FitDirectionType,
    ZoomFitType,
    ImageResolution
)

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

TARGET_VIEW_NAME = "REPLACE_WITH_TARGET_VIEW_NAME"
QC_EXPORT_FOLDER = r"C:\RevitBridge\QC_Exports"


def safe_filename(text):
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = text.replace(" ", "_")
    return text


def find_view_by_exact_name(doc, view_name):
    views = FilteredElementCollector(doc).OfClass(View).ToElements()
    for view in views:
        if view.Name == view_name and not view.IsTemplate:
            return view
    return None


try:
    if not os.path.isdir(QC_EXPORT_FOLDER):
        os.makedirs(QC_EXPORT_FOLDER)

    target_view = find_view_by_exact_name(doc, TARGET_VIEW_NAME)

    if target_view is None:
        raise Exception("Target view not found by exact name: {}".format(TARGET_VIEW_NAME))

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_name = "QC_{}_{}".format(safe_filename(target_view.Name), timestamp)
    export_base_path = os.path.join(QC_EXPORT_FOLDER, base_name)

    opts = ImageExportOptions()
    opts.ExportRange = ExportRange.SetOfViews
    opts.SetViewsAndSheets([target_view.Id])
    opts.FilePath = export_base_path
    opts.HLRandWFViewsFileType = ImageFileType.PNG
    opts.ShadowViewsFileType = ImageFileType.PNG
    opts.ZoomType = ZoomFitType.FitToPage
    opts.PixelSize = 3000
    opts.FitDirection = FitDirectionType.Horizontal
    opts.ImageResolution = ImageResolution.DPI_300

    doc.ExportImage(opts)

    exported_files = []
    for name in os.listdir(QC_EXPORT_FOLDER):
        full = os.path.join(QC_EXPORT_FOLDER, name)
        if name.startswith(base_name) and name.lower().endswith((".png", ".jpg", ".jpeg")):
            exported_files.append(full)

    if exported_files:
        exported_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        image_path = exported_files[0]
    else:
        image_path = export_base_path + ".png"

    print("RESULTS:")
    print("Target view exported for visual QC.")
    print("")
    print("VIEW_NAME:")
    print(target_view.Name)
    print("")
    print("IMAGE_EXPORT_PATH:")
    print(image_path)
    print("")
    print("ERRORS:")
    print("None")
    print("")
    print("NEXT_RECOMMENDED_STATE:")
    print("WAIT_FOR_IMAGE_REVIEW")

except Exception:
    print("RESULTS:")
    print("View export failed.")
    print("")
    print("ERRORS:")
    print(traceback.format_exc())
    print("")
    print("NEXT_RECOMMENDED_STATE:")
    print("FIX_ERRORS")
