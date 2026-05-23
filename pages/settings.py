"""
Settings Page
"""
import asyncio
import base64
import flet as ft
import cv2
import json
import numpy as np
import os
import threading
import time
from config import theme
from fpm_matching import match_fpm, draw_fpm_match, crop_fpm_region


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

    banner = _PILImage.new("RGB", (bw, bh), (20, 20, 20))
    draw   = _PILDraw.Draw(banner)
    for i, line in enumerate(lines):
        tx = pad
        ty = pad // 2 + i * line_h
        draw.text((tx + 2, ty + 2), line, font=pil_font, fill=(0, 0, 0))       # shadow
        draw.text((tx,     ty    ), line, font=pil_font, fill=(255, 255, 255))  # white
    banner_bgr = cv2.cvtColor(np.array(banner), cv2.COLOR_RGB2BGR)

    roi = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = cv2.addWeighted(banner_bgr, 0.85, roi, 0.15, 0)
    cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 200), 2)
    cv2.line(img, (x0, y0), (x0, y1), (0, 0, 230), 6)


def _make_thumb_widget(b64, w, h, border_color, border_r, crops_list, thumbs_row, count_label, count_suffix):
    """Thumbnail with X button to delete."""
    widget_ref = [None]

    def on_delete(e):
        if widget_ref[0] in thumbs_row.controls:
            idx = thumbs_row.controls.index(widget_ref[0])
            thumbs_row.controls.remove(widget_ref[0])
            if 0 <= idx < len(crops_list):
                crops_list.pop(idx)
            count_label.value = f"{len(crops_list)} {count_suffix}"
            e.control.page.update()

    del_btn = ft.Container(
        content=ft.Text("✕", size=10, color="#ffffff", weight=ft.FontWeight.BOLD),
        width=16, height=16,
        bgcolor="#e53935",
        border_radius=8,
        alignment=ft.Alignment(0, 0),
        on_click=on_delete,
        right=0, top=0,
    )

    widget = ft.Stack(
        [
            ft.Container(
                content=ft.Image(
                    src=f"data:image/jpeg;base64,{b64}",
                    width=w, height=h, fit="cover",
                    border_radius=ft.BorderRadius.all(border_r),
                ),
                border=ft.Border.all(2, border_color),
                border_radius=border_r + 1,
            ),
            del_btn,
        ],
        width=w + 4,
        height=h + 4,
    )
    widget_ref[0] = widget
    return widget


