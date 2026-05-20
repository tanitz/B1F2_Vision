"""
Generate image-processing flow report as self-contained HTML.
Run: python gen_flow_report.py
Output: docs/flow_report.html
"""
import base64, cv2, json, math, numpy as np, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fpm_matching import match_fpm, draw_fpm_match, crop_fpm_region

# ── Paths ──────────────────────────────────────────────────────────────────
BASE    = os.path.dirname(os.path.abspath(__file__))
MODEL   = "CV5VS_MODEL"
IMG     = os.path.join(BASE, "image", "B1F2", "image_set1", "Image_20260512174925798.bmp")
MBASE   = os.path.join(BASE, "model", MODEL)
JPATH   = os.path.join(MBASE, f"{MODEL}.json")
OUT_DIR = os.path.join(BASE, "docs")
OUT     = os.path.join(OUT_DIR, "flow_report.html")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Helpers ────────────────────────────────────────────────────────────────
def to_b64(img, quality=82, max_w=None, max_h=None):
    h, w = img.shape[:2]
    if max_w or max_h:
        s = min((max_w / w if max_w else 1.0), (max_h / h if max_h else 1.0), 1.0)
        if s < 1:
            img = cv2.resize(img, (int(w * s), int(h * s)), cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode()

def img_tag(img, max_w=None, max_h=None, q=82, cls="", style=""):
    b = to_b64(img, q, max_w, max_h)
    return f'<img class="{cls}" src="data:image/jpeg;base64,{b}" style="{style}">'

def label_img(img, text, color=(30, 30, 30), bg=(240, 240, 240)):
    h, w = img.shape[:2]
    banner = np.full((32, w, 3), bg, dtype=np.uint8)
    cv2.putText(banner, text, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 1, cv2.LINE_AA)
    return np.vstack([banner, img])

INSP_COLORS = [
    (255, 80,  0),   (0, 180, 255), (220, 0, 160),
    (0, 200, 80),   (220, 180, 0), (140, 0, 255),
    (0, 140, 255),  (255, 40, 40),
]

# ── Load ───────────────────────────────────────────────────────────────────
print("Loading image & model …")
orig = cv2.imread(IMG)
assert orig is not None, f"Cannot read {IMG}"
with open(JPATH, encoding="utf-8") as f:
    template = json.load(f)
inspections = template["inspections"]
H, W = orig.shape[:2]

# ──────────────────────────────────────────────────────────────────────────
# STEP 1 – Original image
# ──────────────────────────────────────────────────────────────────────────
print("Step 1 …")
s1 = orig.copy()
cv2.rectangle(s1, (0, 0), (420, 54), (0, 0, 0), -1)
cv2.putText(s1, f"B1F2 Image  {W} x {H} px  (BMP)", (10, 34),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)

# ──────────────────────────────────────────────────────────────────────────
# STEP 2 – Downscale for matching
# ──────────────────────────────────────────────────────────────────────────
print("Step 2 …")
MATCH_MAX  = 800
mscale     = min(MATCH_MAX / max(W, H), 1.0)
scene_sm   = cv2.resize(orig, (int(W * mscale), int(H * mscale)), cv2.INTER_AREA)
SH, SW     = scene_sm.shape[:2]

# Side-by-side: orig thumbnail | arrow | small scene
thumb_o = cv2.resize(orig, (int(W * 220 / H), 220), cv2.INTER_AREA)
thumb_s = cv2.resize(scene_sm, (int(SW * 220 / SH), 220), cv2.INTER_AREA)
arrow   = np.full((220, 80, 3), 245, dtype=np.uint8)
cv2.arrowedLine(arrow, (5, 110), (72, 110), (60, 120, 220), 5, tipLength=0.4)
s2 = np.hstack([
    label_img(thumb_o, f"Original  {W}x{H}"),
    np.full((220 + 32, 10, 3), 255, dtype=np.uint8),
    label_img(arrow, "Scale down", bg=(245, 245, 245)),
    np.full((220 + 32, 10, 3), 255, dtype=np.uint8),
    label_img(thumb_s, f"Match-scale  {SW}x{SH}  ({mscale:.2f}x)"),
])

# ──────────────────────────────────────────────────────────────────────────
# STEP 3 – Search ROI zones
# ──────────────────────────────────────────────────────────────────────────
print("Step 3 …")
s3 = orig.copy()
for i, insp in enumerate(inspections):
    sroi = insp.get("search_roi", [])
    if sroi and len(sroi) == 4:
        rx, ry, rw, rh = [int(v) for v in sroi]
        col = INSP_COLORS[i % len(INSP_COLORS)]
        ov = s3.copy()
        cv2.rectangle(ov, (rx, ry), (rx + rw, ry + rh), col, -1)
        cv2.addWeighted(ov, 0.18, s3, 0.82, 0, s3)
        cv2.rectangle(s3, (rx, ry), (rx + rw, ry + rh), col, 3)
        name = insp.get("name", "")
        tw, th = cv2.getTextSize(name, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)[0]
        cv2.rectangle(s3, (rx, ry - th - 10), (rx + tw + 8, ry), col, -1)
        cv2.putText(s3, name, (rx + 4, ry - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

# ──────────────────────────────────────────────────────────────────────────
# STEP 4 – Image Pyramid (scene + template)
# ──────────────────────────────────────────────────────────────────────────
print("Step 4 …")
insp0    = inspections[0]
tmpl_raw = cv2.imread(os.path.join(MBASE, insp0["image_paths"][0]))

# Scene pyramid
scene_g = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
s_pyr   = [scene_g.copy()]
cur = scene_g
for _ in range(4):
    if cur.shape[0] < 40 or cur.shape[1] < 40:
        break
    cur = cv2.pyrDown(cur)
    s_pyr.append(cur)

# Template pyramid
tmpl_g = cv2.cvtColor(tmpl_raw, cv2.COLOR_BGR2GRAY)
t_pyr  = [tmpl_g.copy()]
cur = tmpl_g
for _ in range(3):
    if cur.shape[0] < 10 or cur.shape[1] < 10:
        break
    cur = cv2.pyrDown(cur)
    t_pyr.append(cur)

TARGET_H = 180

def make_pyr_strip(imgs, target_h, color_fn=None):
    parts = []
    for lvl, img in enumerate(imgs):
        if img.ndim == 2:
            vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        else:
            vis = img.copy()
        ih, iw = vis.shape[:2]
        s = min(target_h / ih, 350 / iw)
        vis = cv2.resize(vis, (int(iw * s), int(ih * s)), cv2.INTER_AREA)
        vis = label_img(vis, f"L{lvl}  {iw}x{ih}")
        parts.append(vis)
    max_h = max(p.shape[0] for p in parts)
    padded = [cv2.copyMakeBorder(p, 0, max_h - p.shape[0], 0, 0,
                                  cv2.BORDER_CONSTANT, value=(230, 230, 230))
              for p in parts]
    sep = np.full((max_h, 6, 3), 200, dtype=np.uint8)
    result = parts[0]
    for p in parts[1:]:
        result = np.hstack([result, sep, p])
    return result

s_pyr_vis = make_pyr_strip(s_pyr, TARGET_H)
t_pyr_vis = make_pyr_strip(t_pyr, TARGET_H)

# ──────────────────────────────────────────────────────────────────────────
# STEP 5 – NCC Score Map (heatmap)
# ──────────────────────────────────────────────────────────────────────────
print("Step 5 …")
sroi0 = insp0.get("search_roi", [])
if sroi0 and len(sroi0) == 4:
    rx, ry, rw, rh = [int(v) for v in sroi0]
    rx2 = max(0, min(int(rx * mscale), SW - 1))
    ry2 = max(0, min(int(ry * mscale), SH - 1))
    rw2 = min(int(rw * mscale), SW - rx2)
    rh2 = min(int(rh * mscale), SH - ry2)
    roi_g  = cv2.cvtColor(scene_sm[ry2:ry2+rh2, rx2:rx2+rw2], cv2.COLOR_BGR2GRAY)
    roi_vis_area = orig[ry:ry+rh, rx:rx+rw].copy()
else:
    roi_g  = cv2.cvtColor(scene_sm, cv2.COLOR_BGR2GRAY)
    roi_vis_area = orig.copy()

tmpl_sm = cv2.resize(tmpl_raw,
                     (max(1, int(tmpl_raw.shape[1] * mscale)),
                      max(1, int(tmpl_raw.shape[0] * mscale))),
                     cv2.INTER_AREA)
tmpl_sm_g = cv2.cvtColor(tmpl_sm, cv2.COLOR_BGR2GRAY)

if roi_g.shape[0] >= tmpl_sm_g.shape[0] and roi_g.shape[1] >= tmpl_sm_g.shape[1]:
    ncc = cv2.matchTemplate(roi_g, tmpl_sm_g, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(ncc)
    ncc_u8   = cv2.normalize(ncc, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
    heat     = cv2.applyColorMap(ncc_u8, cv2.COLORMAP_JET)
    # Scale up heatmap
    hs = min(300 / heat.shape[0], 400 / heat.shape[1], 4.0)
    heat_big = cv2.resize(heat, (int(heat.shape[1] * hs), int(heat.shape[0] * hs)),
                          cv2.INTER_NEAREST)
    ml_big   = (int(maxloc[0] * hs), int(maxloc[1] * hs))
    cv2.drawMarker(heat_big, ml_big, (255, 255, 255), cv2.MARKER_CROSS, 24, 3)
    cv2.putText(heat_big, f"Peak = {maxv:.3f}", (ml_big[0] + 8, ml_big[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
    heat_big = label_img(heat_big, "NCC Score Map (JET colormap  red=high)")
else:
    heat_big = np.zeros((200, 300, 3), np.uint8)

# ROI crop visualisation
roi_vis = cv2.resize(roi_vis_area,
                     (int(roi_vis_area.shape[1] * 220 / roi_vis_area.shape[0]), 220),
                     cv2.INTER_AREA)
roi_vis = label_img(roi_vis, "Search ROI region")

sep_v = np.full((max(heat_big.shape[0], roi_vis.shape[0]), 20, 3), 255, np.uint8)
# pad heights
def pad_h(img, target):
    d = target - img.shape[0]
    return cv2.copyMakeBorder(img, 0, d, 0, 0, cv2.BORDER_CONSTANT, value=(255,255,255)) if d > 0 else img

th5 = max(heat_big.shape[0], roi_vis.shape[0])
s5  = np.hstack([pad_h(roi_vis, th5), sep_v[:th5], pad_h(heat_big, th5)])

# ──────────────────────────────────────────────────────────────────────────
# STEP 6 – OK vs NG Templates (for Filter Drier)
# ──────────────────────────────────────────────────────────────────────────
print("Step 6 …")
THUMB = 120

def load_thumbs(paths, max_n):
    out = []
    for rel in paths[:max_n]:
        p = os.path.join(MBASE, rel)
        img = cv2.imread(p)
        if img is not None:
            s = min(THUMB / img.shape[0], THUMB / img.shape[1])
            out.append(cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s))))
    return out

ok_imgs = load_thumbs(insp0.get("image_paths", []), 4)
ng_imgs = load_thumbs(insp0.get("ng_image_paths", []), 3)

def hstack_thumbs(imgs, target_h, border_color):
    parts = []
    for img in imgs:
        s   = min(target_h / img.shape[0], 1.5)
        vis = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)))
        vis = cv2.copyMakeBorder(vis, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=border_color)
        parts.append(vis)
    if not parts:
        return np.zeros((target_h, 80, 3), np.uint8)
    mh = max(p.shape[0] for p in parts)
    padded = [cv2.copyMakeBorder(p, 0, mh - p.shape[0], 0, 0,
                                  cv2.BORDER_CONSTANT, value=(255,255,255)) for p in parts]
    return np.hstack(padded)

ok_strip = hstack_thumbs(ok_imgs, THUMB, (0, 180, 0))
ng_strip = hstack_thumbs(ng_imgs, THUMB, (0, 0, 200))
ok_strip = label_img(ok_strip, "OK Templates (เงื่อนไข PASS)", bg=(200, 240, 200))
ng_strip = label_img(ng_strip, "NG Templates (เงื่อนไข FAIL)", bg=(240, 200, 200))

sep6 = np.full((max(ok_strip.shape[0], ng_strip.shape[0]), 20, 3), 255, np.uint8)
th6  = max(ok_strip.shape[0], ng_strip.shape[0])
s6   = np.hstack([pad_h(ok_strip, th6), sep6[:th6], pad_h(ng_strip, th6)])

# ──────────────────────────────────────────────────────────────────────────
# STEP 7 – Decision logic (score comparison card)
# ──────────────────────────────────────────────────────────────────────────
print("Step 7 …")
card_w, card_h = 700, 200
s7 = np.full((card_h, card_w, 3), 252, np.uint8)

boxes = [
    ("Match OK Templates", "score_ok = 0.97", (0, 160, 0)),
    ("Match NG Templates", "score_ng = 0.45", (180, 0, 0)),
]
bw = (card_w - 60) // 2
for i, (title, val, col) in enumerate(boxes):
    x = 20 + i * (bw + 20)
    cv2.rectangle(s7, (x, 20), (x + bw, 120), col, 2)
    cv2.putText(s7, title, (x + 10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    cv2.putText(s7, val, (x + 10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.85, col, 2)

# Arrow down
mid = card_w // 2
cv2.arrowedLine(s7, (mid, 125), (mid, 155), (80, 80, 80), 3, tipLength=0.3)

# Decision
cv2.rectangle(s7, (mid - 200, 155), (mid + 200, 190), (0, 120, 0), -1)
cv2.putText(s7, "score_ok >= score_ng  →  PASS", (mid - 190, 180),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

# ──────────────────────────────────────────────────────────────────────────
# STEP 8 – Full FPM run → Result image
# ──────────────────────────────────────────────────────────────────────────
print("Step 8 – running FPM (may take a moment) …")
inv        = 1.0 / mscale if mscale > 0 else 1.0
result_img = orig.copy()

for i, insp in enumerate(inspections):
    paths   = insp.get("image_paths", [])
    iid     = insp.get("name", "?")
    color   = INSP_COLORS[i % len(INSP_COLORS)]

    fpm_t = []
    for rel in paths:
        t = cv2.imread(os.path.join(MBASE, rel))
        if t is not None:
            if mscale < 1.0:
                t = cv2.resize(t, (max(1, int(t.shape[1] * mscale)),
                                   max(1, int(t.shape[0] * mscale))), cv2.INTER_AREA)
            fpm_t.append((iid, t))
    if not fpm_t:
        continue

    sroi = insp.get("search_roi", [])
    if sroi and len(sroi) == 4:
        rx, ry, rw_s, rh_s = [int(v) for v in sroi]
        rx2 = max(0, min(int(rx * mscale), SW - 1))
        ry2 = max(0, min(int(ry * mscale), SH - 1))
        rw2 = min(int(rw_s * mscale), SW - rx2)
        rh2 = min(int(rh_s * mscale), SH - ry2)
        has_roi = rw2 > 1 and rh2 > 1
        roi_sc  = scene_sm[ry2:ry2+rh2, rx2:rx2+rw2] if has_roi else scene_sm
    else:
        roi_sc  = scene_sm; rx2=ry2=rw2=rh2=0; has_roi = False

    hits = match_fpm(roi_sc, fpm_t, score_threshold=0.50, max_overlap=0.3, tolerance_angle=0)
    if not hits:
        # Draw ROI as NG (grey)
        if has_roi:
            cv2.rectangle(result_img,
                          (rx, ry), (rx + rw_s, ry + rh_s), (120, 120, 120), 2)
        continue

    best = max(hits, key=lambda h: h["score"])
    if has_roi:
        adj = dict(best)
        adj["rect_points"] = [(p[0] + rx2, p[1] + ry2) for p in best["rect_points"]]
        adj["center"]      = (best["center"][0] + rx2, best["center"][1] + ry2)
        bx, by, bww, bhh   = best["bbox"]
        adj["bbox"]        = (bx + rx2, by + ry2, bww, bhh)
        best = adj

    bf = dict(best)
    bf["rect_points"] = [(int(p[0]*inv), int(p[1]*inv)) for p in best["rect_points"]]
    bf["center"]      = (int(best["center"][0]*inv), int(best["center"][1]*inv))
    bx, by, bww, bhh  = best["bbox"]
    bf["bbox"]        = (int(bx*inv), int(by*inv), int(bww*inv), int(bhh*inv))

    draw_fpm_match(result_img, bf, color=color,
                   label=f"{iid}  {best['score']:.2f}")

DISP_H = 380
ds   = min(DISP_H / H, 1.0)
s8   = cv2.resize(result_img, (int(W * ds), int(H * ds)), cv2.INTER_AREA)

# ──────────────────────────────────────────────────────────────────────────
# STEP 9 – CSV snippet card
# ──────────────────────────────────────────────────────────────────────────
csv_card_w, csv_card_h = 900, 220
s9 = np.full((csv_card_h, csv_card_w, 3), 30, np.uint8)
lines = [
    "timestamp,model,inspection_name,result,score,overall_result,result_image_id",
    "2026-05-16 08:00:00,CV5VS_MODEL,Filter Drier,PASS,0.9746,PASS,20260516_080000",
    "2026-05-16 08:00:00,CV5VS_MODEL,Hot Gas Valve,PASS,0.7883,PASS,20260516_080000",
    "2026-05-16 08:00:00,CV5VS_MODEL,Expansion Valve,PASS,0.7177,PASS,20260516_080000",
    "2026-05-16 08:01:30,CV5VS_MODEL,Filter Drier,FAIL,0.4120,FAIL,20260516_080130",
    "  ...",
]
for i, ln in enumerate(lines):
    col = (120, 220, 120) if i == 0 else (200, 200, 200) if "PASS" in ln else (100, 160, 255)
    cv2.putText(s9, ln, (18, 36 + i * 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, col, 1, cv2.LINE_AA)

# ──────────────────────────────────────────────────────────────────────────
# Build HTML
# ──────────────────────────────────────────────────────────────────────────
print("Building HTML …")

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', sans-serif; background: #f4f6fa; color: #222; }
header { background: linear-gradient(135deg,#1565c0,#0097a7); color:#fff;
         padding: 36px 48px; }
header h1 { font-size: 2.2rem; font-weight: 700; letter-spacing: 1px; }
header p  { font-size: 1.0rem; margin-top: 6px; opacity: .85; }
.flow-bar  { display:flex; align-items:center; justify-content:center;
             flex-wrap:nowrap; gap:0; padding:28px 32px 20px;
             background:#fff; border-bottom:2px solid #e0e6f0;
             overflow-x:auto; }
.flow-card { display:flex; flex-direction:column; align-items:center;
             gap:8px; flex-shrink:0; }
.flow-card img { width:130px; height:82px; object-fit:cover;
                 border-radius:8px; border:2px solid #1565c0;
                 box-shadow:0 2px 8px #1565c030; }
.flow-badge { display:flex; align-items:center; gap:5px; }
.flow-num  { background:#1565c0; color:#fff; border-radius:50%;
             width:22px; height:22px; display:flex; align-items:center;
             justify-content:center; font-size:.72rem; font-weight:700; flex-shrink:0; }
.flow-lbl  { font-size:.78rem; font-weight:700; color:#1565c0; white-space:nowrap; }
.flow-arr  { font-size:1.5rem; color:#90a4c8; margin:0 6px;
             padding-bottom:30px; flex-shrink:0; }
.section   { background:#fff; margin:24px 48px; border-radius:12px;
             box-shadow:0 2px 12px #0001; overflow:hidden; }
.sec-hdr   { display:flex; align-items:center; gap:14px; padding:18px 24px;
             background:#f8f9fb; border-bottom:1px solid #eee; }
.step-num  { background:#1565c0; color:#fff; border-radius:50%;
             width:36px; height:36px; display:flex; align-items:center;
             justify-content:center; font-weight:700; font-size:1.1rem; flex-shrink:0; }
.sec-hdr h2 { font-size:1.15rem; font-weight:700; color:#1565c0; }
.sec-hdr .sub { font-size:.88rem; color:#666; margin-top:2px; }
.sec-body  { padding:20px 24px; }
.sec-body img { border-radius:8px; max-width:700px; width:100%; height:auto; display:block; margin:0 auto; }
.note-box  { background:#e3f2fd; border-left:4px solid #1565c0;
             padding:14px 18px; border-radius:0 8px 8px 0; margin-top:14px;
             font-size:.88rem; line-height:1.7; }
.note-box p { margin-bottom:8px; }
.note-box ul { margin:6px 0 6px 18px; }
.note-box li { margin-bottom:4px; }
.note-box .param { display:inline-block; background:#1565c020; border:1px solid #1565c040;
                   border-radius:4px; padding:1px 7px; font-family:monospace;
                   font-size:.84rem; color:#0d47a1; margin:1px; }
.note-box strong { color:#0d47a1; }
.two-col   { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:10px; }
.card      { background:#f8f9fb; border:1px solid #e0e0e0; border-radius:8px; padding:14px; }
.card h3   { font-size:.92rem; font-weight:700; color:#444; margin-bottom:8px; }
.pass      { color:#2e7d32; } .fail { color:#c62828; }
footer     { text-align:center; padding:32px; color:#888; font-size:.82rem; }
"""

def section(num, title, subtitle, img_cv, note, extra_html="", max_w=700, max_h=380):
    itag = img_tag(img_cv, max_w=max_w, max_h=max_h)
    return f"""
<div class="section">
  <div class="sec-hdr">
    <div class="step-num">{num}</div>
    <div>
      <h2>{title}</h2>
      <div class="sub">{subtitle}</div>
    </div>
  </div>
  <div class="sec-body">
    {itag}
    {extra_html}
    <div class="note-box">{note}</div>
  </div>
</div>"""

STEPS = [
    dict(num=1, title="Input Image",
         subtitle="รับภาพจากกล้อง / โหลดไฟล์ BMP",
         img=s1,
         note=f"""
<p><strong>ระบบรับภาพจากกล้องอุตสาหกรรมหรือโหลดจากไฟล์ผ่าน OpenCV</strong>
   ภาพถูกอ่านเป็น NumPy array รูปแบบ BGR โดยไม่มีการแปลงหรือบีบอัดใดๆ</p>
<ul>
  <li><strong>รูปแบบไฟล์:</strong> BMP, JPEG, PNG — BMP แนะนำเพราะไม่สูญเสียข้อมูล (lossless)</li>
  <li><strong>ความละเอียด:</strong> {W} × {H} px ({W*H//1_000_000:.1f} MP) — ความละเอียดสูงช่วยให้ตรวจจับรายละเอียดชิ้นส่วนขนาดเล็กได้แม่นยำ</li>
  <li><strong>สี:</strong> BGR 3 channels (Blue-Green-Red) ตามมาตรฐาน OpenCV</li>
  <li><strong>การเข้าถึง:</strong> ภาพถูกเก็บใน RAM เป็น ndarray พร้อมนำไปประมวลผลต่อทันที</li>
</ul>"""),

    dict(num=2, title="Downscale for Processing",
         subtitle="ย่อภาพเพื่อเพิ่มความเร็ว Template Matching",
         img=s2,
         note=f"""
<p><strong>ภาพต้นฉบับมีขนาดใหญ่เกินไปสำหรับ Template Matching โดยตรง</strong>
   ระบบย่อภาพก่อน matching แล้วแปลงพิกัดผลลัพธ์กลับไปยัง full-resolution สำหรับการวาด overlay</p>
<ul>
  <li><strong>Scale factor:</strong> <span class="param">min(800 / max_side, 1.0)</span> = {mscale:.2f}x
      → ย่อจาก {W}×{H} เหลือ {SW}×{SH} px</li>
  <li><strong>Interpolation:</strong> <span class="param">INTER_AREA</span> — เหมาะสมที่สุดสำหรับการย่อภาพ ลด aliasing</li>
  <li><strong>ผลประหยัด:</strong> พื้นที่ภาพลดลง {(1-(mscale**2))*100:.0f}% → matching เร็วขึ้น ~{1/mscale**2:.0f}x</li>
  <li><strong>Inverse scale:</strong> <span class="param">inv = 1 / {mscale:.2f} = {1/mscale:.2f}x</span>
      ใช้แปลง bounding box กลับเป็น full-resolution ก่อนวาดบนภาพจริง</li>
</ul>"""),

    dict(num=3, title="Search ROI Definition",
         subtitle="กำหนดพื้นที่ค้นหาของแต่ละ Inspection Point จาก Model JSON",
         img=s3,
         note=f"""
<p><strong>แต่ละ Inspection Point มีขอบเขตการค้นหา (Search ROI) ที่กำหนดล่วงหน้าในไฟล์ JSON</strong>
   เพื่อจำกัดพื้นที่ที่ระบบจะค้นหา Template แทนการสแกนทั้งภาพ</p>
<ul>
  <li><strong>โมเดล {MODEL}:</strong> มี {len(inspections)} inspection points ได้แก่
      {', '.join(set(i['name'] for i in inspections))}</li>
  <li><strong>รูปแบบ ROI:</strong> <span class="param">[x, y, width, height]</span>
      กำหนดเป็น pixel coordinates บนภาพ full-resolution</li>
  <li><strong>ลด False Positive:</strong> ป้องกันระบบจับชิ้นส่วนที่คล้ายกันในบริเวณที่ไม่เกี่ยวข้อง</li>
  <li><strong>เพิ่มความเร็ว:</strong> NCC คำนวณเฉพาะภายใน ROI แทนทั้งภาพ — ลดเวลาประมวลผลอย่างมีนัย</li>
  <li><strong>กำหนดครั้งเดียว:</strong> ROI ตั้งค่าตอนสร้างโมเดล (Settings) และใช้ซ้ำในทุก inspection</li>
</ul>"""),

    dict(num=4, title="Image Pyramid Construction",
         subtitle="สร้าง Gaussian Pyramid หลายระดับ — Coarse-to-Fine Strategy",
         img=s_pyr_vis,
         note="""
<p><strong>Image Pyramid คือการสร้างภาพชุดเดียวกันในหลายระดับความละเอียด</strong>
   เพื่อให้ระบบค้นหาตำแหน่งคร่าวๆ จากภาพเล็กก่อน แล้ว refine ลงมาที่ภาพใหญ่</p>
<ul>
  <li><strong>วิธีสร้าง:</strong> <span class="param">cv2.pyrDown()</span>
      — Gaussian blur แล้วลดขนาดครึ่งหนึ่งในแต่ละระดับ (ทั้ง Scene และ Template)</li>
  <li><strong>จำนวนระดับ:</strong> คำนวณอัตโนมัติจาก <span class="param">min_reduce_area = 256</span>
      — ยิ่ง template ใหญ่ยิ่งมีระดับมาก</li>
  <li><strong>Stage 1 (Coarse):</strong> ค้นหา candidate positions บนภาพระดับบนสุด (เล็กสุด)
      → เร็วมาก ได้ตำแหน่งโดยประมาณ</li>
  <li><strong>Stage 2 (Refine):</strong> นำ candidates ลงมา refine ทีละระดับจนถึงระดับ 0 (full-res)
      → ได้ตำแหน่งแม่นยำระดับ pixel</li>
  <li><strong>Score threshold ผ่อนคลาย:</strong> ระดับบน threshold = <span class="param">0.50 × 0.9<sup>n</sup></span>
      เพื่อไม่ตัด candidates ที่ยังไม่แม่นจากภาพย่อ</li>
</ul>""",
         extra='<h3 style="margin:16px 0 6px;font-size:.9rem;color:#555;font-weight:700;">Template Pyramid (ชุด Template ที่ใช้ค้นหา)</h3>' +
               img_tag(t_pyr_vis, max_w=700, max_h=180)),

    dict(num=5, title="NCC Template Matching",
         subtitle="คำนวณ Normalized Cross-Correlation (TM_CCOEFF_NORMED) บน Search ROI",
         img=s5,
         note="""
<p><strong>NCC วัดความคล้ายคลึงระหว่าง Template กับทุกตำแหน่งใน ROI</strong>
   ผลลัพธ์คือ Score Map ที่แต่ละ pixel แสดงค่าความตรงกับ Template ณ ตำแหน่งนั้น</p>
<ul>
  <li><strong>Algorithm:</strong> <span class="param">cv2.TM_CCOEFF_NORMED</span>
      — Normalized Cross-Correlation, ผล = –1 ถึง 1 (1.0 = identical)</li>
  <li><strong>Score Map ขนาด:</strong> (H<sub>ROI</sub> – H<sub>tmpl</sub> + 1) × (W<sub>ROI</sub> – W<sub>tmpl</sub> + 1)
      แต่ละ pixel = score ณ ตำแหน่ง top-left ของ template</li>
  <li><strong>Heatmap (JET colormap):</strong>
      <span style="color:#d32f2f;font-weight:700">■ แดง</span> = score สูง (match ดี) /
      <span style="color:#1565c0;font-weight:700">■ น้ำเงิน</span> = score ต่ำ (ไม่ตรง)</li>
  <li><strong>Peak detection:</strong> <span class="param">cv2.minMaxLoc()</span>
      หา pixel ที่มี score สูงสุด → ตำแหน่งที่ตรงกับ Template มากที่สุด</li>
  <li><strong>Threshold:</strong> <span class="param">score ≥ 0.50</span>
      ถือว่า match — ค่าต่ำกว่านี้ถูกตัดทิ้ง</li>
  <li><strong>Validation:</strong> ผ่านการตรวจ Laplacian variance (กรองพื้นที่ไม่มี texture)
      และ SSIM ≥ 0.35 (กรอง false match จาก normalization artifact)</li>
</ul>"""),

    dict(num=6, title="OK / NG Template Comparison",
         subtitle="รัน FPM กับ Template ทั้งสองชุดแล้วเปรียบ score เพื่อตัดสิน",
         img=s6,
         note=f"""
<p><strong>ระบบมี Template สองชุดต่อ Inspection Point</strong> — ชุด OK (ชิ้นส่วนปกติ) และชุด NG (ชิ้นส่วนผิดปกติ)
   การเปรียบ score ทั้งสองชุดทำให้ตัดสินได้แม่นยำกว่าใช้ threshold เพียงอย่างเดียว</p>
<ul>
  <li><strong>OK Templates:</strong> ภาพตัวอย่างชิ้นส่วนที่ติดตั้ง<em>ถูกต้อง</em>
      หลายรูปเพื่อครอบคลุมความแตกต่างด้านแสง มุม และตำแหน่ง</li>
  <li><strong>NG Templates:</strong> ภาพตัวอย่างชิ้นส่วนที่<em>ผิดปกติ</em>
      เช่น หาย, ผิดรุ่น, ติดตั้งผิด, สายหลุด</li>
  <li><strong>Multi-template matching:</strong> แต่ละชุดอาจมีหลายรูป
      ระบบเลือก score สูงสุดจากทุกรูปในชุดนั้นมาเปรียบกัน</li>
  <li><strong>ตัวอย่างโมเดลนี้:</strong> Filter Drier มี {len(inspections[0].get('image_paths',[]))} OK templates
      และ {len(inspections[0].get('ng_image_paths',[]))} NG templates</li>
  <li><strong>ข้อดี:</strong> แม้ชิ้นส่วนอื่นจะบังอยู่หรือแสงเปลี่ยน
      NG template ยังสามารถจับสภาพ defect ได้โดยตรง</li>
</ul>"""),

    dict(num=7, title="Decision Logic",
         subtitle="ตัดสิน PASS / FAIL / NO_MATCH จากการเปรียบ score_ok กับ score_ng",
         img=s7,
         note="""
<p><strong>กฎการตัดสินผลของแต่ละ Inspection Point</strong> ใช้การเปรียบ score สองชุด
   เพื่อให้ระบบแยกแยะ OK กับ NG ได้แม้ score ของทั้งสองชุดใกล้เคียงกัน</p>
<ul>
  <li><span style="color:#2e7d32;font-weight:700">PASS:</span>
      score_ok ≥ <span class="param">0.50</span> และ score_ok ≥ score_ng
      → ชิ้นส่วนอยู่ครบและตรงกับสภาพปกติมากกว่าสภาพผิดปกติ</li>
  <li><span style="color:#c62828;font-weight:700">FAIL:</span>
      score_ng > score_ok
      → สภาพปัจจุบันตรงกับ NG template มากกว่า → แสดงว่าผิดปกติ</li>
  <li><span style="color:#e65100;font-weight:700">NO_MATCH:</span>
      ทั้ง score_ok และ score_ng < 0.50 → ไม่พบชิ้นส่วนในพื้นที่ที่กำหนด → นับเป็น FAIL</li>
  <li><strong>Overall Result:</strong>
      ทุก Inspection Point PASS → ภาพนี้ <span style="color:#2e7d32;font-weight:700">PASS</span> /
      มี FAIL อย่างน้อย 1 จุด → ภาพนี้ <span style="color:#c62828;font-weight:700">FAIL</span></li>
  <li><strong>ปรับ threshold:</strong> สามารถเปลี่ยนค่า 0.50 ได้ในโค้ด
      (<span class="param">score_threshold=0.50</span>) เพื่อสมดุลระหว่าง sensitivity และ specificity</li>
</ul>"""),

    dict(num=8, title="Result Visualization",
         subtitle="วาด Bounding Box, Score และ Highlight บน Full-Resolution Image",
         img=s8,
         note="""
<p><strong>ผลลัพธ์ทุก Inspection Point ถูกวาดทับบนภาพ full-resolution</strong>
   เพื่อให้ผู้ใช้เห็นว่าระบบตรวจพบชิ้นส่วนที่ไหน และมั่นใจมากน้อยเพียงใด</p>
<ul>
  <li><strong>Rotated Bounding Box:</strong> กล่องสี่เหลี่ยมวาดตามมุมที่ template ตรงกัน
      รองรับการหมุน (tolerance_angle) แต่ปัจจุบัน = 0° (ไม่หมุน)</li>
  <li><strong>สี:</strong>
      <span style="color:#4caf50;font-weight:700">■ เขียว</span> = PASS,
      <span style="color:#f44336;font-weight:700">■ แดง</span> = FAIL,
      <span style="color:#888;font-weight:700">■ เทา</span> = NO_MATCH</li>
  <li><strong>Score label:</strong> แสดง <span class="param">s=0.97</span>
      บนกล่องทุกจุด — ยิ่งใกล้ 1.0 ยิ่งมั่นใจ</li>
  <li><strong>Semi-transparent fill:</strong> <span class="param">fill_alpha=0.15</span>
      ไฮไลต์พื้นที่ที่ match เพื่อให้เห็นชัดขึ้น</li>
  <li><strong>บันทึก Result Image:</strong> ภาพ annotated ถูกบีบอัด JPEG (quality=85)
      และบันทึกใน <span class="param">results/images/</span> พร้อม timestamp ID</li>
</ul>"""),

    dict(num=9, title="Save Report",
         subtitle="บันทึกผลลัพธ์ลง CSV รายวัน (YYYY-MM-DD.csv) และ Result Image",
         img=s9,
         note="""
<p><strong>ทุก inspection run จะถูกบันทึกอัตโนมัติในรูปแบบ CSV รายวัน</strong>
   สามารถเรียกดูผ่านหน้า Report ได้ทันที โดยระบบอ่านไฟล์ของวันนั้นๆ</p>
<ul>
  <li><strong>ไฟล์ CSV:</strong> <span class="param">results/YYYY-MM-DD.csv</span>
      — แยกรายวัน 1 ไฟล์ต่อวัน ง่ายต่อการ backup และ archive</li>
  <li><strong>1 แถว = 1 Inspection Point</strong>
      ภาพ 1 ใบมีหลายแถว (เท่ากับจำนวน inspection points) และมี result_image_id เดียวกัน</li>
  <li><strong>คอลัมน์:</strong> timestamp · model · inspection_name · result · score · overall_result · result_image_id</li>
  <li><strong>Simulated Timestamp:</strong> เริ่ม <span class="param">08:00:00</span>
      + <span class="param">90 วินาที</span> ต่อ inspection run
      เพื่อให้ข้อมูล timeline สมจริง</li>
  <li><strong>Result Image:</strong> บันทึกใน <span class="param">results/images/{timestamp}.jpg</span>
      เชื่อมโยงกับแถว CSV ผ่าน result_image_id</li>
  <li><strong>หน้า Report:</strong> อ่าน CSV วันปัจจุบันโดยอัตโนมัติ แสดง PASS/FAIL พร้อมรูปผลลัพธ์</li>
</ul>"""),
]

flow_labels = ["Input", "Downscale", "ROI", "Pyramid", "NCC Match",
               "OK/NG Compare", "Decision", "Visualize", "Save Report"]
flow_imgs   = [s1, s2, s3, s_pyr_vis, s5, s6, s7, s8, s9]

flow_bar_html = ""
for i, (lbl, fimg) in enumerate(zip(flow_labels, flow_imgs)):
    b64 = to_b64(fimg, quality=78, max_w=160, max_h=100)
    flow_bar_html += f"""
<div class="flow-card">
  <img src="data:image/jpeg;base64,{b64}">
  <div class="flow-badge">
    <div class="flow-num">{i+1}</div>
    <span class="flow-lbl">{lbl}</span>
  </div>
</div>"""
    if i < len(flow_labels) - 1:
        flow_bar_html += '<div class="flow-arr">&#8594;</div>'

body_html = ""
for s in STEPS:
    extra = s.get("extra", "")
    body_html += section(s["num"], s["title"], s["subtitle"],
                         s["img"], s["note"], extra)

html = f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>B1F2 Vision — Image Processing Flow</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>B1F2 Vision — Image Processing Flow</h1>
  <p>FPM (Fastest Pattern Matching) · NCC + Image Pyramid · OK/NG Decision · Auto Report</p>
</header>
<div class="flow-bar">{flow_bar_html}</div>
{body_html}
<footer>B1F2 Vision System · Generated {__import__('datetime').date.today()}</footer>
</body>
</html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\nDone  →  {OUT}")
print(f"File size: {os.path.getsize(OUT)/1024:.0f} KB")
