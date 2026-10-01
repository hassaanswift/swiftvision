#!/usr/bin/env python3
"""
SwiftVision.ai — Offline Image Annotation Tool
===============================================
Python + Tkinter + Pillow. 100% offline.

FEATURES:
- Draw box first, then assign class from side panel OR popup dialog
- RIGHT-CLICK on box = DELETE instantly
- SINGLE CLICK on class = Select instantly
- UNDO (Ctrl+Z) + REDO (Ctrl+Y)
- Arrow-key nudge (Shift = 10px)
- Number keys 1-9 = quick class apply
- Copy labels from previous image
- Batch loading with progress bar
- FORCED AUTO-SAVE with verification
- Empty .txt files are SKIPPED (auto-deleted if stale)
- Auto-save YOLO format .txt files
- SwiftVision.ai green branding + logo + favicon
- Unique AppUserModelID → separate taskbar icon
"""

import os
import sys
import json
import shutil
import tempfile
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from threading import Thread
import time

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
except ImportError:
    raise SystemExit(
        "Pillow is not installed. Please run:\n\n    pip install pillow\n"
    )


# ===========================================================================
# Windows taskbar identity — MUST run before tk.Tk()
# ===========================================================================
def _set_app_user_model_id():
    """Force Windows to treat our app as its OWN taskbar group."""
    if sys.platform != "win32":
        return
    try:
        app_id = "SwiftVision.AI.AnnotationStudio.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        print(f"[icon] AppUserModelID set: {app_id}")
    except Exception as e:
        print(f"[icon] AppUserModelID failed: {e}")


# ===========================================================================
# Resource path helper — works in dev, frozen exe, AND pip install
# ===========================================================================
def _resource_path(filename):
    """
    Find a bundled resource (logo/icon) in this order:
      1. Next to the script (dev mode)
      2. Inside PyInstaller exe (frozen mode)
      3. Inside installed package via importlib.resources (pip install)
      4. Old pkg_resources fallback
    """
    # 1. Frozen (PyInstaller exe)
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        for p in (
            os.path.join(base, filename),
            os.path.join(base, "swiftvision", filename),
        ):
            if os.path.exists(p):
                return p

    # 2. Next to the script (dev mode: python swiftvision/__main__.py)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(here, filename)
        if os.path.exists(p):
            return p
    except Exception:
        pass

    # 3. Installed package via importlib.resources
    try:
        from importlib.resources import files as _pkg_files
        p = _pkg_files("swiftvision").joinpath(filename)
        if p.is_file():
            return str(p)
    except Exception:
        pass

    # 4. Old-style pkg_resources fallback (Python 3.7/3.8)
    try:
        import pkg_resources
        p = pkg_resources.resource_filename("swiftvision", filename)
        if os.path.exists(p):
            return p
    except Exception:
        pass

    return None


def _find_first(names):
    """Return first existing bundled resource from a list of names."""
    for name in names:
        p = _resource_path(name)
        if p:
            return p
    return None


# ===========================================================================
# Theme — SwiftVision green branding
# ===========================================================================
BG = "#0B0F14"
PANEL = "#12181F"
PANEL_ALT = "#171F27"
BORDER = "#232C36"
TEXT = "#E7EDF3"
TEXT_DIM = "#8A96A3"
TEXT_FAINT = "#5A6572"

GREEN = "#22C55E"
GREEN_DARK = "#16A34A"
GREEN_LIGHT = "#4ADE80"

ACCENT = "#16A34A"
ACCENT_FG = "#FFFFFF"
ACCENT2 = "#34D8C6"
DANGER = "#FF5470"

MEASURE_COLOR = "#FFFFFF"
HOVER_COLOR = "#FFFFFF"

PALETTE = ["#22C55E", "#34D8C6", "#F5C842", "#8B7FE8", "#4ADE80",
           "#FB7185", "#38BDF8", "#FFA5D2", "#B8E986", "#A78BFA"]

FONT_UI = ("Segoe UI", 10)
FONT_UI_BOLD = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 9)
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_SUB = ("Segoe UI", 8)

HANDLE_SIZE = 10
MIN_BOX_SIZE = 10

LOGO_FILE_NAMES = [
    "swiftvision_logo.png",
    "swiftvision.png",
    "swiftvision_icon.png",
    "logo.png",
]
ICON_FILE_NAMES = [
    "swiftvision_logo.png",
    "swiftvision_icon.png",
    "swiftvision.png",
    "icon.png",
]
ICO_FILE_NAMES = [
    "swiftvision.ico",
    "swiftvision_icon.ico",
    "icon.ico",
]


