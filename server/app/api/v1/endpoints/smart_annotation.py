from fastapi import APIRouter, HTTPException, Form, Depends
from typing import Optional
import cv2
import numpy as np
import json
from pathlib import Path
import logging

from app.services.database import DatasetService
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

_GRABCUT_ITERATIONS = 8
_BOX_INNER_MARGIN = 0.07    # 7 % of box dim — border inside box treated as probable BG
_POINT_RADIUS_FRAC = 0.008  # point seed radius as fraction of min(w,h)


def _contour_to_polygon(contour, max_pts: int = 96):
    peri = cv2.arcLength(contour, True)
    epsilon = 0.004 * peri
    approx = cv2.approxPolyDP(contour, epsilon, True)
    pts = approx.reshape(-1, 2).tolist()
    if len(pts) > max_pts:
        step = len(pts) / max_pts
        pts = [pts[int(i * step)] for i in range(max_pts)]
    return [{"x": int(p[0]), "y": int(p[1])} for p in pts]


def _refine_to_definite(mask: np.ndarray) -> np.ndarray:
    """Return only definite-FG pixels; if the result is too sparse, fall back to including PR_FGD."""
    strict = np.where(mask == cv2.GC_FGD, 255, 0).astype("uint8")
    if cv2.countNonZero(strict) >= 50:
        return strict
    return np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")


