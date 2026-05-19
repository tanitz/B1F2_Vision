"""
Fastest Pattern Matching (FPM) — Python / OpenCV reimplementation.

Reference : github.com/DennisLiu1993/Fastest_Image_Pattern_Matching
Algorithm : NCC (TM_CCOEFF_NORMED) + image‑pyramid + optional rotation search.
Provides  : match_fpm(), draw_fpm_match(), crop_fpm_region().
"""

import cv2
import math
import numpy as np

# ── constants ────────────────────────────────────────────────
_D2R = math.pi / 180.0
_R2D = 180.0 / math.pi
_TOL = 1e-7
_EXTRA_CANDS = 5            # extra candidates kept per angle


# ── SSIM helper (no skimage dependency) ──────────────────────
def _compute_ssim(img1, img2):
    """Structural Similarity Index between two same-size grayscale images.
    Returns float in [-1, 1]; typical threshold ≥ 0.25 for 'similar'."""
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    a = img1.astype(np.float64)
    b = img2.astype(np.float64)
    mu1 = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(b, (11, 11), 1.5)
    s1_sq = cv2.GaussianBlur(a * a, (11, 11), 1.5) - mu1 * mu1
    s2_sq = cv2.GaussianBlur(b * b, (11, 11), 1.5) - mu2 * mu2
    s12 = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu1 * mu2
    ssim_map = ((2 * mu1 * mu2 + C1) * (2 * s12 + C2)) / \
               ((mu1 * mu1 + mu2 * mu2 + C1) * (s1_sq + s2_sq + C2))
    return float(ssim_map.mean())


# ── template data ────────────────────────────────────────────
class _TemplData:
    """Precomputed template pyramid + border colour."""
    __slots__ = ("pyramid", "border_color")

    def __init__(self, gray, min_reduce_area=256):
        top = _top_layer(gray, int(math.sqrt(min_reduce_area)))
        self.pyramid = [gray.copy()]
        cur = gray
        for _ in range(top):
            cur = cv2.pyrDown(cur)
            self.pyramid.append(cur)
        self.border_color = 255 if cv2.mean(gray)[0] < 128 else 0


def _top_layer(img, min_side):
    """Number of additional pyramid layers."""
    area = img.shape[0] * img.shape[1]
    min_a = min_side * min_side
    n = 0
    while area > min_a:
        area //= 4
        n += 1
    return n


# ── geometry helpers ─────────────────────────────────────────
def _rot_pt(pt, center, angle):
    """Rotate *pt* around *center* by *angle* radians (image coords, Y↓)."""
    dx = pt[0] - center[0]
    dy = pt[1] - center[1]
    c, s = math.cos(angle), math.sin(angle)
    return (dx * c + dy * s + center[0],
            -dx * s + dy * c + center[1])


def _best_rot_size(src_wh, angle_deg):
    """Bounding‑box size of *src* after rotation by *angle_deg*."""
    sw, sh = src_wh
    center = ((sw - 1) / 2.0, (sh - 1) / 2.0)
    ar = angle_deg * _D2R
    corners = [(0, 0), (sw - 1, 0), (sw - 1, sh - 1), (0, sh - 1)]
    rots = [_rot_pt(c, center, ar) for c in corners]
    xs, ys = zip(*rots)
    return (int(math.ceil(max(xs) - min(xs))) + 1,
            int(math.ceil(max(ys) - min(ys))) + 1)


def _get_rot_roi(src, tmpl_wh, pt_lt, angle_deg, border):
    """Extract rotated ROI from *src* centred on *pt_lt* with 3‑px padding."""
    h, w = src.shape[:2]
    center = ((w - 1) / 2.0, (h - 1) / 2.0)
    pt_lt_r = _rot_pt(pt_lt, center, angle_deg * _D2R)
    pad = (tmpl_wh[0] + 6, tmpl_wh[1] + 6)
    R = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    R[0, 2] -= pt_lt_r[0] - 3
    R[1, 2] -= pt_lt_r[1] - 3
    return cv2.warpAffine(src, R, pad, flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=int(border))


