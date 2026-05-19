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
from datetime import datetime, timedelta
import flet as ft
import cv2
from config import theme
from fpm_matching import match_fpm, draw_fpm_match, crop_fpm_region


def _put_label(img, text, x, y, bg=(0, 0, 0), fg=(255, 255, 255), scale=0.85, thick=2):
    (tw, th), bl = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    cv2.rectangle(img, (x - 2, y - th - 4), (x + tw + 4, y + bl + 2), bg, -1)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, fg, thick, cv2.LINE_AA)

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
    seen = {}  # result_image_id -> overall_result
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
    is_running     = {"value": False}
    trigger_state  = {"files": [], "index": -1}

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
    clock_text     = ft.Text("", size=12, color=theme.TEXT_SECONDARY)

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
                    break
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
    DISP_H = 570
    raw_placeholder = ft.Text("RAW", color="#2196f3", weight=ft.FontWeight.BOLD, size=28)
    raw_image = ft.Image(src="placeholder.png", visible=False, fit="fill")
    filename_label = ft.Text("", size=11, color=theme.TEXT_SECONDARY, italic=True)

    raw_img_cont = ft.Container(
        content=ft.Stack([raw_placeholder, raw_image]),
        height=DISP_H,
        alignment=ft.Alignment(-1, -1),
        bgcolor="#f5f5f5",
        border_radius=4,
        border=ft.Border.all(1, "#cccccc"),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    raw_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("RAW", size=14, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
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

    # ── Start/Stop button ──────────────────────────────────────────────────
    start_btn = ft.Button(
        "Start",
        width=120,
        height=40,
        style=ft.ButtonStyle(
            bgcolor={"": "#2196f3"},
            color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=4),
        ),
    )

    def toggle_start(e):
        is_running["value"] = not is_running["value"]
        if is_running["value"]:
            start_btn.text = "Stop"
            start_btn.style.bgcolor = {"": "#f44336"}
        else:
            start_btn.text = "Start"
            start_btn.style.bgcolor = {"": "#2196f3"}
        e.page.update()

    start_btn.on_click = toggle_start

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

    def trigger_clicked(e):
        if is_running["value"]:
            return  # camera mode — handled separately

        page = e.page

        # ── Pick next image ────────────────────────────────────────────────
        if not trigger_state["files"]:
            files = _get_trigger_files()
            if not files:
                return
            random.shuffle(files)
            trigger_state["files"] = files
            trigger_state["index"] = 0
        else:
            trigger_state["index"] = (trigger_state["index"] + 1) % len(trigger_state["files"])

        path = trigger_state["files"][trigger_state["index"]]

        selected_model = model_dropdown.value
        if not selected_model:
            return

        json_path = os.path.join(MODEL_DIR, selected_model, f"{selected_model}.json")
        if not os.path.isfile(json_path):
            return

        _start_clock(page)

        # Show loading state
        result_list.controls.clear()
        result_list.controls.append(ft.Text("Testing...", size=13, color="#888888"))
        ok_ng_label.value = "OK/NG"
        ok_ng_box.bgcolor = "#888888"
        raw_placeholder.visible = True
        raw_image.visible = False
        page.update()

        def run_test():
            t_start = time.perf_counter()
            img_cv = cv2.imread(path)
            if img_cv is None:
                return

            # Show RAW image first (same sizing as settings: fixed DISP_H container)
            h, w = img_cv.shape[:2]
            scale = min(DISP_H / h, 1.0)
            dw, dh = int(w * scale), int(h * scale)
            disp = cv2.resize(img_cv, (dw, dh), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode(".jpg", disp, [cv2.IMWRITE_JPEG_QUALITY, 85])
            raw_image.src    = f"data:image/jpeg;base64,{base64.b64encode(buf).decode()}"
            raw_image.width  = dw
            raw_image.height = dh
            raw_img_cont.width = dw
            raw_image.visible = True
            raw_placeholder.visible = False
            filename_label.value = os.path.basename(path)
            page.update()

            # Load template JSON
            with open(json_path, "r", encoding="utf-8") as f:
                template = json.load(f)
            model_base = os.path.join(MODEL_DIR, selected_model)

            # match_scale: fast matching on downscaled, draw overlays on full-res
            img_h, img_w = img_cv.shape[:2]
            match_scale = min(800 / max(img_w, img_h), 1.0)
            scene_match = (cv2.resize(img_cv,
                                      (int(img_w * match_scale), int(img_h * match_scale)),
                                      interpolation=cv2.INTER_AREA)
                           if match_scale < 1.0 else img_cv)
            inv = 1.0 / match_scale if match_scale > 0 else 1.0

            result_img   = img_cv.copy()
            insp_results = []

            for insp in template.get("inspections", []):
                img_paths_rel = insp.get("image_paths", [])
                if not img_paths_rel:
                    single = insp.get("image_path", "")
                    if single:
                        img_paths_rel = [single]
                insp_id = insp.get("name", "?")

                # Load templates at match_scale
                fpm_tmpls = []
                for rel in img_paths_rel:
                    p = os.path.join(model_base, rel)
                    if not os.path.isfile(p):
                        continue
                    t = cv2.imread(p)
                    if t is not None:
                        if match_scale < 1.0:
                            t = cv2.resize(t,
                                           (max(1, int(t.shape[1] * match_scale)),
                                            max(1, int(t.shape[0] * match_scale))),
                                           interpolation=cv2.INTER_AREA)
                        fpm_tmpls.append((insp_id, t))
                if not fpm_tmpls:
                    insp_results.append((insp_id, None, None, False))
                    continue

                # ROI in scene_match coordinates
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

                # Full-res ROI coords for drawing
                frx = int(rx * inv); fry = int(ry * inv)
                frw = int(rw * inv); frh = int(rh * inv)

                # Scale best OK hit to full-res
                ok_best_f = None
                ok_score = None
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

                # Match NG templates (always, regardless of OK result)
                ng_paths_rel = insp.get("ng_image_paths", [])
                ng_best_f = None
                ng_score = None
                if ng_paths_rel:
                    ng_tmpls = []
                    for rel in ng_paths_rel:
                        p = os.path.join(model_base, rel)
                        if os.path.isfile(p):
                            t = cv2.imread(p)
                            if t is not None:
                                if match_scale < 1.0:
                                    t = cv2.resize(t,
                                                   (max(1, int(t.shape[1]*match_scale)),
                                                    max(1, int(t.shape[0]*match_scale))),
                                                   interpolation=cv2.INTER_AREA)
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

                # Decision: compare scores — higher wins
                if ok_score is None and ng_score is None:
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
                        _put_label(result_img, f"s={ok_score:.2f}", drx, max(dry - 8, 18), bg=(0, 120, 0))
                    else:
                        draw_fpm_match(result_img, ok_best_f, label=f"s={ok_score:.2f}")
                    insp_results.append((insp_id, ok_score, crop_cv, True))
                else:
                    crop_cv = crop_fpm_region(img_cv, ng_best_f)
                    if has_roi:
                        overlay = result_img.copy()
                        cv2.rectangle(overlay, (frx, fry), (frx+frw, fry+frh), (100, 100, 220), -1)
                        cv2.addWeighted(overlay, 0.25, result_img, 0.75, 0, result_img)
                        cv2.rectangle(result_img, (frx, fry), (frx+frw, fry+frh), (0, 0, 220), 2)
                        _put_label(result_img, f"{insp_id} NG s={ng_score:.2f}", frx, max(fry - 8, 18), bg=(0, 0, 160))
                    insp_results.append((insp_id, ng_score, crop_cv, False))

            # Display result image
            h, w = result_img.shape[:2]
            disp_scale = min(DISP_H / h, 1.0)
            dw, dh = int(w * disp_scale), int(h * disp_scale)
            result_disp = cv2.resize(result_img, (dw, dh), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode(".jpg", result_disp, [cv2.IMWRITE_JPEG_QUALITY, 85])
            raw_image.src    = f"data:image/jpeg;base64,{base64.b64encode(buf).decode()}"
            raw_image.width  = dw
            raw_image.height = dh
            raw_img_cont.width = dw
            raw_image.visible = True

            # Overall result
            n_pass = sum(1 for *_, p in insp_results if p)
            overall = "PASS" if n_pass == len(insp_results) and len(insp_results) > 0 else "FAIL"
            ok_ng_label.value = "OK" if overall == "PASS" else "NG"
            ok_ng_box.bgcolor = theme.ACCENT_GREEN if overall == "PASS" else theme.ACCENT_RED

            # Update counters
            if overall == "PASS":
                count_state["ok"] += 1
            else:
                count_state["ng"] += 1
            count_state["total"] += 1
            stat_ok_val.value    = str(count_state["ok"])
            stat_ng_val.value    = str(count_state["ng"])
            stat_total_val.value = str(count_state["total"])

            # Result cards (2 per row)
            cards = []
            for insp_id, sc, crop_cv, is_pass in insp_results:
                if crop_cv is not None:
                    ch, cw = crop_cv.shape[:2]
                    cscale = min(140 / cw, 90 / ch, 1.0)
                    thumb = cv2.resize(crop_cv, (int(cw*cscale), int(ch*cscale)), interpolation=cv2.INTER_AREA)
                    _, cbuf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    img_widget = ft.Image(
                        src=f"data:image/jpeg;base64,{base64.b64encode(cbuf).decode()}",
                        width=140, height=90, fit="contain",
                    )
                else:
                    img_widget = ft.Container(
                        width=140, height=90, bgcolor="#f44336",
                        alignment=ft.Alignment(0, 0),
                        content=ft.Text("NG", size=20, weight=ft.FontWeight.BOLD, color="#ffffff"),
                    )
                if is_pass:
                    border_color, bg_color = "#4caf50", "#e8f5e9"
                    score_text = f"{insp_id}  s={sc:.2f}"
                    text_color = "#2e7d32"
                else:
                    border_color, bg_color = "#f44336", "#ffebee"
                    score_text = f"{insp_id}  NG" if sc is None else f"{insp_id}  NG  s={sc:.2f}"
                    text_color = "#c62828"
                cards.append(
                    ft.Container(
                        content=ft.Column([
                            img_widget,
                            ft.Text(score_text, size=9, weight=ft.FontWeight.BOLD, color=text_color),
                        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=4,
                        bgcolor=bg_color,
                        border=ft.Border.all(2, border_color),
                        border_radius=4,
                        expand=True,
                    )
                )
            result_list.controls.clear()
            for i in range(0, len(cards), 2):
                row_cards = cards[i:i+2]
                result_list.controls.append(
                    ft.Row(row_cards, spacing=4, expand=False)
                )

            time_label.content.value = f"Process: {(time.perf_counter() - t_start) * 1000:.0f} ms"

            # ── Save to report ──────────────────────────────────────────────
            try:
                now           = datetime.now()
                ts            = now.strftime("%Y-%m-%d %H:%M:%S")
                img_stem      = os.path.splitext(os.path.basename(path))[0]
                result_img_id = f"{now.strftime('%Y%m%d_%H%M%S')}_{img_stem}"

                results_dir     = os.path.join(BASE_DIR, "results")
                results_img_dir = os.path.join(results_dir, "images")
                os.makedirs(results_img_dir, exist_ok=True)

                cv2.imwrite(os.path.join(results_img_dir, f"{result_img_id}.jpg"), result_disp)

                csv_path    = _today_csv_path()
                file_exists = os.path.isfile(csv_path)
                with open(csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow([
                            "timestamp", "model", "inspection_name",
                            "result", "score", "overall_result", "result_image_id",
                        ])
                    for insp_id, sc, _, is_pass in insp_results:
                        result_str = "PASS" if is_pass else ("FAIL" if sc is not None else "NO_MATCH")
                        score_str  = f"{sc:.4f}" if sc is not None else ""
                        writer.writerow([
                            ts, selected_model, insp_id,
                            result_str, score_str, overall, result_img_id,
                        ])
            except Exception:
                import traceback
                traceback.print_exc()

            page.update()

        page.run_thread(run_test)

    trigger_btn.on_click = trigger_clicked

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
    return ft.Container(
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
                        [time_label, model_dropdown, trigger_btn, start_btn],
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