# ===========================================================================
# Main Application
# ===========================================================================
class SwiftVisionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SwiftVision.ai — Offline Annotation Studio")
        self.root.geometry("1300x780")
        self.root.configure(bg=BG)
        self.root.minsize(1000, 650)

        # State
        self.images = []
        self.classes = []
        self.annotations = {}
        self.current_image_index = -1
        self.current_class_index = -1
        self.selected_anno_index = None
        self.classes_loaded_from_file = False

        self.disp_w = 0
        self.disp_h = 0
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.image_x_offset = 0
        self.image_y_offset = 0
        self.tk_img = None

        self.drawing = False
        self.start_xy = (0, 0)
        self.temp_rect = None
        self.hover_xy = None

        self.panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.pan_start_pan_x = 0
        self.pan_start_pan_y = 0

        self.edit_mode = None
        self.edit_start_xy = None
        self.edit_original_anno = None
        self.edit_original_pixel = None
        self.shift_pressed = False
        self.is_editing = False

        self._save_timer = None
        self._bitmap_cache_index = None
        self.mode = "annotation"
        self.is_drawing_or_editing = False

        self.undo_stack = []
        self.redo_stack = []
        self.undo_limit = 50

        self._logo_photo = None
        self._icon_photo = None
        self._icon_photo_big = None
        self._programmatic_select = False

        self.progress_window = None
        self.progress_var = None
        self.progress_label = None
        self.is_loading = False

        self._set_window_icon()
        self._build_ui()
        self._bind_keys()
        self.root.after(150, self._set_window_icon)

    # =========================================================
    # Window icon
    # =========================================================
    def _create_s_icon(self, size=256):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        s = float(size)

        draw.polygon(
            [(s * 0.98, s * 0.03),
             (s * 0.98, s * 0.97),
             (s * 0.03, s * 0.50)],
            fill=(34, 197, 94, 255)
        )

        for yy in (0.22, 0.50, 0.78):
            draw.line(
                [(s * 0.58, s * yy), (s * 0.96, s * yy)],
                fill=(255, 255, 255, 255),
                width=max(1, int(s * 0.025))
            )
            r = max(2, int(s * 0.030))
            draw.ellipse(
                [s * 0.96 - r, s * yy - r, s * 0.96 + r, s * yy + r],
                fill=(255, 255, 255, 255)
            )

        font = None
        for fname in ("segoeuib.ttf", "arialbd.ttf",
                      "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(fname, int(s * 0.62))
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        text = "S"
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = s * 0.42 - tw / 2 - bbox[0]
            ty = s * 0.50 - th / 2 - bbox[1]
        except Exception:
            tx, ty = s * 0.30, s * 0.30

        draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)
        return img

    def _set_window_icon(self):
        try:
            ico_path = _find_first(ICO_FILE_NAMES)
            if ico_path:
                try:
                    self.root.iconbitmap(ico_path)
                    self.root.iconbitmap(default=ico_path)
                    print(f"[icon] iconbitmap from .ico: {ico_path}")
                except Exception as e:
                    print(f"[icon] iconbitmap .ico failed: {e}")

            icon_path = _find_first(ICON_FILE_NAMES)
            if icon_path:
                try:
                    img = Image.open(icon_path).convert("RGBA")
                except Exception as e:
                    print(f"[icon] Failed to open {icon_path}: {e}")
                    img = self._create_s_icon(256)
            else:
                print("[icon] No logo file found — using built-in S mark.")
                img = self._create_s_icon(256)

            w, h = img.size
            side = max(w, h)
            if w != h:
                canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                canvas.paste(img, ((side - w) // 2, (side - h) // 2))
                img = canvas

            try:
                tmp_ico = os.path.join(tempfile.gettempdir(),
                                        "swiftvision_icon.ico")
                img.save(
                    tmp_ico,
                    format="ICO",
                    sizes=[(16, 16), (24, 24), (32, 32),
                           (48, 48), (64, 64), (128, 128), (256, 256)]
                )
                self.root.iconbitmap(tmp_ico)
                self.root.iconbitmap(default=tmp_ico)
                print(f"[icon] Taskbar icon set from {tmp_ico}")
            except Exception as e:
                print(f"[icon] iconbitmap failed: {e}")

            try:
                big = img.resize((128, 128), Image.LANCZOS)
                self._icon_photo_big = ImageTk.PhotoImage(big)
                small = img.resize((64, 64), Image.LANCZOS)
                self._icon_photo = ImageTk.PhotoImage(small)
                self.root.iconphoto(True, self._icon_photo_big,
                                    self._icon_photo)
            except Exception as e:
                print(f"[icon] iconphoto failed: {e}")

        except Exception as e:
            print(f"[icon] Unexpected error: {e}")

    # =========================================================
    # UI construction
    # =========================================================
    def _build_ui(self):
        self._build_topbar()
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True)
        self._build_left_sidebar(main)
        self._build_canvas_area(main)
        self._build_right_sidebar(main)
        self._build_statusbar()

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=PANEL, height=58)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        brand = tk.Frame(bar, bg=PANEL)
        brand.pack(side="left", padx=16)

        logo_frame = tk.Frame(brand, bg=PANEL)
        logo_frame.pack()

        logo_drawn = False
        try:
            logo_path = _find_first(LOGO_FILE_NAMES)
            if logo_path:
                limg = Image.open(logo_path).convert("RGBA")
                ratio = 34.0 / limg.height
                limg = limg.resize(
                    (max(1, int(limg.width * ratio)), 34),
                    Image.LANCZOS
                )
                self._logo_photo = ImageTk.PhotoImage(limg)
                tk.Label(logo_frame, image=self._logo_photo, bg=PANEL,
                         bd=0).pack(side="left")
                logo_drawn = True
        except Exception:
            logo_drawn = False

        if not logo_drawn:
            self._make_logo_canvas(logo_frame, 34).pack(side="left")

        tk.Label(brand, text="OFFLINE ANNOTATION STUDIO", font=FONT_SUB,
                 bg=PANEL, fg=TEXT_FAINT).pack(anchor="w", padx=(4, 0))

        nav = tk.Frame(bar, bg=PANEL)
        nav.pack(side="left", padx=30)
        self._make_button(nav, "‹", self.prev_image, width=3).pack(side="left", padx=2)
        self.counter_label = tk.Label(nav, text="0 / 0", font=FONT_MONO,
                                       bg=PANEL_ALT, fg=TEXT_DIM,
                                       width=8, relief="flat", padx=6, pady=4)
        self.counter_label.pack(side="left", padx=6)
        self._make_button(nav, "›", self.next_image, width=3).pack(side="left", padx=2)

        zoom_frame = tk.Frame(bar, bg=PANEL)
        zoom_frame.pack(side="left", padx=20)
        self._make_button(zoom_frame, "🔍-", self.zoom_out, width=3).pack(side="left", padx=2)
        self.zoom_label = tk.Label(zoom_frame, text="100%", font=FONT_MONO,
                                    bg=PANEL_ALT, fg=TEXT_DIM,
                                    width=6, relief="flat", padx=4, pady=4)
        self.zoom_label.pack(side="left", padx=4)
        self._make_button(zoom_frame, "🔍+", self.zoom_in, width=3).pack(side="left", padx=2)
        self._make_button(zoom_frame, "⟲", self.reset_view, width=3).pack(side="left", padx=2)

        actions = tk.Frame(bar, bg=PANEL)
        actions.pack(side="right", padx=16)
        self._make_button(actions, "Load Images", self.load_images, accent=True).pack(side="left", padx=4)
        self._make_button(actions, "Load Folder", self.load_folder).pack(side="left", padx=4)
        self._make_button(actions, "Save Project", self.save_project).pack(side="left", padx=4)
        self._make_button(actions, "Load Project", self.load_project).pack(side="left", padx=4)
        self._make_button(actions, "Export JSON", self.export_json, accent2=True).pack(side="left", padx=4)
        self._make_button(actions, "Export YOLO", self.export_yolo, accent2=True).pack(side="left", padx=4)

        self.auto_save_label = tk.Label(bar, text="💾 TXT AUTO-SAVE",
                                         font=("Consolas", 9, "bold"),
                                         bg=PANEL, fg=GREEN_LIGHT)
        self.auto_save_label.pack(side="right", padx=10)

        self.mode_label = tk.Label(bar, text="🔧 ANNOTATION",
                                    font=("Consolas", 9, "bold"),
                                    bg=PANEL, fg=ACCENT2)
        self.mode_label.pack(side="right", padx=10)

    def _make_logo_canvas(self, parent, size=34):
        c = tk.Canvas(parent, width=size, height=size, bg=PANEL,
                      highlightthickness=0, bd=0)
        s = float(size)
        c.create_polygon(s * 0.98, s * 0.05, s * 0.98, s * 0.95,
                         s * 0.05, s * 0.50, fill=GREEN, outline="")
        for yy in (0.22, 0.50, 0.78):
            c.create_line(s * 0.55, s * yy, s * 0.95, s * yy,
                          fill="white", width=1)
            c.create_oval(s * 0.95 - 2, s * yy - 2,
                          s * 0.95 + 2, s * yy + 2,
                          fill="white", outline="")
        c.create_text(s * 0.42, s * 0.50, text="S", fill="white",
                      font=("Segoe UI", max(10, int(s * 0.55)), "bold"))
        return c

    def _build_left_sidebar(self, parent):
        side = tk.Frame(parent, bg=PANEL, width=230)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        tk.Label(side, text="📁 DATASET", font=("Consolas", 9), bg=PANEL,
                 fg=TEXT_FAINT, anchor="w").pack(fill="x", padx=12, pady=(12, 6))

        batch_frame = tk.Frame(side, bg=PANEL)
        batch_frame.pack(fill="x", padx=8, pady=5)
        self._make_button(batch_frame, "📋 Copy Labels from Previous",
                          self.copy_labels_from_previous,
                          accent2=True).pack(fill="x", pady=2)
        self._make_button(batch_frame, "↩️ Undo (Ctrl+Z)",
                          self.undo_action, accent2=True).pack(fill="x", pady=2)
        self._make_button(batch_frame, "↪️ Redo (Ctrl+Y)",
                          self.redo_action, accent2=True).pack(fill="x", pady=2)
        self._make_button(batch_frame, "💾 Save All Labels",
                          self.save_all_labels, accent=True).pack(fill="x", pady=2)

        list_frame = tk.Frame(side, bg=PANEL)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.image_listbox = tk.Listbox(
            list_frame, bg=PANEL_ALT, fg=TEXT, selectbackground=ACCENT,
            selectforeground="#FFFFFF", font=FONT_UI, bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            yscrollcommand=scrollbar.set, activestyle="none"
        )
        self.image_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.image_listbox.yview)
        self.image_listbox.bind("<<ListboxSelect>>", self.on_image_select)

    def _build_canvas_area(self, parent):
        area = tk.Frame(parent, bg=BG)
        area.pack(side="left", fill="both", expand=True)
        self.canvas_container = tk.Frame(area, bg=BG)
        self.canvas_container.pack(fill="both", expand=True)

        self.placeholder = tk.Label(
            self.canvas_container,
            text=("⚡\n\nSwiftVision.ai\n\nCanvas is empty\n\n"
                  "Load images and drag to draw bounding boxes.\n\n"
                  "📌 Draw box first, then assign class from side panel!\n"
                  "📐 White measurement lines appear while drawing!\n"
                  "🎯 Hover crosshair guide BEFORE you draw!\n"
                  "🔍 Zoom: Mouse Wheel\n"
                  "✋ Pan: Right Click + Drag (on empty area)\n"
                  "🗑️ Right-click on box = DELETE instantly\n"
                  "↩️ Ctrl+Z = UNDO   ↪️ Ctrl+Y = REDO\n"
                  "⬅️➡️ Arrow keys = Move box (Shift = 10px)\n"
                  "🔢 Number keys 1-9 = Quick class apply\n"
                  "📋 Copy labels from previous image\n"
                  "💾 AUTO-SAVE: Only annotated images get a .txt file!"),
            font=FONT_UI, bg=BG, fg=TEXT_FAINT, justify="center"
        )
        self.placeholder.pack(expand=True)

        self.canvas = tk.Canvas(self.canvas_container, bg="black",
                                 highlightthickness=1,
                                 highlightbackground=BORDER, cursor="crosshair")
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click_down)
        self.canvas.bind("<B3-Motion>", self.on_right_click_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_right_click_up)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Leave>", self.on_mouse_leave)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)

    def _build_right_sidebar(self, parent):
        side = tk.Frame(parent, bg=PANEL, width=290)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)

        tk.Label(side, text="🏷️ CLASSES", font=("Consolas", 9), bg=PANEL,
                 fg=TEXT_FAINT, anchor="w").pack(fill="x", padx=12, pady=(12, 6))

        add_row = tk.Frame(side, bg=PANEL)
        add_row.pack(fill="x", padx=10)
        self.class_entry = tk.Entry(add_row, bg=PANEL_ALT, fg=TEXT,
                                     insertbackground=TEXT, font=FONT_UI, bd=0,
                                     highlightthickness=1,
                                     highlightbackground=BORDER,
                                     highlightcolor=GREEN)
        self.class_entry.pack(side="left", fill="x", expand=True,
                              ipady=5, padx=(0, 6))
        self.class_entry.bind("<Return>", lambda e: self.add_class())
        self._make_button(add_row, "+", self.add_class, accent=True,
                          width=3).pack(side="left")

        class_list_frame = tk.Frame(side, bg=PANEL)
        class_list_frame.pack(fill="both", padx=8, pady=8)
        class_scroll = tk.Scrollbar(class_list_frame)
        class_scroll.pack(side="right", fill="y")
        self.class_listbox = tk.Listbox(
            class_list_frame, bg=PANEL_ALT, fg=TEXT,
            selectbackground="#1B3A26", selectforeground=GREEN_LIGHT,
            font=FONT_UI, bd=0, highlightthickness=1,
            highlightbackground=BORDER, yscrollcommand=class_scroll.set,
            height=6, activestyle="none"
        )
        self.class_listbox.pack(side="left", fill="both", expand=True)
        class_scroll.config(command=self.class_listbox.yview)
        self.class_listbox.bind("<ButtonRelease-1>", self.on_class_single_click)
        self.class_listbox.bind("<Double-Button-1>", self.rename_class_dialog)

        class_btn_row = tk.Frame(side, bg=PANEL)
        class_btn_row.pack(fill="x", padx=10, pady=(0, 10))
        self._make_button(class_btn_row, "Rename (R)",
                          self.rename_class_dialog, accent2=True).pack(
            side="left", fill="x", expand=True, padx=(0, 4))
        self._make_button(class_btn_row, "Delete",
                          self.delete_selected_class, danger=True).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

        tk.Frame(side, bg=BORDER, height=1).pack(fill="x")

        tk.Label(side, text="✏️ CHANGE CLASS", font=("Consolas", 9),
                 bg=PANEL, fg=TEXT_FAINT, anchor="w").pack(
            fill="x", padx=12, pady=(12, 6))

        change_frame = tk.Frame(side, bg=PANEL)
        change_frame.pack(fill="x", padx=10, pady=5)

        self.selected_box_label = tk.Label(
            change_frame, text="No box selected",
            font=FONT_UI, bg=PANEL, fg=TEXT_DIM
        )
        self.selected_box_label.pack(anchor="w", pady=(0, 5))

        self.class_change_var = tk.StringVar()
        self.class_change_var.set("Select class...")
        self.class_change_menu = ttk.Combobox(
            change_frame, textvariable=self.class_change_var,
            font=FONT_UI, state="readonly",
            background=PANEL_ALT, foreground=TEXT
        )
        self.class_change_menu.pack(fill="x", pady=5)
        self.class_change_menu.bind("<<ComboboxSelected>>", self.on_class_change)

        self._make_button(change_frame, "Apply Class",
                          self.apply_class_change, accent=True).pack(
            fill="x", pady=5)

        tk.Frame(side, bg=BORDER, height=1).pack(fill="x")

        tk.Label(side, text="📦 ANNOTATIONS", font=("Consolas", 9),
                 bg=PANEL, fg=TEXT_FAINT, anchor="w").pack(
            fill="x", padx=12, pady=(12, 6))

        anno_list_frame = tk.Frame(side, bg=PANEL)
        anno_list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        anno_scroll = tk.Scrollbar(anno_list_frame)
        anno_scroll.pack(side="right", fill="y")
        self.anno_listbox = tk.Listbox(
            anno_list_frame, bg=PANEL_ALT, fg=TEXT,
            selectbackground="#1B3A26", selectforeground=GREEN_LIGHT,
            font=FONT_MONO, bd=0, highlightthickness=1,
            highlightbackground=BORDER, yscrollcommand=anno_scroll.set,
            activestyle="none"
        )
        self.anno_listbox.pack(side="left", fill="both", expand=True)
        anno_scroll.config(command=self.anno_listbox.yview)
        self.anno_listbox.bind("<<ListboxSelect>>", self.on_anno_select)

        del_anno_row = tk.Frame(side, bg=PANEL)
        del_anno_row.pack(fill="x", padx=10, pady=(0, 10))
        self._make_button(del_anno_row, "Delete selected (Del)",
                          self.delete_selected_anno, danger=True).pack(fill="x")

        hint = tk.Label(
            side,
            text=("Draw: Left Click + Drag\n"
                  "Select Box: Left Click on box\n"
                  "DELETE Box: Right-click on box\n"
                  "Move Box: Select box → Drag inside\n"
                  "Resize Box: Drag ANY corner handle\n"
                  "Nudge: Arrow keys (Shift=10px)\n"
                  "Quick Class: 1-9 keys\n"
                  "Change Class: click class in list\n"
                  "UNDO: Ctrl+Z   REDO: Ctrl+Y\n"
                  "Pan: Right Click + Drag (empty area)\n\n"
                  "💾 Empty images get NO .txt file!"),
            font=("Consolas", 8), bg=PANEL, fg=TEXT_FAINT, justify="left"
        )
        hint.pack(fill="x", padx=12, pady=(4, 10))

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PANEL, height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.status_label = tk.Label(
            bar, text="Ready. Single click on class to apply instantly!",
            font=("Consolas", 9), bg=PANEL, fg=TEXT_FAINT, anchor="w"
        )
        self.status_label.pack(side="left", padx=10)

        self.shortcut_label = tk.Label(
            bar,
            text=("←/→ Nudge or Prev/Next  |  Shift+←/→ 10px  |  "
                  "1-9 Class  |  Del Delete  |  Ctrl+Z/Y  |  Ctrl+S Save"),
            font=("Consolas", 8), bg=PANEL, fg=TEXT_DIM
        )
        self.shortcut_label.pack(side="left", padx=20)

        self.zoom_info_label = tk.Label(bar, text="Zoom: 100%",
                                         font=("Consolas", 8),
                                         bg=PANEL, fg=ACCENT2)
        self.zoom_info_label.pack(side="left", padx=10)

        self.coord_label = tk.Label(bar, text="x: 0.000  y: 0.000",
                                     font=("Consolas", 9),
                                     bg=PANEL, fg=ACCENT2, anchor="e")
        self.coord_label.pack(side="right", padx=10)

        self.undo_label = tk.Label(bar, text="↩️ Undo: 0  ↪️ Redo: 0",
                                    font=("Consolas", 8),
                                    bg=PANEL, fg=TEXT_FAINT)
        self.undo_label.pack(side="right", padx=10)

    def _make_button(self, parent, text, command, accent=False, accent2=False,
                     danger=False, width=None):
        bg = PANEL_ALT
        fg = TEXT
        if accent:
            bg, fg = ACCENT, ACCENT_FG
        elif accent2:
            bg, fg = PANEL_ALT, ACCENT2
        elif danger:
            bg, fg = PANEL_ALT, DANGER
        return tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=bg, activeforeground=fg, font=FONT_UI_BOLD,
            bd=0, relief="flat", padx=10, pady=5, cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER,
            width=width
        )

    # =========================================================
    # Keyboard bindings
    # =========================================================
    def _bind_keys(self):
        self.root.bind("<Left>",  self._on_arrow_left)
        self.root.bind("<Right>", self._on_arrow_right)
        self.root.bind("<Up>",    lambda e: self._nudge_selected(0, -1, e))
        self.root.bind("<Down>",  lambda e: self._nudge_selected(0, 1, e))
        self.root.bind("<a>", lambda e: self.prev_image())
        self.root.bind("<A>", lambda e: self.prev_image())
        self.root.bind("<d>", lambda e: self.next_image())
        self.root.bind("<D>", lambda e: self.next_image())
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<BackSpace>", self._on_delete_key)
        self.root.bind("<r>", self._on_r_key)
        self.root.bind("<R>", self._on_r_key)
        self.root.bind("<n>", lambda e: self.class_entry.focus_set())
        self.root.bind("<N>", lambda e: self.class_entry.focus_set())
        for i in range(1, 10):
            self.root.bind(str(i),
                           lambda e, idx=i - 1: self._apply_class_by_index(idx))
        self.root.bind("<Shift_L>", self._shift_pressed)
        self.root.bind("<Shift_R>", self._shift_pressed)
        self.root.bind("<KeyRelease-Shift_L>", self._shift_released)
        self.root.bind("<KeyRelease-Shift_R>", self._shift_released)
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-S>", lambda e: self.save_project())
        self.root.bind("<Control-o>", lambda e: self.load_project())
        self.root.bind("<Control-O>", lambda e: self.load_project())
        self.root.bind("<Control-e>", lambda e: self.export_yolo())
        self.root.bind("<Control-E>", lambda e: self.export_yolo())
        self.root.bind("<Control-0>", lambda e: self.reset_view())
        self.root.bind("<Control-equal>", lambda e: self.zoom_in())
        self.root.bind("<Control-z>", lambda e: self.undo_action())
        self.root.bind("<Control-Z>", lambda e: self.undo_action())
        self.root.bind("<Control-y>", lambda e: self.redo_action())
        self.root.bind("<Control-Y>", lambda e: self.redo_action())

    def _shift_pressed(self, event):
        self.shift_pressed = True

    def _shift_released(self, event):
        self.shift_pressed = False

    def _on_r_key(self, event=None):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Listbox)):
            return
        self.rename_class_dialog()

    def _on_arrow_left(self, event=None):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return
        if self.selected_anno_index is not None:
            self._nudge_selected(-1, 0, event)
        else:
            self.prev_image()

    def _on_arrow_right(self, event=None):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return
        if self.selected_anno_index is not None:
            self._nudge_selected(1, 0, event)
        else:
            self.next_image()

    def _nudge_selected(self, dx, dy, event=None):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return
        if self.selected_anno_index is None:
            return
        annos = self.annotations.get(self.current_image_index, [])
        if self.selected_anno_index >= len(annos):
            return
        step = 10 if self.shift_pressed else 1
        nx = step / max(1, self.disp_w)
        ny = step / max(1, self.disp_h)
        a = annos[self.selected_anno_index]
        old = dict(a)
        a["x"] = max(0.0, min(1.0, a["x"] + dx * nx))
        a["y"] = max(0.0, min(1.0, a["y"] + dy * ny))
        self._save_undo_action("edit", self.current_image_index,
                               self.selected_anno_index, old, dict(a))
        self.render_canvas()
        self.refresh_anno_list()
        self._force_save()

    def _apply_class_by_index(self, class_idx):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, ttk.Combobox)):
            return
        if class_idx < 0 or class_idx >= len(self.classes):
            return
        self.current_class_index = class_idx
        self.refresh_class_list()
        if self.selected_anno_index is not None:
            self._apply_class_to_selected_box(class_idx)
        else:
            self.set_status(
                f"Class selected: {self.classes[class_idx]['name']} "
                f"(select a box to apply)"
            )

    def _on_delete_key(self, event):
        focused = self.root.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Listbox)):
            return
        if self.selected_anno_index is not None:
            annos = self.annotations.get(self.current_image_index, [])
            if 0 <= self.selected_anno_index < len(annos):
                self._save_undo_action(
                    "delete", self.current_image_index,
                    self.selected_anno_index,
                    dict(annos[self.selected_anno_index])
                )
            self._delete_anno_at(self.selected_anno_index)
            self.selected_anno_index = None
            self.render_canvas()
            self.refresh_anno_list()
            self._update_class_change_ui()
            self._force_save()
            self.set_status("Box deleted with DELETE key (Ctrl+Z to undo)")

    # =========================================================
    # FORCE SAVE
    # =========================================================
    def _force_save(self):
        if (self.current_image_index < 0 or
                self.current_image_index >= len(self.images)):
            return False
        for attempt in range(3):
            if self._save_image_txt(self.current_image_index):
                return True
            time.sleep(0.1)
        return False

    # =========================================================
    # UNDO / REDO
    # =========================================================
    def _save_undo_action(self, action_type, image_idx, anno_idx,
                          data=None, new_data=None):
        if len(self.undo_stack) >= self.undo_limit:
            self.undo_stack.pop(0)
        self.undo_stack.append({
            "type": action_type,
            "image_idx": image_idx,
            "anno_idx": anno_idx,
            "data": data,
            "new_data": new_data,
            "timestamp": time.time(),
        })
        self.redo_stack.clear()
        self._update_undo_label()

    def _update_undo_label(self):
        self.undo_label.config(
            text=f"↩️ Undo: {len(self.undo_stack)}  ↪️ Redo: {len(self.redo_stack)}"
        )

    def undo_action(self):
        if not self.undo_stack:
            self.set_status("⚠️ Nothing to undo")
            return
        action = self.undo_stack.pop()
        try:
            t = action["type"]
            img = action["image_idx"]
            idx = action["anno_idx"]

            if t == "add":
                if img in self.annotations and idx < len(self.annotations[img]):
                    action["data"] = dict(self.annotations[img][idx])
                    del self.annotations[img][idx]
                self.set_status("↩️ Undo: Removed added box")
            elif t == "delete":
                data = action["data"]
                self.annotations.setdefault(img, [])
                if idx <= len(self.annotations[img]):
                    self.annotations[img].insert(idx, data)
                else:
                    self.annotations[img].append(data)
                self.set_status("↩️ Undo: Restored deleted box")
            elif t == "edit":
                if img in self.annotations and idx < len(self.annotations[img]):
                    action["new_data"] = dict(self.annotations[img][idx])
                    self.annotations[img][idx] = action["data"]
                self.set_status("↩️ Undo: Restored previous box state")
            elif t == "copy_labels":
                n = action["data"]
                captured = []
                for _ in range(n):
                    if img in self.annotations and self.annotations[img]:
                        captured.insert(0, self.annotations[img].pop())
                action["new_data"] = captured
                self.set_status(f"↩️ Undo: Removed {n} copied labels")

            self.redo_stack.append(action)
            self._update_undo_label()
            self.render_canvas()
            self.refresh_anno_list()
            self.refresh_image_list()
            self._update_class_change_ui()
            self._force_save()
        except Exception as e:
            self.set_status(f"⚠️ Undo error: {e}")
            self.undo_stack.append(action)
            self._update_undo_label()

    def redo_action(self):
        if not self.redo_stack:
            self.set_status("⚠️ Nothing to redo")
            return
        action = self.redo_stack.pop()
        try:
            t = action["type"]
            img = action["image_idx"]
            idx = action["anno_idx"]

            if t == "add":
                self.annotations.setdefault(img, [])
                if idx <= len(self.annotations[img]):
                    self.annotations[img].insert(idx, action["data"])
                else:
                    self.annotations[img].append(action["data"])
                self.set_status("↪️ Redo: Added box")
            elif t == "delete":
                if img in self.annotations and idx < len(self.annotations[img]):
                    del self.annotations[img][idx]
                self.set_status("↪️ Redo: Deleted box")
            elif t == "edit":
                if img in self.annotations and idx < len(self.annotations[img]):
                    self.annotations[img][idx] = action["new_data"]
                self.set_status("↪️ Redo: Applied edit")
            elif t == "copy_labels":
                for box in action.get("new_data", []):
                    self.annotations.setdefault(img, []).append(box)
                self.set_status("↪️ Redo: Re-applied copied labels")

            self.undo_stack.append(action)
            self._update_undo_label()
            self.render_canvas()
            self.refresh_anno_list()
            self.refresh_image_list()
            self._update_class_change_ui()
            self._force_save()
        except Exception as e:
            self.set_status(f"⚠️ Redo error: {e}")
            self.redo_stack.append(action)
            self._update_undo_label()

    def copy_labels_from_previous(self):
        if self.current_image_index <= 0:
            messagebox.showinfo("No Previous Image",
                                "This is the first image. No previous image available.")
            return
        prev_idx = self.current_image_index - 1
        prev_annos = self.annotations.get(prev_idx, [])
        if not prev_annos:
            messagebox.showinfo("No Labels", "Previous image has no labels to copy.")
            return
        if not messagebox.askyesno(
            "Copy Labels",
            f"Copy {len(prev_annos)} labels from previous image to current image?"
        ):
            return
        copied_count = 0
        for anno in prev_annos:
            new_anno = {
                "class_idx": anno["class_idx"],
                "x": anno["x"], "y": anno["y"],
                "w": anno["w"], "h": anno["h"]
            }
            self.annotations.setdefault(self.current_image_index, []).append(new_anno)
            copied_count += 1
        self._save_undo_action(
            "copy_labels", self.current_image_index,
            len(self.annotations[self.current_image_index]) - copied_count,
            copied_count,
            [dict(a) for a in prev_annos]
        )
        self.render_canvas()
        self.refresh_anno_list()
        self.refresh_image_list()
        self._force_save()
        self.set_status(
            f"📋 Copied {copied_count} labels from previous image. (Ctrl+Z to undo)"
        )

    def save_all_labels(self):
        if not self.images:
            messagebox.showinfo("No Images", "No images loaded.")
            return
        total = len(self.images)
        saved = 0
        failed = 0
        self._show_progress(f"Saving {total} images...", total)
        for idx in range(total):
            if self._save_image_txt(idx):
                saved += 1
            else:
                failed += 1
            self._update_progress(
                idx + 1,
                f"Saving... {idx+1}/{total} ({int((idx+1)/total*100)}%)"
            )
        self._hide_progress()
        annotated = sum(
            1 for i in range(total)
            if any(0 <= a["class_idx"] < len(self.classes)
                   for a in self.annotations.get(i, []))
        )
        empty = total - annotated
        self.set_status(
            f"✅ Saved {annotated} annotated images "
            f"({empty} empty skipped), {failed} failed"
        )
        messagebox.showinfo(
            "Save Complete",
            f"Annotated images saved: {annotated}\n"
            f"Empty images skipped:  {empty}\n"
            f"Failed:                {failed}\n\n"
            f"💡 Only images with labels get a .txt file."
        )

    def _update_class_change_ui(self):
        if self.selected_anno_index is None:
            self.selected_box_label.config(text="No box selected", fg=TEXT_DIM)
            self.class_change_var.set("Select class...")
            self.class_change_menu.config(values=[])
            return
        annos = self.annotations.get(self.current_image_index, [])
        if self.selected_anno_index >= len(annos):
            self.selected_anno_index = None
            self._update_class_change_ui()
            return
        a = annos[self.selected_anno_index]
        class_names = [c["name"] for c in self.classes]
        self.class_change_menu.config(values=class_names)
        if 0 <= a["class_idx"] < len(self.classes):
            current_name = self.classes[a["class_idx"]]["name"]
            self.class_change_var.set(current_name)
            self.selected_box_label.config(
                text=f"Box {self.selected_anno_index+1}: {current_name}",
                fg=GREEN_LIGHT
            )
        elif a["class_idx"] == -1:
            self.class_change_var.set("Select class...")
            self.selected_box_label.config(
                text=f"Box {self.selected_anno_index+1}: (unassigned)",
                fg=TEXT_DIM
            )
        else:
            self.class_change_var.set("Select class...")
            self.selected_box_label.config(
                text=f"Box {self.selected_anno_index+1}: (unknown)",
                fg=DANGER
            )

    def on_class_change(self, event=None):
        selected_name = self.class_change_var.get()
        if selected_name == "Select class..." or not selected_name:
            return
        class_idx = -1
        for idx, c in enumerate(self.classes):
            if c["name"] == selected_name:
                class_idx = idx
                break
        if class_idx == -1:
            return
        self._apply_class_to_selected_box(class_idx)

    def apply_class_change(self):
        selected_name = self.class_change_var.get()
        if selected_name == "Select class..." or not selected_name:
            messagebox.showinfo("No Class Selected",
                                "Please select a class from the dropdown first.")
            return
        class_idx = -1
        for idx, c in enumerate(self.classes):
            if c["name"] == selected_name:
                class_idx = idx
                break
        if class_idx == -1:
            return
        self._apply_class_to_selected_box(class_idx)

    def _apply_class_to_selected_box(self, class_idx):
        if self.selected_anno_index is None:
            self.current_class_index = class_idx
            self.refresh_class_list()
            self.set_status(f"Class selected: {self.classes[class_idx]['name']}")
            return
        annos = self.annotations.get(self.current_image_index, [])
        if self.selected_anno_index >= len(annos):
            return
        old_data = dict(annos[self.selected_anno_index])
        annos[self.selected_anno_index]["class_idx"] = class_idx
        self.current_class_index = class_idx
        self._save_undo_action(
            "edit", self.current_image_index, self.selected_anno_index,
            old_data, dict(annos[self.selected_anno_index])
        )
        self.render_canvas()
        self.refresh_anno_list()
        self.refresh_class_list()
        self._update_class_change_ui()
        self._force_save()
        self.set_status(f"✅ Class applied: {self.classes[class_idx]['name']}")

    def on_class_single_click(self, event):
        sel = self.class_listbox.curselection()
        if not sel:
            return
        class_idx = sel[0]
        self.current_class_index = class_idx
        self.refresh_class_list()
        if self.selected_anno_index is not None:
            self._apply_class_to_selected_box(class_idx)
        else:
            self.set_status(
                f"Class selected: {self.classes[class_idx]['name']} "
                f"(click on a box to apply)"
            )

    def _show_class_selection_popup(self, anno_index):
        if not self.classes:
            new_class = simpledialog.askstring(
                "Create Class",
                "No classes exist. Enter a class name for this box:",
                parent=self.root
            )
            if new_class and new_class.strip():
                new_class = new_class.strip()
                if any(c["name"].lower() == new_class.lower() for c in self.classes):
                    for idx, c in enumerate(self.classes):
                        if c["name"].lower() == new_class.lower():
                            self._apply_class_to_selected_box(idx)
                            return
                else:
                    color = PALETTE[len(self.classes) % len(PALETTE)]
                    self.classes.append({"name": new_class, "color": color})
                    self.refresh_class_list()
                    self._save_classes_files()
                    self._apply_class_to_selected_box(len(self.classes) - 1)
                    return
            return
        class_names = [c["name"] for c in self.classes]
        popup = tk.Toplevel(self.root)
        popup.title("Select Class")
        popup.geometry("300x250")
        popup.configure(bg=PANEL)
        popup.transient(self.root)
        popup.grab_set()
        popup.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 250) // 2
        popup.geometry(f"+{x}+{y}")
        tk.Label(popup, text="Select a class for this box:",
                 font=FONT_UI, bg=PANEL, fg=TEXT).pack(pady=(20, 10))
        list_frame = tk.Frame(popup, bg=PANEL)
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        class_list = tk.Listbox(
            list_frame, bg=PANEL_ALT, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#FFFFFF",
            font=FONT_UI, bd=0, highlightthickness=1,
            highlightbackground=BORDER, yscrollcommand=scrollbar.set,
            activestyle="none"
        )
        class_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=class_list.yview)
        for i, name in enumerate(class_names):
            color = self.classes[i]["color"]
            class_list.insert("end", name)
            class_list.itemconfig(i, {"fg": color})
        if class_names:
            class_list.selection_set(0)
        result = [None]

        def confirm_selection():
            sel = class_list.curselection()
            if sel:
                result[0] = sel[0]
                popup.destroy()
            else:
                messagebox.showinfo("No Selection", "Please select a class.")

        def cancel():
            result[0] = -1
            popup.destroy()

        button_frame = tk.Frame(popup, bg=PANEL)
        button_frame.pack(pady=15)
        self._make_button(button_frame, "Apply", confirm_selection,
                          accent=True).pack(side="left", padx=5)
        self._make_button(button_frame, "Skip", cancel).pack(side="left", padx=5)
        class_list.bind("<ButtonRelease-1>", lambda e: confirm_selection())
        popup.bind("<Return>", lambda e: confirm_selection())
        popup.bind("<Escape>", lambda e: cancel())
        self.root.wait_window(popup)
        if result[0] is not None and result[0] >= 0:
            self._apply_class_to_selected_box(result[0])
            return True
        return False

    def _show_progress(self, title, max_value):
        self.progress_window = tk.Toplevel(self.root)
        self.progress_window.title(title)
        self.progress_window.geometry("400x120")
        self.progress_window.configure(bg=PANEL)
        self.progress_window.transient(self.root)
        self.progress_window.grab_set()
        self.progress_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 120) // 2
        self.progress_window.geometry(f"+{x}+{y}")
        tk.Label(self.progress_window, text=title, font=FONT_UI_BOLD,
                 bg=PANEL, fg=TEXT).pack(pady=(15, 5))
        self.progress_label = tk.Label(self.progress_window,
                                        text="Loading... 0%",
                                        font=FONT_UI, bg=PANEL, fg=TEXT_DIM)
        self.progress_label.pack(pady=5)
        self.progress_var = ttk.Progressbar(self.progress_window,
                                             length=350, mode='determinate',
                                             maximum=max_value)
        self.progress_var.pack(pady=10)
        self.progress_var['value'] = 0
        self.root.update()

    def _update_progress(self, value, text=None):
        if self.progress_var:
            self.progress_var['value'] = value
            if text:
                self.progress_label.config(text=text)
            self.progress_window.update()
            self.root.update()

    def _hide_progress(self):
        if self.progress_window:
            self.progress_window.destroy()
            self.progress_window = None
            self.progress_var = None
            self.progress_label = None

    def zoom_in(self):
        self.zoom_level = min(5.0, self.zoom_level * 1.2)
        self.update_zoom_display()
        self.render_canvas()

    def zoom_out(self):
        self.zoom_level = max(0.1, self.zoom_level / 1.2)
        self.update_zoom_display()
        self.render_canvas()

    def reset_view(self):
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update_zoom_display()
        self.render_canvas()

    def update_zoom_display(self):
        percent = int(self.zoom_level * 100)
        self.zoom_label.config(text=f"{percent}%")
        self.zoom_info_label.config(text=f"Zoom: {percent}%")

    def on_mouse_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def _schedule_auto_save(self):
        if self._save_timer:
            self.root.after_cancel(self._save_timer)
        self._force_save()
        self._save_timer = self.root.after(300, self._force_save)

    def _write_classes_txt(self, image_dir):
        if not self.classes:
            return
        try:
            classes_path = os.path.join(image_dir, "classes.txt")
            with open(classes_path, "w", encoding="utf-8") as f:
                f.write("\n".join(c["name"] for c in self.classes))
        except Exception:
            pass

    def _save_image_txt(self, image_index):
        if image_index < 0 or image_index >= len(self.images):
            return False
        im = self.images[image_index]
        annos = self.annotations.get(image_index, [])
        image_dir = os.path.dirname(im["path"])
        base_name = os.path.splitext(im["name"])[0]
        txt_path = os.path.join(image_dir, base_name + ".txt")
        lines = []
        for a in annos:
            if 0 <= a["class_idx"] < len(self.classes):
                lines.append(
                    f"{a['class_idx']} {a['x']:.6f} {a['y']:.6f} "
                    f"{a['w']:.6f} {a['h']:.6f}"
                )
        if not lines:
            try:
                if os.path.exists(txt_path):
                    os.remove(txt_path)
                tmp_path = txt_path + ".tmp"
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            self._write_classes_txt(image_dir)
            self.auto_save_label.config(text="💾 NO LABELS", fg=TEXT_DIM)
            return True
        try:
            temp_path = txt_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            with open(temp_path, "r", encoding="utf-8") as f:
                verify_lines = f.readlines()
            if len(lines) != len(verify_lines):
                raise Exception(
                    f"Save verification failed: expected {len(lines)}, "
                    f"got {len(verify_lines)}"
                )
            if os.path.exists(txt_path):
                os.remove(txt_path)
            os.rename(temp_path, txt_path)
            self._write_classes_txt(image_dir)
            with open(txt_path, "r", encoding="utf-8") as f:
                saved_lines = f.readlines()
            if len(saved_lines) != len(lines):
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                with open(txt_path, "r", encoding="utf-8") as f:
                    final_lines = f.readlines()
                if len(final_lines) != len(lines):
                    self.auto_save_label.config(text="⚠️ PARTIAL SAVE",
                                                 fg="#FFA500")
                    self.set_status(
                        f"⚠️ Warning: Saved {len(final_lines)}/"
                        f"{len(lines)} boxes"
                    )
                    return False
            self.auto_save_label.config(text="💾 SAVED", fg=GREEN_LIGHT)
            return True
        except Exception as e:
            self.auto_save_label.config(text="⚠️ SAVE FAILED", fg=DANGER)
            self.set_status(f"Error saving {txt_path}: {e}")
            return False

    def set_status(self, msg):
        self.status_label.config(text=msg)

    def _load_classes_from_file(self, folder_path):
        classes_path = os.path.join(folder_path, "classes.txt")
        if not os.path.exists(classes_path):
            return False
        try:
            with open(classes_path, "r", encoding="utf-8") as f:
                class_names = [line.strip() for line in f if line.strip()]
            if not class_names:
                return False
            self.classes = []
            for idx, name in enumerate(class_names):
                color = PALETTE[idx % len(PALETTE)]
                self.classes.append({"name": name, "color": color})
            self.classes_loaded_from_file = True
            return True
        except Exception as e:
            print(f"Error loading classes: {e}")
            return False

    def _auto_create_classes(self, max_class_id):
        existing_names = {c["name"] for c in self.classes}
        for i in range(max_class_id + 1):
            name = str(i)
            if name not in existing_names:
                color = PALETTE[len(self.classes) % len(PALETTE)]
                self.classes.append({"name": name, "color": color})
        self.classes_loaded_from_file = False

    def load_images(self):
        paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp")]
        )
        if paths:
            self._add_images(paths)

    def load_folder(self):
        folder = filedialog.askdirectory(title="Select Folder")
        if not folder:
            return
        exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
        paths = [os.path.join(folder, f)
                 for f in sorted(os.listdir(folder))
                 if f.lower().endswith(exts)]
        if not paths:
            messagebox.showinfo("No Images Found",
                                "No supported images found in this folder.")
            return
        if self._load_classes_from_file(folder):
            self.set_status(
                f"Classes loaded from classes.txt ({len(self.classes)} classes)"
            )
            self.refresh_class_list()
            self._update_class_change_ui()
        self._add_images(paths)

    def _add_images(self, paths):
        if self.is_loading:
            return
        self.is_loading = True
        total = len(paths)
        self._show_progress(f"Loading {total} images...", total)

        def load_images_thread():
            added = 0
            max_class_id = -1
            self.root.config(cursor="watch")
            for i, p in enumerate(paths):
                try:
                    with Image.open(p) as probe:
                        w, h = probe.size
                except Exception:
                    self._update_progress(i + 1,
                                           f"Error: {os.path.basename(p)}")
                    continue
                txt_path = os.path.splitext(p)[0] + ".txt"
                annos = []
                if os.path.exists(txt_path):
                    try:
                        with open(txt_path, "r", encoding="utf-8") as f:
                            for line in f:
                                parts = line.strip().split()
                                if len(parts) >= 5:
                                    class_id = int(parts[0])
                                    annos.append({
                                        "class_idx": class_id,
                                        "x": float(parts[1]),
                                        "y": float(parts[2]),
                                        "w": float(parts[3]),
                                        "h": float(parts[4])
                                    })
                                    if class_id > max_class_id:
                                        max_class_id = class_id
                    except Exception:
                        pass
                entry = {"path": p, "name": os.path.basename(p),
                         "w": w, "h": h}
                self.images.append(entry)
                self.annotations[len(self.images) - 1] = annos
                added += 1
                percent = int((i + 1) / total * 100)
                self._update_progress(
                    i + 1,
                    f"Loading... {i+1}/{total} ({percent}%)"
                )
                if i % 10 == 0:
                    self.root.update_idletasks()
            if not self.classes_loaded_from_file and max_class_id >= 0:
                self._auto_create_classes(max_class_id)
                if self.images:
                    folder = os.path.dirname(self.images[0]["path"])
                    classes_path = os.path.join(folder, "classes.txt")
                    with open(classes_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(c["name"] for c in self.classes))
            self.root.after(0, self._finish_loading, added)

        thread = Thread(target=load_images_thread)
        thread.daemon = True
        thread.start()

    def _finish_loading(self, added):
        self.is_loading = False
        self._hide_progress()
        self.root.config(cursor="")
        if added:
            if self.current_image_index == -1:
                self.current_image_index = 0
            self.reset_view()
            self.refresh_image_list()
            self.render_canvas()
            self.refresh_anno_list()
            self.update_counter()
            self.refresh_class_list()
            self._update_class_change_ui()
            self.set_status(
                f"✅ {added} image(s) loaded successfully. Auto-save enabled."
            )
        else:
            self.set_status("⚠️ No images could be loaded.")

    def refresh_image_list(self):
        self.image_listbox.delete(0, "end")
        for idx, im in enumerate(self.images):
            count = len(self.annotations.get(idx, []))
            label = f"{idx+1:02d}. {im['name']}"
            if count:
                label += f"   ({count})"
            self.image_listbox.insert("end", label)
        if self.current_image_index >= 0:
            self.image_listbox.selection_clear(0, "end")
            self.image_listbox.selection_set(self.current_image_index)
            self.image_listbox.see(self.current_image_index)

    def on_image_select(self, event):
        sel = self.image_listbox.curselection()
        if not sel:
            return
        if self.current_image_index >= 0:
            self._force_save()
        self.current_image_index = sel[0]
        self.selected_anno_index = None
        self.is_editing = False
        self.reset_view()
        self.render_canvas()
        self.refresh_anno_list()
        self.update_counter()
        self._update_class_change_ui()
        self.set_status(
            f"Image {self.current_image_index+1} loaded. Auto-save verified."
        )

    def prev_image(self):
        if not self.images:
            return
        if self.current_image_index >= 0:
            self._force_save()
        self.current_image_index = max(0, self.current_image_index - 1)
        self.selected_anno_index = None
        self.is_editing = False
        self.reset_view()
        self.refresh_image_list()
        self.render_canvas()
        self.refresh_anno_list()
        self.update_counter()
        self._update_class_change_ui()

    def next_image(self):
        if not self.images:
            return
        if self.current_image_index >= 0:
            self._force_save()
        self.current_image_index = min(len(self.images) - 1,
                                        self.current_image_index + 1)
        self.selected_anno_index = None
        self.is_editing = False
        self.reset_view()
        self.refresh_image_list()
        self.render_canvas()
        self.refresh_anno_list()
        self.update_counter()
        self._update_class_change_ui()

    def update_counter(self):
        if not self.images:
            self.counter_label.config(text="0 / 0")
        else:
            self.counter_label.config(
                text=f"{self.current_image_index+1} / {len(self.images)}"
            )

    def add_class(self):
        name = self.class_entry.get().strip()
        if not name:
            name = str(len(self.classes))
        if any(c["name"].lower() == name.lower() for c in self.classes):
            messagebox.showinfo("Duplicate", f"Class '{name}' already exists.")
            return
        color = PALETTE[len(self.classes) % len(PALETTE)]
        self.classes.append({"name": name, "color": color})
        self.current_class_index = len(self.classes) - 1
        self.class_entry.delete(0, "end")
        self.refresh_class_list()
        self._save_classes_files()
        self._save_all_txt()
        self._update_class_change_ui()
        self.set_status(f"Class '{name}' added. Auto-saved.")

    def _save_classes_files(self):
        folders = set()
        for im in self.images:
            folders.add(os.path.dirname(im["path"]))
        for folder in folders:
            classes_path = os.path.join(folder, "classes.txt")
            with open(classes_path, "w", encoding="utf-8") as f:
                f.write("\n".join(c["name"] for c in self.classes))

    def refresh_class_list(self):
        self.class_listbox.delete(0, "end")
        for idx, c in enumerate(self.classes):
            self.class_listbox.insert("end", f"  ■  {c['name']}")
            self.class_listbox.itemconfig(idx, {"fg": c["color"]})
        if 0 <= self.current_class_index < len(self.classes):
            self.class_listbox.selection_clear(0, "end")
            self.class_listbox.selection_set(self.current_class_index)
            self.class_listbox.see(self.current_class_index)
        class_names = [c["name"] for c in self.classes]
        self.class_change_menu.config(values=class_names)
        if not class_names:
            self.class_change_var.set("Select class...")

    def on_class_select(self, event):
        pass

    def rename_class_dialog(self, event=None):
        sel = self.class_listbox.curselection()
        if sel:
            idx = sel[0]
        elif 0 <= self.current_class_index < len(self.classes):
            idx = self.current_class_index
        else:
            messagebox.showinfo("No Class Selected",
                                "Please select a class from the list first.")
            return
        old_name = self.classes[idx]["name"]
        new_name = simpledialog.askstring(
            "Rename Class",
            f"Rename '{old_name}' to:",
            initialvalue=old_name,
            parent=self.root
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        if any(j != idx and c["name"].lower() == new_name.lower()
               for j, c in enumerate(self.classes)):
            messagebox.showinfo("Duplicate",
                                "This name is already used by another class.")
            return
        self.classes[idx]["name"] = new_name
        self.current_class_index = idx
        self.refresh_class_list()
        self.class_listbox.selection_clear(0, "end")
        self.class_listbox.selection_set(idx)
        self.class_listbox.see(idx)
        self.refresh_anno_list()
        self.render_canvas()
        self._save_classes_files()
        self._save_all_txt()
        self._update_class_change_ui()
        self.set_status(f"✅ Class renamed: '{old_name}' → '{new_name}'")

    def delete_selected_class(self):
        if (self.current_class_index < 0 or
                self.current_class_index >= len(self.classes)):
            sel = self.class_listbox.curselection()
            if sel:
                self.current_class_index = sel[0]
            else:
                messagebox.showinfo("No Class Selected",
                                    "Please select a class from the list first.")
                return
        idx = self.current_class_index
        name = self.classes[idx]["name"]
        if not messagebox.askyesno(
            "Confirm",
            f"Delete class '{name}'? All associated boxes will also be removed."
        ):
            return
        del self.classes[idx]
        for img_idx in list(self.annotations.keys()):
            new_list = []
            for a in self.annotations[img_idx]:
                if a["class_idx"] == idx:
                    continue
                if a["class_idx"] > idx:
                    a = dict(a)
                    a["class_idx"] -= 1
                new_list.append(a)
            self.annotations[img_idx] = new_list
        if self.classes:
            self.current_class_index = min(idx, len(self.classes) - 1)
        else:
            self.current_class_index = -1
        self.selected_anno_index = None
        self.is_editing = False
        self.refresh_class_list()
        self.refresh_anno_list()
        self.refresh_image_list()
        self.render_canvas()
        self._save_classes_files()
        self._save_all_txt()
        self._update_class_change_ui()
        self.set_status(f"Class '{name}' deleted. Auto-saved.")

    def current_image(self):
        if 0 <= self.current_image_index < len(self.images):
            return self.images[self.current_image_index]
        return None

    def render_canvas(self):
        im = self.current_image()
        if im is None:
            self.canvas.pack_forget()
            self.placeholder.pack(expand=True)
            return
        self.placeholder.pack_forget()
        self.canvas.pack(expand=True)
        self.canvas_container.update_idletasks()
        container_w = max(200, int(self.canvas_container.winfo_width() * 0.94))
        container_h = max(200, int(self.canvas_container.winfo_height() * 0.92))
        base_scale = min(container_w / im["w"], container_h / im["h"])
        base_w = int(im["w"] * base_scale)
        base_h = int(im["h"] * base_scale)
        self.disp_w = int(base_w * self.zoom_level)
        self.disp_h = int(base_h * self.zoom_level)
        max_pan_x = max(0, self.disp_w - container_w) // 2
        max_pan_y = max(0, self.disp_h - container_h) // 2
        self.pan_x = max(-max_pan_x, min(max_pan_x, self.pan_x))
        self.pan_y = max(-max_pan_y, min(max_pan_y, self.pan_y))
        cache_key = (self.current_image_index, self.disp_w, self.disp_h)
        if self._bitmap_cache_index != cache_key:
            try:
                self.tk_img = self._load_bitmap(im["path"], self.disp_w,
                                                 self.disp_h)
                self._bitmap_cache_index = cache_key
            except Exception as e:
                self.canvas.delete("all")
                self.canvas.create_text(
                    container_w / 2, container_h / 2,
                    text=f"Image failed to load:\n{e}",
                    fill=DANGER, font=FONT_UI
                )
                return
        self.canvas.delete("all")
        self.canvas.config(width=container_w, height=container_h)
        x_offset = (container_w - self.disp_w) // 2 + self.pan_x
        y_offset = (container_h - self.disp_h) // 2 + self.pan_y
        self.image_x_offset = x_offset
        self.image_y_offset = y_offset
        self.canvas.create_image(x_offset, y_offset, anchor="nw",
                                  image=self.tk_img)
        annos = self.annotations.get(self.current_image_index, [])
        for i, a in enumerate(annos):
            self._draw_box_with_pan(a, selected=(i == self.selected_anno_index))
        if self.temp_rect:
            self._draw_labelimg_measurements_with_pan()
        elif self.hover_xy is not None:
            self._draw_hover_guides(self.hover_xy[0], self.hover_xy[1])

    def _load_bitmap(self, path, disp_w, disp_h):
        img = Image.open(path)
        try:
            img.draft("RGB", (disp_w, disp_h))
        except Exception:
            pass
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        resized = img.resize((disp_w, disp_h), Image.BILINEAR)
        return ImageTk.PhotoImage(resized)

    def _get_pixel_coords(self, a):
        bx = (a["x"] - a["w"] / 2) * self.disp_w + self.image_x_offset
        by = (a["y"] - a["h"] / 2) * self.disp_h + self.image_y_offset
        bw = a["w"] * self.disp_w
        bh = a["h"] * self.disp_h
        return bx, by, bw, bh

    def _box_from_pixel_rect_with_pan(self, bx, by, bw, bh):
        cx = (bx + bw / 2 - self.image_x_offset) / self.disp_w
        cy = (by + bh / 2 - self.image_y_offset) / self.disp_h
        w = bw / self.disp_w
        h = bh / self.disp_h
        return {"x": max(0, min(1, cx)), "y": max(0, min(1, cy)),
                "w": max(0.01, min(1, w)), "h": max(0.01, min(1, h))}

    def _draw_box_with_pan(self, a, selected=False):
        if 0 <= a["class_idx"] < len(self.classes):
            cls = self.classes[a["class_idx"]]
            color = cls["color"]
            label = cls["name"]
        elif a["class_idx"] == -1:
            color = "#888888"
            label = "?"
        else:
            color = "#ffffff"
            label = "?"
        bx, by, bw, bh = self._get_pixel_coords(a)
        width = 3 if selected else 2
        self.canvas.create_rectangle(bx, by, bx + bw, by + bh,
                                      outline=color, width=width)
        label_h = 16
        ly = by - label_h if by - label_h >= 0 else by + bh
        text_w = 7 * len(label) + 12
        self.canvas.create_rectangle(bx, ly, bx + text_w, ly + label_h,
                                      fill=color, outline=color)
        self.canvas.create_text(bx + 6, ly + label_h / 2, text=label,
                                 anchor="w", fill="#0B0F14",
                                 font=("Consolas", 9, "bold"))
        if selected:
            handles = self._get_handle_rects(bx, by, bw, bh)
            for key, (hx0, hy0, hx1, hy1) in handles.items():
                self.canvas.create_rectangle(hx0, hy0, hx1, hy1, fill=color,
                                              outline="#FFFFFF", width=1)

    def _get_handle_rects(self, bx, by, bw, bh):
        s = HANDLE_SIZE
        half = s / 2
        return {
            "tl": (bx - half, by - half, bx + half, by + half),
            "tr": (bx + bw - half, by - half, bx + bw + half, by + half),
            "bl": (bx - half, by + bh - half, bx + half, by + bh + half),
            "br": (bx + bw - half, by + bh - half, bx + bw + half, by + bh + half)
        }

    def _draw_labelimg_measurements_with_pan(self):
        x, y, w, h = self.temp_rect
        px = x + self.image_x_offset
        py = y + self.image_y_offset
        color = "#ffffff"
        self.canvas.create_rectangle(px, py, px + w, py + h, outline=color,
                                      width=2, dash=(5, 4))
        line_y = py + h / 2
        self.canvas.create_line(self.image_x_offset, line_y,
                                 self.image_x_offset + self.disp_w, line_y,
                                 fill=MEASURE_COLOR, width=2, dash=(6, 4))
        line_x = px + w / 2
        self.canvas.create_line(line_x, self.image_y_offset, line_x,
                                 self.image_y_offset + self.disp_h,
                                 fill=MEASURE_COLOR, width=2, dash=(6, 4))
        dim_y = py + h + 25
        self.canvas.create_line(px, dim_y, px + w, dim_y,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(px, dim_y - 6, px, dim_y + 6,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(px + w, dim_y - 6, px + w, dim_y + 6,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(px, dim_y, px + 6, dim_y - 5,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(px, dim_y, px + 6, dim_y + 5,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(px + w, dim_y, px + w - 6, dim_y - 5,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(px + w, dim_y, px + w - 6, dim_y + 5,
                                 fill=MEASURE_COLOR, width=2)
        width_pixels = int(w)
        self.canvas.create_text(px + w / 2, dim_y + 18,
                                 text=f"{width_pixels}px",
                                 fill=MEASURE_COLOR,
                                 font=("Consolas", 9, "bold"))
        dim_x = px + w + 25
        self.canvas.create_line(dim_x, py, dim_x, py + h,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(dim_x - 6, py, dim_x + 6, py,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(dim_x - 6, py + h, dim_x + 6, py + h,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(dim_x, py, dim_x - 5, py + 6,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(dim_x, py, dim_x + 5, py + 6,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(dim_x, py + h, dim_x - 5, py + h - 6,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(dim_x, py + h, dim_x + 5, py + h - 6,
                                 fill=MEASURE_COLOR, width=2)
        height_pixels = int(h)
        self.canvas.create_text(dim_x + 18, py + h / 2,
                                 text=f"{height_pixels}px",
                                 fill=MEASURE_COLOR,
                                 font=("Consolas", 9, "bold"))
        marker_size = 14
        self.canvas.create_line(px, py + marker_size, px, py,
                                 px + marker_size, py,
                                 fill=color, width=3)
        self.canvas.create_line(px + w - marker_size, py, px + w, py,
                                 px + w, py + marker_size,
                                 fill=color, width=3)
        self.canvas.create_line(px, py + h - marker_size, px, py + h,
                                 px + marker_size, py + h,
                                 fill=color, width=3)
        self.canvas.create_line(px + w - marker_size, py + h, px + w, py + h,
                                 px + w, py + h - marker_size,
                                 fill=color, width=3)
        cx = px + w / 2
        cy = py + h / 2
        cross_size = 8
        self.canvas.create_line(cx - cross_size, cy, cx + cross_size, cy,
                                 fill=MEASURE_COLOR, width=2)
        self.canvas.create_line(cx, cy - cross_size, cx, cy + cross_size,
                                 fill=MEASURE_COLOR, width=2)

    def _draw_hover_guides(self, cx, cy):
        if self.disp_w == 0 or self.disp_h == 0:
            return
        if self.drawing or self.is_editing or self.panning:
            return
        img_x, img_y = self._get_original_coords(cx, cy)
        if not (0 <= img_x <= self.disp_w and 0 <= img_y <= self.disp_h):
            return
        self.canvas.create_line(
            self.image_x_offset, cy, self.image_x_offset + self.disp_w, cy,
            fill=HOVER_COLOR, width=1, dash=(4, 3), tags="hover_guide"
        )
        self.canvas.create_line(
            cx, self.image_y_offset, cx, self.image_y_offset + self.disp_h,
            fill=HOVER_COLOR, width=1, dash=(4, 3), tags="hover_guide"
        )
        tick = 6
        self.canvas.create_line(cx - tick, cy, cx + tick, cy,
                                 fill=HOVER_COLOR, width=1, tags="hover_guide")
        self.canvas.create_line(cx, cy - tick, cx, cy + tick,
                                 fill=HOVER_COLOR, width=1, tags="hover_guide")
        label_x = cx + 12
        label_y = cy - 14
        text = f"({int(img_x)}, {int(img_y)})"
        text_w = 7 * len(text) + 8
        self.canvas.create_rectangle(
            label_x - 2, label_y - 8, label_x + text_w, label_y + 8,
            fill="#000000", outline=HOVER_COLOR, width=1, tags="hover_guide"
        )
        self.canvas.create_text(
            label_x + 2, label_y, text=text,
            fill=HOVER_COLOR, font=("Consolas", 8, "bold"),
            anchor="w", tags="hover_guide"
        )

    def _get_original_coords(self, canvas_x, canvas_y):
        img_x = canvas_x - self.image_x_offset
        img_y = canvas_y - self.image_y_offset
        return img_x, img_y

    def _is_point_on_box_with_pan(self, canvas_x, canvas_y, a):
        bx, by, bw, bh = self._get_pixel_coords(a)
        tolerance = 5
        return (bx - tolerance <= canvas_x <= bx + bw + tolerance and
                by - tolerance <= canvas_y <= by + bh + tolerance)

    def _is_point_on_handle_with_pan(self, canvas_x, canvas_y, a):
        bx, by, bw, bh = self._get_pixel_coords(a)
        handles = self._get_handle_rects(bx, by, bw, bh)
        handle_threshold = HANDLE_SIZE + 4
        for key, (hx0, hy0, hx1, hy1) in handles.items():
            if (hx0 - handle_threshold <= canvas_x <= hx1 + handle_threshold and
                    hy0 - handle_threshold <= canvas_y <= hy1 + handle_threshold):
                return key
        return None

    def _get_box_at_point_with_pan(self, canvas_x, canvas_y, annos):
        for i in range(len(annos) - 1, -1, -1):
            if self._is_point_on_box_with_pan(canvas_x, canvas_y, annos[i]):
                return i
        return None

    def on_mouse_down(self, event):
        if self.current_image() is None:
            return
        x, y = event.x, event.y
        annos = self.annotations.get(self.current_image_index, [])
        self.canvas.delete("hover_guide")
        if self.shift_pressed:
            self.selected_anno_index = None
            self.drawing = True
            self.is_drawing_or_editing = True
            self.start_xy = (x, y)
            self.temp_rect = None
            return
        if (self.selected_anno_index is not None and
                0 <= self.selected_anno_index < len(annos)):
            handle = self._is_point_on_handle_with_pan(
                x, y, annos[self.selected_anno_index]
            )
            if handle:
                self.edit_mode = f"resize_{handle}"
                self.edit_start_xy = (x, y)
                self.edit_original_anno = dict(annos[self.selected_anno_index])
                obx, oby, obw, obh = self._get_pixel_coords(
                    annos[self.selected_anno_index]
                )
                self.edit_original_pixel = (obx, oby, obw, obh)
                self.is_editing = True
                self.is_drawing_or_editing = True
                return
            if self._is_point_on_box_with_pan(
                x, y, annos[self.selected_anno_index]
            ):
                self.edit_mode = "move"
                self.edit_start_xy = (x, y)
                self.edit_original_anno = dict(annos[self.selected_anno_index])
                obx, oby, obw, obh = self._get_pixel_coords(
                    annos[self.selected_anno_index]
                )
                self.edit_original_pixel = (obx, oby, obw, obh)
                self.is_editing = True
                self.is_drawing_or_editing = True
                return
        idx = self._get_box_at_point_with_pan(x, y, annos)
        if idx is not None:
            self.selected_anno_index = idx
            self.render_canvas()
            self.refresh_anno_list()
            self._update_class_change_ui()
            self.set_status(
                f"Box {idx+1} selected. Drag inside to move, corners to resize."
            )
            return
        self.selected_anno_index = None
        self._update_class_change_ui()
        self.drawing = True
        self.is_drawing_or_editing = True
        self.start_xy = (x, y)
        self.temp_rect = None

    def on_mouse_drag(self, event):
        if self.current_image() is None:
            return
        x, y = event.x, event.y
        if self.drawing:
            img_x, img_y = self._get_original_coords(x, y)
            img_x = max(0, min(self.disp_w, img_x))
            img_y = max(0, min(self.disp_h, img_y))
            sx, sy = self.start_xy
            orig_sx, orig_sy = self._get_original_coords(sx, sy)
            orig_sx = max(0, min(self.disp_w, orig_sx))
            orig_sy = max(0, min(self.disp_h, orig_sy))
            self.temp_rect = (min(orig_sx, img_x), min(orig_sy, img_y),
                              abs(img_x - orig_sx), abs(img_y - orig_sy))
            self.render_canvas()
            return
        if not (self.is_editing and self.edit_original_pixel is not None):
            return
        annos = self.annotations.get(self.current_image_index, [])
        if (self.selected_anno_index is None or
                self.selected_anno_index >= len(annos)):
            return
        orig_bx = self.edit_original_pixel[0] - self.image_x_offset
        orig_by = self.edit_original_pixel[1] - self.image_y_offset
        orig_bw = self.edit_original_pixel[2]
        orig_bh = self.edit_original_pixel[3]
        sx, sy = self.edit_start_xy
        dx = (x - self.image_x_offset) - (sx - self.image_x_offset)
        dy = (y - self.image_y_offset) - (sy - self.image_y_offset)
        new_bx, new_by, new_bw, new_bh = orig_bx, orig_by, orig_bw, orig_bh
        if self.edit_mode == "move":
            new_bx += dx
            new_by += dy
        elif self.edit_mode == "resize_tl":
            new_bx += dx; new_by += dy
            new_bw -= dx; new_bh -= dy
        elif self.edit_mode == "resize_tr":
            new_by += dy
            new_bw += dx; new_bh -= dy
        elif self.edit_mode == "resize_bl":
            new_bx += dx
            new_bw -= dx; new_bh += dy
        elif self.edit_mode == "resize_br":
            new_bw += dx; new_bh += dy
        if new_bw < MIN_BOX_SIZE:
            if self.edit_mode in ("resize_tl", "resize_bl"):
                new_bx = orig_bx + orig_bw - MIN_BOX_SIZE
            new_bw = MIN_BOX_SIZE
        if new_bh < MIN_BOX_SIZE:
            if self.edit_mode in ("resize_tl", "resize_tr"):
                new_by = orig_by + orig_bh - MIN_BOX_SIZE
            new_bh = MIN_BOX_SIZE
        if new_bx < 0:
            if self.edit_mode in ("resize_tl", "resize_bl"):
                new_bw += new_bx
            new_bx = 0
            new_bw = max(MIN_BOX_SIZE, new_bw)
        if new_by < 0:
            if self.edit_mode in ("resize_tl", "resize_tr"):
                new_bh += new_by
            new_by = 0
            new_bh = max(MIN_BOX_SIZE, new_bh)
        if new_bx + new_bw > self.disp_w:
            if self.edit_mode in ("resize_tr", "resize_br"):
                new_bw = self.disp_w - new_bx
            else:
                new_bx = self.disp_w - new_bw
            new_bw = max(MIN_BOX_SIZE, new_bw)
        if new_by + new_bh > self.disp_h:
            if self.edit_mode in ("resize_bl", "resize_br"):
                new_bh = self.disp_h - new_by
            else:
                new_by = self.disp_h - new_bh
            new_bh = max(MIN_BOX_SIZE, new_bh)
        new_anno = {
            "class_idx": self.edit_original_anno["class_idx"],
            "x": (new_bx + new_bw / 2) / self.disp_w,
            "y": (new_by + new_bh / 2) / self.disp_h,
            "w": new_bw / self.disp_w,
            "h": new_bh / self.disp_h,
        }
        annos[self.selected_anno_index] = new_anno
        self.render_canvas()
        self.refresh_anno_list()

    def on_mouse_up(self, event):
        if self.drawing:
            self.drawing = False
            self.is_drawing_or_editing = False
            if self.temp_rect and self.temp_rect[2] > 4 and self.temp_rect[3] > 4:
                tx, ty, tw, th = self.temp_rect
                cx = (tx + tw / 2) / self.disp_w
                cy = (ty + th / 2) / self.disp_h
                w = tw / self.disp_w
                h = th / self.disp_h
                new_anno = {"class_idx": -1, "x": cx, "y": cy, "w": w, "h": h}
                self.annotations.setdefault(self.current_image_index,
                                              []).append(new_anno)
                new_index = len(self.annotations[self.current_image_index]) - 1
                self._save_undo_action("add", self.current_image_index,
                                        new_index, None)
                self.selected_anno_index = new_index
                self.render_canvas()
                self.refresh_anno_list()
                self.refresh_image_list()
                self._update_class_change_ui()
                self._force_save()
                self._show_class_selection_popup(new_index)
                self.set_status("Box added! (Auto-saved) (Ctrl+Z to undo)")
            self.temp_rect = None
            self.render_canvas()
            return
        if self.is_editing and self.edit_original_pixel is not None:
            self.is_drawing_or_editing = False
            if (self.edit_original_anno is not None and
                    self.selected_anno_index is not None):
                annos = self.annotations.get(self.current_image_index, [])
                if self.selected_anno_index < len(annos):
                    if dict(annos[self.selected_anno_index]) != self.edit_original_anno:
                        self._save_undo_action(
                            "edit", self.current_image_index,
                            self.selected_anno_index,
                            dict(self.edit_original_anno),
                            dict(annos[self.selected_anno_index])
                        )
            self._force_save()
            self.set_status(f"Box {self.edit_mode} completed. Auto-saved.")
            self.edit_mode = None
            self.edit_start_xy = None
            self.edit_original_anno = None
            self.edit_original_pixel = None
            self.is_editing = False
            self.render_canvas()
            self.refresh_anno_list()

    def on_right_click_down(self, event):
        if self.current_image() is None:
            return
        if self.is_drawing_or_editing:
            return
        annos = self.annotations.get(self.current_image_index, [])
        x, y = event.x, event.y
        idx = self._get_box_at_point_with_pan(x, y, annos)
        if idx is not None:
            class_name = "unassigned"
            if 0 <= annos[idx]["class_idx"] < len(self.classes):
                class_name = self.classes[annos[idx]["class_idx"]]["name"]
            self._save_undo_action("delete", self.current_image_index,
                                    idx, dict(annos[idx]))
            self._delete_anno_at(idx)
            if self.selected_anno_index == idx:
                self.selected_anno_index = None
            self.render_canvas()
            self.refresh_anno_list()
            self._update_class_change_ui()
            self._force_save()
            self.set_status(
                f"🗑️ Box DELETED instantly! (Class: {class_name}) "
                f"(Ctrl+Z to undo)"
            )
            return
        self.canvas.delete("hover_guide")
        self.panning = True
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.pan_start_pan_x = self.pan_x
        self.pan_start_pan_y = self.pan_y
        self.canvas.config(cursor="fleur")
        self.set_status("Pan mode: Drag to move image")

    def on_right_click_drag(self, event):
        if not self.panning:
            return
        dx = event.x - self.pan_start_x
        dy = event.y - self.pan_start_y
        self.pan_x = self.pan_start_pan_x + dx
        self.pan_y = self.pan_start_pan_y + dy
        self.render_canvas()

    def on_right_click_up(self, event):
        if self.panning:
            self.panning = False
            self.canvas.config(cursor="crosshair")
            self.set_status("Ready")

    def _delete_anno_at(self, index):
        annos = self.annotations.get(self.current_image_index, [])
        if not (0 <= index < len(annos)):
            return
        del annos[index]
        if self.selected_anno_index == index:
            self.selected_anno_index = None
        elif (self.selected_anno_index is not None and
                self.selected_anno_index > index):
            self.selected_anno_index -= 1
        self.render_canvas()
        self.refresh_anno_list()
        self.refresh_image_list()
        self._update_class_change_ui()
        self._force_save()

    def on_mouse_move(self, event):
        if self.current_image() is None or self.disp_w == 0:
            self.canvas.delete("hover_guide")
            return
        img_x, img_y = self._get_original_coords(event.x, event.y)
        nx = max(0, min(1, img_x / self.disp_w))
        ny = max(0, min(1, img_y / self.disp_h))
        self.coord_label.config(text=f"x: {nx:.3f}  y: {ny:.3f}")
        if self.panning:
            return
        if self.drawing or self.is_drawing_or_editing:
            return
        if self.mode == "annotation":
            annos = self.annotations.get(self.current_image_index, [])
            x, y = event.x, event.y
            if (self.selected_anno_index is not None and
                    0 <= self.selected_anno_index < len(annos)):
                handle = self._is_point_on_handle_with_pan(
                    x, y, annos[self.selected_anno_index]
                )
                if handle:
                    self.canvas.config(cursor="sizing")
                    self.hover_xy = None
                    self.canvas.delete("hover_guide")
                    return
                if self._is_point_on_box_with_pan(
                    x, y, annos[self.selected_anno_index]
                ):
                    self.canvas.config(cursor="fleur")
                    self.hover_xy = None
                    self.canvas.delete("hover_guide")
                    return
            idx = self._get_box_at_point_with_pan(x, y, annos)
            if idx is not None:
                self.canvas.config(cursor="hand2")
                self.hover_xy = None
                self.canvas.delete("hover_guide")
                return
            self.canvas.config(cursor="crosshair")
            self.hover_xy = (x, y)
            self.canvas.delete("hover_guide")
            self._draw_hover_guides(x, y)

    def on_mouse_leave(self, event):
        self.hover_xy = None
        self.canvas.delete("hover_guide")

    def refresh_anno_list(self):
        self.anno_listbox.delete(0, "end")
        annos = self.annotations.get(self.current_image_index, [])
        for a in annos:
            if 0 <= a["class_idx"] < len(self.classes):
                name = self.classes[a["class_idx"]]["name"]
                color = self.classes[a["class_idx"]]["color"]
            elif a["class_idx"] == -1:
                name = "(unassigned)"
                color = "#888888"
            else:
                name = "(unknown)"
                color = "#ffffff"
            line = (f"{name:<14} x:{a['x']:.2f} y:{a['y']:.2f} "
                    f"w:{a['w']:.2f} h:{a['h']:.2f}")
            self.anno_listbox.insert("end", line)
            if color:
                self.anno_listbox.itemconfig("end", {"fg": color})
        if (self.selected_anno_index is not None and
                0 <= self.selected_anno_index < len(annos)):
            self.anno_listbox.selection_clear(0, "end")
            self.anno_listbox.selection_set(self.selected_anno_index)

    def on_anno_select(self, event):
        sel = self.anno_listbox.curselection()
        if not sel:
            return
        self.selected_anno_index = sel[0]
        self.render_canvas()
        self._update_class_change_ui()

    def delete_selected_anno(self):
        if self.selected_anno_index is None:
            messagebox.showinfo(
                "No Box Selected",
                "Please select a box from the list or click on it on the canvas."
            )
            return
        annos = self.annotations.get(self.current_image_index, [])
        if 0 <= self.selected_anno_index < len(annos):
            self._save_undo_action(
                "delete", self.current_image_index,
                self.selected_anno_index,
                dict(annos[self.selected_anno_index])
            )
        self._delete_anno_at(self.selected_anno_index)
        self.selected_anno_index = None
        self.render_canvas()
        self.refresh_anno_list()
        self._update_class_change_ui()
        self._force_save()
        self.set_status("Box deleted (Ctrl+Z to undo)")

    def save_project(self):
        if not self.images:
            messagebox.showinfo("Empty Project",
                                "Please load some images first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save Project", defaultextension=".json",
            filetypes=[("SwiftVision.ai Project", "*.json")]
        )
        if not path:
            return
        self._save_all_txt()
        data = {
            "classes": self.classes,
            "images": [
                {"path": im["path"],
                 "annotations": self.annotations.get(i, [])}
                for i, im in enumerate(self.images)
            ]
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))
            return
        self.set_status(f"Project saved: {os.path.basename(path)}")
        messagebox.showinfo("Success", f"Project saved to:\n{path}")

    def load_project(self):
        path = filedialog.askopenfilename(
            title="Load Project",
            filetypes=[("SwiftVision.ai Project", "*.json")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load project:\n{e}")
            return
        self.images = []
        self.annotations = {}
        self.classes = data.get("classes", [])
        self.current_class_index = 0 if self.classes else -1
        missing = []
        for idx, entry in enumerate(data.get("images", [])):
            p = entry["path"]
            if not os.path.exists(p):
                missing.append(p)
                continue
            try:
                with Image.open(p) as probe:
                    w, h = probe.size
            except Exception:
                missing.append(p)
                continue
            self.images.append({"path": p, "name": os.path.basename(p),
                                 "w": w, "h": h})
            self.annotations[len(self.images) - 1] = entry.get("annotations", [])
        self.current_image_index = 0 if self.images else -1
        self.selected_anno_index = None
        self.reset_view()
        self.refresh_class_list()
        self.refresh_image_list()
        self.render_canvas()
        self.refresh_anno_list()
        self.update_counter()
        self._save_all_txt()
        msg = f"Project loaded ({len(self.images)} images)."
        if missing:
            msg += f" {len(missing)} image(s) not found (path may have changed)."
        self.set_status(msg)

    def _save_all_txt(self):
        total = len(self.images)
        if total == 0:
            return 0, 0
        saved = 0
        failed = 0
        self._show_progress(f"Saving {total} images...", total)
        for idx in range(total):
            if self._save_image_txt(idx):
                saved += 1
            else:
                failed += 1
            self._update_progress(
                idx + 1,
                f"Saving... {idx+1}/{total} ({int((idx+1)/total*100)}%)"
            )
        self._hide_progress()
        self.set_status(f"✅ Saved {saved} images, {failed} failed")
        return saved, failed

    def export_json(self):
        if not self.images:
            messagebox.showinfo("No Images",
                                "Please load images before exporting.")
            return
        path = filedialog.asksaveasfilename(
            title="Save JSON", defaultextension=".json",
            initialfile="annotations.json", filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        self._save_all_txt()
        data = {"classes": [c["name"] for c in self.classes], "images": []}
        for idx, im in enumerate(self.images):
            annos = self.annotations.get(idx, [])
            data["images"].append({
                "file_name": im["name"],
                "width": im["w"],
                "height": im["h"],
                "annotations": [
                    {
                        "class": (self.classes[a["class_idx"]]["name"]
                                  if 0 <= a["class_idx"] < len(self.classes)
                                  else None),
                        "x_center": round(a["x"], 6),
                        "y_center": round(a["y"], 6),
                        "width": round(a["w"], 6),
                        "height": round(a["h"], 6),
                    }
                    for a in annos if a["class_idx"] >= 0
                ]
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.set_status(f"Export complete: {os.path.basename(path)}")
        messagebox.showinfo("Done", f"JSON export complete:\n{path}")

    def export_yolo(self):
        if not self.images:
            messagebox.showinfo("No Images",
                                "Please load images before exporting.")
            return
        if not self.classes:
            messagebox.showinfo("No Classes",
                                "Please add at least one class before exporting.")
            return
        out_dir = filedialog.askdirectory(
            title="Select Output Folder (dataset will be created here)"
        )
        if not out_dir:
            return
        self._save_all_txt()
        images_dir = os.path.join(out_dir, "images")
        labels_dir = os.path.join(out_dir, "labels")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(labels_dir, exist_ok=True)
        with open(os.path.join(out_dir, "classes.txt"),
                  "w", encoding="utf-8") as f:
            f.write("\n".join(c["name"] for c in self.classes))
        for idx, im in enumerate(self.images):
            try:
                shutil.copy2(im["path"], os.path.join(images_dir, im["name"]))
            except Exception as e:
                self.set_status(f"Copy error: {im['name']} — {e}")
                continue
            base_name = os.path.splitext(im["name"])[0]
            annos = self.annotations.get(idx, [])
            lines = [
                f"{a['class_idx']} {a['x']:.6f} {a['y']:.6f} "
                f"{a['w']:.6f} {a['h']:.6f}"
                for a in annos if a["class_idx"] >= 0
            ]
            if not lines:
                continue
            with open(os.path.join(labels_dir, base_name + ".txt"),
                      "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        self.set_status(f"YOLO dataset exported to: {out_dir}")
        messagebox.showinfo(
            "Done",
            f"YOLO dataset exported to:\n{out_dir}\n\n"
            "images/, labels/, classes.txt\n"
            "💡 Only images with labels got a .txt file."
        )


# ===========================================================================
# Entry point
# ===========================================================================
def main():
    # MUST be called BEFORE tk.Tk()
    _set_app_user_model_id()

    root = tk.Tk()
    app = SwiftVisionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()