# ── NMS helpers ──────────────────────────────────────────────
def _next_max(result, loc, tmpl_hw, max_overlap):
    """Black‑out region around *loc* and return the next maximum."""
    th, tw = tmpl_hw
    sx = int(loc[0] - tw * (1 - max_overlap))
    sy = int(loc[1] - th * (1 - max_overlap))
    ew = int(2 * tw * (1 - max_overlap))
    eh = int(2 * th * (1 - max_overlap))
    cv2.rectangle(result, (sx, sy), (sx + ew, sy + eh), -1.0, -1)
    _, val, _, loc2 = cv2.minMaxLoc(result)
    return loc2, val


def _rrect_overlap(r1, r2):
    """Overlap ratio of two ``RotatedRect`` tuples (center, size, angle)."""
    ret, pts = cv2.rotatedRectangleIntersection(r1, r2)
    if ret == cv2.INTERSECT_NONE or pts is None:
        return 0.0
    if ret == cv2.INTERSECT_FULL:
        return 1.0
    if len(pts) < 3:
        return 0.0
    hull = cv2.convexHull(pts)
    inter = cv2.contourArea(hull)
    a1 = r1[1][0] * r1[1][1]
    return inter / a1 if a1 > 0 else 0.0


def _nms_rrect(items, max_ov):
    """Greedy NMS using rotated‑rectangle intersection."""
    items.sort(key=lambda c: c["score"], reverse=True)
    keep = []
    for c in items:
        if all(_rrect_overlap(c["_rr"], k["_rr"]) <= max_ov for k in keep):
            keep.append(c)
    return keep


