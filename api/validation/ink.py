"""Does the image hold the root the model says it drew?

The ink integral passes through no threshold and no skeleton: sum(255-gray)/255
is the projected root area of the rendering in pixels. The model's own Sum(L*d)
is the same quantity. If they disagree, the disagreement is the dataset's.
"""

import csv
import os
import pathlib
import sys

import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "validation"))
sys.path.insert(0, str(HERE / "src"))
import compare as c  # noqa: E402

DPI = int(os.environ.get("DPI", 1200))
PX_PER_MM = DPI / 25.4


def model_area() -> dict[str, float]:
    rows = {}
    with (c.IMAGES / "ground_truth_data_2D.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows[row["image"].removesuffix(".rsml")] = (
                float(row["tot_prim_length"]) * float(row["mean_prim_diameter"])
                + float(row[" tot_lat_length"]) * float(row["mean_lat_diameter"])
            )
    return rows


truth, areas, key = c.truth_rows(), model_area(), c.system_of(DPI)
ours = c.measured_rows(c.RESULTS / f"simulated-{DPI}.csv", key)

ink_error, length_error, names = [], [], []
for image in sorted(c.IMAGES.glob(f"{DPI}-*.jpg")):
    name = key(image.name)
    if name not in areas or name not in ours:
        continue
    gray = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
    ink = float((255.0 - gray).sum() / 255.0) / (PX_PER_MM**2)  # mm2 of root drawn
    ink_error.append(ink / areas[name] - 1.0)
    length_error.append(
        ours[name]["total_root_length"] / truth[name]["total_root_length"] - 1.0
    )
    names.append(name)

ink_error = np.array(ink_error)
length_error = np.array(length_error)
print(f"{len(names)} systems at {DPI} DPI\n")
print(f"ink in the image vs the model's own L*d : {100 * ink_error.mean():+.2f}%")
print(f"length we measure vs the model's length : {100 * length_error.mean():+.2f}%")
print(f"\ncorrelation between the two, per system : {np.corrcoef(ink_error, length_error)[0, 1]:+.3f}")
slope, intercept = np.polyfit(ink_error, length_error, 1)
print(f"length error = {slope:.2f} * ink error {intercept:+.4f}")
print(f"\nlength error with the ink deficit taken out: "
      f"{100 * (length_error - ink_error).mean():+.2f}%")
