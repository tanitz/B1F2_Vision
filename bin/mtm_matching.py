"""
Multi-Template-Matching (cv2 only — no scipy / MTM dependency).
Uses cv2.matchTemplate + local-peak extraction + IoU-based NMS.
Provides match_mtm(), draw_mtm_match(), crop_mtm_region().
"""

import cv2
import numpy as np


def _local_peaks(corr_map, threshold):
    """Return list of (y, x) peak locations above *threshold*."""
    if corr_map.size == 0:
        return []
    # dilate = local-max filter; compare to find peaks
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dilated = cv2.dilate(corr_map, kernel)
    peaks = (corr_map == dilated) & (corr_map >= threshold)
    ys, xs = np.where(peaks)
    return list(zip(ys.tolist(), xs.tolist()))


def _iou(a, b):
    """IoU between two (x,y,w,h) boxes."""
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _nms(hits, max_overlap):
    """Non-Maximum Suppression on list of (label, bbox, score)."""
    hits.sort(key=lambda h: h[2], reverse=True)
    keep = []
    for h in hits:
        if all(_iou(h[1], k[1]) <= max_overlap for k in keep):
            keep.append(h)
    return keep


def match_mtm(scene_bgr, templates, score_threshold=0.7, max_overlap=0.15,
              method=cv2.TM_CCOEFF_NORMED):
    """
    Multi-template matching using cv2.matchTemplate + NMS.

    Parameters
    ----------
    scene_bgr : numpy array (BGR or grayscale)
    templates : list of (label_str, template_bgr_array)
    score_threshold : float  (0-1)
    max_overlap : float  (IoU threshold for NMS)
    method : OpenCV TM method (default TM_CCOEFF_NORMED)

    Returns
    -------
    list of dict with keys: label, bbox, score, center, rect_points
    """
    if not templates:
        return []

    all_hits = []
    for label, tmpl in templates:
        if tmpl.shape[0] > scene_bgr.shape[0] or tmpl.shape[1] > scene_bgr.shape[1]:
            continue
        corr = cv2.matchTemplate(scene_bgr, tmpl, method)
        h, w = tmpl.shape[:2]
        peaks = _local_peaks(corr, score_threshold)
        for py, px in peaks:
            score = float(corr[py, px])
            all_hits.append((label, (px, py, w, h), score))

    kept = _nms(all_hits, max_overlap)

    results = []
    for label, bbox, score in kept:
        x, y, w, h = bbox
        cx = x + w // 2
        cy = y + h // 2
        rect_points = [
            (x, y),
            (x + w, y),
            (x + w, y + h),
            (x, y + h),
        ]
        results.append({
            "label": label,
            "bbox": (x, y, w, h),
            "score": float(score),
            "center": (cx, cy),
            "rect_points": rect_points,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def draw_mtm_match(scene_bgr, result, color=(0, 255, 0), thickness=2, label=""):
    """Draw bounding box on scene_bgr for one MTM result dict."""
    x, y, w, h = result["bbox"]
    cv2.rectangle(scene_bgr, (x, y), (x + w, y + h), color, thickness)
    if label:
        org = (x, y - 6)
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(scene_bgr,
                      (org[0], org[1] - lh - 4),
                      (org[0] + lw + 6, org[1] + 4), color, -1)
        cv2.putText(scene_bgr, label,
                    (org[0] + 3, org[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    return scene_bgr


def crop_mtm_region(scene_bgr, result):
    """Crop the bounding-box region from scene_bgr for one MTM result."""
    x, y, w, h = result["bbox"]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(scene_bgr.shape[1], x + w)
    y2 = min(scene_bgr.shape[0], y + h)
    if x2 <= x1 or y2 <= y1:
        return None
    return scene_bgr[y1:y2, x1:x2].copy()
