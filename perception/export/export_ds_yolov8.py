"""Run DeepStream-Yolo utils/export_yoloV8.py (commit 2894bab) with the legacy TorchScript ONNX exporter.

Newer PyTorch defaults torch.onnx.export to dynamo=True, which handles opset 12 poorly.
This wrapper forces dynamo=False when the installed torch.onnx.export has that parameter,
then runs the upstream script unchanged with the same command-line arguments.

Usage (from the output folder, the .pt beside it):
  python -I ../export_ds_yolov8.py -w yolov8n.pt -s 256 416 --opset 12 --simplify
"""
import importlib.util
import inspect
import os
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = os.path.join(HERE, "dsyolo_2894bab", "export_yoloV8.py")

_orig_export = torch.onnx.export
_has_dynamo = "dynamo" in inspect.signature(_orig_export).parameters


def _export_legacy(*args, **kwargs):
    if _has_dynamo:
        kwargs["dynamo"] = False
    return _orig_export(*args, **kwargs)


torch.onnx.export = _export_legacy
print(f"torch {torch.__version__}: torch.onnx.export has dynamo={_has_dynamo} -> "
      f"{'forced dynamo=False' if _has_dynamo else 'legacy exporter only'}")

spec = importlib.util.spec_from_file_location("export_yoloV8", UPSTREAM)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.argv[0] = UPSTREAM
mod.main(mod.parse_args())
