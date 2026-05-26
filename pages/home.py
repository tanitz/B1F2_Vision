"""
Home Page - Dashboard with camera views
"""
import base64
import csv
import json
import os
import random
import threading
import time
from datetime import datetime
import flet as ft
import cv2
import numpy as np
from config import theme
from fpm_matching import match_fpm, draw_fpm_match, crop_fpm_region
import camera_manager as _cam_mod

# Template image cache — avoid disk reads on every trigger
_tmpl_cache: dict = {}  # (abs_path, scale_key) → np.ndarray BGR


def _load_tmpl(path: str, scale: float):
    key = (path, round(scale, 4))
    if key not in _tmpl_cache:
        t = cv2.imread(path)
        if t is not None and scale < 1.0:
            t = cv2.resize(t,
                           (max(1, int(t.shape[1] * scale)),
                            max(1, int(t.shape[0] * scale))),
                           interpolation=cv2.INTER_AREA)
        _tmpl_cache[key] = t
    return _tmpl_cache.get(key)


# Shared state broadcast to all open sessions
_broadcast: dict = {
    "img_src": None,             # full data URI of result image
    "img_w": 0, "img_h": 0,
    "overall": None,
    "ok": 0, "ng": 0, "total": 0,
    "cards": [],                 # list of {insp_id, sc, crop_b64, is_pass}
}


def _put_label(img, text, x, y, bg=(0, 0, 0), fg=(255, 255, 255), scale=0.85, thick=2):
    (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    cv2.rectangle(img, (x - 2, y - th - 4), (x + tw + 4, y + bl + 2), bg, -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, fg, thick, cv2.LINE_AA)


def _draw_ng_banner(img, ng_items):
    """Draw NG summary at top-right using PIL (Thai support). Only converts the banner region."""
    if not ng_items:
        return
    try:
        from PIL import Image as _PILImage, ImageDraw as _PILDraw, ImageFont as _PILFont
    except ImportError:
        return

    font_size = 80
    _font_candidates = [
        r"C:\Windows\Fonts\THSarabunNew.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\Tahoma.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
    ]
    pil_font = None
    for fp in _font_candidates:
        if os.path.isfile(fp):
            try:
                pil_font = _PILFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if pil_font is None:
        pil_font = _PILFont.load_default()

    lines = [f"{n}: {d}" if d else n for n, d in ng_items]

    _dummy_draw = _PILDraw.Draw(_PILImage.new("RGB", (1, 1)))
    bboxes  = [_dummy_draw.textbbox((0, 0), l, font=pil_font) for l in lines]
    widths  = [b[2] - b[0] for b in bboxes]
    heights = [b[3] - b[1] for b in bboxes]

    pad    = 20
    line_h = max(heights) + 14
    box_w  = max(widths)  + pad * 2
    box_h  = len(lines) * line_h + pad

    img_h, img_w = img.shape[:2]
    x0, y0 = max(img_w - box_w - 10, 0), 10
    x1, y1 = min(x0 + box_w, img_w - 1), min(y0 + box_h, img_h - 1)
    bw, bh = x1 - x0, y1 - y0

    # Render text on a small PIL image (banner size only — fast)
    banner = _PILImage.new("RGB", (bw, bh), (20, 20, 20))
    draw   = _PILDraw.Draw(banner)
    for i, line in enumerate(lines):
        tx = pad
        ty = pad // 2 + i * line_h
        draw.text((tx + 2, ty + 2), line, font=pil_font, fill=(0, 0, 0))       # shadow
        draw.text((tx,     ty    ), line, font=pil_font, fill=(255, 255, 255))  # white
    banner_bgr = cv2.cvtColor(np.array(banner), cv2.COLOR_RGB2BGR)

    # Blend banner onto image region (no full-image copy)
    roi = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = cv2.addWeighted(banner_bgr, 0.85, roi, 0.15, 0)
    cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 200), 2)
    cv2.line(img, (x0, y0), (x0, y1), (0, 0, 230), 6)

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR   = os.path.join(BASE_DIR, "model")
TRIGGER_DIR = os.path.join(BASE_DIR, "image", "B1F2", "image_set1")
IMG_EXTS    = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def _today_csv_path():
    results_dir = os.path.join(BASE_DIR, "results")
    return os.path.join(results_dir, datetime.now().strftime("%Y-%m-%d") + ".csv")


def _load_today_counts():
    path = _today_csv_path()
    if not os.path.isfile(path):
        return {"ok": 0, "ng": 0, "total": 0}
    seen = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rid = row.get("result_image_id", "")
                if rid and rid not in seen:
                    seen[rid] = row.get("overall_result", "")
    except Exception:
        return {"ok": 0, "ng": 0, "total": 0}
    ok    = sum(1 for v in seen.values() if v == "PASS")
    ng    = sum(1 for v in seen.values() if v == "FAIL")
    total = len(seen)
    return {"ok": ok, "ng": ng, "total": total}


