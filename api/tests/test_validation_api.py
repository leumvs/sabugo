import csv

import pytest

from validation.api import export_images


def test_validation_uses_routes_and_preserves_existing_output_on_failure(job_factory, tmp_path):
    source = job_factory().image_path
    other = tmp_path / "another.png"
    other.write_bytes(source.read_bytes())
    long_name = tmp_path / ("z" * 100 + ".png")
    long_name.write_bytes(source.read_bytes())
    output = tmp_path / "features.csv"
    export_images([source, other, long_name], 300, {}, output)
    with output.open() as handle:
        rows = list(csv.DictReader(handle))
    assert [row["File.Name"] for row in rows] == ["another.png", "bar.png", long_name.name]
    assert all(float(row["Total.Root.Length.mm"]) > 0 for row in rows)
    previous = output.read_bytes()
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"invalid")
    with pytest.raises(Exception):
        export_images([source, broken], 300, {}, output)
    assert output.read_bytes() == previous
    assert sorted(path.name for path in tmp_path.iterdir()) == ["another.png", "bar.png", "broken.png", "features.csv", long_name.name]
