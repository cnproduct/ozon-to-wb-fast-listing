import os
import sys

steps = [
    ("3250297312", 18),
    ("3250297808", 44),
    ("4236959651", 45),
    ("1584575749", 46),
    ("1584575959", 47),
    ("859858825",  48),
    ("1313913821", 49),
    ("2274268625", 50),
    ("3250295860", 51),
    ("2015497315", 52),
    ("1323005138", 53),
    ("167019125",  54),
    ("1584575895", 55),
    ("184957428",  57),
    ("1722341870", 58),
    ("504843716",  59),
    ("1423480207", 60),
    ("3250295358", 61),
    ("996552942",  62),
    ("4236959228", 63),
    ("1722342283", 64),
    ("3250297496", 65),
    ("1940789030", 66),
    ("3594519545", 67),
    ("1743765999", 68),
]

base_dir = r"C:\Users\Administrator\.gemini\antigravity\brain\7de286f0-cde1-4bb8-8574-f96b54468ce7\.system_generated\steps"

for sku, step_num in steps:
    fpath = os.path.join(base_dir, str(step_num), "content.md")
    if not os.path.exists(fpath):
        print(f"MISSING: {sku} at step {step_num}")
        continue
    sz = os.path.getsize(fpath)
    print(f"SKU {sku} (step {step_num}): size={sz} bytes")
