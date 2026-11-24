"""Run the whole pipeline (steps 01–07). Step 00 (BDOT10k extraction) runs only with --extract."""
import runpy
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["01_parse_gpr.py", "02_build_graph.py", "03_locate_sections.py", "04_build_network.py",
         "05_qa_report.py", "06_render_cartogram.py", "07_style_qgis.py"]

if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    steps = (["00_extract_bdot.py"] if "--extract" in sys.argv else []) + STEPS
    for step in steps:
        t = time.time()
        print(f"\n=== {step} ===", flush=True)
        runpy.run_path(str(HERE / step), run_name="__main__")
        print(f"--- {step} done in {time.time() - t:.0f}s", flush=True)
