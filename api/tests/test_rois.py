"""Regions of interest."""


import numpy as np
import pytest

from imaging import Params
from imaging.analysis import regions

ANNOTATION = """#ROI Name, Class Name, X Position, Y Position, Width, Height
roi_1, root, 10, 20, 30, 40
roi_2, root, 5, 5, 10, 10
"""












def test_without_rois_the_whole_image_is_the_region():
    image = np.zeros((10, 12), np.uint8)
    names = [name for name, _ in regions(image, Params())]
    assert names == ["Full"]
    assert regions(image, Params())[0][1].shape == image.shape


def test_a_roi_is_x_y_width_height_of_the_original_image():
    image = np.arange(200 * 300, dtype=np.uint8).reshape(200, 300)
    params = Params(rois=[("roi_1", 30, 20, 40, 50)])
    name, region = regions(image, params)[0]

    assert name == "roi_1"
    assert region.shape == (50, 40)
    assert np.array_equal(region, image[20:70, 30:70])








def test_full_image_roi_matches_full_analysis(job_factory):
    from services.processing import analyse_upload

    first, _ = analyse_upload(job_factory(), 100)
    second, _ = analyse_upload(job_factory(rois=[{"name": "whole", "x": 0, "y": 0, "width": 300, "height": 200}]), 100)
    for name, value in first["results"][0]["metrics"].items():
        if name != "processingTimeMs":
            assert second["results"][0]["metrics"][name] == value
