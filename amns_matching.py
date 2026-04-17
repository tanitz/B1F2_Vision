"""
A-MNS Template Matching (Python / OpenCV / NumPy)  — FAST version

Based on the paper:
  "Fast and robust template matching with majority neighbour similarity
   and annulus projection transformation"
  Pattern Recognition, 2020

Optimised for speed:
  • Scene is downsampled before ring-map convolution.
  • float32 throughout.
  • Vectorised SSD (all blocks at once, no Python loop over pixels).
  • Fewer scales by default.
"""

import math
import functools
import numpy as np
import cv2


# ── lookup tables ────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=16)
def _build_tables(ldisk):
    R = ldisk // 2
    x = [1]
    for _ in range(R):
        sq = (R - x[-1]) ** 2 - (2 * R - 1)
        if sq < 0:
            break
        nxt = int(R - math.sqrt(sq) + 0.5)
        if nxt <= x[-1]:
            break
        x.append(nxt)
    num_rings = len(x)

    iy, ix = np.mgrid[0:ldisk, 0:ldisk]
    r = np.round(np.sqrt((iy - R) ** 2 + (ix - R) ** 2)).astype(np.int32)

    annulus_table = np.full((ldisk, ldisk), num_rings, dtype=np.int32)
    for k in range(num_rings):
        mask = (r > (R - x[k])) & (annulus_table == num_rings)
        annulus_table[mask] = k
    inner = (r <= R) & (annulus_table == num_rings)
    annulus_table[inner] = num_rings - 1

    ring_counts = np.array(
        [int(np.sum(annulus_table == k)) for k in range(num_rings)], dtype=np.float32
    )

    ring_masks = []
    for k in range(num_rings):
        m = (annulus_table == k).astype(np.float32)
        if ring_counts[k] > 0:
            m /= ring_counts[k]
        ring_masks.append(m)

    return annulus_table, ring_counts, num_rings, ring_masks, R


def _annulus_vector(block, annulus_table, num_rings, ring_counts):
    flat = block.ravel().astype(np.float32)
    tbl = annulus_table.ravel()
    valid = tbl < num_rings
    sums = np.bincount(tbl[valid], weights=flat[valid], minlength=num_rings).astype(np.float32)
    P = np.zeros(num_rings, dtype=np.float32)
    nz = ring_counts > 0
    P[nz] = sums[:num_rings][nz] / ring_counts[nz]
    return P


