import json
import subprocess
import sys

from imaging.pipeline import Params
from schemas import AnalysisDocument, AnalysisParams
from services.processing import analyse_upload


def test_wire_defaults_and_pipeline_defaults_stay_consistent():
    defaults = Params()
    wire = AnalysisParams().model_dump()
    for name, value in wire.items():
        if hasattr(defaults, name):
            assert getattr(defaults, name) == value, name
    rois = [{"name": "first", "x": 2, "y": 3, "width": 4, "height": 5}]
    params = Params.from_options(wire, rois)
    assert params.rois == [("first", 2, 3, 4, 5)]
    assert not hasattr(params, "show_medial_axis")


def test_completed_documents_match_the_documented_schema(job_factory):
    for preview in (False, True):
        document, _ = analyse_upload(job_factory(preview=preview), 50)
        checked = AnalysisDocument.model_validate(document).model_dump()
        assert checked == document


def test_child_sets_native_pixel_limit_before_importing_decoder(job_factory):
    job = job_factory()
    source = '''
import json, os, sys
from pathlib import Path
from services.jobs import Job
from services.processing import _process
assert 'cv2' not in sys.modules
class Connection:
    def send(self, event):
        print(json.dumps(event))
    def close(self):
        pass
_process(Connection(), Job(Path(sys.argv[1]), 'scan.png', 300, {}, []), 0.01)
assert os.environ['OPENCV_IO_MAX_IMAGE_PIXELS'] == '10000'
import cv2
try:
    cv2.imread(sys.argv[1], cv2.IMREAD_UNCHANGED)
except cv2.error as error:
    assert error.func == 'validateInputImageSize'
else:
    raise AssertionError('decoder allocated oversized image')
'''
    completed = subprocess.run([sys.executable, "-c", source, str(job.image_path)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == ["failed", {"code": "IMAGE_TOO_LARGE", "message": "image_too_large"}]
