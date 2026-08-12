"""The CLI: runs the pipeline locally"""

from __future__ import annotations

import sys
from contextlib import ExitStack
from pathlib import Path

import cv2

from . import export, jsonout, render
from .analysis import analyse, regions
from .args import build_parser, read_annotations
from .pipeline import MAX_PIXELS, Params, PipelineError, load_image, segment
from .progress import Progress
from .report import report

EXTENSIONS = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dpi = args.dpi if args.dpi else args.pixels_per_mm * 25.4
    params = Params(
        **{f.name: getattr(args, f.name) for f in Params.__dataclass_fields__.values()
           if hasattr(args, f.name)}
    )
    if args.roipath:
        params.rois = read_annotations(args.roipath)

    images = (
        sorted(f for f in args.path.iterdir() if f.suffix.lower() in EXTENSIONS)
        if args.path.is_dir()
        else [args.path]
    )
    if not images:
        print(f"no images in {args.path}", file=sys.stderr)
        return 1

    max_pixels = (
        int(args.max_megapixels * 1_000_000) if args.max_megapixels else MAX_PIXELS
    )
    per_image = max(len(params.rois), 1)
    progress = Progress(args.progress, len(images) * per_image)

    with ExitStack() as stack:
        table = None
        if args.output:
            handle = stack.enter_context(
                args.output.open("w", newline="", encoding="utf-8")
            )
            table = export.writer(handle, params.diameter_ranges_mm, params.mode)

        failed = False
        results = []
        for image_path in images:
            try:
                image = load_image(str(image_path), max_pixels)
            except PipelineError as error:
                failed = True
                print(f"{image_path}: {error}", file=sys.stderr)
                continue
            progress.stage("load")
            for index, (name, region) in enumerate(regions(image, params)):
                try:
                    if args.preview:
                        seg = segment(region, dpi, params)
                        progress.stage("segment", name)
                        values, skeleton = None, None
                    else:
                        values, seg, skeleton = analyse(region, dpi, params, progress, name)
                except PipelineError as error:
                    failed = True
                    print(f"{image_path} [{name}]: {error}", file=sys.stderr)
                    progress.unit_done()
                    continue
                pictures = write_pictures(args, image_path, name, seg, skeleton, params)
                progress.stage("render", name)
                if values is None:
                    if args.json_output:
                        results.append(
                            jsonout.preview(
                                image_path.name, name, -1 if name == "Full" else index,
                                seg.threshold_value_used, pictures,
                            )
                        )
                    progress.unit_done()
                    continue
                if table is not None:
                    table.writerow(
                        export.row(
                            image_path.name, values, params.diameter_ranges_mm, name,
                            params.mode,
                        )
                    )
                elif not args.json_output:
                    report(image_path, name, values, seg.threshold_value_used,
                           params.diameter_ranges_mm)
                if args.json_output:
                    results.append(
                        jsonout.result(
                            image_path.name, name, -1 if name == "Full" else index,
                            values, seg.threshold_value_used, pictures, params.mode,
                        )
                    )
                progress.unit_done()

        if args.json_output:
            with args.json_output.open("w", encoding="utf-8") as handle:
                jsonout.write(handle, results)
    return 1 if failed else 0


def write_pictures(args, image_path: Path, region: str, seg, skeleton, params) -> dict:
    """Returns where each image landed, or `None` for the ones not asked
    for."""
    tag = "" if region == "Full" else f"_{region}"
    written = {"segmented": None, "skeleton": None}
    if args.segment:
        target = image_path.with_name(f"{image_path.stem}{tag}{args.ssuffix}.png")
        cv2.imwrite(str(target), render.segmented(seg.mask))
        written["segmented"] = target
    if args.feature and skeleton is not None:
        target = image_path.with_name(f"{image_path.stem}{tag}{args.fsuffix}.png")
        cv2.imwrite(
            str(target),
            render.skeleton_picture(
                seg.mask, seg.dt, skeleton, seg.mm_per_px, params.diameter_ranges_mm,
                pen=args.medialwidth, holes=args.holes, hull=args.hull,
                contour=args.contour, contour_width=args.contourwidth,
                show_distance_map=args.distancemap,
                medial_axis=args.medialaxis, colour_by_class=args.classcolour,
            ),
        )
        written["skeleton"] = target
    return written


if __name__ == "__main__":
    raise SystemExit(main())