# ── main matching ────────────────────────────────────────────
def match_fpm(scene_bgr, templates, score_threshold=0.5, max_overlap=0.3,
              tolerance_angle=0.0, max_targets=70, min_reduce_area=256,
              validate_ssim=True):
    """
    Fastest Pattern Matching (NCC + image pyramid + rotation).

    Parameters
    ----------
    scene_bgr       : ndarray – scene image (BGR **or** grayscale).
    templates       : list[(label, image)] – template(s) to search for.
    score_threshold : float 0‑1, minimum NCC score.
    max_overlap     : float 0‑1, max overlap ratio for NMS.
    tolerance_angle : float degrees (0‑180). 0 = no rotation search.
    max_targets     : int, max number of returned matches.
    min_reduce_area : int, controls image‑pyramid depth.

    Returns
    -------
    list[dict] with keys: label, bbox, score, center, rect_points, angle
    """
    if not templates:
        return []

    scene_g = (cv2.cvtColor(scene_bgr, cv2.COLOR_BGR2GRAY)
               if scene_bgr.ndim == 3 else scene_bgr)

    all_res = []

    for lbl, tmpl in templates:
        tmpl_g = (cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
                  if tmpl.ndim == 3 else tmpl)
        if (tmpl_g.shape[0] > scene_g.shape[0] or
                tmpl_g.shape[1] > scene_g.shape[1]):
            continue
        if tmpl_g.size > scene_g.size:
            continue

        td = _TemplData(tmpl_g, min_reduce_area)
        nL = len(td.pyramid) - 1          # top‑layer index

        # source pyramid
        src_pyr = [scene_g]
        cur = scene_g
        for _ in range(nL):
            cur = cv2.pyrDown(cur)
            src_pyr.append(cur)

        # angle list
        top_h, top_w = td.pyramid[nL].shape[:2]
        a_step = math.atan(2.0 / max(top_w, top_h, 1)) * _R2D

        if tolerance_angle < _TOL:
            angles = [0.0]
        else:
            angles = []
            a = 0.0
            while a <= tolerance_angle + a_step:
                angles.append(a)
                a += a_step
            a = -a_step
            while a >= -(tolerance_angle + a_step):
                angles.append(a)
                a -= a_step

        # per‑layer score thresholds (relaxed at higher layers)
        layer_th = [score_threshold]
        for _ in range(nL):
            layer_th.append(layer_th[-1] * 0.9)

        # ── Stage 1 : coarse match at top layer ─────────────
        top_src = src_pyr[nL]
        tsh, tsw = top_src.shape[:2]
        center = ((tsw - 1) / 2.0, (tsh - 1) / 2.0)

        cands = []
        for ang in angles:
            bsz = _best_rot_size((tsw, tsh), ang)
            R = cv2.getRotationMatrix2D(center, ang, 1.0)
            tx = (bsz[0] - 1) / 2.0 - center[0]
            ty = (bsz[1] - 1) / 2.0 - center[1]
            R[0, 2] += tx
            R[1, 2] += ty

            rot_src = cv2.warpAffine(
                top_src, R, bsz,
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=int(td.border_color))

            if rot_src.shape[0] < top_h or rot_src.shape[1] < top_w:
                continue

            res = cv2.matchTemplate(rot_src, td.pyramid[nL],
                                    cv2.TM_CCOEFF_NORMED)
            _, mv, _, ml = cv2.minMaxLoc(res)
            if mv < layer_th[nL]:
                continue

            cands.append({
                "pt": (ml[0] - tx, ml[1] - ty),
                "score": mv, "angle": ang,
            })
            for _ in range(max_targets + _EXTRA_CANDS - 1):
                ml, mv = _next_max(res, ml, (top_h, top_w), max_overlap)
                if mv < layer_th[nL]:
                    break
                cands.append({
                    "pt": (ml[0] - tx, ml[1] - ty),
                    "score": mv, "angle": ang,
                })

        cands.sort(key=lambda c: c["score"], reverse=True)

        # ── Stage 2 : refine through lower layers ───────────
        refined = []

        for cand in cands:
            cur_ang = cand["angle"]
            # ptLT in original top‑layer source coords
            ptLT = _rot_pt(cand["pt"], center, -cur_ang * _D2R)

            ok = True
            final_score = cand["score"]

            for iL in range(nL - 1, -1, -1):
                lh, lw = td.pyramid[iL].shape[:2]
                la_step = math.atan(2.0 / max(lw, lh, 1)) * _R2D

                if tolerance_angle < _TOL:
                    sub_angs = [0.0]
                else:
                    sub_angs = [cur_ang + la_step * k for k in [-1, 0, 1]]

                sc = ((src_pyr[iL].shape[1] - 1) / 2.0,
                      (src_pyr[iL].shape[0] - 1) / 2.0)

                best_v, best_j, best_loc = -1, 0, (0, 0)
                for j, sa in enumerate(sub_angs):
                    pt2x = (ptLT[0] * 2, ptLT[1] * 2)
                    roi = _get_rot_roi(src_pyr[iL], (lw, lh),
                                       pt2x, sa, td.border_color)
                    if roi.shape[0] < lh or roi.shape[1] < lw:
                        continue

                    mr = cv2.matchTemplate(roi, td.pyramid[iL],
                                           cv2.TM_CCOEFF_NORMED)
                    _, dv, _, dl = cv2.minMaxLoc(mr)
                    if dv > best_v:
                        best_v, best_j, best_loc = dv, j, dl

                if best_v < layer_th[iL]:
                    ok = False
                    break

                final_score = best_v
                new_ang = sub_angs[best_j]

                # transform coordinates back to source layer
                pt2x = (ptLT[0] * 2, ptLT[1] * 2)
                pt_pad = _rot_pt(pt2x, sc, new_ang * _D2R)
                pt_pad = (pt_pad[0] - 3, pt_pad[1] - 3)

                new_pt = (best_loc[0] + pt_pad[0],
                          best_loc[1] + pt_pad[1])
                new_pt = _rot_pt(new_pt, sc, -new_ang * _D2R)

                ptLT = new_pt
                cur_ang = new_ang

            if not ok:
                continue

            # ── texture + structural validation ──────────────
            # NCC can give false-high scores on regions that are
            # structurally different (normalisation artifact).
            # 1) Laplacian variance: reject featureless patches.
            # 2) SSIM: reject structurally dissimilar patches.
            iW = td.pyramid[0].shape[1]
            iH = td.pyramid[0].shape[0]
            _x0 = max(0, int(round(ptLT[0])))
            _y0 = max(0, int(round(ptLT[1])))
            _x1 = min(_x0 + iW, scene_g.shape[1])
            _y1 = min(_y0 + iH, scene_g.shape[0])
            if _x1 > _x0 and _y1 > _y0:
                _patch = scene_g[_y0:_y1, _x0:_x1]
                # --- Laplacian variance check ---
                _p_var = cv2.Laplacian(_patch, cv2.CV_64F).var()
                _t_var = cv2.Laplacian(td.pyramid[0], cv2.CV_64F).var()
                if _t_var > 50 and _p_var < _t_var * 0.15:
                    continue  # region too blurry / featureless
                # --- SSIM check (skip in fast mode) ---
                if validate_ssim:
                    _tp = td.pyramid[0]
                    _pp = cv2.resize(_patch, (_tp.shape[1], _tp.shape[0]),
                                     interpolation=cv2.INTER_AREA)
                    _ssim = _compute_ssim(_pp, _tp)
                    if _ssim < 0.35:
                        continue  # structurally dissimilar

            # ── build corner points ──────────────────────────
            ra = -cur_ang * _D2R
            ca, sa = math.cos(ra), math.sin(ra)

            pLT = ptLT
            pRT = (pLT[0] + iW * ca, pLT[1] - iW * sa)
            pLB = (pLT[0] + iH * sa, pLT[1] + iH * ca)
            pRB = (pRT[0] + iH * sa, pRT[1] + iH * ca)
            pC = ((pLT[0] + pRT[0] + pRB[0] + pLB[0]) / 4,
                  (pLT[1] + pRT[1] + pRB[1] + pLB[1]) / 4)

            m_angle = -cur_ang
            if m_angle < -180:
                m_angle += 360
            if m_angle > 180:
                m_angle -= 360

            pts_arr = np.array([pLT, pRT, pRB, pLB], dtype=np.float32)
            bx, by, bw, bh = cv2.boundingRect(pts_arr)

            rr = ((float(pC[0]), float(pC[1])),
                  (float(iW), float(iH)),
                  float(m_angle))

            refined.append({
                "label": lbl,
                "bbox": (int(bx), int(by), int(bw), int(bh)),
                "score": float(final_score),
                "center": (int(round(pC[0])), int(round(pC[1]))),
                "rect_points": [
                    (int(round(pLT[0])), int(round(pLT[1]))),
                    (int(round(pRT[0])), int(round(pRT[1]))),
                    (int(round(pRB[0])), int(round(pRB[1]))),
                    (int(round(pLB[0])), int(round(pLB[1]))),
                ],
                "angle": float(m_angle),
                "_rr": rr,
            })

        # score filter + NMS + limit
        refined = [r for r in refined if r["score"] >= score_threshold]
        refined = _nms_rrect(refined, max_overlap)
        refined = refined[:max_targets]
        all_res.extend(refined)

    # remove internal key
    for r in all_res:
        r.pop("_rr", None)
    all_res.sort(key=lambda r: r["score"], reverse=True)
    return all_res