@router.post("/segment")
async def segment_object(
    dataset_id: str = Form(...),
    image_id: str = Form(...),
    x: float = Form(0.5),
    y: float = Form(0.5),
    box: Optional[str] = Form(None),
    fg_points: Optional[str] = Form(None),
    bg_points: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    try:
        images = DatasetService.get_dataset_images(dataset_id)
        img_data = next((img for img in images if str(img["id"]) == str(image_id)), None)
        if not img_data:
            raise HTTPException(status_code=404, detail="Image not found")

        img_path = Path(img_data["path"])
        if not img_path.exists():
            raise HTTPException(status_code=404, detail="Image file missing")

        img = cv2.imread(str(img_path))
        if img is None:
            raise HTTPException(status_code=500, detail="Failed to load image")

        h, w = img.shape[:2]
        min_dim = min(w, h)
        pt_r = max(2, int(min_dim * _POINT_RADIUS_FRAC))

        fg_pts_norm = json.loads(fg_points) if fg_points else []
        bg_pts_norm = json.loads(bg_points) if bg_points else []
        box_norm = json.loads(box) if box else None

        px = max(0, min(int(x * w), w - 1))
        py = max(0, min(int(y * h), h - 1))

        # ── Initial mask: everything is definite background ──────────────────
        mask = np.full((h, w), cv2.GC_BGD, dtype=np.uint8)

        if box_norm:
            bx1 = max(0, min(int(box_norm["x1"] * w), w - 1))
            by1 = max(0, min(int(box_norm["y1"] * h), h - 1))
            bx2 = max(0, min(int(box_norm["x2"] * w), w - 1))
            by2 = max(0, min(int(box_norm["y2"] * h), h - 1))

            if bx2 > bx1 and by2 > by1:
                bw_box = bx2 - bx1
                bh_box = by2 - by1
                mx = max(1, int(bw_box * _BOX_INNER_MARGIN))
                my = max(1, int(bh_box * _BOX_INNER_MARGIN))

                # Narrow inner border → probable BG (object rarely fills edge-to-edge)
                mask[by1:by2, bx1:bx2] = cv2.GC_PR_BGD
                # Interior → probable FG
                mask[by1 + my:by2 - my, bx1 + mx:bx2 - mx] = cv2.GC_PR_FGD

                px = (bx1 + bx2) // 2
                py = (by1 + by2) // 2
        else:
            # No box → seed from click using narrow flood-fill
            ff_mask = np.zeros((h + 2, w + 2), np.uint8)
            ff_flags = 4 | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY
            cv2.floodFill(img, ff_mask, (px, py), (255, 255, 255), (20, 20, 20), (20, 20, 20), ff_flags)
            ff_mask = ff_mask[1:-1, 1:-1]

            # Only flood-filled region and its tight surrounding box are allowed
            ys, xs = np.where(ff_mask == 255)
            if len(xs):
                fx1, fx2 = int(xs.min()), int(xs.max())
                fy1, fy2 = int(ys.min()), int(ys.max())
                pad = max(4, min_dim // 30)
                fx1, fy1 = max(0, fx1 - pad), max(0, fy1 - pad)
                fx2, fy2 = min(w - 1, fx2 + pad), min(h - 1, fy2 + pad)
                mask[fy1:fy2, fx1:fx2] = cv2.GC_PR_FGD
                mask[ff_mask == 255] = cv2.GC_PR_FGD

            # Definite seed at click point
            mask[max(0, py - pt_r):min(h, py + pt_r), max(0, px - pt_r):min(w, px + pt_r)] = cv2.GC_FGD

        # ── Apply user FG / BG point seeds (tight radius) ───────────────────
        for pt in fg_pts_norm:
            fpx = max(0, min(int(pt["x"] * w), w - 1))
            fpy = max(0, min(int(pt["y"] * h), h - 1))
            mask[max(0, fpy - pt_r):min(h, fpy + pt_r), max(0, fpx - pt_r):min(w, fpx + pt_r)] = cv2.GC_FGD

        for pt in bg_pts_norm:
            bpx = max(0, min(int(pt["x"] * w), w - 1))
            bpy = max(0, min(int(pt["y"] * h), h - 1))
            r_bg = pt_r * 2  # slightly wider BG seed for stronger exclusion
            mask[max(0, bpy - r_bg):min(h, bpy + r_bg), max(0, bpx - r_bg):min(w, bpx + r_bg)] = cv2.GC_BGD

        # ── Sanity check ─────────────────────────────────────────────────────
        has_fg = np.any((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD))
        has_bg = np.any((mask == cv2.GC_BGD) | (mask == cv2.GC_PR_BGD))
        if not has_fg or not has_bg:
            raise ValueError("Degenerate mask: need both FG and BG seeds")

        # ── GrabCut ──────────────────────────────────────────────────────────
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        cv2.grabCut(img, mask, None, bgd_model, fgd_model, _GRABCUT_ITERATIONS, cv2.GC_INIT_WITH_MASK)

        # ── Strict final mask: prefer definite FG only ───────────────────────
        final_mask = _refine_to_definite(mask)

        # Tighten with open (remove tiny spurious blobs) then close small holes
        k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_OPEN, k_open)
        final_mask = cv2.morphologyEx(final_mask, cv2.MORPH_CLOSE, k_close)

        # One-pixel erosion for tight boundary hug
        k_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        final_mask = cv2.erode(final_mask, k_erode, iterations=1)

        contours, _ = cv2.findContours(final_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            box_size = max(20, min_dim // 20)
            fallback_box = {"x": max(0, px - box_size // 2), "y": max(0, py - box_size // 2), "width": box_size, "height": box_size}
            return {
                "success": True,
                "polygon": [
                    {"x": fallback_box["x"], "y": fallback_box["y"]},
                    {"x": fallback_box["x"] + fallback_box["width"], "y": fallback_box["y"]},
                    {"x": fallback_box["x"] + fallback_box["width"], "y": fallback_box["y"] + fallback_box["height"]},
                    {"x": fallback_box["x"], "y": fallback_box["y"] + fallback_box["height"]},
                ],
                "box": fallback_box, "image_width": w, "image_height": h,
            }

        largest = max(contours, key=cv2.contourArea)
        bx, by, bw_c, bh_c = cv2.boundingRect(largest)
        if bw_c < 5 or bh_c < 5:
            box_size = 20
            bx, by, bw_c, bh_c = max(0, px - box_size // 2), max(0, py - box_size // 2), box_size, box_size

        polygon = _contour_to_polygon(largest)

        return {
            "success": True,
            "polygon": polygon,
            "box": {"x": int(bx), "y": int(by), "width": int(bw_c), "height": int(bh_c)},
            "image_width": w,
            "image_height": h,
        }

    except Exception as e:
        logger.error(f"Segmentation failed: {e}")
        fallback_x = max(0, int(x * 100) - 25)
        fallback_y = max(0, int(y * 100) - 25)
        return {
            "success": False,
            "detail": str(e),
            "polygon": [
                {"x": fallback_x, "y": fallback_y},
                {"x": fallback_x + 50, "y": fallback_y},
                {"x": fallback_x + 50, "y": fallback_y + 50},
                {"x": fallback_x, "y": fallback_y + 50},
            ],
            "box": {"x": fallback_x, "y": fallback_y, "width": 50, "height": 50},
        }