def _get_models():
    if not os.path.isdir(MODEL_DIR):
        return []
    return sorted([d for d in os.listdir(MODEL_DIR)
                   if os.path.isdir(os.path.join(MODEL_DIR, d))])


def _get_trigger_files():
    if not os.path.isdir(TRIGGER_DIR):
        return []
    return sorted([
        os.path.join(TRIGGER_DIR, f)
        for f in os.listdir(TRIGGER_DIR)
        if os.path.splitext(f)[1].lower() in IMG_EXTS
    ])


def create_home_page(page=None):
    """สร้างหน้า Home"""

    # ── State ──────────────────────────────────────────────────────────────
    is_running    = {"value": False}
    trigger_state = {"files": [], "index": -1}
    grab_state    = {"running": False}
    last_frame    = {"img": None, "stem": None}  # most recent frame from running loop

    # ── OK/NG indicator ────────────────────────────────────────────────────
    ok_ng_label = ft.Text("OK/NG", size=20, weight=ft.FontWeight.BOLD, color="#ffffff")
    ok_ng_box = ft.Container(
        content=ok_ng_label,
        border_radius=6,
        padding=ft.Padding.symmetric(horizontal=20, vertical=12),
        bgcolor="#888888",
        alignment=ft.Alignment(0, 0),
    )

    # ── Result list ────────────────────────────────────────────────────────
    result_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

    # ── Counter + clock ────────────────────────────────────────────────────
    count_state  = _load_today_counts()
    clock_thread = {"started": False}

    stat_ok_val    = ft.Text(str(count_state["ok"]),    size=35, weight=ft.FontWeight.BOLD, color="#4caf50")
    stat_ng_val    = ft.Text(str(count_state["ng"]),    size=35, weight=ft.FontWeight.BOLD, color="#f44336")
    stat_total_val = ft.Text(str(count_state["total"]), size=35, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY)
    clock_text     = ft.Text(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"), size=12, color=theme.TEXT_SECONDARY)

    def _stat_col(label, val_widget, color):
        return ft.Column(
            [ft.Text(label, size=15, weight=ft.FontWeight.BOLD, color=color), val_widget],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

    stats_row = ft.Row(
        [
            _stat_col("OK",    stat_ok_val,    "#4caf50"),
            ft.VerticalDivider(width=2, color="#dddddd", thickness=1),
            _stat_col("NG",    stat_ng_val,    "#f44336"),
            ft.VerticalDivider(width=2, color="#dddddd", thickness=1),
            _stat_col("TOTAL", stat_total_val, theme.TEXT_PRIMARY),
        ],
        spacing=20,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
    )

    def _start_clock(pg):
        if clock_thread["started"]:
            return
        clock_thread["started"] = True
        _current_date = {"value": datetime.now().date()}
        def _loop():
            while True:
                now = datetime.now()
                clock_text.value = now.strftime("%Y-%m-%d  %H:%M:%S")
                if now.date() != _current_date["value"]:
                    _current_date["value"] = now.date()
                    new_counts = _load_today_counts()
                    count_state["ok"]    = new_counts["ok"]
                    count_state["ng"]    = new_counts["ng"]
                    count_state["total"] = new_counts["total"]
                    stat_ok_val.value    = str(count_state["ok"])
                    stat_ng_val.value    = str(count_state["ng"])
                    stat_total_val.value = str(count_state["total"])
                try:
                    pg.update()
                except Exception:
                    pass
                time.sleep(1)
        threading.Thread(target=_loop, daemon=True).start()

    if page is not None:
        _start_clock(page)

    # ── Processing time label ──────────────────────────────────────────────
    time_label = ft.Container(
        content=ft.Text("Process: NA", size=12, color=theme.TEXT_SECONDARY),
        width=130,
    )

    # ── Model dropdown ─────────────────────────────────────────────────────
    models = _get_models()
    model_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option(m) for m in models],
        value=models[0] if models else None,
        hint_text="No model" if not models else None,
        width=180,
        text_size=13,
        content_padding=ft.Padding.only(left=10, right=0, top=4, bottom=4),
        border_color="#cccccc",
        border_radius=4,
    )

    # ── RAW image display ─────────────────────────────────────────────────
    _disp = {"h": max(500, int((page.height or 1080) * 0.75)) if page else 684}

    raw_image = ft.Image(src="placeholder.png", visible=False, fit="contain", expand=True)
    filename_label = ft.Text("", size=11, color=theme.TEXT_SECONDARY, italic=True)

    raw_img_cont = ft.Container(
        content=ft.Stack([raw_image]),
        expand=True,
        alignment=ft.Alignment(0, 0),
        bgcolor="#f5f5f5",
        border_radius=4,
        border=ft.Border.all(1, "#cccccc"),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    raw_panel = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=raw_img_cont,
                    expand=True,
                    alignment=ft.Alignment(0, 0),
                ),
            ],
            spacing=6,
            expand=True,
        ),
        expand=7,
        padding=ft.Padding.all(8),
    )

    # ── RESULT panel ───────────────────────────────────────────────────────
    result_panel = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=stats_row,
                    alignment=ft.Alignment(0, 0),
                    expand=False,
                ),
                ok_ng_box,
                ft.Divider(color="#dddddd", height=1, thickness=1),
                result_list,
            ],
            spacing=8,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=3,
        padding=ft.Padding.all(8),
        border=ft.Border.only(left=ft.BorderSide(1, "#cccccc")),
    )

    # ── Camera status indicator ────────────────────────────────────────────
    cam_dot   = ft.Container(width=12, height=12, border_radius=6, bgcolor="#888888")
    cam_label = ft.Text("Camera Off", size=12, color=theme.TEXT_SECONDARY)

    # ── Start / Stop button ────────────────────────────────────────────────
    # Use ft.Text as content so value changes are reliably detected by Flet diff
    _start_label = ft.Text("Start", color="#ffffff", size=13, weight=ft.FontWeight.W_500)
    start_btn = ft.Button(
        content=_start_label,
        width=120,
        height=40,
        style=ft.ButtonStyle(
            bgcolor={"": "#2196f3"},
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )

    # ── Trigger button ─────────────────────────────────────────────────────
    trigger_btn = ft.Button(
        "Trigger",
        width=120,
        height=40,
        style=ft.ButtonStyle(
            bgcolor={"": "#f57c00"},
            color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )

    # ── Shared inspection function ─────────────────────────────────────────
    def _inspect(img_cv, img_stem, pg):
        t_start = time.perf_counter()
        print(f"[Home] _inspect: START stem={img_stem} img_shape={img_cv.shape if img_cv is not None else None}")

        selected_model = model_dropdown.value
        if not selected_model:
            print("[Home] _inspect: no model selected — abort")
            return
        json_path = os.path.join(MODEL_DIR, selected_model, f"{selected_model}.json")
        if not os.path.isfile(json_path):
            print(f"[Home] _inspect: json not found: {json_path} — abort")
            return

        # Load template JSON
        with open(json_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        model_base = os.path.join(MODEL_DIR, selected_model)

        img_h, img_w = img_cv.shape[:2]
        match_scale = min(800 / max(img_w, img_h), 1.0)
        scene_match = (cv2.resize(img_cv,
                                  (int(img_w * match_scale), int(img_h * match_scale)),
                                  interpolation=cv2.INTER_AREA)
                       if match_scale < 1.0 else img_cv)
        inv = 1.0 / match_scale if match_scale > 0 else 1.0

        result_img   = img_cv.copy()
        insp_results = []
        ng_summary   = []  # collect (name, description) for every NG inspection

        for insp in template.get("inspections", []):
            img_paths_rel = insp.get("image_paths", [])
            if not img_paths_rel:
                single = insp.get("image_path", "")
                if single:
                    img_paths_rel = [single]
            insp_id   = insp.get("name", "?")
            insp_desc = insp.get("description", "")

            fpm_tmpls = []
            for rel in img_paths_rel:
                p = os.path.join(model_base, rel)
                if not os.path.isfile(p):
                    continue
                t = _load_tmpl(p, match_scale)
                if t is not None:
                    fpm_tmpls.append((insp_id, t))
            if not fpm_tmpls:
                insp_results.append((insp_id, None, None, False))
                continue

            sroi = insp.get("search_roi", [])
            if sroi and len(sroi) == 4:
                sm_h, sm_w = scene_match.shape[:2]
                rx = max(0, min(int(sroi[0] * match_scale), sm_w - 1))
                ry = max(0, min(int(sroi[1] * match_scale), sm_h - 1))
                rw = min(int(sroi[2] * match_scale), sm_w - rx)
                rh = min(int(sroi[3] * match_scale), sm_h - ry)
                has_roi = rw > 1 and rh > 1
                roi_scene = scene_match[ry:ry+rh, rx:rx+rw] if has_roi else scene_match
            else:
                roi_scene = scene_match
                rx, ry, rw, rh = 0, 0, 0, 0
                has_roi = False

            hits = match_fpm(roi_scene, fpm_tmpls, score_threshold=0.50,
                             max_overlap=0.3, tolerance_angle=0)

            frx = int(rx * inv); fry = int(ry * inv)
            frw = int(rw * inv); frh = int(rh * inv)

            ok_best_f = None
            ok_score  = None
            if hits:
                best_ok = max(hits, key=lambda h: h["score"])
                if has_roi:
                    adj = dict(best_ok)
                    adj["rect_points"] = [(pt[0]+rx, pt[1]+ry) for pt in best_ok["rect_points"]]
                    adj["center"] = (best_ok["center"][0]+rx, best_ok["center"][1]+ry)
                    bx, by, bw_b, bh_b = best_ok["bbox"]
                    adj["bbox"] = (bx+rx, by+ry, bw_b, bh_b)
                    best_ok = adj
                ok_best_f = dict(best_ok)
                ok_best_f["rect_points"] = [(int(p[0]*inv), int(p[1]*inv)) for p in best_ok["rect_points"]]
                ok_best_f["center"] = (int(best_ok["center"][0]*inv), int(best_ok["center"][1]*inv))
                bx, by, bw_b, bh_b = best_ok["bbox"]
                ok_best_f["bbox"] = (int(bx*inv), int(by*inv), int(bw_b*inv), int(bh_b*inv))
                ok_score = best_ok["score"]

            ng_paths_rel = insp.get("ng_image_paths", [])
            ng_best_f = None
            ng_score  = None
            if ng_paths_rel:
                ng_tmpls = []
                for rel in ng_paths_rel:
                    p = os.path.join(model_base, rel)
                    if os.path.isfile(p):
                        t = _load_tmpl(p, match_scale)
                        if t is not None:
                            ng_tmpls.append((insp_id, t))
                if ng_tmpls:
                    ng_hits = match_fpm(roi_scene, ng_tmpls, score_threshold=0.50,
                                        max_overlap=0.3, tolerance_angle=0)
                    if ng_hits:
                        best_ng = max(ng_hits, key=lambda h: h["score"])
                        if has_roi:
                            ng_adj = dict(best_ng)
                            ng_adj["rect_points"] = [(pt[0]+rx, pt[1]+ry) for pt in best_ng["rect_points"]]
                            ng_adj["center"] = (best_ng["center"][0]+rx, best_ng["center"][1]+ry)
                            bx, by, bw_b, bh_b = best_ng["bbox"]
                            ng_adj["bbox"] = (bx+rx, by+ry, bw_b, bh_b)
                            best_ng = ng_adj
                        ng_best_f = dict(best_ng)
                        ng_best_f["rect_points"] = [(int(p[0]*inv), int(p[1]*inv)) for p in best_ng["rect_points"]]
                        ng_best_f["center"] = (int(best_ng["center"][0]*inv), int(best_ng["center"][1]*inv))
                        bx, by, bw_b, bh_b = best_ng["bbox"]
                        ng_best_f["bbox"] = (int(bx*inv), int(by*inv), int(bw_b*inv), int(bh_b*inv))
                        ng_score = best_ng["score"]

            if ok_score is None and ng_score is None:
                ng_summary.append((insp_id, insp_desc))
                if has_roi:
                    overlay = result_img.copy()
                    cv2.rectangle(overlay, (frx, fry), (frx+frw, fry+frh), (100, 100, 220), -1)
                    cv2.addWeighted(overlay, 0.25, result_img, 0.75, 0, result_img)
                    cv2.rectangle(result_img, (frx, fry), (frx+frw, fry+frh), (0, 0, 220), 2)
                    _put_label(result_img, f"{insp_id} NG", frx, max(fry - 8, 18), bg=(0, 0, 160))
                insp_results.append((insp_id, None, None, False))
            elif ok_score is not None and (ng_score is None or ok_score >= ng_score):
                crop_cv = crop_fpm_region(img_cv, ok_best_f)
                if has_roi:
                    overlay = result_img.copy()
                    cx, cy = ok_best_f["center"]
                    drx, dry = cx - frw // 2, cy - frh // 2
                    cv2.rectangle(overlay, (drx, dry), (drx+frw, dry+frh), (144, 238, 144), -1)
                    cv2.addWeighted(overlay, 0.30, result_img, 0.70, 0, result_img)
                    cv2.rectangle(result_img, (drx, dry), (drx+frw, dry+frh), (0, 200, 0), 2)
                    _put_label(result_img, insp_id, drx, max(dry - 8, 18), bg=(0, 120, 0))
                else:
                    draw_fpm_match(result_img, ok_best_f, label=insp_id)
                insp_results.append((insp_id, ok_score, crop_cv, True))
            else:
                ng_summary.append((insp_id, insp_desc))
                crop_cv = crop_fpm_region(img_cv, ng_best_f)
                if has_roi:
                    overlay = result_img.copy()
                    cv2.rectangle(overlay, (frx, fry), (frx+frw, fry+frh), (100, 100, 220), -1)
                    cv2.addWeighted(overlay, 0.25, result_img, 0.75, 0, result_img)
                    cv2.rectangle(result_img, (frx, fry), (frx+frw, fry+frh), (0, 0, 220), 2)
                    _put_label(result_img, f"{insp_id} NG", frx, max(fry - 8, 18), bg=(0, 0, 160))
                insp_results.append((insp_id, ng_score, crop_cv, False))

        _draw_ng_banner(result_img, ng_summary)

        # ── Prepare display data in thread (CPU-bound) ─────────────────────
        h, w = result_img.shape[:2]
        disp_scale = min(_disp["h"] / h, 1.0)
        dw, dh = int(w * disp_scale), int(h * disp_scale)
        result_disp = cv2.resize(result_img, (dw, dh), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode(".jpg", result_disp, [cv2.IMWRITE_JPEG_QUALITY, 80])
        img_bytes = bytes(buf)

        n_pass  = sum(1 for *_, p in insp_results if p)
        overall = "PASS" if n_pass == len(insp_results) and len(insp_results) > 0 else "FAIL"

        elapsed_ms = (time.perf_counter() - t_start) * 1000

        prepared = []
        for insp_id, sc, crop_cv, is_pass in insp_results:
            if crop_cv is not None:
                ch, cw = crop_cv.shape[:2]
                cscale = min(182 / cw, 117 / ch, 1.0)
                thumb = cv2.resize(crop_cv, (int(cw*cscale), int(ch*cscale)), interpolation=cv2.INTER_AREA)
                _, cbuf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 72])
                prepared.append((insp_id, bytes(cbuf), is_pass))
            else:
                prepared.append((insp_id, None, is_pass))

        # ── Save to CSV + disk in background ──────────────────────────────────
        _save_ts      = datetime.now()
        _save_stem    = img_stem
        _save_model   = selected_model
        _save_results = list(insp_results)
        _save_overall = overall
        _save_disp    = result_disp.copy()

        def _bg_save():
            try:
                ts            = _save_ts.strftime("%Y-%m-%d %H:%M:%S")
                result_img_id = f"{_save_ts.strftime('%Y%m%d_%H%M%S')}_{_save_stem}"
                results_dir     = os.path.join(BASE_DIR, "results")
                results_img_dir = os.path.join(results_dir, "images")
                os.makedirs(results_img_dir, exist_ok=True)
                cv2.imwrite(os.path.join(results_img_dir, f"{result_img_id}.jpg"), _save_disp)
                csv_path    = _today_csv_path()
                file_exists = os.path.isfile(csv_path)
                with open(csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow([
                            "timestamp", "model", "inspection_name",
                            "result", "score", "overall_result", "result_image_id",
                        ])
                    for insp_id, sc, _, is_pass in _save_results:
                        result_str = "PASS" if is_pass else ("FAIL" if sc is not None else "NO_MATCH")
                        score_str  = f"{sc:.4f}" if sc is not None else ""
                        writer.writerow([
                            ts, _save_model, insp_id,
                            result_str, score_str, _save_overall, result_img_id,
                        ])
            except Exception:
                import traceback
                traceback.print_exc()

        threading.Thread(target=_bg_save, daemon=True).start()

        # ── Pre-encode broadcast cards (still in thread) ───────────────────
        bcast_cards = []
        for insp_id, sc, crop_cv, is_pass in insp_results:
            crop_b64 = None
            if crop_cv is not None:
                ch, cw = crop_cv.shape[:2]
                cscale = min(182 / cw, 117 / ch, 1.0)
                thumb  = cv2.resize(crop_cv, (int(cw*cscale), int(ch*cscale)),
                                    interpolation=cv2.INTER_AREA)
                _, cbuf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 72])
                crop_b64 = base64.b64encode(cbuf).decode()
            bcast_cards.append({"insp_id": insp_id, "sc": sc, "crop_b64": crop_b64, "is_pass": is_pass})

        # ── Push to UI via async task (flushes WebSocket immediately) ─────
        _inspect_done = threading.Event()
        _result       = {"overall": None}

        async def _push(ib=img_bytes, dw_=dw, dh_=dh, ovr=overall,
                        prep=prepared, bc=bcast_cards, el=elapsed_ms):
            data_uri = f"data:image/jpeg;base64,{base64.b64encode(ib).decode()}"
            raw_image.src    = data_uri
            raw_image.width  = int(dw_ * 1.6)
            raw_image.height = int(dh_ * 1.6)
            raw_img_cont.width = None  # expand to fill panel; image centered by alignment
            raw_image.visible = True
            filename_label.value = img_stem

            ok_ng_label.value = "OK" if ovr == "PASS" else "NG"
            ok_ng_box.bgcolor = theme.ACCENT_GREEN if ovr == "PASS" else theme.ACCENT_RED

            if ovr == "PASS":
                count_state["ok"] += 1
            else:
                count_state["ng"] += 1
            count_state["total"] += 1
            stat_ok_val.value    = str(count_state["ok"])
            stat_ng_val.value    = str(count_state["ng"])
            stat_total_val.value = str(count_state["total"])

            time_label.content.value = f"Process: {el:.0f} ms"
            pg.update()

            cards = []
            for insp_id, thumb_b, is_pass in prep:
                if thumb_b is not None:
                    img_widget = ft.Image(
                        src=f"data:image/jpeg;base64,{base64.b64encode(thumb_b).decode()}",
                        width=182, height=117, fit="contain",
                    )
                else:
                    img_widget = ft.Container(
                        width=182, height=117, bgcolor="#f44336",
                        alignment=ft.Alignment(0, 0),
                        content=ft.Text("NG", size=20, weight=ft.FontWeight.BOLD, color="#ffffff"),
                    )
                bc_ = "#4caf50" if is_pass else "#f44336"
                bg_ = "#e8f5e9" if is_pass else "#ffebee"
                tc_ = "#2e7d32" if is_pass else "#c62828"
                cards.append(ft.Container(
                    content=ft.Column([
                        img_widget,
                        ft.Text(insp_id if is_pass else f"{insp_id}  NG",
                                size=9, weight=ft.FontWeight.BOLD, color=tc_),
                    ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=4, bgcolor=bg_,
                    border=ft.Border.all(2, bc_), border_radius=4, expand=True,
                ))
            result_list.controls.clear()
            for i in range(0, len(cards), 2):
                result_list.controls.append(ft.Row(cards[i:i+2], spacing=4, expand=False))

            # Broadcast result to all open sessions
            _broadcast["img_src"] = data_uri
            _broadcast["img_w"]   = dw_
            _broadcast["img_h"]   = dh_
            _broadcast["overall"] = ovr
            _broadcast["ok"]      = count_state["ok"]
            _broadcast["ng"]      = count_state["ng"]
            _broadcast["total"]   = count_state["total"]
            _broadcast["cards"]   = bc

            pg.pubsub.send_all_on_topic("home_update", id(pg))
            pg.pubsub.send_all_on_topic("report_update", None)
            pg.update()
            _result["overall"] = ovr
            _inspect_done.set()

        pg.run_task(_push)
        _inspect_done.wait(timeout=10.0)
        return _result.get("overall")

    # ── Y1 / Y2 Modbus output helpers ─────────────────────────────────────
    def _write_y1(val: bool):
        fn = getattr(page, "_mb_write_y1", None)
        if callable(fn):
            fn(val)

    def _write_y2(val: bool):
        fn = getattr(page, "_mb_write_y2", None)
        if callable(fn):
            fn(val)

    # ── Camera grab loop ───────────────────────────────────────────────────
    def _start_camera_loop(pg):
        _hik = _cam_mod.get_camera()

        def _stop_loop():
            """Reset UI state after camera loop ends."""
            grab_state["running"]   = False
            is_running["value"]     = False
            _set_start_btn(False)
            cam_dot.bgcolor = "#888888"
            cam_label.value = "Camera Off"
            _write_y2(False)
            pg.pubsub.send_all_on_topic("cam_state", False)
            pg.update()

        def _loop():
            # Stop settings live/grab loops so they don't compete for the camera
            stop_preview = getattr(pg, "_stop_cam_preview", None)
            if callable(stop_preview):
                stop_preview()
                time.sleep(0.3)  # give the settings loops time to release the frame lock

            cfg    = _cam_mod.load_config()
            cam_ip = cfg.get("camera_ip", "").strip()
            if not cam_ip:
                cam_dot.bgcolor = "#f44336"
                cam_label.value = "No camera IP configured"
                _stop_loop()
                return

            cam_dot.bgcolor = "#ff9800"
            cam_label.value = f"Connecting {cam_ip}..."
            pg.update()

            ok, msg = _hik.connect_by_ip(cam_ip)
            if not ok:
                cam_dot.bgcolor = "#f44336"
                cam_label.value = f"Error: {msg}"
                _stop_loop()
                return

            pg.pubsub.send_all_on_topic("cam_state", True)

            ok, msg = _hik.start_streaming(preserve_trigger=True)
            if not ok:
                cam_dot.bgcolor = "#f44336"
                cam_label.value = f"Stream error: {msg}"
                _hik.disconnect()
                _stop_loop()
                return

            cam_dot.bgcolor = "#4caf50"
            cam_label.value = f"Connected: {cam_ip}"
            pg.update()

            _write_y2(True)

            while grab_state["running"]:
                frame = _hik.get_frame(timeout_ms=5000)  # must exceed TriggerDelay (2s)
                if frame is None:
                    continue
                if not grab_state["running"]:
                    break
                stem = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
                last_frame["img"]  = frame
                last_frame["stem"] = stem
                if model_dropdown.value:
                    overall = _inspect(frame, stem, pg)
                    if overall == "PASS" and grab_state["running"]:
                        _write_y2(False)
                        time.sleep(2.0)
                        if grab_state["running"]:
                            _write_y2(True)
                    elif overall == "FAIL" and grab_state["running"]:
                        _write_y1(True)
                        time.sleep(1.0)
                        _write_y1(False)

            _hik.stop_streaming()
            _hik.disconnect()
            _stop_loop()

        threading.Thread(target=_loop, daemon=True).start()

    # ── Toggle Start/Stop ──────────────────────────────────────────────────
    def _set_start_btn(running: bool):
        print(f"[Home] _set_start_btn: running={running}")
        _start_label.value = "Stop" if running else "Start"
        start_btn.style = ft.ButtonStyle(
            bgcolor={"": "#f44336" if running else "#2196f3"},
            shape=ft.RoundedRectangleBorder(radius=4),
        )
        print(f"[Home] _set_start_btn: label.value='{_start_label.value}' style set")

    def toggle_start(e):
        print(f"[Home] toggle_start: clicked, is_running={is_running['value']}")
        is_running["value"] = not is_running["value"]
        if is_running["value"]:
            grab_state["running"] = True
            _set_start_btn(True)
            _start_clock(e.page)
            _start_camera_loop(e.page)
        else:
            grab_state["running"] = False
            _set_start_btn(False)
        print(f"[Home] toggle_start: calling page.update()")
        e.page.update()
        print(f"[Home] toggle_start: done")

    start_btn.on_click = toggle_start

    def _on_cam_state_home(_, connected):
        if connected:
            cam_dot.bgcolor = "#4caf50"
            if cam_label.value in ("Camera Off", "Disconnected"):
                cam_label.value = "Connected"
        else:
            if not grab_state["running"]:
                cam_dot.bgcolor = "#888888"
                cam_label.value = "Camera Off"
        page.update()

    page.pubsub.subscribe_topic("cam_state", _on_cam_state_home)

    # ── Trigger button — grab from camera if connected, else file ──────────
    def trigger_clicked(e):
        print(f"[Home] trigger_clicked: is_running={is_running['value']}, model={model_dropdown.value}")
        if not model_dropdown.value:
            print("[Home] trigger_clicked: blocked — no model selected")
            return

        pg = e.page

        # ── Case 1: loop is running → use the most recent frame it captured ──
        if is_running["value"]:
            print(f"[Home] trigger_clicked: loop running — using last_frame, img={'yes' if last_frame['img'] is not None else 'none'}")
            if last_frame["img"] is None:
                result_list.controls.clear()
                result_list.controls.append(ft.Text("รอ frame แรกจากกล้อง...", size=13, color="#888888"))
                pg.update()
                return
            frame = last_frame["img"]
            stem  = last_frame["stem"]
            _start_clock(pg)
            result_list.controls.clear()
            result_list.controls.append(ft.Text("Testing...", size=13, color="#888888"))
            ok_ng_label.value = "OK/NG"
            ok_ng_box.bgcolor = "#888888"
            raw_image.visible = False
            pg.update()
            pg.run_thread(lambda: _inspect(frame, stem, pg))
            return

        # ── Case 2: loop not running ─────────────────────────────────────────
        _hik_local = _cam_mod.get_camera()
        print(f"[Home] trigger_clicked: camera obj={_hik_local}, connected={getattr(_hik_local,'connected',None)}")

        _start_clock(pg)
        result_list.controls.clear()
        result_list.controls.append(ft.Text("Testing...", size=13, color="#888888"))
        ok_ng_label.value = "OK/NG"
        ok_ng_box.bgcolor = "#888888"
        raw_image.visible = False
        pg.update()

        if _hik_local and _hik_local.connected:
            print("[Home] trigger_clicked: path → camera grab")
            # Grab from camera (software trigger)
            def run_from_camera():
                print(f"[Home] trigger: grab_one() start, connected={_hik_local.connected}")
                frame = _hik_local.grab_one()
                print(f"[Home] trigger: grab_one() returned {'frame' if frame is not None else 'None'}")
                if frame is None:
                    err = getattr(_hik_local, "last_error", "grab failed")
                    result_list.controls.clear()
                    result_list.controls.append(ft.Text(f"Camera error: {err}", size=13, color="#f44336"))
                    pg.update()
                    return
                img_stem = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
                _inspect(frame, img_stem, pg)
            pg.run_thread(run_from_camera)
        else:
            # Fallback: cycle through test images
            print(f"[Home] trigger_clicked: path → file fallback, TRIGGER_DIR={TRIGGER_DIR}")
            if not trigger_state["files"]:
                files = _get_trigger_files()
                print(f"[Home] trigger_clicked: found {len(files)} trigger files")
                if not files:
                    result_list.controls.clear()
                    result_list.controls.append(
                        ft.Text("Camera not connected and no test images found", size=13, color="#f44336")
                    )
                    pg.update()
                    return
                random.shuffle(files)
                trigger_state["files"] = files
                trigger_state["index"] = 0
            else:
                trigger_state["index"] = (trigger_state["index"] + 1) % len(trigger_state["files"])

            path = trigger_state["files"][trigger_state["index"]]
            print(f"[Home] trigger_clicked: loading file {path}")

            def run_from_file():
                img_cv = cv2.imread(path)
                print(f"[Home] run_from_file: imread={'ok' if img_cv is not None else 'FAILED'} path={path}")
                if img_cv is None:
                    return
                img_stem = os.path.splitext(os.path.basename(path))[0]
                _inspect(img_cv, img_stem, pg)
            pg.run_thread(run_from_file)

    trigger_btn.on_click = trigger_clicked

    # ── Apply broadcast to this session's widgets ──────────────────────────
    def _apply_broadcast():
        b = _broadcast
        if not b["img_src"]:
            return
        raw_img_cont.content = ft.Stack([
            ft.Image(
                src=b["img_src"],
                width=int(b["img_w"] * 1.6), height=int(b["img_h"] * 1.6),
                fit="fill", visible=True,
            )
        ])
        raw_img_cont.width = None

        count_state["ok"]    = b["ok"]
        count_state["ng"]    = b["ng"]
        count_state["total"] = b["total"]
        stat_ok_val.value    = str(b["ok"])
        stat_ng_val.value    = str(b["ng"])
        stat_total_val.value = str(b["total"])

        ok_ng_label.value = "OK" if b["overall"] == "PASS" else "NG"
        ok_ng_box.bgcolor = theme.ACCENT_GREEN if b["overall"] == "PASS" else theme.ACCENT_RED

        cards = []
        for c in b["cards"]:
            insp_id  = c["insp_id"]
            is_pass  = c["is_pass"]
            crop_b64 = c["crop_b64"]
            if crop_b64:
                img_widget = ft.Image(
                    src=f"data:image/jpeg;base64,{crop_b64}",
                    width=182, height=117, fit="contain",
                )
            else:
                img_widget = ft.Container(
                    width=182, height=117, bgcolor="#f44336",
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text("NG", size=20, weight=ft.FontWeight.BOLD, color="#ffffff"),
                )
            if is_pass:
                border_color, bg_color = "#4caf50", "#e8f5e9"
                score_text, text_color = insp_id, "#2e7d32"
            else:
                border_color, bg_color = "#f44336", "#ffebee"
                score_text, text_color = f"{insp_id}  NG", "#c62828"
            cards.append(ft.Container(
                content=ft.Column(
                    [img_widget, ft.Text(score_text, size=9,
                                        weight=ft.FontWeight.BOLD, color=text_color)],
                    spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=4, bgcolor=bg_color,
                border=ft.Border.all(2, border_color),
                border_radius=4, expand=True,
            ))
        result_list.controls.clear()
        for i in range(0, len(cards), 2):
            result_list.controls.append(ft.Row(cards[i:i+2], spacing=4, expand=False))

    if page is not None:
        def _on_home_update(_topic, sender_id):
            if sender_id == id(page):
                return
            _apply_broadcast()
            page.update()

        page.pubsub.unsubscribe_topic("home_update")
        page.pubsub.subscribe_topic("home_update", _on_home_update)

    # Register model-refresh callback so settings.py can call it after save
    def _refresh_home_models(select_model=None):
        models = _get_models()
        model_dropdown.options = [ft.dropdown.Option(m) for m in models]
        if select_model and select_model in models:
            model_dropdown.value = select_model
        elif model_dropdown.value not in models:
            model_dropdown.value = models[0] if models else None
        if page:
            page.update()

    if page:
        setattr(page, "_home_refresh_models", _refresh_home_models)

    # ── Layout ────────────────────────────────────────────────────────────
    home_container = ft.Container(
        content=ft.Column(
            [
                # Header
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("DASHBOARD", size=33, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                    ft.Container(expand=True),
                                    clock_text,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Divider(color=ft.Colors.GREY_400, height=1, thickness=1),
                        ],
                        spacing=4,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                ),

                # Main: RAW (7) | RESULT (3)
                ft.Container(
                    content=ft.Row(
                        [raw_panel, result_panel],
                        spacing=0,
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    expand=True,
                    padding=ft.Padding.only(left=4, right=4, top=0, bottom=0),
                ),

                # Bottom control bar
                ft.Container(
                    content=ft.Row(
                        [
                            time_label,
                            model_dropdown,
                            trigger_btn,
                            start_btn,
                            cam_dot,
                            cam_label,
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                ),
            ],
            spacing=0,
            expand=True,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )

    def _on_resize(e):
        _disp["h"] = max(500, int(page.height * 0.75))

    if page:
        page.on_resized = _on_resize

    return home_container

