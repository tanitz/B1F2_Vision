"""
Settings Page
"""
import base64
import flet as ft
import cv2
import json
import numpy as np
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog
from config import theme
from fpm_matching import match_fpm, draw_fpm_match, crop_fpm_region


def create_settings_page():

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
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
        )

    btn_create = ft.ElevatedButton("CREATE MODEL", height=34, style=tab_style(True))
    btn_camera = ft.ElevatedButton("CAMERA SETTING", height=34, style=tab_style(False))

    #  Content panels 
    content_area = ft.Container(expand=True, padding=ft.padding.only(left=12, right=12, bottom=12))

    #  Inspection rows 
    inspection_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
    inspection_counter = {"value": 0}
    image_state = {"path": "", "files": [], "index": -1, "cv_img": None, "scale": 1.0, "act_w": 320, "act_h": 570}
    image_counter_text = ft.Text("", size=12, color=theme.TEXT_SECONDARY)
    inspection_data = []
    crop_state = {"active": False, "target": None, "start_x": 0, "start_y": 0, "cur_x": 0, "cur_y": 0}

    def make_inspection_row():
        inspection_counter["value"] += 1
        idx = inspection_counter["value"]
        row_ref = {"row": None}
        crop_ref = {"roi": None, "img_path": None, "source": None}
        crops_list = []  # list of {"roi":..., "img_path":..., "source":...}

        preview_placeholder = ft.Text("IMG", color="#2196f3", weight=ft.FontWeight.BOLD, size=12)
        preview_img = ft.Image(src="placeholder.png", visible=False, fit="contain", width=280, height=160)
        preview_container = ft.Container(
            content=ft.Stack([preview_placeholder, preview_img]),
            width=280, height=160,
            border=ft.border.all(1, "#aaaaaa"),
            border_radius=4,
            alignment=ft.Alignment(0, 0),
            bgcolor="#ffffff",
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

        # thumbnails row for multi-crop
        thumbs_row = ft.Row(spacing=4, scroll=ft.ScrollMode.AUTO, height=50, width=280)

        name_field = ft.TextField(height=28, text_size=12, content_padding=ft.padding.symmetric(horizontal=6, vertical=2), expand=True)
        desc_field = ft.TextField(height=28, text_size=12, content_padding=ft.padding.symmetric(horizontal=6, vertical=2), expand=True)

        crop_count_label = ft.Text("0 templates", size=10, color="#888888")

        data_entry = {"name_field": name_field, "desc_field": desc_field, "crop_ref": crop_ref,
                      "crops_list": crops_list, "thumbs_row": thumbs_row,
                      "crop_count_label": crop_count_label,
                      "row": None, "preview_img": preview_img, "preview_placeholder": preview_placeholder}

        def crop_clicked(e):
            if image_state.get("cv_img") is None:
                return
            crop_state["active"] = True
            crop_state["target"] = data_entry
            selection_rect.visible = False
            crop_label.visible = True
            e.page.update()

        row = ft.Row(
            [
                ft.Text(f"{idx}", size=12, weight=ft.FontWeight.BOLD, width=20, color=theme.TEXT_PRIMARY),
                ft.Column(
                    [
                        preview_container,
                        ft.Row([
                            ft.ElevatedButton("Crop", height=28,
                                style=ft.ButtonStyle(
                                    bgcolor={"":"#2196f3"}, color={"":"#ffffff"},
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                    padding=ft.padding.symmetric(horizontal=8, vertical=2),
                                ),
                                on_click=crop_clicked),
                            crop_count_label,
                        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        thumbs_row,
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
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
        )

    #  Right action buttons 
    right_btns = ft.Column(
        [
            ft.ElevatedButton("Connect camera", width=120, height=34, style=btn_style_sm("#f57c00")),
            ft.ElevatedButton("Trigger Image",  width=120, height=34, style=btn_style_sm("#f57c00")),
            ft.ElevatedButton("Open File",      width=120, height=34, style=btn_style_sm("#f57c00")),
            ft.ElevatedButton("Next",           width=120, height=34, style=btn_style_sm("#f57c00")),
            ft.ElevatedButton("Previous",       width=120, height=34, style=btn_style_sm("#f57c00")),
            ft.ElevatedButton("Test",           width=120, height=34, style=btn_style_sm("#f57c00")),
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
        border=ft.border.all(2, "#ff0000"),
        visible=False,
    )
    crop_label = ft.Container(
        content=ft.Text("CROP MODE - drag to select", color="#ffffff", size=11, weight=ft.FontWeight.BOLD),
        bgcolor="#e53935",
        padding=ft.padding.symmetric(horizontal=8, vertical=2),
        border_radius=4,
        top=4, left=4,
        visible=False,
    )

    def on_pan_start(e):
        if not crop_state["active"]:
            return
        crop_state["start_x"] = e.local_position.x
        crop_state["start_y"] = e.local_position.y
        crop_state["cur_x"] = e.local_position.x
        crop_state["cur_y"] = e.local_position.y
        selection_rect.left = e.local_position.x
        selection_rect.top = e.local_position.y
        selection_rect.width = 0
        selection_rect.height = 0
        selection_rect.visible = True
        e.page.update()

    def on_pan_update(e):
        if not crop_state["active"]:
            return
        crop_state["cur_x"] = e.local_position.x
        crop_state["cur_y"] = e.local_position.y
        sx, sy = crop_state["start_x"], crop_state["start_y"]
        cx, cy = crop_state["cur_x"], crop_state["cur_y"]
        x = max(0, min(sx, cx))
        y = max(0, min(sy, cy))
        act_w = image_state["act_w"]
        act_h = image_state["act_h"]
        w = min(abs(cx - sx), act_w - x)
        h = min(abs(cy - sy), act_h - y)
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
            selection_rect.visible = False
            crop_state["active"] = False
            crop_state["target"] = None
            crop_label.visible = False
            e.page.update()
            return
        cropped = cv_img[oy:oy+oh, ox:ox+ow]
        crop_dir = os.path.join(os.path.dirname(image_state["path"]), "_crops")
        os.makedirs(crop_dir, exist_ok=True)
        crop_path = os.path.join(crop_dir, f"crop_{int(time.time()*1000)}.jpg")
        cv2.imwrite(crop_path, cropped)
        target = crop_state["target"]
        target["crop_ref"]["roi"] = (ox, oy, ow, oh)
        target["crop_ref"]["img_path"] = crop_path
        target["crop_ref"]["source"] = image_state["path"]
        # append to multi-crop list
        target["crops_list"].append({
            "roi": (ox, oy, ow, oh),
            "img_path": crop_path,
            "source": image_state["path"],
        })
        _, buf = cv2.imencode(".jpg", cropped, [cv2.IMWRITE_JPEG_QUALITY, 90])
        b64 = base64.b64encode(buf).decode()
        target["preview_img"].src = f"data:image/jpeg;base64,{b64}"
        target["preview_img"].visible = True
        target["preview_placeholder"].visible = False
        # add thumbnail
        target["thumbs_row"].controls.append(
            ft.Image(src=f"data:image/jpeg;base64,{b64}", width=44, height=44, fit="cover",
                     border_radius=ft.border_radius.all(3))
        )
        target["crop_count_label"].value = f"{len(target['crops_list'])} templates"
        selection_rect.visible = False
        crop_state["active"] = False
        crop_state["target"] = None
        crop_label.visible = False
        e.page.update()

    large_img_container = ft.Container(
        content=ft.GestureDetector(
            content=ft.Stack([large_img_placeholder, large_img, selection_rect, crop_label]),
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
        border=ft.border.only(right=ft.BorderSide(1, "#aaaaaa")),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    #  MODEL panel (inspection list) — content set after model_name_field is defined
    model_panel_col = ft.Column(spacing=8, expand=True, scroll=ft.ScrollMode.AUTO)
    model_panel = ft.Container(
        content=model_panel_col,
        width=350,
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
                    border=ft.border.only(right=ft.BorderSide(1, "#aaaaaa")),
                ),
                result_panel,
                model_panel,
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        border=ft.border.all(1, "#aaaaaa"),
        border_radius=4,
        padding=4,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    #  Image loader helper (cv2 resize + base64 = fast)
    def load_image_by_path(path, page):
        img_cv = cv2.imread(path)
        if img_cv is not None:
            image_state["cv_img"] = img_cv
            h, w = img_cv.shape[:2]
            scale = min(DISP_H / h, 1.0)
            image_state["scale"] = scale
            disp_w = int(w * scale)
            disp_h = int(h * scale)
            image_state["act_w"] = disp_w
            image_state["act_h"] = disp_h
            large_img.width = disp_w
            large_img.height = disp_h
            large_img_container.width = disp_w
            _, buf = cv2.imencode(".jpg", img_cv, [cv2.IMWRITE_JPEG_QUALITY, 90])
            b64 = base64.b64encode(buf).decode()
            large_img.src = f"data:image/jpeg;base64,{b64}"
            large_img.visible = True
            large_img_placeholder.visible = False
            selection_rect.visible = False
            crop_label.visible = False
            files = image_state["files"]
            if files:
                image_counter_text.value = f"{image_state['index'] + 1}/{len(files)}"
            else:
                image_counter_text.value = ""
            page.update()

    #  Open File dialog (tkinter — instant, no subprocess overhead)
    def open_file_clicked(e):
        page = e.page
        def pick_and_load():
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Select Image",
                initialdir=r"E:\99IS\B1F2\image\B1F2",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")],
                parent=root,
            )
            root.destroy()
            if path:
                folder = os.path.dirname(path)
                exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
                files = sorted([
                    os.path.join(folder, f) for f in os.listdir(folder)
                    if os.path.splitext(f)[1].lower() in exts
                ])
                image_state["files"] = files
                image_state["index"] = files.index(path) if path in files else 0
                image_state["path"] = path
                load_image_by_path(path, page)
        page.run_thread(pick_and_load)

    #  Next / Previous image
    def next_image_clicked(e):
        files = image_state["files"]
        if files and image_state["index"] < len(files) - 1:
            image_state["index"] += 1
            image_state["path"] = files[image_state["index"]]
            load_image_by_path(image_state["path"], e.page)

    def previous_image_clicked(e):
        files = image_state["files"]
        if files and image_state["index"] > 0:
            image_state["index"] -= 1
            image_state["path"] = files[image_state["index"]]
            load_image_by_path(image_state["path"], e.page)

    #  Save template as JSON
    def save_template(e):
        model_name = (model_name_field.value or "").strip()
        if not model_name:
            return
        # Create model folder: E:\99IS\B1F2\model\<model_name>\img
        model_dir = os.path.join(r"E:\99IS\B1F2\model", model_name)
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
            insp = {
                "name": data["name_field"].value or "",
                "description": data["desc_field"].value or "",
                "image_path": saved_imgs[0] if saved_imgs else "",
                "image_paths": saved_imgs,
                "crop_roi": list(crop_ref["roi"]) if crop_ref["roi"] else [],
                "source_image": crop_ref.get("source") or "",
            }
            template["inspections"].append(insp)

        json_path = os.path.join(model_dir, f"{model_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)

        dlg = ft.AlertDialog(
            title=ft.Text("Success"),
            content=ft.Text(f"Model \"{model_name}\" saved successfully."),
            open=True,
        )
        e.page.overlay.append(dlg)
        refresh_model_dropdown()
        e.page.update()

    #  Model name field
    model_name_field = ft.TextField(height=32, text_size=13, content_padding=ft.padding.symmetric(horizontal=8, vertical=4), expand=True)

    #  Populate MODEL panel now that model_name_field exists
    model_panel_col.controls = [
        ft.Row([ft.Text("Model:", size=14, weight=ft.FontWeight.BOLD), model_name_field],
               spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([
            ft.ElevatedButton("ADD INSPECTION", height=32,
                style=ft.ButtonStyle(bgcolor={"":"#ffffff"}, color={"":"#222222"},
                    shape=ft.RoundedRectangleBorder(radius=4), side=ft.BorderSide(1,"#888888")),
                on_click=add_inspection),
            ft.ElevatedButton("DELETE", height=32,
                style=ft.ButtonStyle(bgcolor={"":"#ffffff"}, color={"":"#e53935"},
                    shape=ft.RoundedRectangleBorder(radius=4), side=ft.BorderSide(1,"#e53935")),
                on_click=delete_last),
            ft.ElevatedButton("SAVE", height=32,
                style=ft.ButtonStyle(bgcolor={"":"#4caf50"}, color={"":"#ffffff"},
                    shape=ft.RoundedRectangleBorder(radius=4)),
                on_click=save_template),
        ], spacing=8),
        ft.Container(content=inspection_list, expand=True,
            border=ft.border.all(1,"#dddddd"), border_radius=4, padding=6),
    ]

    #  Model dropdown for Test
    MODEL_DIR = r"E:\99IS\B1F2\model"

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
                        _, tbuf = cv2.imencode(".jpg", tmpl_cv, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        tb64 = base64.b64encode(tbuf).decode()
                        data_entry["thumbs_row"].controls.append(
                            ft.Image(src=f"data:image/jpeg;base64,{tb64}", width=44, height=44,
                                     fit="cover", border_radius=ft.border_radius.all(3))
                        )

            data_entry["crop_count_label"].value = f"{len(data_entry['crops_list'])} templates"

            # Show first image as main preview
            if img_paths_rel:
                first_path = os.path.join(model_base, img_paths_rel[0])
                data_entry["crop_ref"]["img_path"] = first_path
                if os.path.isfile(first_path):
                    tmpl_cv = cv2.imread(first_path)
                    if tmpl_cv is not None:
                        _, buf = cv2.imencode(".jpg", tmpl_cv, [cv2.IMWRITE_JPEG_QUALITY, 85])
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

        def do_test():
            try:
                print(f"[TEST] Starting FPM test with model: {selected_model}")
                with open(json_path, "r", encoding="utf-8") as f:
                    template = json.load(f)
                model_base = os.path.join(MODEL_DIR, selected_model)
                result_img = cv_img.copy()
                # each entry: (insp_id, score_or_None, crop_cv_or_None, is_pass)
                insp_results = []

                for insp in template.get("inspections", []):
                    img_paths_rel = insp.get("image_paths", [])
                    if not img_paths_rel:
                        single = insp.get("image_path", "")
                        if single:
                            img_paths_rel = [single]
                    insp_id = insp.get("name", "?")
                    fpm_tmpls = []
                    for rel in img_paths_rel:
                        p = os.path.join(model_base, rel)
                        if not os.path.isfile(p):
                            continue
                        t = cv2.imread(p)
                        if t is not None:
                            fpm_tmpls.append((insp_id, t))
                    if not fpm_tmpls:
                        insp_results.append((insp_id, None, None, False))
                        print(f"[TEST]   '{insp_id}' – no templates")
                        continue
                    print(f"[TEST]   FPM '{insp_id}' ({len(fpm_tmpls)} templates) ...")
                    hits = match_fpm(
                        cv_img, fpm_tmpls,
                        score_threshold=0.75,
                        max_overlap=0.3,
                        tolerance_angle=0,
                    )
                    if not hits:
                        insp_results.append((insp_id, None, None, False))
                        print(f"[TEST]   '{insp_id}' – no match")
                        continue
                    best = max(hits, key=lambda h: h["score"])
                    is_pass = best["score"] >= 0.75
                    crop_cv = crop_fpm_region(cv_img, best)
                    if is_pass:
                        label = f"ID:{insp_id} s={best['score']:.2f}"
                        draw_fpm_match(result_img, best, label=label)
                    insp_results.append((insp_id, best["score"], crop_cv, is_pass))
                    status = "OK" if is_pass else "NG"
                    print(f"[TEST]   '{insp_id}': score={best['score']:.3f} [{status}]")

                # Display result on RAW
                _, buf = cv2.imencode(".jpg", result_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                b64 = base64.b64encode(buf).decode()
                large_img.src = f"data:image/jpeg;base64,{b64}"
                large_img.visible = True
                large_img_placeholder.visible = False

                # Populate RESULT panel – every inspection point
                result_list.controls.clear()
                for insp_id, sc, crop_cv, is_pass in insp_results:
                    if is_pass and crop_cv is not None:
                        _, cbuf = cv2.imencode(".jpg", crop_cv, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        cb64 = base64.b64encode(cbuf).decode()
                        img_widget = ft.Image(src=f"data:image/jpeg;base64,{cb64}",
                                              width=200, height=120, fit="contain")
                    else:
                        ng_label = "NG" if sc is not None else "NG"
                        img_widget = ft.Container(
                            width=200, height=120, bgcolor="#f44336",
                            alignment=ft.Alignment(0, 0),
                            content=ft.Text(ng_label, size=24, weight=ft.FontWeight.BOLD, color="#ffffff"),
                        )
                    if is_pass:
                        border_color = "#4caf50"   # green
                        bg_color = "#e8f5e9"
                        score_text = f"{insp_id}  s={sc:.2f}"
                        text_color = "#2e7d32"
                    else:
                        border_color = "#f44336"   # red
                        bg_color = "#ffebee"
                        score_text = f"{insp_id}  NG" if sc is None else f"{insp_id}  NG  s={sc:.2f}"
                        text_color = "#c62828"
                    result_list.controls.append(
                        ft.Container(
                            content=ft.Column([
                                img_widget,
                                ft.Text(score_text, size=10, weight=ft.FontWeight.BOLD, color=text_color),
                            ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                            padding=4,
                            bgcolor=bg_color,
                            border=ft.border.all(2, border_color),
                            border_radius=4,
                        )
                    )
                page.update()
                n_pass = sum(1 for *_, p in insp_results if p)
                print(f"[TEST] Done. {n_pass}/{len(insp_results)} passed.")
            except Exception as ex:
                import traceback
                traceback.print_exc()
                print(f"[TEST] Error: {ex}")

        page.run_thread(do_test)

    #  Create Model panel 
    create_model_view = ft.Row(
        [
            # RAW+RESULT+MODEL box + buttons below
            ft.Column(
                [
                    raw_result_box,
                    ft.Row(
                        [
                            ft.ElevatedButton("Connect camera", width=120, height=34, style=btn_style_sm("#f57c00")),
                            ft.ElevatedButton("Trigger Image",  width=120, height=34, style=btn_style_sm("#f57c00")),
                            ft.ElevatedButton("Open File",      width=120, height=34, style=btn_style_sm("#f57c00"),
                                              on_click=open_file_clicked),
                            ft.ElevatedButton("Previous",           width=120, height=34, style=btn_style_sm("#f57c00"),
                                              on_click=previous_image_clicked),
                            ft.ElevatedButton("Next",       width=120, height=34, style=btn_style_sm("#f57c00"),
                                              on_click=next_image_clicked),
                            model_dropdown,
                            ft.ElevatedButton("Test",           width=120, height=34, style=btn_style_sm("#f57c00"),
                                              on_click=test_clicked),
                        ],
                        spacing=6,
                        wrap=True,
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

    #  Camera Setting panel 
    camera_setting_view = ft.Container(
        content=ft.Text("CAMERA SETTING - pending design", color=theme.TEXT_PRIMARY, size=14),
        expand=True,
        padding=12,
    )

    def show_tab(tab):
        active_tab["value"] = tab
        btn_create.style = tab_style(tab == "create")
        btn_camera.style = tab_style(tab == "camera")
        content_area.content = create_model_view if tab == "create" else camera_setting_view
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
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                ),
                # Sub-tab buttons + algorithm selector
                ft.Container(
                    content=ft.Row([btn_create, btn_camera, ft.Container(expand=True), algo_dropdown], spacing=8,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.only(left=12, right=12, bottom=8),
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
