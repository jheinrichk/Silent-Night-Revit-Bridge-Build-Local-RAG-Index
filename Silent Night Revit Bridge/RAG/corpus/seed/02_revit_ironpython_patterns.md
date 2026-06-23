# Revit IronPython Defensive Patterns

Use clr.AddReference('RevitAPI') and clr.AddReference('RevitAPIUI'). Use uidoc = __revit__.ActiveUIDocument and doc = uidoc.Document. Avoid f-strings and type hints. Use System.Collections.Generic.List[ElementId] for Revit API lists.

Parameter discovery pattern: iterate elem.Parameters and print Definition.Name, StorageType, HasValue, AsString/AsValueString where safe. Do not guess parameter names when a built-in parameter or exact shared parameter has not been confirmed.

Transaction pattern: create a Transaction, start, apply failure handling if ai_apply_failure_handling exists, commit only after successful doc.Regenerate. On exception, rollback and print traceback.

For sheet/view work, report the target View.Name, View.Id, View.Scale, crop box, sheet number, viewport id and viewport box outline. Position annotations relative to a visible crop or viewport reference, not arbitrary model coordinates.
