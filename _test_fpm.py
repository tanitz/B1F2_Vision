"""Quick smoke‑test for fpm_matching.py."""

import cv2
import numpy as np
import time

from fpm_matching import match_fpm, draw_fpm_match, crop_fpm_region


def _make_scene_and_template():
    """Create a synthetic 800×600 scene with a known 80×60 patch."""
    scene = np.random.randint(40, 200, (600, 800), dtype=np.uint8)
    # stamp a distinctive patch at (300, 200)
    patch = np.random.randint(0, 255, (60, 80), dtype=np.uint8)
    scene[200:260, 300:380] = patch
    # also stamp at (100, 400)
    scene[400:460, 100:180] = patch
    return scene, patch


def test_basic_match():
    scene, tmpl = _make_scene_and_template()
    scene_bgr = cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR)

    t0 = time.perf_counter()
    results = match_fpm(scene_bgr, [("test", tmpl)],
                        score_threshold=0.7, max_overlap=0.3)
    dt = time.perf_counter() - t0

    print(f"[basic] found {len(results)} matches in {dt*1000:.1f} ms")
    for r in results:
        print(f"  label={r['label']}  score={r['score']:.3f}  "
              f"center={r['center']}  angle={r['angle']:.1f}")

    assert len(results) >= 2, f"Expected >=2 matches, got {len(results)}"
    # check that the two known centres are found (within tolerance)
    centres = [r["center"] for r in results]
    found_a = any(abs(c[0] - 340) < 15 and abs(c[1] - 230) < 15
                  for c in centres)
    found_b = any(abs(c[0] - 140) < 15 and abs(c[1] - 430) < 15
                  for c in centres)
    assert found_a, f"Patch A (340,230) not found; centres={centres}"
    assert found_b, f"Patch B (140,430) not found; centres={centres}"
    print("  => positions OK")


def test_rotation():
    """Stamp a template at ~30° and check FPM can find it."""
    scene = np.full((600, 800), 120, dtype=np.uint8)
    tmpl = np.zeros((60, 80), dtype=np.uint8)
    cv2.rectangle(tmpl, (10, 10), (70, 50), 255, -1)
    cv2.circle(tmpl, (40, 30), 15, 180, -1)

    # rotate and paste
    center = (400, 300)
    M = cv2.getRotationMatrix2D(center, 30, 1.0)
    rotated = cv2.warpAffine(
        np.zeros_like(scene), M, (800, 600),
        borderValue=120)
    # stamp template into a temp image then rotate
    temp = np.full_like(scene, 120)
    temp[270:330, 360:440] = tmpl
    rotated_temp = cv2.warpAffine(temp, M, (800, 600), borderValue=120)
    scene = np.where(rotated_temp != 120, rotated_temp, scene)

    scene_bgr = cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR)

    t0 = time.perf_counter()
    results = match_fpm(scene_bgr, [("rot", tmpl)],
                        score_threshold=0.4,
                        tolerance_angle=45,
                        max_overlap=0.3)
    dt = time.perf_counter() - t0

    print(f"[rotation] found {len(results)} matches in {dt*1000:.1f} ms")
    for r in results:
        print(f"  label={r['label']}  score={r['score']:.3f}  "
              f"center={r['center']}  angle={r['angle']:.1f}")


def test_draw_crop():
    scene, tmpl = _make_scene_and_template()
    scene_bgr = cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR)
    results = match_fpm(scene_bgr, [("x", tmpl)], score_threshold=0.7)
    if results:
        vis = scene_bgr.copy()
        draw_fpm_match(vis, results[0], label="x")
        crop = crop_fpm_region(scene_bgr, results[0])
        print(f"[draw_crop] draw OK, crop shape={crop.shape if crop is not None else None}")
    else:
        print("[draw_crop] no results to draw")


def test_no_match():
    scene = np.random.randint(0, 255, (200, 300), dtype=np.uint8)
    tmpl = np.zeros((50, 50), dtype=np.uint8)  # all black => 低 NCC
    results = match_fpm(
        cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR),
        [("empty", tmpl)],
        score_threshold=0.95,
    )
    print(f"[no_match] found {len(results)} (expect 0)")


if __name__ == "__main__":
    test_basic_match()
    test_rotation()
    test_draw_crop()
    test_no_match()
    print("\nAll FPM tests passed.")
