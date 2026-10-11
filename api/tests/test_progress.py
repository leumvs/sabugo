from services.processing import analyse_upload
from imaging.progress import Progress


def test_default_progress_is_silent(capsys):
    progress = Progress()
    progress.stage("load")
    assert capsys.readouterr() == ("", "")


def test_progress_names_regions_and_never_goes_backwards(job_factory):
    rois = [{"name": name, "x": 0, "y": y, "width": 300, "height": 40}
            for name, y in (("top", 30), ("bottom", 130))]
    events = []
    analyse_upload(job_factory(rois=rois), 100, events.append)
    percents = [event["percent"] for event in events]
    assert percents == sorted(percents)
    assert percents[-1] >= 95
    assert {"top", "bottom"} <= {event["region"] for event in events}
    assert all(event["stage"] in Progress.STAGES and 0 < event["percent"] <= 100 for event in events)


def test_pruning_only_reports_when_enabled(job_factory):
    for enabled in (False, True):
        events = []
        analyse_upload(job_factory(params={"enable_root_pruning": enabled}), 100, events.append)
        assert ("prune" in {event["stage"] for event in events}) == enabled