def create_settings_page(page=None):

    #  Sub-page state 
    active_tab = {"value": "create"}
    algo_state = {"value": "FPM"}

    #  Algorithm selector
    algo_dropdown = ft.Dropdown(
        label="Algorithm",
        width=200,
        height=40,
        text_size=12,
        value="FPM",
        options=[
            ft.dropdown.Option("FPM"),
        ],
        on_select=lambda e: algo_state.update({"value": e.control.value}),
    )

    #  Tab buttons 
    def tab_style(active):
        return ft.ButtonStyle(
            bgcolor={"": theme.SIDEBAR_ITEM_ACTIVE if active else "#e0e0e0"},
            color={"": "#ffffff" if active else "#333333"},
            shape=ft.RoundedRectangleBorder(radius=0),
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )

    btn_create = ft.Button("CREATE MODEL", height=34, style=tab_style(True))
    btn_camera = ft.Button("CAMERA SETTING", height=34, style=tab_style(False))

    #  Content panels 
    content_area = ft.Container(expand=True, padding=ft.Padding.only(left=12, right=12, bottom=12))

    #  Inspection rows 
    inspection_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
    inspection_counter = {"value": 0}
    image_state = {"path": "", "files": [], "web_files": [], "index": -1, "cv_img": None, "scale": 1.0, "act_w": 320, "act_h": 570}
    image_counter_text = ft.Text("", size=12, color=theme.TEXT_SECONDARY)
    inspection_data = []
    crop_state = {"active": False, "target": None, "start_x": 0, "start_y": 0, "cur_x": 0, "cur_y": 0, "mode": "crop", "dragging_corner": None, "fixed_x": 0, "fixed_y": 0, "press_x": 0, "press_y": 0}

    def make_inspection_row():
        inspection_counter["value"] += 1
        idx = inspection_counter["value"]
        row_ref = {"row": None}
        crop_ref = {"roi": None, "img_path": None, "source": None}
        crops_list = []      # OK templates
        ng_crops_list = []   # NG templates

        preview_placeholder = ft.Text("IMG", color="#2196f3", weight=ft.FontWeight.BOLD, size=12)
        preview_img = ft.Image(src="placeholder.png", visible=False, fit="contain", width=280, height=160)
        preview_container = ft.Container(
            content=ft.Stack([preview_placeholder, preview_img]),
            width=280, height=160,
            border=ft.Border.all(1, "#aaaaaa"),
            border_radius=4,
            alignment=ft.Alignment(0, 0),
            bgcolor="#ffffff",
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        # thumbnails row for multi-crop
        thumbs_row = ft.Row(spacing=4, scroll=ft.ScrollMode.AUTO, height=50, width=280)
        ng_thumbs_row = ft.Row(spacing=4, scroll=ft.ScrollMode.AUTO, height=50, width=280)

        name_field = ft.TextField(height=28, text_size=12, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), expand=True)
        desc_field = ft.TextField(height=28, text_size=12, content_padding=ft.Padding.symmetric(horizontal=6, vertical=2), expand=True)

        crop_count_label = ft.Text("0 OK", size=10, color="#888888")
        ng_crop_count_label = ft.Text("0 NG", size=10, color="#f44336")

        roi_label = ft.Text("ROI: not set", size=10, color="#888888")
        data_entry = {"name_field": name_field, "desc_field": desc_field, "crop_ref": crop_ref,
                      "crops_list": crops_list, "thumbs_row": thumbs_row,
                      "crop_count_label": crop_count_label,
                      "ng_crops_list": ng_crops_list, "ng_thumbs_row": ng_thumbs_row,
                      "ng_crop_count_label": ng_crop_count_label,
                      "row": None, "preview_img": preview_img, "preview_placeholder": preview_placeholder,
                      "search_roi": None, "roi_label": roi_label}

        def crop_clicked(e):
            if image_state.get("cv_img") is None:
                return
            crop_state["active"] = True
            crop_state["target"] = data_entry
            crop_state["mode"] = "crop"
            selection_rect.visible = False
            _hide_handles()
            crop_label.content.value = "CROP OK - drag to select"
            crop_label.bgcolor = "#e53935"
            crop_label.visible = True
            e.page.update()

        def crop_ng_clicked(e):
            if image_state.get("cv_img") is None:
                return
            crop_state["active"] = True
            crop_state["target"] = data_entry
            crop_state["mode"] = "ng_crop"
            selection_rect.visible = False
            _hide_handles()
            crop_label.content.value = "CROP NG - drag to select"
            crop_label.bgcolor = "#b71c1c"
            crop_label.visible = True
            e.page.update()

        def roi_clicked(e):
            if image_state.get("cv_img") is None:
                return
            existing = data_entry.get("search_roi")
            if existing:
                ox, oy, ow, oh = existing
                scale = image_state.get("scale", 1.0)
                dx, dy, dw, dh = ox * scale, oy * scale, ow * scale, oh * scale
                selection_rect.left = dx
                selection_rect.top = dy
                selection_rect.width = dw
                selection_rect.height = dh
                selection_rect.visible = True
                _update_handles(dx, dy, dw, dh)
                crop_state["active"] = True
                crop_state["target"] = data_entry
                crop_state["mode"] = "roi_adjust"
                crop_state["dragging_corner"] = None
                crop_label.content.value = "ROI - drag corners to adjust"
                crop_label.bgcolor = "#1565c0"
                crop_label.visible = True
            else:
                crop_state["active"] = True
                crop_state["target"] = data_entry
                crop_state["mode"] = "roi"
                selection_rect.visible = False
                _hide_handles()
                crop_label.content.value = "ROI MODE - drag to set search area"
                crop_label.bgcolor = "#1565c0"
                crop_label.visible = True
            e.page.update()

        row = ft.Row(
            [
                ft.Text(f"{idx}", size=12, weight=ft.FontWeight.BOLD, width=20, color=theme.TEXT_PRIMARY),
                ft.Column(
                    [
                        preview_container,
                        ft.Row([
                            ft.Button("Crop OK", height=28,
                                style=ft.ButtonStyle(
                                    bgcolor={"":"#2196f3"}, color={"":"#ffffff"},
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                ),
                                on_click=crop_clicked),
                            ft.Button("Crop NG", height=28,
                                style=ft.ButtonStyle(
                                    bgcolor={"":"#b71c1c"}, color={"":"#ffffff"},
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                ),
                                on_click=crop_ng_clicked),
                            ft.Button("Set ROI", height=28,
                                style=ft.ButtonStyle(
                                    bgcolor={"":"#f57c00"}, color={"":"#ffffff"},
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                ),
                                on_click=roi_clicked),
                        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Row([crop_count_label, ft.Text("  |", size=10, color="#cccccc"), ng_crop_count_label,
                                ft.Text("  |", size=10, color="#cccccc"), roi_label],
                               spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Container(content=thumbs_row,
                                     border=ft.Border.all(1, "#4caf50"),
                                     border_radius=4, padding=2),
                        ft.Container(content=ng_thumbs_row,
                                     border=ft.Border.all(1, "#f44336"),
                                     border_radius=4, padding=2, visible=True),
                        ft.Row([
                            ft.Text("Name", size=11, width=100),
                            name_field,
                        ], spacing=4),
                        ft.Row([
                            ft.Text("Description", size=11, width=100),
                            desc_field,
                        ], spacing=4),
                    ],
                    spacing=6,
                    width=290,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        row_ref["row"] = row
        data_entry["row"] = row
        inspection_data.append(data_entry)
        return row

    # pre-populate with 1 row
    inspection_list.controls.append(make_inspection_row())

    def add_inspection(e):
        inspection_list.controls.insert(0, make_inspection_row())
        # newest on top = highest ID
        total = len(inspection_list.controls)
        for i, r in enumerate(inspection_list.controls):
            r.controls[0].value = str(total - i)
        e.page.update()

    def delete_last(e):
        if inspection_list.controls:
            removed_row = inspection_list.controls.pop(0)
            inspection_data[:] = [d for d in inspection_data if d["row"] is not removed_row]
            inspection_counter["value"] = max(0, inspection_counter["value"] - 1)
            total = len(inspection_list.controls)
            for i, r in enumerate(inspection_list.controls):
                r.controls[0].value = str(total - i)
            e.page.update()

    def btn_style_sm(color):
        return ft.ButtonStyle(
            bgcolor={"": color},
            color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=4),
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        )

    #  Right action buttons 
    right_btns = ft.Column(
        [
            ft.Button("Connect camera", width=120, height=38, style=btn_style_sm("#f57c00")),
            ft.Button("Trigger Image",  width=120, height=38, style=btn_style_sm("#f57c00")),
            ft.Button("Open File",      width=120, height=38, style=btn_style_sm("#f57c00")),
            ft.Button("Next",           width=120, height=38, style=btn_style_sm("#f57c00")),
            ft.Button("Previous",       width=120, height=38, style=btn_style_sm("#f57c00")),
            ft.Button("Test",           width=120, height=38, style=btn_style_sm("#f57c00")),
        ],
        spacing=6,
    )

    #  Display size constants (portrait 9:16)
    DISP_W = 320
    DISP_H = 570

    #  Large IMG display 
    large_img = ft.Image(src="placeholder.png", visible=False, fit="fill")
    large_img_placeholder = ft.Text("IMG", color="#2196f3", weight=ft.FontWeight.BOLD, size=18)
    selection_rect = ft.Container(
        left=0, top=0, width=0, height=0,
        border=ft.Border.all(2, "#ff0000"),
        visible=False,
    )
    crop_label = ft.Container(
        content=ft.Text("CROP MODE - drag to select", color="#ffffff", size=11, weight=ft.FontWeight.BOLD),
        bgcolor="#e53935",
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        border_radius=4,
        top=4, left=4,
        visible=False,
    )

    HANDLE_SIZE = 14
    roi_handles = [
        ft.Container(
            left=0, top=0, width=HANDLE_SIZE, height=HANDLE_SIZE,
            bgcolor="#ff0000",
            border=ft.Border.all(2, "#ffffff"),
            border_radius=2,
            visible=False,
        )
        for _ in range(4)
    ]

    def _update_handles(x, y, w, h):
        half = HANDLE_SIZE / 2
        positions = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
        for i, (hx, hy) in enumerate(positions):
            roi_handles[i].left = hx - half
            roi_handles[i].top = hy - half
            roi_handles[i].visible = True

    def _hide_handles():
        for h in roi_handles:
            h.visible = False

    def on_pan_down(e):
        # Fires on initial pointer contact — before drag threshold — captures true click position
        if not crop_state["active"]:
            return
        crop_state["press_x"] = e.local_position.x
        crop_state["press_y"] = e.local_position.y

    def on_pan_start(e):
        if not crop_state["active"]:
            return
        # Use press position (captured before drag threshold) so selection starts at actual click point
        sx = crop_state.get("press_x", e.local_position.x)
        sy = crop_state.get("press_y", e.local_position.y)
        if crop_state.get("mode") == "roi_adjust":
            rx = selection_rect.left or 0
            ry = selection_rect.top or 0
            rw = selection_rect.width or 0
            rh = selection_rect.height or 0
            corners = [(rx, ry), (rx + rw, ry), (rx, ry + rh), (rx + rw, ry + rh)]
            for i, (cx, cy) in enumerate(corners):
                if abs(sx - cx) <= 18 and abs(sy - cy) <= 18:
                    crop_state["dragging_corner"] = i
                    crop_state["fixed_x"] = rx + rw if i in (0, 2) else rx
                    crop_state["fixed_y"] = ry + rh if i in (0, 1) else ry
                    return
            # ไม่ได้แตะมุม → วาดใหม่
            crop_state["mode"] = "roi"
            crop_state["dragging_corner"] = None
            _hide_handles()
        crop_state["start_x"] = sx
        crop_state["start_y"] = sy
        crop_state["cur_x"] = sx
        crop_state["cur_y"] = sy
        selection_rect.left = sx
        selection_rect.top = sy
        selection_rect.width = 0
        selection_rect.height = 0
        selection_rect.visible = True
        e.page.update()

    def on_pan_update(e):
        if not crop_state["active"]:
            return
        act_w = image_state["act_w"]
        act_h = image_state["act_h"]
        px, py = e.local_position.x, e.local_position.y
        if crop_state.get("mode") == "roi_adjust" and crop_state.get("dragging_corner") is not None:
            fx = crop_state["fixed_x"]
            fy = crop_state["fixed_y"]
            px = max(0, min(px, act_w))
            py = max(0, min(py, act_h))
            x = min(fx, px)
            y = min(fy, py)
            w = abs(px - fx)
            h = abs(py - fy)
            selection_rect.left = x
            selection_rect.top = y
            selection_rect.width = w
            selection_rect.height = h
            _update_handles(x, y, w, h)
            e.page.update()
            return
        crop_state["cur_x"] = px
        crop_state["cur_y"] = py
        sx, sy = crop_state["start_x"], crop_state["start_y"]
        x = max(0, min(sx, px))
        y = max(0, min(sy, py))
        w = min(abs(px - sx), act_w - x)
        h = min(abs(py - sy), act_h - y)
        selection_rect.left = x
        selection_rect.top = y
        selection_rect.width = w
        selection_rect.height = h
        e.page.update()

    def on_pan_end(e):
        if not crop_state["active"] or not crop_state["target"]:
            return
        cv_img = image_state.get("cv_img")
        if cv_img is None:
            return
        rx = selection_rect.left or 0
        ry = selection_rect.top or 0
        rw = selection_rect.width or 0
        rh = selection_rect.height or 0
        if rw < 5 or rh < 5:
            _hide_handles()
            selection_rect.visible = False
            crop_state["active"] = False
            crop_state["target"] = None
            crop_label.visible = False
            e.page.update()
            return
        scale = image_state["scale"]
        img_h, img_w = cv_img.shape[:2]
        ox = int(rx / scale)
        oy = int(ry / scale)
        ow = int(rw / scale)
        oh = int(rh / scale)
        ox = max(0, min(ox, img_w - 1))
        oy = max(0, min(oy, img_h - 1))
        ow = min(ow, img_w - ox)
        oh = min(oh, img_h - oy)
        if ow < 2 or oh < 2:
            _hide_handles()
            selection_rect.visible = False
            crop_state["active"] = False
            crop_state["target"] = None
            crop_label.visible = False
            e.page.update()
            return
        if crop_state.get("mode") == "roi_adjust":
            crop_state["dragging_corner"] = None
            target = crop_state["target"]
            target["search_roi"] = (ox, oy, ow, oh)
            if "roi_label" in target:
                target["roi_label"].value = f"ROI: ({ox},{oy}) {ow}×{oh}"
            _hide_handles()
            selection_rect.visible = False
            crop_state["active"] = False
            crop_state["target"] = None
            crop_label.visible = False
            e.page.update()
            return
        if crop_state.get("mode") == "roi":
            target = crop_state["target"]
            target["search_roi"] = (ox, oy, ow, oh)
            if "roi_label" in target:
                target["roi_label"].value = f"ROI: ({ox},{oy}) {ow}×{oh}"
            selection_rect.visible = False
            crop_state["active"] = False
            crop_state["target"] = None
            crop_label.visible = False
            e.page.update()
            return
        cropped = cv_img[oy:oy+oh, ox:ox+ow]
        crop_dir = os.path.join(
            os.path.dirname(image_state["path"]) if image_state["path"] and os.path.isabs(image_state["path"]) else BASE_DIR,
            "_crops"
        )
        os.makedirs(crop_dir, exist_ok=True)
        crop_path = os.path.join(crop_dir, f"crop_{int(time.time()*1000)}.jpg")
        cv2.imwrite(crop_path, cropped)
        target = crop_state["target"]
        target["crop_ref"]["roi"] = (ox, oy, ow, oh)
        target["crop_ref"]["img_path"] = crop_path
        target["crop_ref"]["source"] = image_state["path"]
        # append to multi-crop list
        _, buf = cv2.imencode(".jpg", cropped, [cv2.IMWRITE_JPEG_QUALITY, 90])
        b64 = base64.b64encode(buf).decode()
        if crop_state.get("mode") == "ng_crop":
            target["ng_crops_list"].append({
                "roi": (ox, oy, ow, oh),
                "img_path": crop_path,
                "source": image_state["path"],
            })
            target["ng_thumbs_row"].controls.append(
                _make_thumb_widget(b64, 40, 40, "#f44336", 2,
                                   target["ng_crops_list"], target["ng_thumbs_row"],
                                   target["ng_crop_count_label"], "NG")
            )
            target["ng_crop_count_label"].value = f"{len(target['ng_crops_list'])} NG"
        else:
            target["crops_list"].append({
                "roi": (ox, oy, ow, oh),
                "img_path": crop_path,
                "source": image_state["path"],
            })
            target["preview_img"].src = f"data:image/jpeg;base64,{b64}"
            target["preview_img"].visible = True
            target["preview_placeholder"].visible = False
            target["thumbs_row"].controls.append(
                _make_thumb_widget(b64, 44, 44, "#4caf50", 3,
                                   target["crops_list"], target["thumbs_row"],
                                   target["crop_count_label"], "OK")
            )
            target["crop_count_label"].value = f"{len(target['crops_list'])} OK"
        selection_rect.visible = False
        crop_state["active"] = False
        crop_state["target"] = None
        crop_label.visible = False
        e.page.update()

    large_img_container = ft.Container(
        content=ft.GestureDetector(
            content=ft.Stack([large_img_placeholder, large_img, selection_rect, *roi_handles, crop_label]),
            on_pan_down=on_pan_down,
            on_pan_start=on_pan_start,
            on_pan_update=on_pan_update,
            on_pan_end=on_pan_end,
        ),
        height=DISP_H,
        alignment=ft.Alignment(-1, -1),
        bgcolor="#ffffff",
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    #  RESULT panel (inside shared box with RAW)
    result_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
    result_panel = ft.Container(
        content=ft.Column(
            [
                ft.Text("RESULT", size=14, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                result_list,
            ],
            spacing=4,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=280,
        height=DISP_H + 30,
        padding=4,
        border=ft.Border.only(right=ft.BorderSide(1, "#aaaaaa")),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    #  MODEL panel (inspection list) — content set after model_name_field is defined
    model_panel_col = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.AUTO)
    model_panel = ft.Container(
        content=model_panel_col,
        width=385,
        height=DISP_H + 30,
        padding=4,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    #  Combined RAW | RESULT | MODEL box
    raw_result_box = ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("RAW", size=14, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                    image_counter_text,
                                ],
                                spacing=8,
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            large_img_container,
                        ],
                        spacing=2,
                        expand=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    expand=True,
                    border=ft.Border.only(right=ft.BorderSide(1, "#aaaaaa")),
                ),
                result_panel,
                model_panel,
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        border=ft.Border.all(1, "#aaaaaa"),
        border_radius=4,
        padding=4,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    #  Image loader helper (cv2 resize + base64 = fast)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def load_image_by_path(path, page, img_bytes=None):
        print(f"[DEBUG] load_image_by_path: START - path={path is not None}, img_bytes={img_bytes is not None}")
        try:
            print("[DEBUG] load_image_by_path: Reading/decoding image...")
            if img_bytes is not None:
                print(f"[DEBUG] load_image_by_path: Decoding from bytes (size={len(img_bytes)})...")
                raw = bytes(img_bytes) if not isinstance(img_bytes, (bytes, bytearray)) else img_bytes
                arr = np.frombuffer(raw, np.uint8)
                img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                print(f"[DEBUG] load_image_by_path: Decoded, shape={img_cv.shape if img_cv is not None else None}")
            else:
                print(f"[DEBUG] load_image_by_path: Reading from path: {path}")
                img_cv = cv2.imread(path) if path else None
                print(f"[DEBUG] load_image_by_path: Read, shape={img_cv.shape if img_cv is not None else None}")
            if img_cv is not None:
                print("[DEBUG] load_image_by_path: Image loaded successfully, processing...")
                image_state["cv_img"] = img_cv
                h, w = img_cv.shape[:2]
                print(f"[DEBUG] load_image_by_path: Original size={w}x{h}")
                scale = min(DISP_H / h, 1.0)
                image_state["scale"] = scale
                disp_w = int(w * scale)
                disp_h = int(h * scale)
                image_state["act_w"] = disp_w
                image_state["act_h"] = disp_h
                large_img.width = disp_w
                large_img.height = disp_h
                large_img_container.width = disp_w
                # Resize to display size before encoding → much smaller base64 payload
                print(f"[DEBUG] load_image_by_path: Resizing to {disp_w}x{disp_h}...")
                display_img = cv2.resize(img_cv, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
                print("[DEBUG] load_image_by_path: Encoding to JPEG...")
                _, buf = cv2.imencode(".jpg", display_img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                print(f"[DEBUG] load_image_by_path: Encoded, buffer size={len(buf)}")
                print("[DEBUG] load_image_by_path: Encoding to base64...")
                b64 = base64.b64encode(buf).decode()
                print(f"[DEBUG] load_image_by_path: Base64 length={len(b64)}")
                large_img.src = f"data:image/jpeg;base64,{b64}"
                large_img.visible = True
                large_img_placeholder.visible = False
                selection_rect.visible = False
                _hide_handles()
                crop_label.visible = False
                web_files = image_state.get("web_files", [])
                files = image_state["files"]
                if web_files:
                    image_counter_text.value = f"{image_state['index'] + 1}/{len(web_files)}"
                elif files:
                    image_counter_text.value = f"{image_state['index'] + 1}/{len(files)}"
                else:
                    image_counter_text.value = ""
                print("[DEBUG] load_image_by_path: Calling page.update()...")
                page.update()
                print("[DEBUG] load_image_by_path: page.update() completed")
            else:
                print("[DEBUG] load_image_by_path: Image is None, showing placeholder")
                large_img.visible = False
                large_img_placeholder.visible = True
                page.update()
        except Exception as _ex:
            print(f"[ERROR] load_image_by_path: {_ex}")
            import traceback
            traceback.print_exc()
        print("[DEBUG] load_image_by_path: EXIT")

    #  Open images (multiple files)
    _file_picker_state = {"picker": None}

    async def open_images_clicked(e):
        page = e.page
        if _file_picker_state["picker"] is None:
            fp = ft.FilePicker()
            page.services.append(fp)
            page.update()
            await asyncio.sleep(0.3)
            _file_picker_state["picker"] = fp

        picked = await _file_picker_state["picker"].pick_files(
            dialog_title="Select Image",
            initial_directory=os.path.join(BASE_DIR, "image"),
            file_type=ft.FilePickerFileType.IMAGE,
            allow_multiple=False,
            with_data=False,
        )
        if not picked or not picked[0].path:
            return

        chosen_path = picked[0].path
        folder = os.path.dirname(chosen_path)

        img_exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
        all_paths = sorted(
            [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if os.path.splitext(f)[1].lower() in img_exts
                and os.path.isfile(os.path.join(folder, f))
            ],
            key=lambda p: os.path.basename(p).lower(),
        )
        if not all_paths:
            return

        start_index = next(
            (i for i, p in enumerate(all_paths) if os.path.normcase(p) == os.path.normcase(chosen_path)),
            0,
        )

        image_state["files"] = all_paths
        image_state["web_files"] = []
        image_state["index"] = start_index
        image_state["path"] = chosen_path
        image_state["cv_img"] = None
        image_counter_text.value = f"{start_index + 1}/{len(all_paths)}"
        large_img_placeholder.visible = True
        large_img.visible = False
        page.update()
        page.run_thread(lambda: load_image_by_path(chosen_path, page))

    #  Next / Previous image
    def next_image_clicked(e):
        print("[DEBUG] next_image_clicked: START")
        web_files = image_state.get("web_files", [])
        files = image_state["files"]
        print(f"[DEBUG] next_image_clicked: web_files={len(web_files)}, files={len(files)}, current_index={image_state['index']}")
        
        if web_files:
            # Web mode: load from stored FilePickerFile bytes
            print("[DEBUG] next_image_clicked: Web mode")
            if image_state["index"] >= len(web_files) - 1:
                image_state["index"] = 0
            else:
                image_state["index"] += 1
            print(f"[DEBUG] next_image_clicked: Web - new index={image_state['index']}")
            
            f = web_files[image_state["index"]]
            if f.bytes is not None:
                print(f"[DEBUG] next_image_clicked: Web - bytes size={len(f.bytes)}")
                image_counter_text.value = f"{image_state['index'] + 1}/{len(web_files)}"
                large_img_placeholder.visible = True
                large_img.visible = False
                print("[DEBUG] next_image_clicked: Web - calling page.update()...")
                e.page.update()
                print("[DEBUG] next_image_clicked: Web - starting run_thread...")
                raw = bytes(f.bytes)
                e.page.run_thread(lambda: load_image_by_path(None, e.page, img_bytes=raw))
            print("[DEBUG] next_image_clicked: Web mode EXIT")
            return
        
        if files:
            # Desktop mode: load from stored file path
            print("[DEBUG] next_image_clicked: Desktop mode")
            if image_state["index"] >= len(files) - 1:
                image_state["index"] = 0
            else:
                image_state["index"] += 1
            print(f"[DEBUG] next_image_clicked: Desktop - new index={image_state['index']}")
            
            path = files[image_state["index"]]
            image_state["path"] = path
            print(f"[DEBUG] next_image_clicked: Desktop - path={path}")
            image_counter_text.value = f"{image_state['index'] + 1}/{len(files)}"
            large_img_placeholder.visible = True
            large_img.visible = False
            print("[DEBUG] next_image_clicked: Desktop - calling page.update()...")
            e.page.update()
            print("[DEBUG] next_image_clicked: Desktop - starting run_thread...")
            e.page.run_thread(lambda: load_image_by_path(path, e.page))
            print("[DEBUG] next_image_clicked: Desktop mode EXIT")

    def previous_image_clicked(e):
        print("[DEBUG] previous_image_clicked: START")
        web_files = image_state.get("web_files", [])
        files = image_state["files"]
        print(f"[DEBUG] previous_image_clicked: web_files={len(web_files)}, files={len(files)}, current_index={image_state['index']}")
        
        if web_files:
            # Web mode: load from stored FilePickerFile bytes
            print("[DEBUG] previous_image_clicked: Web mode")
            if image_state["index"] <= 0:
                image_state["index"] = len(web_files) - 1
            else:
                image_state["index"] -= 1
            print(f"[DEBUG] previous_image_clicked: Web - new index={image_state['index']}")
            
            f = web_files[image_state["index"]]
            if f.bytes is not None:
                print(f"[DEBUG] previous_image_clicked: Web - bytes size={len(f.bytes)}")
                image_counter_text.value = f"{image_state['index'] + 1}/{len(web_files)}"
                large_img_placeholder.visible = True
                large_img.visible = False
                print("[DEBUG] previous_image_clicked: Web - calling page.update()...")
                e.page.update()
                print("[DEBUG] previous_image_clicked: Web - starting run_thread...")
                raw = bytes(f.bytes)
                e.page.run_thread(lambda: load_image_by_path(None, e.page, img_bytes=raw))
            print("[DEBUG] previous_image_clicked: Web mode EXIT")
            return
        
        if files:
            # Desktop mode: load from stored file path
            print("[DEBUG] previous_image_clicked: Desktop mode")
            if image_state["index"] <= 0:
                image_state["index"] = len(files) - 1
            else:
                image_state["index"] -= 1
            print(f"[DEBUG] previous_image_clicked: Desktop - new index={image_state['index']}")
            
            path = files[image_state["index"]]
            image_state["path"] = path
            print(f"[DEBUG] previous_image_clicked: Desktop - path={path}")
            image_counter_text.value = f"{image_state['index'] + 1}/{len(files)}"
            large_img_placeholder.visible = True
            large_img.visible = False
            print("[DEBUG] previous_image_clicked: Desktop - calling page.update()...")
            e.page.update()
            print("[DEBUG] previous_image_clicked: Desktop - starting run_thread...")
            e.page.run_thread(lambda: load_image_by_path(path, e.page))
            print("[DEBUG] previous_image_clicked: Desktop mode EXIT")

    #  Save template as JSON
    def save_template(e):
        model_name = (model_name_field.value or "").strip()
        if not model_name:
            return
        # Create model folder under project root
        model_dir = os.path.join(BASE_DIR, "model", model_name)
        img_dir = os.path.join(model_dir, "img")
        os.makedirs(img_dir, exist_ok=True)

        template = {
            "model": model_name,
            "inspections": []
        }
        for data in inspection_data:
            crop_ref = data["crop_ref"]
            crops_list = data.get("crops_list", [])
            saved_imgs = []
            # Save all crop images for multi-template
            for crop_item in crops_list:
                cp = crop_item.get("img_path", "")
                if cp and os.path.isfile(cp):
                    fname = os.path.basename(cp)
                    dest = os.path.join(img_dir, fname)
                    img = cv2.imread(cp)
                    if img is not None:
                        cv2.imwrite(dest, img)
                        saved_imgs.append(f"img/{fname}")
            # fallback: single crop_ref if crops_list is empty
            if not saved_imgs and crop_ref.get("img_path") and os.path.isfile(crop_ref["img_path"]):
                fname = os.path.basename(crop_ref["img_path"])
                dest = os.path.join(img_dir, fname)
                img = cv2.imread(crop_ref["img_path"])
                if img is not None:
                    cv2.imwrite(dest, img)
                    saved_imgs.append(f"img/{fname}")
            ng_saved_imgs = []
            for crop_item in data.get("ng_crops_list", []):
                cp = crop_item.get("img_path", "")
                if cp and os.path.isfile(cp):
                    fname = "ng_" + os.path.basename(cp)
                    dest = os.path.join(img_dir, fname)
                    img = cv2.imread(cp)
                    if img is not None:
                        cv2.imwrite(dest, img)
                        ng_saved_imgs.append(f"img/{fname}")
            insp = {
                "name": data["name_field"].value or "",
                "description": data["desc_field"].value or "",
                "image_path": saved_imgs[0] if saved_imgs else "",
                "image_paths": saved_imgs,
                "ng_image_paths": ng_saved_imgs,
                "crop_roi": list(crop_ref["roi"]) if crop_ref["roi"] else [],
                "source_image": crop_ref.get("source") or "",
                "search_roi": list(data["search_roi"]) if data.get("search_roi") else [],
            }
            template["inspections"].append(insp)

        json_path = os.path.join(model_dir, f"{model_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)

        refresh_model_dropdown()
        model_dropdown.value = model_name

        # Refresh home page model dropdown if it is registered
        home_refresh = getattr(e.page, "_home_refresh_models", None)
        if home_refresh:
            home_refresh(model_name)

        dlg = ft.AlertDialog(
            title=ft.Text("Success"),
            content=ft.Text(f"Model \"{model_name}\" saved successfully."),
            open=True,
        )
        e.page.overlay.append(dlg)
        e.page.update()

    #  Model name field
    model_name_field = ft.TextField(height=32, text_size=13, content_padding=ft.Padding.symmetric(horizontal=8, vertical=4), expand=True)

    #  Populate MODEL panel now that model_name_field exists
    model_panel_col.controls = [
        ft.Row([ft.Text("Model:", size=14, weight=ft.FontWeight.BOLD), model_name_field],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Container(content=inspection_list, expand=True,
            border=ft.Border.all(1,"#dddddd"), border_radius=4, padding=6),
    ]

    #  Model dropdown for Test
    MODEL_DIR = os.path.join(BASE_DIR, "model")

    def get_model_list():
        if not os.path.isdir(MODEL_DIR):
            return []
        return sorted([d for d in os.listdir(MODEL_DIR)
                       if os.path.isdir(os.path.join(MODEL_DIR, d))])

    model_dropdown = ft.Dropdown(
        label="Select Model",
        width=200,
        height=40,
        text_size=12,
        options=[ft.dropdown.Option(m) for m in get_model_list()],
        on_select=lambda e: show_model_info(e),
    )

    def refresh_model_dropdown():
        model_dropdown.options = [ft.dropdown.Option(m) for m in get_model_list()]

    def show_model_info(e):
        selected = model_dropdown.value
        if not selected:
            return
        json_path = os.path.join(MODEL_DIR, selected, f"{selected}.json")
        if not os.path.isfile(json_path):
            return
        with open(json_path, "r", encoding="utf-8") as f:
            template = json.load(f)

        # Fill model name
        model_name_field.value = template.get("model", "")

        # Clear existing inspection rows & data
        inspection_list.controls.clear()
        inspection_data.clear()
        inspection_counter["value"] = 0

        model_base = os.path.join(MODEL_DIR, selected)
        inspections = template.get("inspections", [])
        for insp in inspections:
            row = make_inspection_row()
            inspection_list.controls.append(row)
            data_entry = inspection_data[-1]  # last added by make_inspection_row

            # Fill name & description
            data_entry["name_field"].value = insp.get("name", "")
            data_entry["desc_field"].value = insp.get("description", "")

            # Fill crop_ref
            roi = insp.get("crop_roi", [])
            if roi:
                data_entry["crop_ref"]["roi"] = tuple(roi)
            data_entry["crop_ref"]["source"] = insp.get("source_image", "")

            # Load all template images (multi-crop)
            img_paths_rel = insp.get("image_paths", [])
            if not img_paths_rel:
                # backward compat: single image_path
                single = insp.get("image_path", "")
                if single:
                    img_paths_rel = [single]

            for img_rel in img_paths_rel:
                img_path = os.path.join(model_base, img_rel)
                if os.path.isfile(img_path):
                    data_entry["crops_list"].append({
                        "roi": tuple(roi) if roi else None,
                        "img_path": img_path,
                        "source": insp.get("source_image", ""),
                    })
                    # add thumbnail
                    tmpl_cv = cv2.imread(img_path)
                    if tmpl_cv is not None:
                        tmpl_thumb = cv2.resize(tmpl_cv, (44, 44), interpolation=cv2.INTER_AREA)
                        _, tbuf = cv2.imencode(".jpg", tmpl_thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        tb64 = base64.b64encode(tbuf).decode()
                        data_entry["thumbs_row"].controls.append(
                            _make_thumb_widget(tb64, 44, 44, "#4caf50", 3,
                                               data_entry["crops_list"], data_entry["thumbs_row"],
                                               data_entry["crop_count_label"], "OK")
                        )

            data_entry["crop_count_label"].value = f"{len(data_entry['crops_list'])} OK"

            # Load NG templates
            ng_img_paths_rel = insp.get("ng_image_paths", [])
            for img_rel in ng_img_paths_rel:
                img_path = os.path.join(model_base, img_rel)
                if os.path.isfile(img_path):
                    data_entry["ng_crops_list"].append({
                        "roi": tuple(roi) if roi else None,
                        "img_path": img_path,
                        "source": insp.get("source_image", ""),
                    })
                    tmpl_cv = cv2.imread(img_path)
                    if tmpl_cv is not None:
                        tmpl_thumb = cv2.resize(tmpl_cv, (40, 40), interpolation=cv2.INTER_AREA)
                        _, tbuf = cv2.imencode(".jpg", tmpl_thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        tb64 = base64.b64encode(tbuf).decode()
                        data_entry["ng_thumbs_row"].controls.append(
                            _make_thumb_widget(tb64, 40, 40, "#f44336", 2,
                                               data_entry["ng_crops_list"], data_entry["ng_thumbs_row"],
                                               data_entry["ng_crop_count_label"], "NG")
                        )
            data_entry["ng_crop_count_label"].value = f"{len(data_entry['ng_crops_list'])} NG"

            # Load search_roi
            search_roi = insp.get("search_roi", [])
            if search_roi and len(search_roi) == 4:
                data_entry["search_roi"] = tuple(int(v) for v in search_roi)
                if "roi_label" in data_entry:
                    ox, oy, ow, oh = [int(v) for v in search_roi]
                    data_entry["roi_label"].value = f"ROI: ({ox},{oy}) {ow}×{oh}"

            # Show first image as main preview
            if img_paths_rel:
                first_path = os.path.join(model_base, img_paths_rel[0])
                data_entry["crop_ref"]["img_path"] = first_path
                if os.path.isfile(first_path):
                    tmpl_cv = cv2.imread(first_path)
                    if tmpl_cv is not None:
                        ph, pw = tmpl_cv.shape[:2]
                        ps = min(280 / pw, 160 / ph, 1.0)
                        prev_img = cv2.resize(tmpl_cv, (int(pw*ps), int(ph*ps)), interpolation=cv2.INTER_AREA)
                        _, buf = cv2.imencode(".jpg", prev_img, [cv2.IMWRITE_JPEG_QUALITY, 72])
                        b64 = base64.b64encode(buf).decode()
                        data_entry["preview_img"].src = f"data:image/jpeg;base64,{b64}"
                        data_entry["preview_img"].visible = True
                        data_entry["preview_placeholder"].visible = False

        # Reverse so latest (highest number) is on top, 1 at bottom
        inspection_list.controls.reverse()
        total = len(inspection_list.controls)
        for i, r in enumerate(inspection_list.controls):
            r.controls[0].value = str(total - i)

        if not inspections:
            # Add one empty row if model has no inspections
            inspection_list.controls.append(make_inspection_row())

        e.page.update()

    #  Feature Matching Test
    def test_clicked(e):
        page = e.page
        cv_img = image_state.get("cv_img")
        if cv_img is None:
            print("[TEST] No image loaded")
            return
        selected_model = model_dropdown.value
        if not selected_model:
            print("[TEST] No model selected")
            return
        json_path = os.path.join(MODEL_DIR, selected_model, f"{selected_model}.json")
        if not os.path.isfile(json_path):
            print(f"[TEST] JSON not found: {json_path}")
            return

        # Show loading indicator immediately
        result_list.controls.clear()
        result_list.controls.append(ft.Text("Testing...", size=13, color="#888888"))
        page.update()

        def do_test():
            try:
                print(f"[TEST] Starting FPM test with model: {selected_model}")
                with open(json_path, "r", encoding="utf-8") as f:
                    template = json.load(f)
                model_base = os.path.join(MODEL_DIR, selected_model)
                # match_scale เหมือน home.py: matching บน scene เล็ก, วาด overlay บน full-res
                img_h, img_w = cv_img.shape[:2]
                match_scale = min(800 / max(img_w, img_h), 1.0)
                scene_match = (cv2.resize(cv_img,
                                          (int(img_w * match_scale), int(img_h * match_scale)),
                                          interpolation=cv2.INTER_AREA)
                               if match_scale < 1.0 else cv_img)
                inv = 1.0 / match_scale if match_scale > 0 else 1.0

                result_img = cv_img.copy()
                insp_results = []
                ng_summary   = []

                for insp in template.get("inspections", []):
                    img_paths_rel = insp.get("image_paths", [])
                    if not img_paths_rel:
                        single = insp.get("image_path", "")
                        if single:
                            img_paths_rel = [single]
                    insp_id   = insp.get("name", "?")
                    insp_desc = insp.get("description", "")

                    # โหลด template ที่ match_scale
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
                        print(f"[TEST]   '{insp_id}' – no templates")
                        continue

                    # ROI ใน scene_match coordinates
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

                    print(f"[TEST]   FPM '{insp_id}' ({len(fpm_tmpls)} templates) ...")
                    hits = match_fpm(roi_scene, fpm_tmpls,
                                     score_threshold=0.50, max_overlap=0.3, tolerance_angle=0)

                    # scale ขึ้น full-res สำหรับ drawing
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
                            bx, by, bw, bh = best_ok["bbox"]
                            adj["bbox"] = (bx+rx, by+ry, bw, bh)
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
                                    bx, by, bw, bh = best_ng["bbox"]
                                    ng_adj["bbox"] = (bx+rx, by+ry, bw, bh)
                                    best_ng = ng_adj
                                ng_best_f = dict(best_ng)
                                ng_best_f["rect_points"] = [(int(p[0]*inv), int(p[1]*inv)) for p in best_ng["rect_points"]]
                                ng_best_f["center"] = (int(best_ng["center"][0]*inv), int(best_ng["center"][1]*inv))
                                bx, by, bw_b, bh_b = best_ng["bbox"]
                                ng_best_f["bbox"] = (int(bx*inv), int(by*inv), int(bw_b*inv), int(bh_b*inv))
                                ng_score = best_ng["score"]

                    # Decision: compare scores — higher wins
                    if ok_score is None and ng_score is None:
                        ng_summary.append((insp_id, insp_desc))
                        if has_roi:
                            overlay = result_img.copy()
                            cv2.rectangle(overlay, (frx, fry), (frx+frw, fry+frh), (100, 100, 220), -1)
                            cv2.addWeighted(overlay, 0.25, result_img, 0.75, 0, result_img)
                            cv2.rectangle(result_img, (frx, fry), (frx+frw, fry+frh), (0, 0, 220), 2)
                            _put_label(result_img, f"{insp_id} NG", frx, max(fry - 8, 18), bg=(0, 0, 160))
                        insp_results.append((insp_id, None, None, False))
                        print(f"[TEST]   '{insp_id}' – no match")
                    elif ok_score is not None and (ng_score is None or ok_score >= ng_score):
                        crop_cv = crop_fpm_region(cv_img, ok_best_f)
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
                        print(f"[TEST]   '{insp_id}': OK s={ok_score:.3f}" + (f" vs NG s={ng_score:.3f}" if ng_score else ""))
                    else:
                        ng_summary.append((insp_id, insp_desc))
                        crop_cv = crop_fpm_region(cv_img, ng_best_f)
                        if has_roi:
                            overlay = result_img.copy()
                            cv2.rectangle(overlay, (frx, fry), (frx+frw, fry+frh), (100, 100, 220), -1)
                            cv2.addWeighted(overlay, 0.25, result_img, 0.75, 0, result_img)
                            cv2.rectangle(result_img, (frx, fry), (frx+frw, fry+frh), (0, 0, 220), 2)
                            _put_label(result_img, f"{insp_id} NG", frx, max(fry - 8, 18), bg=(0, 0, 160))
                        insp_results.append((insp_id, ng_score, crop_cv, False))
                        print(f"[TEST]   '{insp_id}': NG s={ng_score:.3f}" + (f" vs OK s={ok_score:.3f}" if ok_score else ""))

                _draw_ng_banner(result_img, ng_summary)

                # ── Prepare display data in thread (CPU-bound) ────────────────
                h, w = result_img.shape[:2]
                scale = min(DISP_H / h, 1.0)
                disp_w, disp_h = int(w * scale), int(h * scale)
                result_disp = cv2.resize(result_img, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode(".jpg", result_disp, [cv2.IMWRITE_JPEG_QUALITY, 85])
                img_bytes = bytes(buf)
                _hide_handles()

                prepared = []
                for insp_id, sc, crop_cv, is_pass in insp_results:
                    if crop_cv is not None:
                        ch, cw = crop_cv.shape[:2]
                        cscale = min(200 / cw, 120 / ch, 1.0)
                        thumb = cv2.resize(crop_cv, (int(cw*cscale), int(ch*cscale)), interpolation=cv2.INTER_AREA)
                        _, cbuf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 72])
                        prepared.append((insp_id, bytes(cbuf), is_pass))
                    else:
                        prepared.append((insp_id, None, is_pass))

                n_pass = sum(1 for *_, p in insp_results if p)
                print(f"[TEST] Done. {n_pass}/{len(insp_results)} passed.")

                # ── Push to UI via async task (flushes WebSocket immediately) ──
                _test_done = threading.Event()

                async def _push(ib=img_bytes, dw=disp_w, dh=disp_h, prep=prepared):
                    large_img.src     = ib
                    large_img.width   = dw
                    large_img.height  = dh
                    large_img.visible = True
                    large_img_placeholder.visible = False
                    page.update()

                    result_list.controls.clear()
                    for insp_id, thumb_b, is_pass in prep:
                        if thumb_b is not None:
                            img_w = ft.Image(src=thumb_b, width=200, height=120, fit="contain")
                        else:
                            img_w = ft.Container(
                                width=200, height=120, bgcolor="#f44336",
                                alignment=ft.Alignment(0, 0),
                                content=ft.Text("NG", size=24,
                                                weight=ft.FontWeight.BOLD, color="#ffffff"),
                            )
                        bc = "#4caf50" if is_pass else "#f44336"
                        bg = "#e8f5e9" if is_pass else "#ffebee"
                        tc = "#2e7d32" if is_pass else "#c62828"
                        result_list.controls.append(
                            ft.Container(
                                content=ft.Column(
                                    [img_w, ft.Text(insp_id if is_pass else f"{insp_id}  NG",
                                                    size=10, weight=ft.FontWeight.BOLD, color=tc)],
                                    spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                padding=4, bgcolor=bg,
                                border=ft.Border.all(2, bc), border_radius=4,
                            )
                        )
                    page.update()
                    _test_done.set()

                page.run_task(_push)
                _test_done.wait(timeout=10.0)

            except Exception as ex:
                import traceback
                traceback.print_exc()
                print(f"[TEST] Error: {ex}")

        page.run_thread(do_test)

    # ── Connect camera / Trigger Image (CREATE tab) ───────────────────────────
    # Defined as variable so _on_cam_state can update it
    btn_cam_connect_create = ft.Button(
        "Connect camera", width=120, height=34,
        style=btn_style_sm("#f57c00"),
    )

    def cam_connect_create(e):
        if not _hik:
            return
        pg = e.page
        if _hik.connected:
            _hik.disconnect()
            pg.pubsub.send_all_on_topic("cam_state", False)
            pg.update()
        else:
            try:
                cfg = _cam_mod.load_config()
            except Exception:
                cfg = {}
            ip = cfg.get("camera_ip", "").strip()
            if not ip:
                return
            def _do():
                ok, _ = _hik.connect_by_ip(ip)
                if ok:
                    pg.pubsub.send_all_on_topic("cam_state", True)
                pg.update()
            pg.run_thread(_do)

    btn_cam_connect_create.on_click = cam_connect_create

    def cam_trigger_create(e):
        if not _hik or not _hik.connected:
            return
        def _do():
            frame = _hik.grab_one()
            if frame is not None:
                _, buf = cv2.imencode(".jpg", frame)
                load_image_by_path(None, e.page, img_bytes=buf.tobytes())
            else:
                err = getattr(_hik, "last_error", "") or "unknown error"
                print(f"[Settings] cam_trigger_create grab failed: {err}")
        e.page.run_thread(_do)

    # ── Start / Stop grab+inspect loop ───────────────────────────────────────
    _grab_state = {"running": False}

    btn_start_grab = ft.Button(
        "Start", width=120, height=34,
        style=btn_style_sm("#43a047"),
    )

    def _set_grab_btn(running: bool):
        btn_start_grab.text  = "Stop" if running else "Start"
        btn_start_grab.style = btn_style_sm("#e53935" if running else "#43a047")

    _grab_ui_done = threading.Event()

    def _grab_loop(pg, model_name):
        print(f"[Grab] loop started, model={model_name}")
        if _hik._streaming:
            _hik.stop_streaming()
            time.sleep(0.1)
        ok, msg = _hik.start_streaming(preserve_trigger=True)
        print(f"[Grab] start_streaming: {ok} — {msg}")
        if not ok:
            _grab_state["running"] = False
            _set_grab_btn(False)
            pg.run_task(_async_noop)
            return

        while _grab_state["running"]:
            t0 = time.monotonic()
            frame = _hik.get_frame(timeout_ms=3000)
            t1 = time.monotonic()
            if frame is None:
                continue
            if not _grab_state["running"]:
                break

            result_img, is_pass, insp_results = _do_inspect(frame, model_name)
            t2 = time.monotonic()

            # ── Prepare display data in thread (CPU-bound) ────────────────────
            h, w   = result_img.shape[:2]
            scale  = min(DISP_H / h, 1.0)
            dw, dh = int(w * scale), int(h * scale)
            disp   = cv2.resize(result_img, (dw, dh), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode(".jpg", disp, [cv2.IMWRITE_JPEG_QUALITY, 80])
            img_bytes = bytes(buf)

            # Pre-encode thumbnails in thread so async task is lightweight
            prepared = []
            for insp_id, sc, crop_cv, ok in insp_results:
                if crop_cv is not None:
                    ch, cw  = crop_cv.shape[:2]
                    cs      = min(200 / cw, 120 / ch, 1.0)
                    thumb   = cv2.resize(crop_cv, (int(cw*cs), int(ch*cs)),
                                         interpolation=cv2.INTER_AREA)
                    _, cbuf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    prepared.append((insp_id, bytes(cbuf), ok))
                else:
                    prepared.append((insp_id, None, ok))

            # ── Push to UI via async task (flushes WebSocket immediately) ─────
            _grab_ui_done.clear()

            async def _push(ib=img_bytes, dw_=dw, dh_=dh, fr=frame,
                            prep=prepared, _t0=t0, _t1=t1, _t2=t2, sc=scale):
                t3 = time.monotonic()
                large_img.src     = ib
                large_img.width   = dw_
                large_img.height  = dh_
                large_img.visible = True
                large_img_placeholder.visible = False
                image_state["cv_img"] = fr
                image_state["scale"]  = sc
                image_state["act_w"]  = dw_
                image_state["act_h"]  = dh_
                large_img_container.width = dw_
                pg.update()
                t4 = time.monotonic()

                result_list.controls.clear()
                for insp_id, thumb_b, ok_ in prep:
                    if thumb_b is not None:
                        img_w = ft.Image(src=thumb_b, width=200, height=120, fit="contain")
                    else:
                        img_w = ft.Container(
                            width=200, height=120, bgcolor="#f44336",
                            alignment=ft.Alignment(0, 0),
                            content=ft.Text("NG", size=24,
                                            weight=ft.FontWeight.BOLD, color="#ffffff"),
                        )
                    bc = "#4caf50" if ok_ else "#f44336"
                    bg = "#e8f5e9" if ok_ else "#ffebee"
                    tc = "#2e7d32" if ok_ else "#c62828"
                    result_list.controls.append(
                        ft.Container(
                            content=ft.Column(
                                [img_w, ft.Text(insp_id if ok_ else f"{insp_id}  NG",
                                                size=10, weight=ft.FontWeight.BOLD, color=tc)],
                                spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            padding=4, bgcolor=bg,
                            border=ft.Border.all(2, bc), border_radius=4,
                        )
                    )
                pg.update()
                t5 = time.monotonic()

                print(
                    f"[Grab] get_frame={1000*(_t1-_t0):.0f}ms  "
                    f"inspect={1000*(_t2-_t1):.0f}ms  "
                    f"img_update={1000*(t4-t3):.0f}ms  "
                    f"cards_update={1000*(t5-t4):.0f}ms  "
                    f"total={1000*(t5-_t0):.0f}ms"
                )
                _grab_ui_done.set()

            pg.run_task(_push)
            _grab_ui_done.wait(timeout=5.0)   # wait for async flush before next frame

        _hik.stop_streaming()
        print("[Grab] loop stopped")

    def toggle_grab(e):
        pg = e.page
        if _grab_state["running"]:
            _grab_state["running"] = False
            _set_grab_btn(False)
            pg.update()
        else:
            if not _hik or not _hik.connected:
                return
            model = model_dropdown.value
            if not model:
                return
            _grab_state["running"] = True
            _set_grab_btn(True)
            pg.update()
            pg.run_thread(lambda: _grab_loop(pg, model))

    btn_start_grab.on_click = toggle_grab

    #  Create Model panel
    create_model_view = ft.Row(
        [
            # RAW+RESULT+MODEL box + buttons below
            ft.Column(
                [
                    raw_result_box,
                    ft.Row(
                        [
                            model_dropdown,
                            btn_cam_connect_create,
                            ft.Button("Open",           width=120, height=34, style=btn_style_sm("#f57c00"),
                                      on_click=open_images_clicked),
                            ft.Button("Previous",       width=120, height=34, style=btn_style_sm("#f57c00"),
                                      on_click=previous_image_clicked),
                            ft.Button("Next",           width=120, height=34, style=btn_style_sm("#f57c00"),
                                      on_click=next_image_clicked),
                            ft.Button("Trigger Image",  width=120, height=34, style=btn_style_sm("#f57c00"),
                                      on_click=cam_trigger_create),
                            ft.Button("Test",           width=120, height=34, style=btn_style_sm("#f57c00"),
                                      on_click=test_clicked),
                            btn_start_grab,
                            ft.Container(expand=True),
                            ft.Button("ADD INSPECTION", width=160, height=34,
                                style=ft.ButtonStyle(bgcolor={"":"#ffffff"}, color={"":"#222222"},
                                    shape=ft.RoundedRectangleBorder(radius=4), side=ft.BorderSide(1,"#888888"),
                                    text_style=ft.TextStyle(size=11)),
                                on_click=add_inspection),
                            ft.Button("DELETE", width=110, height=34,
                                style=ft.ButtonStyle(bgcolor={"":"#ffffff"}, color={"":"#e53935"},
                                    shape=ft.RoundedRectangleBorder(radius=4), side=ft.BorderSide(1,"#e53935")),
                                on_click=delete_last),
                            ft.Button("SAVE", width=110, height=34,
                                style=ft.ButtonStyle(bgcolor={"":"#4caf50"}, color={"":"#ffffff"},
                                    shape=ft.RoundedRectangleBorder(radius=4)),
                                on_click=save_template),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=4,
                expand=True,
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.START,
        alignment=ft.MainAxisAlignment.CENTER,
        expand=True,
    )

    create_model_view = ft.Column(
        [create_model_view],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )

    # ── Camera Setting panel (HikRobot MVS SDK — connect by IP) ──────────────
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        import camera_manager as _cam_mod
        _hik = _cam_mod.get_camera()
        _cfg = _cam_mod.load_config()
    except Exception:
        _hik = None
        _cfg = {}

    _sdk_ready = _hik is not None and _hik.sdk_ok()

    cam_status_dot  = ft.Container(width=10, height=10, border_radius=5, bgcolor="#888888")
    cam_status_text = ft.Text(
        "Ready" if _sdk_ready else f"SDK unavailable: {_hik.sdk_err() if _hik else 'import failed'}",
        size=12, color="#555555",
    )
    cam_info_text = ft.Text("", size=11, color=theme.TEXT_SECONDARY)

    def _cbtn(label, color, handler):
        return ft.Button(
            label, height=32,
            style=ft.ButtonStyle(
                bgcolor={"": color}, color={"": "#ffffff"},
                shape=ft.RoundedRectangleBorder(radius=4),
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                text_style=ft.TextStyle(size=12),
            ),
            on_click=handler,
        )

    def _set_status(text, color, page):
        cam_status_text.value = text
        cam_status_dot.bgcolor = color
        page.update()

    # ── Input fields ──────────────────────────────────────────────────────────
    def _tf(label, val, w):
        return ft.TextField(
            label=label, value=str(val), width=w, text_size=12, border_radius=6,
            content_padding=ft.Padding.symmetric(horizontal=8, vertical=6),
        )

    cam_ip_field = _tf("Camera IP", _cfg.get("camera_ip", "192.168.1.64"), 260)

    # ── Scanned camera list ───────────────────────────────────────────────────
    _scan_ui      = {"selected_idx": -1}
    cam_list_col  = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)
    cam_count_lbl = ft.Text("", size=11, color="#888888")

    def _build_cam_list(page=None):
        cam_list_col.controls.clear()
        cameras = _hik.cameras if _hik else []
        if not cameras:
            cam_list_col.controls.append(
                ft.Container(
                    content=ft.Text("No cameras — click Scan", size=12, color="#aaaaaa", italic=True),
                    alignment=ft.Alignment(0, 0), height=50,
                )
            )
            cam_count_lbl.value = ""
        else:
            cam_count_lbl.value = f"{len(cameras)} found"
            for c in cameras:
                idx    = c["index"]
                is_sel = _scan_ui["selected_idx"] == idx
                cam_list_col.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Container(
                                content=ft.Text(c["type"], size=10, color="#ffffff",
                                                weight=ft.FontWeight.BOLD),
                                bgcolor="#1565c0" if c["type"] == "GigE" else "#6a1b9a",
                                border_radius=3,
                                padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                            ),
                            ft.Column([
                                ft.Text(c["name"] or "Unknown", size=12,
                                        weight=ft.FontWeight.W_500, color=theme.TEXT_PRIMARY),
                                ft.Text(c["ip"], size=10, color=theme.TEXT_SECONDARY),
                            ], spacing=0, expand=True),
                            ft.Icon(
                                ft.Icons.RADIO_BUTTON_CHECKED if is_sel
                                else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                color="#1976d2" if is_sel else "#cccccc", size=18,
                            ),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor="#e3f2fd" if is_sel else "#fafafa",
                        border=ft.Border.all(1.5, "#1976d2" if is_sel else "#e0e0e0"),
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        on_click=lambda e, i=idx: _select_cam(e, i),
                        ink=True,
                    )
                )
        if page:
            page.update()

    def _select_cam(e, idx):
        _scan_ui["selected_idx"] = idx
        # Fill IP field with selected camera IP
        cameras = _hik.cameras if _hik else []
        for c in cameras:
            if c["index"] == idx:
                cam_ip_field.value = c["ip"]
                break
        _build_cam_list(e.page)

    # ── Actions ───────────────────────────────────────────────────────────────
    def do_scan(e):
        page = e.page
        _set_status("Scanning network...", "#ff9800", page)
        def _scan():
            cameras = _hik.enum_devices() if _hik else []
            _scan_ui["selected_idx"] = -1
            _build_cam_list()
            _set_status(
                f"Found {len(cameras)} camera(s)" if cameras else "No cameras found on network",
                "#4caf50" if cameras else "#888888",
                page,
            )
        page.run_thread(_scan)

    def do_connect_ip(e):
        page = e.page
        ip = cam_ip_field.value.strip()
        if not ip:
            _set_status("Enter camera IP address", "#f44336", page)
            return
        _set_status(f"Connecting to {ip}...", "#ff9800", page)
        def _conn():
            ok, msg = _hik.connect_by_ip(ip) if _hik else (False, "SDK not available")
            cam_info_text.value = ""
            if ok:
                try: _cam_mod.save_config({"camera_ip": ip, "net_ip": ""})
                except Exception: pass
                _apply_params(page)
                page.pubsub.send_all_on_topic("cam_state", True)
            _set_status(msg, "#4caf50" if ok else "#f44336", page)
        page.run_thread(_conn)

    def do_connect_scan(e):
        page = e.page
        idx = _scan_ui["selected_idx"]
        if idx < 0:
            _set_status("Select a camera from the list first", "#f44336", page)
            return
        _set_status("Connecting...", "#ff9800", page)
        def _conn():
            ok, msg = _hik.connect_by_index(idx) if _hik else (False, "SDK not available")
            if ok:
                _apply_params(page)
                page.pubsub.send_all_on_topic("cam_state", True)
            _set_status(msg, "#4caf50" if ok else "#f44336", page)
        page.run_thread(_conn)

    def do_disconnect(e):
        if _hik:
            _hik.disconnect()
        cam_info_text.value = ""
        _set_status("Disconnected", "#888888", e.page)
        e.page.pubsub.send_all_on_topic("cam_state", False)

    # ── Parameters ────────────────────────────────────────────────────────────
    exp_field  = _tf("Exposure (µs)", "10000", 160)
    gain_field = _tf("Gain (dB)",     "1.00",  160)
    fps_field  = _tf("Frame Rate",    "25.0",  160)
    trig_dd    = ft.Dropdown(
        label="Trigger Mode", width=160, text_size=12, value="OFF",
        options=[ft.dropdown.Option("OFF"), ft.dropdown.Option("ON")],
        border_radius=6,
        content_padding=ft.Padding.only(left=10, right=0, top=4, bottom=4),
    )

    def _apply_params(page):
        """Read params from camera and update UI fields."""
        p = _hik.get_params() if _hik else None
        if p:
            exp_field.value  = f"{p['exposure']:.0f}"
            gain_field.value = f"{p['gain']:.2f}"
            fps_field.value  = f"{p['frame_rate']:.1f}"
            page.update()

    def do_get_params(e):
        if not _hik or not _hik.connected:
            _set_status("Not connected", "#f44336", e.page)
            return
        _apply_params(e.page)
        _set_status("Parameters read", "#4caf50", e.page)

    def do_set_params(e):
        page = e.page
        if not _hik or not _hik.connected:
            _set_status("Not connected", "#f44336", page)
            return
        try:
            exp  = float(exp_field.value  or "10000")
            gain = float(gain_field.value or "1.0")
            fps  = float(fps_field.value  or "25.0")
            trig = trig_dd.value == "ON"
        except ValueError:
            _set_status("Invalid parameter value", "#f44336", page)
            return
        _set_status("Applying...", "#ff9800", page)
        def _apply():
            ok, msg = _hik.set_params(exposure=exp, gain=gain, frame_rate=fps, trigger_on=trig)
            _set_status(msg, "#4caf50" if ok else "#f44336", page)
        page.run_thread(_apply)

    # ── Live preview ──────────────────────────────────────────────────────────
    prev_placeholder = ft.Text("กำลังรอสัญญาณกล้อง...", size=14, color="#aaaaaa", italic=True)
    prev_img         = ft.Image(src=b"", visible=False, fit="contain", expand=True,
                                gapless_playback=True)
    prev_info_text   = ft.Text("", size=11, color="#888888")

    _live = {"running": False, "pg": None, "lock": threading.Lock()}

    def _start_live(pg):
        with _live["lock"]:
            if _live["running"]:
                return
            if not _hik or not _hik.connected:
                return
            _live["running"] = True
        _live["pg"]      = pg
        prev_placeholder.value   = "กำลังโหลดภาพ..."
        prev_placeholder.visible = True
        prev_img.visible         = False
        prev_info_text.value     = ""

        def _loop():
            import base64 as _b64
            print(f"[Live] _loop started, connected={_hik.connected}, streaming={_hik._streaming}")

            # Stop any existing stream, then start in continuous mode (TriggerMode=Off)
            was_streaming = _hik._streaming
            if was_streaming:
                print("[Live] stopping existing stream first")
                _hik.stop_streaming()
                time.sleep(0.15)

            ok, msg = _hik.start_streaming(preserve_trigger=True)
            print(f"[Live] start_streaming: {ok} — {msg}, _streaming={_hik._streaming}")
            if not ok:
                _live["running"] = False
                return

            PREVIEW_W    = 1024         # width cap for live preview
            TARGET_FPS   = 15
            _interval    = 1.0 / TARGET_FPS
            _pending     = {"v": False}
            _t_last      = [0.0]
            _first_shown = [False]

            async def _push(data: bytes, info: str, first: bool):
                prev_img.src         = data
                prev_info_text.value = info
                if first:
                    prev_img.visible         = True
                    prev_placeholder.visible = False
                    pg.update()
                else:
                    prev_img.update()
                    prev_info_text.update()
                await asyncio.sleep(0)
                _pending["v"] = False

            while _live["running"]:
                now     = time.monotonic()
                elapsed = now - _t_last[0]
                if elapsed < _interval:
                    time.sleep(_interval - elapsed)
                    continue

                frame = _hik.get_frame(timeout_ms=2000)
                if frame is None:
                    continue
                if _pending["v"]:
                    continue

                _t_last[0] = time.monotonic()
                orig_h, orig_w = frame.shape[:2]
                h, w = orig_h, orig_w
                if w > PREVIEW_W:
                    scale = PREVIEW_W / w
                    frame = cv2.resize(frame, (PREVIEW_W, int(h * scale)),
                                       interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                data  = bytes(buf)
                info  = f"{orig_w}×{orig_h}"
                first = not _first_shown[0]
                if first:
                    _first_shown[0] = True
                _pending["v"] = True
                pg.run_task(_push, data, info, first)

            _hik.stop_streaming()
            prev_info_text.value = ""

        threading.Thread(target=_loop, daemon=True).start()

    def _stop_live():
        # Just signal the loop to stop — it exits within frame_timeout ms (500ms)
        # and handles stream cleanup itself
        _live["running"] = False

    # ── Inspection (Start button) ─────────────────────────────────────────────
    _inspect_state = {"running": False, "model": None}

    async def _async_noop():
        pass

    _tmpl_cache_s: dict = {}   # (path, scale) -> cv2 image
    _json_cache_s: dict = {}   # model_name -> (mtime, template_dict)

    def _load_tmpl_s(path: str, scale: float):
        key = (path, round(scale, 4))
        if key not in _tmpl_cache_s:
            t = cv2.imread(path)
            if t is not None and scale < 1.0:
                t = cv2.resize(t,
                               (max(1, int(t.shape[1] * scale)),
                                max(1, int(t.shape[0] * scale))),
                               interpolation=cv2.INTER_AREA)
            _tmpl_cache_s[key] = t
        return _tmpl_cache_s.get(key)

    def _do_inspect(frame, model_name):
        """Run FPM inspection. Returns (result_img, is_pass, insp_results) or (frame, None, [])."""
        try:
            json_path = os.path.join(MODEL_DIR, model_name, f"{model_name}.json")
            if not os.path.isfile(json_path):
                return frame, None, []

            # Cache JSON — only re-read when file changes on disk
            mtime = os.path.getmtime(json_path)
            if _json_cache_s.get(model_name, (None,))[0] != mtime:
                with open(json_path, "r", encoding="utf-8") as f:
                    _json_cache_s[model_name] = (mtime, json.load(f))
            template = _json_cache_s[model_name][1]

            model_base   = os.path.join(MODEL_DIR, model_name)
            img_h, img_w = frame.shape[:2]
            match_scale  = min(640 / max(img_w, img_h), 1.0)  # 640 is faster than 800
            scene_match  = (cv2.resize(frame,
                                       (int(img_w * match_scale), int(img_h * match_scale)),
                                       interpolation=cv2.INTER_AREA)
                            if match_scale < 1.0 else frame)
            inv          = 1.0 / match_scale if match_scale > 0 else 1.0
            result_img   = frame.copy()
            ng_summary   = []
            insp_results = []

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
                    t = _load_tmpl_s(os.path.join(model_base, rel), match_scale)
                    if t is not None:
                        fpm_tmpls.append((insp_id, t))
                if not fpm_tmpls:
                    ng_summary.append((insp_id, insp_desc))
                    insp_results.append((insp_id, None, None, False))
                    continue

                sroi = insp.get("search_roi", [])
                if sroi and len(sroi) == 4:
                    sm_h, sm_w = scene_match.shape[:2]
                    rx = max(0, min(int(sroi[0] * match_scale), sm_w - 1))
                    ry = max(0, min(int(sroi[1] * match_scale), sm_h - 1))
                    rw = min(int(sroi[2] * match_scale), sm_w - rx)
                    rh = min(int(sroi[3] * match_scale), sm_h - ry)
                    has_roi   = rw > 1 and rh > 1
                    roi_scene = scene_match[ry:ry+rh, rx:rx+rw] if has_roi else scene_match
                else:
                    roi_scene      = scene_match
                    rx, ry, rw, rh = 0, 0, 0, 0
                    has_roi        = False

                hits = match_fpm(roi_scene, fpm_tmpls, score_threshold=0.50,
                                 max_overlap=0.3, tolerance_angle=0)
                frx = int(rx * inv); fry = int(ry * inv)
                frw = int(rw * inv); frh = int(rh * inv)

                ok_best_f, ok_score = None, None
                if hits:
                    best_ok = max(hits, key=lambda h: h["score"])
                    if has_roi:
                        adj = dict(best_ok)
                        adj["rect_points"] = [(pt[0]+rx, pt[1]+ry) for pt in best_ok["rect_points"]]
                        adj["center"]      = (best_ok["center"][0]+rx, best_ok["center"][1]+ry)
                        bx, by, bw_b, bh_b = best_ok["bbox"]
                        adj["bbox"]        = (bx+rx, by+ry, bw_b, bh_b)
                        best_ok            = adj
                    ok_best_f = dict(best_ok)
                    ok_best_f["rect_points"] = [(int(p[0]*inv), int(p[1]*inv)) for p in best_ok["rect_points"]]
                    ok_best_f["center"]      = (int(best_ok["center"][0]*inv), int(best_ok["center"][1]*inv))
                    bx, by, bw_b, bh_b       = best_ok["bbox"]
                    ok_best_f["bbox"]         = (int(bx*inv), int(by*inv), int(bw_b*inv), int(bh_b*inv))
                    ok_score                  = best_ok["score"]

                # Batch all NG templates into a single match_fpm call (faster than one call per template)
                ng_best_f, ng_score = None, None
                ng_paths_rel = insp.get("ng_image_paths", [])
                if ng_paths_rel:
                    ng_tmpls = []
                    for rel in ng_paths_rel:
                        t = _load_tmpl_s(os.path.join(model_base, rel), match_scale)
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
                                ng_adj["center"]      = (best_ng["center"][0]+rx, best_ng["center"][1]+ry)
                                bx, by, bw_b, bh_b   = best_ng["bbox"]
                                ng_adj["bbox"]        = (bx+rx, by+ry, bw_b, bh_b)
                                best_ng               = ng_adj
                            ng_best_f = dict(best_ng)
                            ng_best_f["rect_points"] = [(int(p[0]*inv), int(p[1]*inv)) for p in best_ng["rect_points"]]
                            ng_best_f["center"]      = (int(best_ng["center"][0]*inv), int(best_ng["center"][1]*inv))
                            bx, by, bw_b, bh_b       = best_ng["bbox"]
                            ng_best_f["bbox"]         = (int(bx*inv), int(by*inv), int(bw_b*inv), int(bh_b*inv))
                            ng_score                  = best_ng["score"]

                if ok_score is None and ng_score is None:
                    ng_summary.append((insp_id, insp_desc))
                    if has_roi:
                        overlay = result_img.copy()
                        cv2.rectangle(overlay, (frx, fry), (frx+frw, fry+frh), (100, 100, 220), -1)
                        cv2.addWeighted(overlay, 0.25, result_img, 0.75, 0, result_img)
                        cv2.rectangle(result_img, (frx, fry), (frx+frw, fry+frh), (0, 0, 220), 2)
                        _put_label(result_img, f"{insp_id} NG", frx, max(fry-8, 18), bg=(0, 0, 160))
                    insp_results.append((insp_id, None, None, False))
                elif ok_score is not None and (ng_score is None or ok_score >= ng_score):
                    crop_cv = crop_fpm_region(frame, ok_best_f)
                    if has_roi:
                        overlay = result_img.copy()
                        cx, cy   = ok_best_f["center"]
                        drx, dry = cx - frw//2, cy - frh//2
                        cv2.rectangle(overlay, (drx, dry), (drx+frw, dry+frh), (144, 238, 144), -1)
                        cv2.addWeighted(overlay, 0.30, result_img, 0.70, 0, result_img)
                        cv2.rectangle(result_img, (drx, dry), (drx+frw, dry+frh), (0, 200, 0), 2)
                        _put_label(result_img, insp_id, drx, max(dry-8, 18), bg=(0, 120, 0))
                    else:
                        draw_fpm_match(result_img, ok_best_f, label=insp_id)
                    insp_results.append((insp_id, ok_score, crop_cv, True))
                else:
                    ng_summary.append((insp_id, insp_desc))
                    crop_cv = crop_fpm_region(frame, ng_best_f) if ng_best_f is not None else None
                    if has_roi:
                        overlay = result_img.copy()
                        cv2.rectangle(overlay, (frx, fry), (frx+frw, fry+frh), (100, 100, 220), -1)
                        cv2.addWeighted(overlay, 0.25, result_img, 0.75, 0, result_img)
                        cv2.rectangle(result_img, (frx, fry), (frx+frw, fry+frh), (0, 0, 220), 2)
                        _put_label(result_img, f"{insp_id} NG", frx, max(fry-8, 18), bg=(0, 0, 160))
                    insp_results.append((insp_id, ng_score, crop_cv, False))

            _draw_ng_banner(result_img, ng_summary)
            return result_img, (len(ng_summary) == 0), insp_results
        except Exception as ex:
            print(f"[Inspect] error: {ex}")
            import traceback; traceback.print_exc()
            return frame, None, []

    _build_cam_list()

    camera_setting_view = ft.Container(
        content=ft.Row(
            [
                # ── Left: controls ────────────────────────────────────────────
                ft.Container(
                    content=ft.Column(
                        [
                            # Status bar
                            ft.Container(
                                content=ft.Row(
                                    [cam_status_dot, cam_status_text,
                                     ft.Container(expand=True), cam_info_text],
                                    spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                bgcolor="#f5f5f5", border_radius=6,
                                border=ft.Border.all(1, "#e0e0e0"),
                                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                            ),

                            # Connect by IP card
                            ft.Container(
                                content=ft.Column([
                                    ft.Text("CONNECT BY IP", size=12,
                                            weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                    cam_ip_field,
                                    ft.Row([
                                        _cbtn("Connect", "#1976d2", do_connect_ip),
                                        _cbtn("Disconnect", "#d32f2f", do_disconnect),
                                    ], spacing=6),
                                ], spacing=10),
                                bgcolor="#ffffff", border_radius=8,
                                border=ft.Border.all(1, "#e0e0e0"),
                                padding=ft.Padding.all(12),
                                shadow=ft.BoxShadow(blur_radius=4, color="#00000012",
                                                    offset=ft.Offset(0, 2)),
                            ),

                            # Scan card
                            ft.Container(
                                content=ft.Column([
                                    ft.Row([
                                        ft.Text("SCAN NETWORK", size=12,
                                                weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                        ft.Container(expand=True),
                                        cam_count_lbl,
                                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                    ft.Container(
                                        content=cam_list_col, height=140,
                                        border=ft.Border.all(1, "#e0e0e0"),
                                        border_radius=6, padding=6,
                                        clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                    ),
                                    ft.Row([
                                        _cbtn("Scan", "#607d8b", do_scan),
                                        _cbtn("Connect Selected", "#1976d2", do_connect_scan),
                                    ], spacing=6),
                                ], spacing=8),
                                bgcolor="#ffffff", border_radius=8,
                                border=ft.Border.all(1, "#e0e0e0"),
                                padding=ft.Padding.all(12),
                                shadow=ft.BoxShadow(blur_radius=4, color="#00000012",
                                                    offset=ft.Offset(0, 2)),
                            ),

                            # Parameters card
                            ft.Container(
                                content=ft.Column([
                                    ft.Text("PARAMETERS", size=12,
                                            weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                    ft.Row([exp_field,  gain_field], spacing=8),
                                    ft.Row([fps_field,  trig_dd],   spacing=8),
                                    ft.Row([
                                        _cbtn("Read",  "#607d8b", do_get_params),
                                        _cbtn("Apply", "#43a047", do_set_params),
                                    ], spacing=6),
                                ], spacing=10),
                                bgcolor="#ffffff", border_radius=8,
                                border=ft.Border.all(1, "#e0e0e0"),
                                padding=ft.Padding.all(12),
                                shadow=ft.BoxShadow(blur_radius=4, color="#00000012",
                                                    offset=ft.Offset(0, 2)),
                            ),

                        ],
                        spacing=12,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    width=430,
                    padding=ft.Padding.all(12),
                ),

                # ── Right: live preview ───────────────────────────────────────
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row([
                                ft.Text("LIVE PREVIEW", size=12, weight=ft.FontWeight.BOLD,
                                        color=theme.TEXT_PRIMARY),
                                ft.Container(expand=True),
                                prev_info_text,
                            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Container(
                                content=ft.Stack([
                                    ft.Container(
                                        content=prev_placeholder,
                                        expand=True,
                                        alignment=ft.Alignment(0, 0),
                                        bgcolor="#f5f5f5",
                                    ),
                                    ft.Container(
                                        content=prev_img,
                                        expand=True,
                                        alignment=ft.Alignment(0, 0),
                                    ),
                                ], expand=True),
                                expand=True,
                                border=ft.Border.all(1, "#cccccc"),
                                border_radius=8,
                                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                bgcolor="#f5f5f5",
                                alignment=ft.Alignment(0, 0),
                            ),
                        ],
                        spacing=8,
                        expand=True,
                    ),
                    expand=True,
                    padding=ft.Padding.all(12),
                ),
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        expand=True,
        bgcolor=theme.BG_COLOR,
    )

    # ── Sync camera connection state across all pages ─────────────────────────
    def _apply_cam_state_settings(connected: bool, pg=None):
        """Update both tabs' camera widgets based on connection state."""
        if connected:
            cam_status_dot.bgcolor  = "#4caf50"
            cam_status_text.value   = "Connected"
            btn_cam_connect_create.text  = "Disconnect"
            btn_cam_connect_create.style = btn_style_sm("#f44336")
            if active_tab["value"] == "camera" and pg:
                _start_live(pg)
        else:
            cam_status_dot.bgcolor  = "#888888"
            cam_status_text.value   = "Disconnected"
            btn_cam_connect_create.text  = "Connect camera"
            btn_cam_connect_create.style = btn_style_sm("#f57c00")
            _grab_state["running"] = False
            _set_grab_btn(False)
            _stop_live()
            prev_img.visible         = False
            prev_placeholder.value   = "กำลังรอสัญญาณกล้อง..."
            prev_placeholder.visible = True
            prev_info_text.value     = ""

    def _on_cam_state_settings(_topic, connected):
        _apply_cam_state_settings(connected, page)
        page.update()

    page.pubsub.subscribe_topic("cam_state", _on_cam_state_settings)

    def show_tab(tab):
        prev_tab = active_tab["value"]
        active_tab["value"] = tab
        btn_create.style = tab_style(tab == "create")
        btn_camera.style = tab_style(tab == "camera")
        content_area.content = create_model_view if tab == "create" else camera_setting_view
        # Start live preview when entering camera tab (if connected)
        if tab == "camera" and _hik and _hik.connected:
            _start_live(page)
        # Stop live preview when leaving camera tab
        elif prev_tab == "camera" and tab != "camera":
            _stop_live()
        content_area.update()
        btn_create.update()
        btn_camera.update()

    btn_create.on_click = lambda e: show_tab("create")
    btn_camera.on_click = lambda e: show_tab("camera")

    # default view
    content_area.content = create_model_view

    #  Full page layout 
    return ft.Container(
        content=ft.Column(
            [
                # Header
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("SETTINGS", size=22, weight=ft.FontWeight.BOLD, color=theme.TEXT_PRIMARY),
                                    ft.Container(expand=True),
                                ],
                                height=48,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Divider(color=ft.Colors.GREY_400, height=1, thickness=1),
                        ],
                        spacing=4,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                ),
                # Sub-tab buttons + algorithm selector
                ft.Container(
                    content=ft.Row([btn_create, btn_camera, ft.Container(expand=True), ft.Container(content=algo_dropdown, visible=False)], spacing=8,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding.only(left=12, right=12, bottom=8),
                ),
                # Content
                content_area,
            ],
            spacing=0,
            expand=True,
        ),
        bgcolor=theme.BG_COLOR,
        expand=True,
    )
