from fastapi import APIRouter, HTTPException, Form, Depends
from typing import Optional
import cv2
import numpy as np
import json
from pathlib import Path
import logging
import threading

from app.services.database import DatasetService
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# ── SAM model (lazy singleton) ────────────────────────────────────────────────

_SAM_MODEL_NAME = "sam_b.pt"   # ViT-B: ~375 MB, downloaded once automatically
_sam_model      = None
_sam_lock       = threading.Lock()


def _get_sam():
    global _sam_model
    if _sam_model is None:
        with _sam_lock:
            if _sam_model is None:
                try:
                    from ultralytics import SAM
                    _sam_model = SAM(_SAM_MODEL_NAME)
                    logger.info("SAM loaded: %s", _SAM_MODEL_NAME)
                except Exception as e:
                    logger.error("SAM load failed — using GrabCut fallback: %s", e)
    return _sam_model


# ── Polygon helpers ───────────────────────────────────────────────────────────

def _smooth_pts(pts, sigma: float = 1.0):
    """Circular Gaussian smooth over polygon vertex coordinates."""
    n = len(pts)
    if n < 8:
        return pts
    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)
    ksize = max(3, int(sigma * 3) | 1)
    half  = ksize // 2
    k     = np.exp(-np.arange(-half, half + 1, dtype=np.float64) ** 2 / (2 * sigma ** 2))
    k    /= k.sum()

    def _circ(arr):
        padded = np.concatenate([arr[-half:], arr, arr[:half]])
        return np.convolve(padded, k, mode='valid')

    return list(zip(_circ(xs).astype(int), _circ(ys).astype(int)))


def _contour_to_polygon(contour, max_pts: int = 200, smooth: bool = True):
    """Convert an OpenCV contour to a simplified polygon point list.

    For SAM masks (already clean), pass smooth=False to skip Gaussian
    blurring which would destroy edge detail. GrabCut masks benefit from
    smoothing to remove pixel-level noise.
    """
    peri    = cv2.arcLength(contour, True)
    # Less aggressive epsilon → more detail preserved
    epsilon = 0.003 * peri
    approx  = cv2.approxPolyDP(contour, epsilon, True)
    pts     = approx.reshape(-1, 2).tolist()
    if len(pts) > max_pts:
        step = len(pts) / max_pts
        pts  = [pts[int(i * step)] for i in range(max_pts)]
    if smooth:
        pts = _smooth_pts(pts, sigma=1.5)
    return [{"x": int(p[0]), "y": int(p[1])} for p in pts]


