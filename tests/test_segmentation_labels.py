"""
Polygon conversion for segmentation versions.

The failure this guards against is silent: the version generator used to read
`box["width"]` for every shape, which is absent on a polygon, so it came back
0, tripped the degenerate-box guard and dropped the instance. Nothing logged,
nothing raised — the polygon work simply never reached training. These tests
pin the conversion that replaced it.
"""

from app.services import segmentation_labels as seglabels

W, H = 200, 100


def _polygon(points, class_id=0, shape="polygon"):
    return {
        "type": shape,
        "class_id": class_id,
        "points": [{"x": x, "y": y} for x, y in points],
    }


# --- boxes become polygons -------------------------------------------------


def test_a_box_becomes_its_four_corners():
    # YOLO's segment format has no "box only" instance, so a rectangle has to
    # be expressed as a polygon rather than dropped.
    box = {"type": "box", "x": 50, "y": 25, "width": 100, "height": 50}
    assert seglabels.instance_polygon(box, W, H) == [
        (0.25, 0.25),
        (0.75, 0.25),
        (0.75, 0.75),
        (0.25, 0.75),
    ]


def test_a_box_with_no_type_is_still_treated_as_a_box():
    box = {"x": 0, "y": 0, "width": 200, "height": 100}
    assert seglabels.instance_polygon(box, W, H) == [
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (0.0, 1.0),
    ]


def test_a_box_overflowing_the_frame_is_clamped():
    box = {"type": "box", "x": -20, "y": -10, "width": 400, "height": 200}
    assert seglabels.instance_polygon(box, W, H) == [
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (0.0, 1.0),
    ]


def test_a_degenerate_box_is_skipped():
    box = {"type": "box", "x": 10, "y": 10, "width": 0, "height": 50}
    assert seglabels.instance_polygon(box, W, H) is None


# --- polygons --------------------------------------------------------------


def test_polygon_points_are_normalised():
    poly = _polygon([(0, 0), (200, 0), (100, 100)])
    assert seglabels.instance_polygon(poly, W, H) == [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]


def test_polygon_vertices_outside_the_frame_are_clamped():
    poly = _polygon([(-50, -50), (400, 0), (100, 300)])
    assert seglabels.instance_polygon(poly, W, H) == [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]


def test_a_two_point_line_has_no_interior_and_is_skipped():
    assert seglabels.instance_polygon(_polygon([(0, 0), (100, 50)], shape="line"), W, H) is None


def test_a_closed_line_of_three_points_is_usable():
    poly = _polygon([(0, 0), (200, 0), (100, 100)], shape="line")
    assert seglabels.instance_polygon(poly, W, H) is not None


def test_a_collapsed_polygon_is_skipped():
    # Every vertex on the same vertical line — no area, so no mask.
    assert seglabels.instance_polygon(_polygon([(50, 0), (50, 50), (50, 100)]), W, H) is None


def test_malformed_points_skip_the_instance_rather_than_raising():
    assert seglabels.instance_polygon({"type": "polygon", "points": [{"x": 1}] * 3}, W, H) is None
    assert (
        seglabels.instance_polygon(
            {"type": "polygon", "points": [{"x": "a", "y": 0}] * 3}, W, H
        )
        is None
    )


def test_a_joint_is_not_a_segmentation_instance():
    # A keypoint has no area, and YOLO pose needs a per-object skeleton this
    # data model does not record, so a joint is skipped rather than guessed at.
    assert seglabels.instance_polygon({"type": "joint", "x": 10, "y": 10}, W, H) is None


def test_zero_sized_image_dimensions_skip_the_instance():
    box = {"type": "box", "x": 1, "y": 1, "width": 5, "height": 5}
    assert seglabels.instance_polygon(box, 0, H) is None
    assert seglabels.instance_polygon(box, W, 0) is None


# --- derived bounding box --------------------------------------------------


def test_polygon_bbox_covers_the_whole_shape():
    x, y, w, h = seglabels.polygon_bbox([(0.2, 0.1), (0.8, 0.3), (0.5, 0.9)])
    assert (round(x, 6), round(y, 6), round(w, 6), round(h, 6)) == (0.2, 0.1, 0.6, 0.8)


def test_polygon_bbox_of_a_rectangle_is_the_rectangle():
    x, y, w, h = seglabels.polygon_bbox(
        [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
    )
    assert (round(x, 6), round(y, 6), round(w, 6), round(h, 6)) == (0.25, 0.25, 0.5, 0.5)


# --- label lines -----------------------------------------------------------


def test_label_line_is_class_then_flat_normalised_pairs():
    line = seglabels.format_segment_line(2, [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)])
    assert line == "2 0.000000 0.000000 1.000000 0.000000 0.500000 1.000000"


def test_label_line_clamps_rather_than_emitting_out_of_range_coordinates():
    # YOLO rejects a normalised coordinate outside [0, 1] at load time, which
    # would fail the whole run rather than one instance.
    line = seglabels.format_segment_line(0, [(-0.5, 1.5), (0.5, 0.5), (0.2, 0.2)])
    assert line == "0 0.000000 1.000000 0.500000 0.500000 0.200000 0.200000"


def test_label_line_coerces_a_float_class_id():
    assert seglabels.format_segment_line(1.0, [(0, 0), (1, 0), (0, 1)]).startswith("1 ")


# --- dataset-level counting ------------------------------------------------


def test_counts_only_real_polygons():
    annotations = [
        {"boxes": [_polygon([(0, 0), (10, 0), (5, 5)]), {"type": "box", "x": 0, "y": 0}]},
        {"boxes": [_polygon([(0, 0), (10, 0)], shape="line")]},  # too few points
        {"boxes": [_polygon([(0, 0), (10, 0), (5, 5)], shape="line")]},
        {"boxes": []},
        {},
    ]
    assert seglabels.count_polygon_instances(annotations) == 2


def test_counting_an_empty_dataset_is_zero():
    assert seglabels.count_polygon_instances([]) == 0