def _divide_template(tmpl_gray, ldisk, annulus_table, num_rings, ring_counts):
    R = ldisk // 2
    h, w = tmpl_gray.shape
    wn = max(1, (w // ldisk) * 2 - 1)
    hn = max(1, (h // ldisk) * 2 - 1)

    centres, vectors = [], []
    for idx in range(wn * hn):
        bx = (idx % wn) * R
        by = (idx // wn) * R
        if by + ldisk > h or bx + ldisk > w:
            continue
        block = tmpl_gray[by:by + ldisk, bx:bx + ldisk]
        P = _annulus_vector(block, annulus_table, num_rings, ring_counts)
        P_ssd = float(np.sum((P - P.mean()) ** 2))
        if P_ssd > 4 * num_rings:
            centres.append((bx + R, by + R))
            vectors.append(P)
    return centres, vectors


def _scene_ring_maps(scene_f32, ring_masks, ldisk):
    """Compute ring-average maps via filter2D. Returns (nrings, vh, vw) float32."""
    h, w = scene_f32.shape
    vh, vw = h - ldisk + 1, w - ldisk + 1
    nrings = len(ring_masks)
    out = np.empty((nrings, vh, vw), dtype=np.float32)
    for k, km in enumerate(ring_masks):
        filt = cv2.filter2D(scene_f32, cv2.CV_32F, km,
                            anchor=(0, 0),
                            borderType=cv2.BORDER_CONSTANT)
        out[k] = filt[:vh, :vw]
    return out


def _precompute_scene(scene_gray, max_px=500):
    """Downsample scene and prepare cache dict for reuse across templates."""
    sh, sw = scene_gray.shape
    longest = max(sh, sw)
    ds = longest / max_px if longest > max_px else 1.0
    if ds > 1.0:
        small = cv2.resize(scene_gray, (int(sw / ds), int(sh / ds)),
                           interpolation=cv2.INTER_AREA)
    else:
        ds = 1.0
        small = scene_gray
    return {
        "scene_f32": small.astype(np.float32),
        "shape": small.shape,
        "ds": ds,
        "_rmaps": {},
    }


def _get_cached_rmaps(cache, rmasks, ld):
    """Retrieve or compute ring maps from cache (keyed by ldisk)."""
    if ld not in cache["_rmaps"]:
        cache["_rmaps"][ld] = _scene_ring_maps(cache["scene_f32"], rmasks, ld)
    return cache["_rmaps"][ld]


# ── public API ───────────────────────────────────────────────────────────────

def match_amns(scene_gray, template_gray,
               ldisk=None,
               num_candidates=3,
               ps_mode=0.5,
               mns_threshold=2,
               scales=None,
               downsample=None,
               _scene_cache=None):
    """
    A-MNS template matching  — fast version.

    Parameters
    ----------
    scene_gray     : uint8 grayscale scene
    template_gray  : uint8 grayscale template
    ldisk          : block size (auto if None)
    num_candidates : candidates kept per block (default 3)
    ps_mode        : neighbour distance multiplier
    mns_threshold  : min neighbour count
    scales         : list[float]  (default [0.8, 1.0, 1.2])
    downsample     : scene downsample factor (auto if None)
    _scene_cache   : precomputed scene dict from _precompute_scene (internal)

    Returns
    -------
    list[dict] sorted best→worst
    """
    if scales is None:
        scales = [0.8, 1.0, 1.2]

    sh, sw = scene_gray.shape

    if _scene_cache is not None:
        scene_f32 = _scene_cache["scene_f32"]
        ds = _scene_cache["ds"]
        ssh, ssw = _scene_cache["shape"]
    else:
        # auto downsample: keep working resolution ≤ 600 px on longest side
        if downsample is None:
            longest = max(sh, sw)
            if longest > 600:
                downsample = longest / 600.0
            else:
                downsample = 1.0

        if downsample > 1.0:
            ds = downsample
            scene_small = cv2.resize(scene_gray, (int(sw / ds), int(sh / ds)),
                                     interpolation=cv2.INTER_AREA)
        else:
            ds = 1.0
            scene_small = scene_gray

        scene_f32 = scene_small.astype(np.float32)
        ssh, ssw = scene_f32.shape[:2]

    results = []

    for scale in scales:
        # scale template, also apply downsample factor
        eff_scale = scale / ds
        if eff_scale != 1.0:
            tmpl = cv2.resize(template_gray, None,
                              fx=eff_scale, fy=eff_scale,
                              interpolation=cv2.INTER_LINEAR)
        else:
            tmpl = template_gray

        th, tw = tmpl.shape
        if th > ssh or tw > ssw or th < 8 or tw < 8:
            continue

        # block size
        if ldisk is None:
            ld = max(8, int(math.sqrt(th * tw / 25)))
            ld += ld % 2
        else:
            ld = max(4, int(ldisk / ds))
            ld += ld % 2
        ld = min(ld, min(th, tw))
        if ld < 4:
            continue

        R = ld // 2

        ann_tbl, rcnt, nrings, rmasks, _ = _build_tables(ld)

        centres, vectors = _divide_template(tmpl, ld, ann_tbl, nrings, rcnt)
        nb = len(centres)
        if nb == 0:
            continue

        # ring maps on downsampled scene (cached when _scene_cache provided)
        if _scene_cache is not None:
            rmaps = _get_cached_rmaps(_scene_cache, rmasks, ld)
        else:
            rmaps = _scene_ring_maps(scene_f32, rmasks, ld)
        vh, vw = rmaps.shape[1], rmaps.shape[2]

        # SSD via BLAS matmul — avoids huge (nb, nrings, vh, vw) tensor
        P_arr = np.array(vectors, dtype=np.float32)  # (nb, nrings)
        rmaps_flat = rmaps.reshape(nrings, -1)         # (nrings, vh*vw)
        P_sq = np.sum(P_arr * P_arr, axis=1, keepdims=True)  # (nb, 1)
        rmap_sq = np.sum(rmaps_flat * rmaps_flat, axis=0, keepdims=True)  # (1, vh*vw)
        cross = P_arr @ rmaps_flat                     # (nb, vh*vw)  — BLAS
        ssd_all = (P_sq - 2.0 * cross + rmap_sq).reshape(nb, vh, vw)

        # mask flat regions
        vmean = rmaps_flat.mean(axis=0)
        vvar = np.sum((rmaps_flat - vmean[None, :]) ** 2, axis=0)
        flat_mask = (vvar < 4.0 * nrings).reshape(vh, vw)
        ssd_all[:, flat_mask] = 1e18

        # extract candidates per block
        all_cands = []
        for bi in range(nb):
            ssd = ssd_all[bi].copy()
            cands = []
            for _ in range(num_candidates):
                idx = int(np.argmin(ssd))
                my, mx = divmod(idx, vw)
                if ssd[my, mx] >= 1e18:
                    break
                cands.append((mx + R, my + R))
                # suppress neighbourhood
                y1 = max(0, my - R)
                y2 = min(vh, my + R + 1)
                x1 = max(0, mx - R)
                x2 = min(vw, mx + R + 1)
                ssd[y1:y2, x1:x2] = 1e18
            all_cands.append(cands)

        if not any(all_cands):
            continue

        # MNS — vectorised
        thresh_dist = ps_mode * R

        # pre-compute expected distances
        c_arr = np.array(centres, dtype=np.float32)
        exp_dist = np.sqrt(np.sum((c_arr[:, None, :] - c_arr[None, :, :]) ** 2, axis=2))

        # build padded candidate array (nb, max_c, 2) + validity mask
        max_c = max(len(c) for c in all_cands)
        cand_xy = np.full((nb, max_c, 2), np.inf, dtype=np.float32)
        cand_ok = np.zeros((nb, max_c), dtype=bool)
        for bi in range(nb):
            for ci, (cx, cy) in enumerate(all_cands[bi]):
                cand_xy[bi, ci] = (cx, cy)
                cand_ok[bi, ci] = True

        # pairwise squared distances: (nb, max_c, nb, max_c)
        dx = cand_xy[:, :, None, None, 0] - cand_xy[None, None, :, :, 0]
        dy = cand_xy[:, :, None, None, 1] - cand_xy[None, None, :, :, 1]
        adist_sq = dx * dx + dy * dy

        # |actual - expected| < threshold  →  compare squared to avoid sqrt
        ed = exp_dist[:, None, :, None]  # (nb, 1, nb, 1)
        # |sqrt(adist_sq) - ed| < thresh  ⟺  (sqrt(adist_sq) - ed)^2 < thresh^2
        # expand: adist_sq - 2*ed*sqrt(adist_sq) + ed^2 < thresh^2
        # Use: low < sqrt(adist_sq) < high  →  low^2 < adist_sq < high^2
        lo = np.maximum(ed - thresh_dist, 0.0)
        hi = ed + thresh_dist
        ok = (adist_sq >= lo * lo) & (adist_sq <= hi * hi) \
             & cand_ok[None, None, :, :]
        # any match per (bi, ci, bj)?
        any_ok = ok.any(axis=3)                              # (nb, max_c, nb)
        any_ok[np.arange(nb), :, np.arange(nb)] = False     # exclude self
        ncounts = any_ok.sum(axis=2)                         # (nb, max_c)
        ncounts[~cand_ok] = -1

        best_ci = ncounts.argmax(axis=1)
        best_cnt_v = ncounts[np.arange(nb), best_ci]

        best_pts = [None] * nb
        best_cnt = [0] * nb
        for bi in range(nb):
            if best_cnt_v[bi] >= mns_threshold and cand_ok[bi, best_ci[bi]]:
                pt = cand_xy[bi, best_ci[bi]]
                best_pts[bi] = (int(pt[0]), int(pt[1]))
                best_cnt[bi] = int(best_cnt_v[bi])

        valid = [(bi, best_pts[bi], best_cnt[bi])
                 for bi in range(nb) if best_pts[bi] is not None]
        if not valid:
            continue

        # scoring — vectorised
        v_bi = np.array([v[0] for v in valid], dtype=np.intp)
        v_pts = np.array([(v[1][0], v[1][1]) for v in valid], dtype=np.float32)
        vdx = v_pts[:, None, 0] - v_pts[None, :, 0]
        vdy = v_pts[:, None, 1] - v_pts[None, :, 1]
        vdist = np.sqrt(vdx * vdx + vdy * vdy)
        vedist = exp_dist[v_bi[:, None], v_bi[None, :]]
        vmatch = np.abs(vdist - vedist) < thresh_dist
        np.fill_diagonal(vmatch, False)
        vscores = vmatch.sum(axis=1)

        order = np.argsort(-vscores)
        first_bi = int(v_bi[order[0]])
        first_pt = (int(v_pts[order[0], 0]), int(v_pts[order[0], 1]))
        first_sc = int(vscores[order[0]])

        # rotation angle
        angle = 0.0
        if len(order) >= 2:
            second_bi = int(v_bi[order[1]])
            second_pt = (int(v_pts[order[1], 0]), int(v_pts[order[1], 1]))
            ref = math.atan2(-(centres[second_bi][1] - centres[first_bi][1]),
                              centres[second_bi][0] - centres[first_bi][0])
            act = math.atan2(-(second_pt[1] - first_pt[1]),
                              second_pt[0] - first_pt[0])
            angle = math.degrees(act - ref)
            if angle < -180:
                angle += 360
            if angle > 180:
                angle -= 360

        # map coordinates back to original scene resolution
        fp_x = first_pt[0] * ds
        fp_y = first_pt[1] * ds
        tw_orig = tw * ds
        th_orig = th * ds

        cos_a = math.cos(math.radians(angle))
        sin_a = math.sin(math.radians(angle))

        tcx = (tw_orig / 2) - (centres[first_bi][0] * ds)
        tcy = (th_orig / 2) - (centres[first_bi][1] * ds)
        mcx = fp_x + tcx * cos_a + tcy * sin_a
        mcy = fp_y - tcx * sin_a + tcy * cos_a

        corners = []
        for dx, dy in [(-tw_orig / 2, -th_orig / 2), (tw_orig / 2, -th_orig / 2),
                       (tw_orig / 2, th_orig / 2), (-tw_orig / 2, th_orig / 2)]:
            rx = mcx + dx * cos_a + dy * sin_a
            ry = mcy - dx * sin_a + dy * cos_a
            corners.append((int(rx), int(ry)))

        results.append({
            "center": (int(mcx), int(mcy)),
            "angle": round(angle, 2),
            "rect_points": corners,
            "score": first_sc,
            "scale": scale,
            "template_size": (int(tw_orig), int(th_orig)),
            "num_valid_blocks": len(valid),
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def match_amns_multi(scene_gray, template_grays, **kwargs):
    """
    Try multiple template images for one inspection point.
    Precomputes scene data once, caches ring maps across templates.
    Returns the best match (highest neighbours score).

    Parameters
    ----------
    scene_gray     : uint8 grayscale scene
    template_grays : list[ndarray]  — multiple grayscale templates for same point
    **kwargs       : forwarded to match_amns (ps_mode, mns_threshold, etc.)
                     defaults overridden for speed: scales=[1.0], num_candidates=5

    Returns
    -------
    list[dict] — best result from whichever template scored highest
    """
    # speed defaults — single scale, fewer candidates
    kwargs.setdefault("scales", [1.0])
    kwargs.setdefault("num_candidates", 5)

    # precompute scene once (downsample + f32)
    cache = _precompute_scene(scene_gray, max_px=500)
    kwargs["_scene_cache"] = cache

    best_hits = []
    best_score = -1
    for tmpl_gray in template_grays:
        hits = match_amns(scene_gray, tmpl_gray, **kwargs)
        if hits and hits[0]["score"] > best_score:
            best_score = hits[0]["score"]
            best_hits = hits
    return best_hits


# ── drawing helpers ──────────────────────────────────────────────────────────

def draw_match(scene_bgr, result, color=(0, 255, 0), thickness=2, label=""):
    pts = result["rect_points"]
    for i in range(4):
        cv2.line(scene_bgr, pts[i], pts[(i + 1) % 4], color, thickness)
    if label:
        org = (pts[0][0], pts[0][1] - 6)
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(scene_bgr,
                      (org[0], org[1] - lh - 4),
                      (org[0] + lw + 6, org[1] + 4), color, -1)
        cv2.putText(scene_bgr, label,
                    (org[0] + 3, org[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    return scene_bgr


def crop_match_region(scene_bgr, result):
    pts = np.array(result["rect_points"])
    x1 = max(0, int(pts[:, 0].min()))
    y1 = max(0, int(pts[:, 1].min()))
    x2 = min(scene_bgr.shape[1], int(pts[:, 0].max()))
    y2 = min(scene_bgr.shape[0], int(pts[:, 1].max()))
    if x2 <= x1 or y2 <= y1:
        return None
    return scene_bgr[y1:y2, x1:x2].copy()