def _mask_to_response(binary_mask, orig_w, orig_h, algo, smooth_polygon: bool = True):
    contours, _ = cv2.findContours(
        binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    largest  = max(contours, key=cv2.contourArea)
    bx, by, bw_c, bh_c = cv2.boundingRect(largest)
    polygon  = _contour_to_polygon(largest, smooth=smooth_polygon)
    area_px  = int(cv2.contourArea(largest))
    return {
        "success":      True,
        "polygon":      polygon,
        "box":          {"x": bx, "y": by, "width": bw_c, "height": bh_c},
        "image_width":  orig_w,
        "image_height": orig_h,
        "algo_version": algo,
        "area":         area_px,
        "confidence":   min(1.0, area_px / max(1, orig_w * orig_h * 0.05)),
    }


# ── GrabCut fallback ──────────────────────────────────────────────────────────

_GRABCUT_ITER_PASS1 = 6
_GRABCUT_ITER_PASS2 = 5
_BOX_INNER_MARGIN   = 0.04
_POINT_RADIUS_FRAC  = 0.012
_MAX_GRABCUT_DIM    = 800


def _grabcut_fg_mask(mask):
    return np.where(
        (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0
    ).astype("uint8")


def _preprocess(img):
    filtered = cv2.bilateralFilter(img, d=7, sigmaColor=50, sigmaSpace=50)
    lab = cv2.cvtColor(filtered, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _two_pass_grabcut(img, seed_mask):
    mask = seed_mask.copy()
    bgd1 = np.zeros((1, 65), np.float64)
    fgd1 = np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask, None, bgd1, fgd1,
                _GRABCUT_ITER_PASS1, cv2.GC_INIT_WITH_MASK)
    fg1 = _grabcut_fg_mask(mask)

    if cv2.countNonZero(fg1) < 50:
        return fg1

    k_e = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    k_d = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    definite_fg = cv2.erode(fg1, k_e, iterations=2)
    definite_bg = cv2.bitwise_not(cv2.dilate(fg1, k_d, iterations=3))

    mask2 = np.full(img.shape[:2], cv2.GC_PR_BGD, dtype=np.uint8)
    mask2[fg1 == 255]      = cv2.GC_PR_FGD
    mask2[definite_fg > 0] = cv2.GC_FGD
    mask2[definite_bg > 0] = cv2.GC_BGD
    mask2[seed_mask == cv2.GC_FGD] = cv2.GC_FGD
    mask2[seed_mask == cv2.GC_BGD] = cv2.GC_BGD

    bgd2 = np.zeros((1, 65), np.float64)
    fgd2 = np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask2, None, bgd2, fgd2,
                _GRABCUT_ITER_PASS2, cv2.GC_INIT_WITH_MASK)
    fg2 = _grabcut_fg_mask(mask2)

    area1, area2 = cv2.countNonZero(fg1), cv2.countNonZero(fg2)
    if area2 < 50 or area2 > area1 * 3:
        return fg1
    return fg2


def _segment_grabcut(img_path, orig_w, orig_h, box_norm,
                     fg_pts_norm, bg_pts_norm, x, y):
    """Two-pass GrabCut — used when SAM is unavailable."""
    img = cv2.imread(str(img_path))
    scale = 1.0
    if max(orig_w, orig_h) > _MAX_GRABCUT_DIM:
        scale = _MAX_GRABCUT_DIM / max(orig_w, orig_h)
        img = cv2.resize(img,
                         (int(orig_w * scale), int(orig_h * scale)),
                         interpolation=cv2.INTER_AREA)
    img = _preprocess(img)
    h, w = img.shape[:2]
    min_dim = min(w, h)
    pt_r = max(3, int(min_dim * _POINT_RADIUS_FRAC))

    px = max(0, min(int(x * w), w - 1))
    py = max(0, min(int(y * h), h - 1))

    seed_mask = np.full((h, w), cv2.GC_BGD, dtype=np.uint8)
    bx1 = by1 = bx2 = by2 = 0

    if box_norm:
        bx1 = max(0, min(int(box_norm["x1"] * w), w - 1))
        by1 = max(0, min(int(box_norm["y1"] * h), h - 1))
        bx2 = max(0, min(int(box_norm["x2"] * w), w - 1))
        by2 = max(0, min(int(box_norm["y2"] * h), h - 1))
        if bx2 > bx1 and by2 > by1:
            bw_b = bx2 - bx1;  bh_b = by2 - by1
            mx = max(1, int(bw_b * _BOX_INNER_MARGIN))
            my = max(1, int(bh_b * _BOX_INNER_MARGIN))
            seed_mask[by1:by2, bx1:bx2] = cv2.GC_PR_FGD
            seed_mask[by1:by1+my, bx1:bx2] = cv2.GC_PR_BGD
            seed_mask[by2-my:by2, bx1:bx2] = cv2.GC_PR_BGD
            seed_mask[by1:by2, bx1:bx1+mx] = cv2.GC_PR_BGD
            seed_mask[by1:by2, bx2-mx:bx2] = cv2.GC_PR_BGD
            cx, cy = (bx1+bx2)//2, (by1+by2)//2
            sr = max(pt_r, int(min(bw_b, bh_b) * 0.04))
            seed_mask[max(0,cy-sr):min(h,cy+sr),
                      max(0,cx-sr):min(w,cx+sr)] = cv2.GC_FGD
            px, py = cx, cy
    else:
        ff_mask = np.zeros((h+2, w+2), np.uint8)
        flags = (4 | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY)
        cv2.floodFill(img, ff_mask, (px, py),
                      (255,255,255), (20,20,20), (20,20,20), flags)
        ff_mask = ff_mask[1:-1, 1:-1]
        ys, xs = np.where(ff_mask == 255)
        if len(xs):
            pad = max(4, min_dim // 30)
            fx1,fy1 = max(0,int(xs.min())-pad), max(0,int(ys.min())-pad)
            fx2,fy2 = min(w-1,int(xs.max())+pad), min(h-1,int(ys.max())+pad)
            seed_mask[fy1:fy2, fx1:fx2] = cv2.GC_PR_FGD
            seed_mask[ff_mask == 255] = cv2.GC_PR_FGD
        seed_mask[max(0,py-pt_r):min(h,py+pt_r),
                  max(0,px-pt_r):min(w,px+pt_r)] = cv2.GC_FGD

    for pt in fg_pts_norm:
        fpx = max(0, min(int(pt["x"]*w), w-1))
        fpy = max(0, min(int(pt["y"]*h), h-1))
        seed_mask[max(0,fpy-pt_r):min(h,fpy+pt_r),
                  max(0,fpx-pt_r):min(w,fpx+pt_r)] = cv2.GC_FGD

    for pt in bg_pts_norm:
        bpx = max(0, min(int(pt["x"]*w), w-1))
        bpy = max(0, min(int(pt["y"]*h), h-1))
        r_bg = pt_r * 2
        seed_mask[max(0,bpy-r_bg):min(h,bpy+r_bg),
                  max(0,bpx-r_bg):min(w,bpx+r_bg)] = cv2.GC_BGD

    has_fg = np.any((seed_mask==cv2.GC_FGD)|(seed_mask==cv2.GC_PR_FGD))
    has_bg = np.any((seed_mask==cv2.GC_BGD)|(seed_mask==cv2.GC_PR_BGD))
    if not has_fg or not has_bg:
        raise ValueError("Degenerate seed mask")

    fg_mask = _two_pass_grabcut(img, seed_mask)
    k_o = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    k_c = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN,  k_o)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, k_c)

    # Clip to box
    if box_norm and bx2 > bx1:
        clip = np.zeros_like(fg_mask)
        clip[by1:by2, bx1:bx2] = 255
        fg_mask = cv2.bitwise_and(fg_mask, clip)

    # Scale back to original coords
    if scale != 1.0:
        fg_mask = cv2.resize(fg_mask, (orig_w, orig_h),
                             interpolation=cv2.INTER_NEAREST)

    return fg_mask


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/segment")
async def segment_object(
    dataset_id: str       = Form(...),
    image_id:   str       = Form(...),
    x:          float     = Form(0.5),
    y:          float     = Form(0.5),
    box:        Optional[str] = Form(None),
    fg_points:  Optional[str] = Form(None),
    bg_points:  Optional[str] = Form(None),
    current_user: dict    = Depends(get_current_user)
):
    try:
        images   = DatasetService.get_dataset_images(dataset_id)
        img_data = next((i for i in images if str(i["id"]) == str(image_id)), None)
        if not img_data:
            raise HTTPException(status_code=404, detail="Image not found")

        img_path = Path(img_data["path"])
        if not img_path.exists():
            raise HTTPException(status_code=404, detail="Image file missing")

        # Get original dimensions
        probe = cv2.imread(str(img_path))
        if probe is None:
            raise HTTPException(status_code=500, detail="Failed to load image")
        orig_h, orig_w = probe.shape[:2]
        del probe

        fg_pts_norm = json.loads(fg_points) if fg_points else []
        bg_pts_norm = json.loads(bg_points) if bg_points else []
        box_norm    = json.loads(box)        if box        else None

        # ── Convert normalised → absolute pixel coords ────────────────────────
        box_abs = None
        if box_norm:
            box_abs = [
                box_norm["x1"] * orig_w, box_norm["y1"] * orig_h,
                box_norm["x2"] * orig_w, box_norm["y2"] * orig_h,
            ]

        # fg / bg point prompts in absolute coords
        fg_abs = [[pt["x"] * orig_w, pt["y"] * orig_h] for pt in fg_pts_norm]
        bg_abs = [[pt["x"] * orig_w, pt["y"] * orig_h] for pt in bg_pts_norm]

        # Fall back to box centre if no explicit click point
        if not fg_abs and not bg_abs and not box_abs:
            fg_abs = [[x * orig_w, y * orig_h]]

        all_points = fg_abs + bg_abs
        all_labels = [1] * len(fg_abs) + [0] * len(bg_abs)

        # ── Try SAM ───────────────────────────────────────────────────────────
        model = _get_sam()
        if model is not None:
            try:
                results = model(
                    str(img_path),
                    bboxes=[box_abs]          if box_abs    else None,
                    points=[all_points]       if all_points else None,
                    labels=[all_labels]       if all_labels else None,
                    verbose=False,
                )

                if results and results[0].masks is not None and len(results[0].masks.data):
                    # Pick the mask with the highest predicted IoU score
                    masks_data = results[0].masks.data  # (N, H, W) tensor
                    if hasattr(results[0], 'masks') and hasattr(results[0].masks, 'conf') \
                            and results[0].masks.conf is not None:
                        best_idx = int(results[0].masks.conf.argmax())
                    else:
                        best_idx = 0

                    raw = masks_data[best_idx].cpu().numpy()
                    binary_mask = (raw > 0.5).astype(np.uint8) * 255

                    # Ensure mask matches original image size
                    if binary_mask.shape != (orig_h, orig_w):
                        binary_mask = cv2.resize(
                            binary_mask, (orig_w, orig_h),
                            interpolation=cv2.INTER_NEAREST)

                    # Clip to box
                    if box_abs:
                        bx1 = max(0, int(box_abs[0]));  by1 = max(0, int(box_abs[1]))
                        bx2 = min(orig_w, int(box_abs[2])); by2 = min(orig_h, int(box_abs[3]))
                        clip = np.zeros_like(binary_mask)
                        clip[by1:by2, bx1:bx2] = 255
                        binary_mask = cv2.bitwise_and(binary_mask, clip)

                    # SAM already produces clean masks — skip Gaussian smoothing
                    # so the polygon hugs the actual object edges
                    resp = _mask_to_response(binary_mask, orig_w, orig_h, "sam_v1",
                                            smooth_polygon=False)
                    if resp:
                        return resp

                logger.warning("SAM returned no mask — falling back to GrabCut")

            except Exception as sam_err:
                logger.error("SAM inference failed — falling back to GrabCut: %s", sam_err)

        # ── GrabCut fallback ──────────────────────────────────────────────────
        fg_mask = _segment_grabcut(
            img_path, orig_w, orig_h,
            box_norm, fg_pts_norm, bg_pts_norm, x, y)

        # GrabCut masks are noisy — smoothing is still beneficial here
        resp = _mask_to_response(fg_mask, orig_w, orig_h, "grabcut_v5", smooth_polygon=True)
        if resp:
            return resp

        # Nothing worked — return the raw box as last resort
        if box_norm:
            fb_x = int(box_norm["x1"] * orig_w);  fb_y = int(box_norm["y1"] * orig_h)
            fb_w = int((box_norm["x2"] - box_norm["x1"]) * orig_w)
            fb_h = int((box_norm["y2"] - box_norm["y1"]) * orig_h)
        else:
            bs = 40
            fb_x = max(0, int(x * orig_w) - bs // 2)
            fb_y = max(0, int(y * orig_h) - bs // 2)
            fb_w = fb_h = bs

        return {
            "success": True,
            "polygon": [
                {"x": fb_x,        "y": fb_y},
                {"x": fb_x + fb_w, "y": fb_y},
                {"x": fb_x + fb_w, "y": fb_y + fb_h},
                {"x": fb_x,        "y": fb_y + fb_h},
            ],
            "box": {"x": fb_x, "y": fb_y, "width": fb_w, "height": fb_h},
            "image_width": orig_w, "image_height": orig_h,
            "algo_version": "bbox_fallback",
            "area": fb_w * fb_h, "confidence": 0.1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Segmentation failed: %s", e)
        fw = fh = 640
        try:
            fw, fh = orig_w, orig_h
        except NameError:
            pass
        fx = max(0, int(x * fw) - 25)
        fy = max(0, int(y * fh) - 25)
        return {
            "success": False, "detail": str(e),
            "polygon": [
                {"x": fx,      "y": fy},
                {"x": fx + 50, "y": fy},
                {"x": fx + 50, "y": fy + 50},
                {"x": fx,      "y": fy + 50},
            ],
            "box": {"x": fx, "y": fy, "width": 50, "height": 50},
            "algo_version": "error_fallback",
            "area": 2500, "confidence": 0.1,
        }