# ── draw / crop helpers ──────────────────────────────────────
def draw_fpm_match(scene_bgr, result, color=(0, 255, 0), thickness=2,
                   label="", fill_alpha=0.15, label_scale=0.55):
    """Draw rotated bounding box with semi-transparent highlight fill."""
    pts = result["rect_points"]
    pts_arr = np.array(pts, dtype=np.int32)

    # Semi-transparent bright-green fill over detected polygon
    overlay = scene_bgr.copy()
    cv2.fillPoly(overlay, [pts_arr], (0, 255, 80))
    cv2.addWeighted(overlay, fill_alpha, scene_bgr, 1 - fill_alpha, 0, scene_bgr)

    # Outline border
    for i in range(4):
        cv2.line(scene_bgr, pts[i], pts[(i + 1) % 4], color, thickness)

    cx, cy = result["center"]
    cv2.drawMarker(scene_bgr, (cx, cy), color, cv2.MARKER_CROSS, 10, 1)
    if label:
        org = (pts[0][0], pts[0][1] - 6)
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                                       label_scale, 2)
        cv2.rectangle(scene_bgr,
                      (org[0], org[1] - lh - 4),
                      (org[0] + lw + 6, org[1] + 4), color, -1)
        cv2.putText(scene_bgr, label, (org[0] + 3, org[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, label_scale, (0, 0, 0), 2)
    return scene_bgr


def crop_fpm_region(scene_bgr, result):
    """Crop the bounding‑box region from *scene_bgr* for one FPM result."""
    x, y, w, h = result["bbox"]
    x1, y1 = max(0, x), max(0, y)
    x2 = min(scene_bgr.shape[1], x + w)
    y2 = min(scene_bgr.shape[0], y + h)
    if x2 <= x1 or y2 <= y1:
        return None
    return scene_bgr[y1:y2, x1:x2].copy()
