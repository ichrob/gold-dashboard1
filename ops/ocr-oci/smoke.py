"""Synthetic-only packaging proof. Never use actual DEGIRO screenshots in CI."""
import base64
import io
import json
from PIL import Image, ImageDraw
import subprocess
import sys

im = Image.new("RGB", (640, 480), "white")
ImageDraw.Draw(im).text((30, 100), "SYNTHETIC OCR MODEL TEST 1234", fill="black")
buf = io.BytesIO()
im.save(buf, format="PNG")
input_data = json.dumps([{"png": base64.b64encode(buf.getvalue()).decode()}])
# Exercises the same child, seccomp sandbox and native model used in OCI Ampere A1.
result = subprocess.run([sys.executable, "handset_list_worker.py", "--ocr"],
                        input=input_data, text=True, capture_output=True, timeout=65)
if result.returncode:
    raise SystemExit("offline_ocr_child_failed")
try:
    value = json.loads(result.stdout)
except ValueError:
    raise SystemExit("offline_ocr_invalid_output")
if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
    raise SystemExit("offline_ocr_invalid_shape")
if not 2 <= len(value[0]) <= 3 or any(not isinstance(x, str) for x in value[0]):
    raise SystemExit("offline_ocr_invalid_passes")
print("synthetic_ocr_engine_loaded=true")
