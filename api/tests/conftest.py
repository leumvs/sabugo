import cv2
import numpy as np
import pytest

from schemas import AnalysisParams
from services.jobs import Job


@pytest.fixture
def job_factory(tmp_path):
    image = np.full((200, 300), 255, np.uint8)
    image[40:60, 20:280] = 0
    image[140:150, 20:280] = 0
    path = tmp_path / "bar.png"
    cv2.imwrite(str(path), image)

    def make(params=None, **kwargs):
        return Job(path, "bar.png", kwargs.pop("dpi", 300), AnalysisParams.model_validate(params or {}).model_dump(), kwargs.pop("rois", []), **kwargs)

    return make
