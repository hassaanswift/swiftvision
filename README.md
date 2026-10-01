# SwiftVision.ai

![SwiftVision Logo](https://raw.githubusercontent.com/hassaanswift/swiftvision/main/swiftvision/swiftvision_logo.png)

**Offline Image Annotation Studio** - A fast, keyboard-driven bounding box annotation tool for creating YOLO-format datasets. 100% offline, no cloud, no account required.

[![PyPI version](https://badge.fury.io/py/swiftvision.svg)](https://pypi.org/project/swiftvision/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- Draw boxes with mouse, drag corners to resize
- Arrow keys to nudge boxes (Shift = 10px steps)
- Number keys 1-9 to apply classes instantly
- Undo / Redo with Ctrl+Z / Ctrl+Y
- Auto-save YOLO .txt files, only for annotated images
- Copy labels from previous image in one click
- SwiftVision green branding with custom logo + favicon
- Zoom, pan, hover crosshair guides for precision
- Right-click a box to delete instantly
- Full-screen canvas with sidebars

## Installation

    pip install swiftvision

Requirements: Python 3.8+, Pillow

Linux users: If Tkinter is missing, run sudo apt install python3-tk

## Quick Start

    swiftvision

1. Click Load Folder and pick your images directory
2. Add class names in the right sidebar
3. Draw boxes by dragging on the image
4. Assign a class via single-click or number keys 1-9
5. Use Ctrl+Z / Ctrl+Y for undo/redo
6. Click Save All Labels to write .txt files

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Left / Right | Move box 1px (or prev/next image) |
| Shift + Left / Right | Move 10px |
| Up / Down | Move box vertically |
| 1-9 | Apply class N |
| Del / Backspace | Delete selected box |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |
| Ctrl+S | Save project |
| Ctrl+E | Export YOLO |
| R | Rename class |
| N | Focus new class input |

## Mouse Controls

| Action | What it does |
|--------|-------------|
| Left click + drag | Draw new box |
| Left click on box | Select box |
| Drag inside box | Move it |
| Drag corner | Resize |
| Right click on box | Delete |
| Right click + drag | Pan image |
| Mouse wheel | Zoom |

## License

MIT License