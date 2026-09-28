#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import math
import random
import json
import os
import shutil
import zipfile
import sqlite3
import tempfile
import subprocess
import logging
from datetime import datetime
from ctypes import windll

try:
    import PyQt6
except ImportError as _e:
    windll.user32.MessageBoxW(
        0,
        f"缺少 PyQt6 依赖，请运行以下命令安装：\n\n"
        f"python -m pip install PyQt6\n\n"
        f"原始错误：{_e}",
        "依赖缺失",
        0x10
    )
    sys.exit(1)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDialog, QSystemTrayIcon, QMenu,
    QScrollArea, QFrame, QGridLayout, QColorDialog, QFileDialog,
    QLineEdit, QTextEdit, QProgressBar, QCheckBox, QSpacerItem,
    QSizePolicy, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QHeaderView, QAbstractItemView, QComboBox,
    QStyle, QStyleOptionViewItem
)
from PyQt6.QtGui import (
    QColor, QLinearGradient, QRadialGradient, QConicalGradient,
    QBrush, QPainter, QPainterPath, QFont, QIcon, QPixmap
)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, pyqtSignal, QTranslator, QLibraryInfo, QLocale, QThread


def get_app_dir():
    """程序数据目录：打包后固定用 %LOCALAPPDATA%\\WorkBuddyBackup
    （exe 可能在桌面，绝不能把日志/配置写进 exe 所在目录）；
    脚本运行为脚本目录。"""
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.join(
                os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                'WorkBuddyBackup')
            os.makedirs(base, exist_ok=True)
            return base
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.path.expanduser("~")


# 配置日志（固定写入程序目录，不再写入当前工作目录/桌面）
logging.basicConfig(
    filename=os.path.join(get_app_dir(), 'WorkBuddyBackup_error.log'),
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

APP_VERSION = "1.0.0"

# ─────────────────────────────────────────────
# 配置文件路径
# ─────────────────────────────────────────────
def get_config_path():
    try:
        return os.path.join(get_app_dir(), "WorkBuddyBackup_config.json")
    except Exception:
        return os.path.join(os.path.expanduser("~"), "WorkBuddyBackup_config.json")

CONFIG_PATH = get_config_path()
BACKUP_CONFIG_PATH = os.path.join(os.path.dirname(get_config_path()), 'WorkBuddyBackup_config.json')

# ─────────────────────────────────────────────
# 全局背景状态（供主窗口和设置对话框共享）
# ─────────────────────────────────────────────
BG_MODE = "dual"
BG_DIRECTION = "diagonal"
BG_EFFECTIVE_DIR = "diagonal"
BG_RANDOM_PARAMS = {}
BG_COLORS = [
    QColor(210, 235, 255),
    QColor(230, 210, 255),
    QColor(200, 245, 220),
    QColor(255, 245, 220),
]

WINDOW_WIDTH = 1080
WINDOW_HEIGHT = 840

PRESETS = [
    ("樱粉·海蓝",  [QColor(255,209,220), QColor(180,210,255), QColor(200,245,230), QColor(255,240,200)]),
    ("薰衣草",     [QColor(230,210,255), QColor(210,225,255), QColor(240,230,255), QColor(220,240,255)]),
    ("晴空蓝",     [QColor(200,235,255), QColor(180,220,255), QColor(215,245,255), QColor(190,230,250)]),
    ("橙霞暖光",   [QColor(255,220,180), QColor(255,200,160), QColor(255,235,200), QColor(255,215,175)]),
    ("薄荷清风",   [QColor(200,245,220), QColor(185,240,210), QColor(215,250,230), QColor(195,245,215)]),
    ("玫瑰金",     [QColor(255,210,200), QColor(255,195,190), QColor(255,225,215), QColor(250,205,195)]),
]

RANDOM_PATTERN_TYPES = [
    "random-linear", "radial", "conical", "wave",
    "spiral", "diamond", "noise", "burst"
]


# ══════════════════════════════════════════════════════
#  配置保存 / 加载
# ══════════════════════════════════════════════════════
DEFAULT_BACKUP_CONFIG = {
    "save_root": "D:\\",
    "workspaces_root": os.path.expanduser("~\\WorkBuddy"),
    "workbuddy_dir": os.path.expanduser("~\\.workbuddy"),
    "excludes": [
        "node_modules", "__pycache__", ".venv", "venv", ".gradle",
        "build", "dist", "out", "target", ".next", ".dart_tool",
        "DerivedData", "xcuserdata", ".DS_Store", "Thumbs.db",
    ],
    "wb_exclude_app_session": True,
    "wb_exclude_traces": True,
    "wb_exclude_appearance": True,
    "wb_exclude_connectors_marketplace": True,
}

def load_backup_config():
    cfg = dict(DEFAULT_BACKUP_CONFIG)
    try:
        if os.path.exists(BACKUP_CONFIG_PATH):
            with open(BACKUP_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg.update(data)
    except Exception as e:
        logging.error(f"加载备份配置失败: {e}")
    return cfg

def save_backup_config(cfg):
    try:
        with open(BACKUP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存备份配置失败: {e}")


def detect_workbuddy_paths():
    """自动检测 WorkBuddy 安装路径与数据路径，返回 (install_path, workbuddy_dir, workspaces_root)。"""
    user_home = os.path.expanduser("~")
    install_candidates = [
        os.path.join(user_home, "AppData", "Local", "Programs", "WorkBuddy", "WorkBuddy.exe"),
        "C:/Program Files/WorkBuddy/WorkBuddy.exe",
        "C:/Program Files (x86)/WorkBuddy/WorkBuddy.exe",
        os.path.join(user_home, "AppData", "Local", "Programs", "WorkBuddy", "WorkBuddy"),
    ]
    install_path = ""
    for c in install_candidates:
        if os.path.exists(c):
            install_path = c
            break
    wb_candidates = [
        os.path.join(user_home, ".workbuddy"),
        os.path.join(user_home, "AppData", "Roaming", ".workbuddy"),
    ]
    workbuddy_dir = ""
    for c in wb_candidates:
        if os.path.isdir(c):
            workbuddy_dir = c
            break
    ws_candidates = [
        os.path.join(user_home, "WorkBuddy"),
        os.path.join(user_home, "AppData", "Roaming", "WorkBuddy"),
    ]
    workspaces_root = ""
    for c in ws_candidates:
        if os.path.isdir(c):
            workspaces_root = c
            break
    return install_path, workbuddy_dir, workspaces_root


def auto_adjust_config(cfg):
    """软件启动时自动校准：若配置的数据路径不存在，则用自动检测结果填充，并写入检测到的安装路径。"""
    install_path, workbuddy_dir, workspaces_root = detect_workbuddy_paths()
    if install_path:
        cfg["install_path"] = install_path
    if workbuddy_dir and not os.path.isdir(cfg.get("workbuddy_dir", "")):
        cfg["workbuddy_dir"] = workbuddy_dir
    if workspaces_root and not os.path.isdir(cfg.get("workspaces_root", "")):
        cfg["workspaces_root"] = workspaces_root
    return cfg


def save_config():
    try:
        data = {
            "bg_mode": BG_MODE,
            "bg_direction": BG_DIRECTION,
            "bg_effective_dir": BG_EFFECTIVE_DIR,
            "bg_colors": [[c.red(), c.green(), c.blue()] for c in BG_COLORS],
            "bg_random_params": BG_RANDOM_PARAMS,
            "window_width": WINDOW_WIDTH,
            "window_height": WINDOW_HEIGHT,
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存配置失败: {e}")

def load_config():
    global BG_MODE, BG_DIRECTION, BG_EFFECTIVE_DIR, BG_COLORS, BG_RANDOM_PARAMS
    global WINDOW_WIDTH, WINDOW_HEIGHT
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            BG_MODE = data.get("bg_mode", BG_MODE)
            BG_DIRECTION = data.get("bg_direction", BG_DIRECTION)
            BG_EFFECTIVE_DIR = data.get("bg_effective_dir", BG_EFFECTIVE_DIR)
            BG_RANDOM_PARAMS = data.get("bg_random_params", {})
            loaded_colors = data.get("bg_colors", [])
            if loaded_colors and len(loaded_colors) >= 1:
                BG_COLORS = [QColor(*c[:3]) for c in loaded_colors]
            WINDOW_WIDTH = max(int(data.get("window_width", WINDOW_WIDTH)), WINDOW_WIDTH)
            WINDOW_HEIGHT = max(int(data.get("window_height", WINDOW_HEIGHT)), WINDOW_HEIGHT)
    except Exception as e:
        logging.error(f"加载外观配置失败: {e}")


# ══════════════════════════════════════════════════════
#  随机图案生成
# ══════════════════════════════════════════════════════
def generate_random_pattern():
    pattern_type = random.choice(RANDOM_PATTERN_TYPES)
    params = {}
    if pattern_type == "random-linear":
        params = {"angle": random.uniform(0, 360)}
    elif pattern_type == "radial":
        params = {
            "cx": random.uniform(0.2, 0.8), "cy": random.uniform(0.2, 0.8),
            "fx": random.uniform(0.1, 0.9), "fy": random.uniform(0.1, 0.9),
            "radius_ratio": random.uniform(0.5, 1.0),
        }
    elif pattern_type == "conical":
        params = {
            "cx": random.uniform(0.3, 0.7), "cy": random.uniform(0.3, 0.7),
            "start_angle": random.uniform(0, 360),
        }
    elif pattern_type == "wave":
        params = {
            "direction": random.choice(["h", "v"]),
            "frequency": random.uniform(3, 10),
            "amplitude": random.uniform(0.15, 0.45),
        }
    elif pattern_type == "spiral":
        params = {
            "cx": random.uniform(0.3, 0.7), "cy": random.uniform(0.3, 0.7),
            "turns": random.uniform(2, 8), "tightness": random.uniform(0.4, 2.0),
        }
    elif pattern_type == "diamond":
        params = {"angle": random.uniform(0, 90), "exponent": random.uniform(0.5, 2.0)}
    elif pattern_type == "noise":
        params = {"density": random.uniform(0.15, 0.5), "scale": random.uniform(4, 16)}
    elif pattern_type == "burst":
        params = {
            "cx": random.uniform(0.3, 0.7), "cy": random.uniform(0.3, 0.7),
            "num_rays": random.randint(10, 30), "softness": random.uniform(0.3, 0.8),
        }
    return pattern_type, params


# ══════════════════════════════════════════════════════
#  渐变/图案绘制核心
# ══════════════════════════════════════════════════════
def get_stops_for_mode(mode, colors):
    if mode == "single":
        return [colors[0]] if colors else [QColor(240, 240, 240)]
    elif mode == "dual":
        c0 = colors[0] if colors else QColor(240, 240, 240)
        c1 = colors[1] if len(colors) > 1 else c0
        return [c0, c1]
    else:
        c0 = colors[0] if len(colors) > 0 else QColor(255, 255, 255)
        c1 = colors[1] if len(colors) > 1 else c0
        c2 = colors[2] if len(colors) > 2 else c0
        c3 = colors[3] if len(colors) > 3 else c1
        return [c0, c1, c2, c3]

def apply_gradient_stops(gradient, mode, colors):
    stops = get_stops_for_mode(mode, colors)
    if mode == "single":
        gradient.setColorAt(0.0, stops[0])
    elif mode == "dual":
        gradient.setColorAt(0.0, stops[0])
        gradient.setColorAt(1.0, stops[1])
    else:
        gradient.setColorAt(0.0,  stops[0])
        gradient.setColorAt(0.33, stops[1])
        gradient.setColorAt(0.66, stops[2])
        gradient.setColorAt(1.0,  stops[3])

def paint_background(painter, x, y, w, h, mode, colors, direction, params=None):
    if not colors:
        painter.fillRect(x, y, w, h, QBrush(QColor(240, 240, 240)))
        return
    if mode == "single":
        painter.fillRect(x, y, w, h, QBrush(colors[0]))
        return
    params = params or {}
    if direction == "diagonal":
        g = QLinearGradient(x, y, x + w, y + h)
        apply_gradient_stops(g, mode, colors)
        painter.fillRect(x, y, w, h, QBrush(g))
    elif direction == "reverse":
        g = QLinearGradient(x + w, y + h, x, y)
        apply_gradient_stops(g, mode, colors)
        painter.fillRect(x, y, w, h, QBrush(g))
    elif direction == "s-curve":
        paint_s_wave(painter, x, y, w, h, mode, colors)
    elif direction == "random-linear":
        angle = params.get("angle", 45)
        rad = math.radians(angle)
        dx = math.cos(rad) * w * 0.8
        dy = math.sin(rad) * h * 0.8
        cx, cy = x + w / 2, y + h / 2
        g = QLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy)
        apply_gradient_stops(g, mode, colors)
        painter.fillRect(x, y, w, h, QBrush(g))
    elif direction == "radial":
        cx = x + w * params.get("cx", 0.5)
        cy = y + h * params.get("cy", 0.5)
        fx = x + w * params.get("fx", 0.5)
        fy = y + h * params.get("fy", 0.5)
        radius = min(w, h) * params.get("radius_ratio", 0.8)
        g = QRadialGradient(cx, cy, radius, fx, fy)
        apply_gradient_stops(g, mode, colors)
        painter.fillRect(x, y, w, h, QBrush(g))
    elif direction == "conical":
        cx = x + w * params.get("cx", 0.5)
        cy = y + h * params.get("cy", 0.5)
        start_angle = params.get("start_angle", 0)
        g = QConicalGradient(cx, cy, start_angle)
        apply_gradient_stops(g, mode, colors)
        painter.fillRect(x, y, w, h, QBrush(g))
    elif direction == "wave":
        paint_wave(painter, x, y, w, h, mode, colors, params)
    elif direction == "spiral":
        paint_spiral(painter, x, y, w, h, mode, colors, params)
    elif direction == "diamond":
        paint_diamond(painter, x, y, w, h, mode, colors, params)
    elif direction == "noise":
        paint_noise(painter, x, y, w, h, mode, colors, params)
    elif direction == "burst":
        paint_burst(painter, x, y, w, h, mode, colors, params)
    else:
        g = QLinearGradient(x, y, x + w, y + h)
        apply_gradient_stops(g, mode, colors)
        painter.fillRect(x, y, w, h, QBrush(g))

def paint_s_wave(painter, x, y, w, h, mode, colors):
    if not colors or h <= 0 or w <= 0:
        return
    strip_h = 2
    stops = get_stops_for_mode(mode, colors)
    for row in range(0, h, strip_h):
        t = row / h
        phase = t * math.pi * 5
        wave = math.sin(phase)
        shift = wave * w * 0.35
        gx1 = shift
        gy1 = row
        gx2 = w - shift
        gy2 = row + strip_h * 3
        g = QLinearGradient(gx1, gy1, gx2, gy2)
        if mode == "dual":
            g.setColorAt(0.0, stops[0])
            g.setColorAt(1.0, stops[1])
        else:
            g.setColorAt(0.0,  stops[0])
            g.setColorAt(0.33, stops[1])
            g.setColorAt(0.66, stops[2])
            g.setColorAt(1.0,  stops[3])
        painter.fillRect(x, y + row, w, strip_h, QBrush(g))

def paint_wave(painter, x, y, w, h, mode, colors, params):
    if not colors or h <= 0 or w <= 0:
        return
    direction = params.get("direction", "h")
    frequency = params.get("frequency", 5)
    amplitude = params.get("amplitude", 0.3)
    stops = get_stops_for_mode(mode, colors)
    strip = 2
    if direction == "h":
        for row in range(0, h, strip):
            t = row / h
            wave = math.sin(t * math.pi * frequency)
            shift = wave * w * amplitude
            g = QLinearGradient(shift, row, w - shift, row + strip * 2)
            if mode == "dual":
                g.setColorAt(0.0, stops[0])
                g.setColorAt(1.0, stops[1])
            else:
                g.setColorAt(0.0,  stops[0])
                g.setColorAt(0.33, stops[1])
                g.setColorAt(0.66, stops[2])
                g.setColorAt(1.0,  stops[3])
            painter.fillRect(x, y + row, w, strip, QBrush(g))
    else:
        for col in range(0, w, strip):
            t = col / w
            wave = math.sin(t * math.pi * frequency)
            shift = wave * h * amplitude
            g = QLinearGradient(col, shift, col + strip * 2, h - shift)
            if mode == "dual":
                g.setColorAt(0.0, stops[0])
                g.setColorAt(1.0, stops[1])
            else:
                g.setColorAt(0.0,  stops[0])
                g.setColorAt(0.33, stops[1])
                g.setColorAt(0.66, stops[2])
                g.setColorAt(1.0,  stops[3])
            painter.fillRect(x + col, y, strip, h, QBrush(g))

def paint_spiral(painter, x, y, w, h, mode, colors, params):
    if not colors or w <= 0 or h <= 0:
        return
    cx = x + w * params.get("cx", 0.5)
    cy = y + h * params.get("cy", 0.5)
    turns = params.get("turns", 4)
    tightness = params.get("tightness", 1.0)
    stops = get_stops_for_mode(mode, colors)
    num_bands = 80
    max_r = math.hypot(w, h)
    for i in range(num_bands, -1, -1):
        t = i / num_bands
        r = t * max_r
        band_width = max_r / num_bands * 1.2
        color_idx = int(t * (len(stops) - 1))
        color_t = (t * (len(stops) - 1)) - color_idx
        c1 = stops[min(color_idx, len(stops) - 1)]
        c2 = stops[min(color_idx + 1, len(stops) - 1)]
        r_val = int(c1.red() * (1 - color_t) + c2.red() * color_t)
        g_val = int(c1.green() * (1 - color_t) + c2.green() * color_t)
        b_val = int(c1.blue() * (1 - color_t) + c2.blue() * color_t)
        color = QColor(r_val, g_val, b_val)
        path = QPainterPath()
        for a in range(0, 360 * 2, 5):
            rad = math.radians(a)
            sr = r + (a / 360) * band_width * tightness
            px = cx + math.cos(rad * turns + rad) * sr
            py = cy + math.sin(rad * turns + rad) * sr
            if a == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(path)

def paint_diamond(painter, x, y, w, h, mode, colors, params):
    if not colors or w <= 0 or h <= 0:
        return
    angle = math.radians(params.get("angle", 0))
    exponent = params.get("exponent", 1.0)
    stops = get_stops_for_mode(mode, colors)
    strip = 3
    for row in range(0, h, strip):
        for col in range(0, w, strip):
            rx = (col / w - 0.5) * 2
            ry = (row / h - 0.5) * 2
            rot_x = rx * math.cos(angle) - ry * math.sin(angle)
            rot_y = rx * math.sin(angle) + ry * math.cos(angle)
            dist = (abs(rot_x) ** exponent + abs(rot_y) ** exponent) / 2
            dist = max(0, min(1, dist))
            color_idx = int(dist * (len(stops) - 1))
            color_t = (dist * (len(stops) - 1)) - color_idx
            c1 = stops[min(color_idx, len(stops) - 1)]
            c2 = stops[min(color_idx + 1, len(stops) - 1)]
            r_val = int(c1.red() * (1 - color_t) + c2.red() * color_t)
            g_val = int(c1.green() * (1 - color_t) + c2.green() * color_t)
            b_val = int(c1.blue() * (1 - color_t) + c2.blue() * color_t)
            painter.fillRect(x + col, y + row, strip, strip, QBrush(QColor(r_val, g_val, b_val)))

def paint_noise(painter, x, y, w, h, mode, colors, params):
    if not colors or w <= 0 or h <= 0:
        return
    g = QLinearGradient(x, y, x + w, y + h)
    apply_gradient_stops(g, mode, colors)
    painter.fillRect(x, y, w, h, QBrush(g))
    density = params.get("density", 0.3)
    scale = int(params.get("scale", 8))
    stops = get_stops_for_mode(mode, colors)
    for row in range(0, h, scale):
        for col in range(0, w, scale):
            if random.random() < density:
                base_color = random.choice(stops)
                noise_r = max(0, min(255, base_color.red() + random.randint(-40, 40)))
                noise_g = max(0, min(255, base_color.green() + random.randint(-40, 40)))
                noise_b = max(0, min(255, base_color.blue() + random.randint(-40, 40)))
                painter.fillRect(x + col, y + row, scale, scale,
                                 QBrush(QColor(noise_r, noise_g, noise_b, 120)))

def paint_burst(painter, x, y, w, h, mode, colors, params):
    if not colors or w <= 0 or h <= 0:
        return
    cx = x + w * params.get("cx", 0.5)
    cy = y + h * params.get("cy", 0.5)
    num_rays = params.get("num_rays", 16)
    softness = params.get("softness", 0.5)
    stops = get_stops_for_mode(mode, colors)
    max_r = math.hypot(w, h)
    g = QRadialGradient(cx, cy, max_r, cx, cy)
    apply_gradient_stops(g, mode, colors)
    painter.fillRect(x, y, w, h, QBrush(g))
    for i in range(num_rays):
        ray_angle = (2 * math.pi / num_rays) * i
        next_angle = (2 * math.pi / num_rays) * (i + 1)
        mid_angle = (ray_angle + next_angle) / 2
        color = stops[i % len(stops)]
        path = QPainterPath()
        path.moveTo(cx, cy)
        for step in range(0, 101, 5):
            t = step / 100
            r = max_r * t
            spread = softness * (1 - t) * math.pi / num_rays
            a1 = mid_angle - spread
            a2 = mid_angle + spread
            px1 = cx + math.cos(a1) * r
            py1 = cy + math.sin(a1) * r
            px2 = cx + math.cos(a2) * r
            py2 = cy + math.sin(a2) * r
            path.lineTo(px1, py1)
            path.lineTo(px2, py2)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 60)))
        painter.drawPath(path)


# ══════════════════════════════════════════════════════
#  备份/恢复 核心引擎
# ══════════════════════════════════════════════════════
class BackupEngine:
    WB_EXCLUDE_FILES = {
        'workbuddy.db-shm', 'workbuddy.db-wal', 'usage-log.json',
        'desktop_conversation_migrated', 'session_fragment_repair_done',
        'session_fragment_repair_done520', 'epoch-marker.json',
        'clean_residual.py',
    }

    def __init__(self, cfg=None):
        self.cfg = cfg or load_backup_config()
        self.wb_dir = os.path.normpath(self.cfg.get("workbuddy_dir", os.path.expanduser("~\\.workbuddy")))
        self.ws_root = os.path.normpath(self.cfg.get("workspaces_root", os.path.expanduser("~\\WorkBuddy")))
        self.save_root = os.path.normpath(self.cfg.get("save_root", "D:\\"))
        self.excludes = [e.strip() for e in self.cfg.get("excludes", []) if e.strip()]

    def _wb_exclude_paths(self):
        paths = {
            'binaries', 'cache', 'clipboard-images', 'logs', 'plugins', 'vendor',
            'blobs', 'local_storage', 'audit-log',
            'automation-backups', 'pending-telemetry',
        }
        if self.cfg.get("wb_exclude_app_session", True):
            paths.add('app/session')
        if self.cfg.get("wb_exclude_traces", True):
            paths.add('traces')
        if self.cfg.get("wb_exclude_appearance", True):
            paths.add('appearance-resources')
        if self.cfg.get("wb_exclude_connectors_marketplace", True):
            paths.add('connectors-marketplace')
        return paths

    def _path_excluded_in_wb(self, rel):
        rel = rel.replace('\\', '/')
        for ep in self._wb_exclude_paths():
            if rel == ep or rel.startswith(ep + '/'):
                return True
        return False

    def _workspace_path_excluded(self, rel):
        rel_l = rel.replace('\\', '/').lower()
        parts = rel_l.split('/')
        for pat in self.excludes:
            if pat.lower() in parts:
                return True
        return False

    def collect_items(self, progress=None, selected_ws=None):
        items = []
        total_estimate = 0
        # .workbuddy
        for root, dirs, files in os.walk(self.wb_dir):
            rel = os.path.relpath(root, self.wb_dir)
            if self._path_excluded_in_wb(rel):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not self._path_excluded_in_wb(os.path.join(rel, d))]
            for f in files:
                if f in self.WB_EXCLUDE_FILES:
                    continue
                src = os.path.join(root, f)
                if rel == '.':
                    arc = os.path.join('.workbuddy', f)
                else:
                    arc = os.path.join('.workbuddy', rel, f)
                items.append(('wb', src, arc.replace('\\', '/')))
                if progress and len(items) % 500 == 0:
                    progress.emit("count", len(items), 0)
        # workspaces
        if os.path.isdir(self.ws_root):
            for name in os.listdir(self.ws_root):
                p = os.path.join(self.ws_root, name)
                if not os.path.isdir(p):
                    continue
                if selected_ws is not None and name not in selected_ws:
                    continue
                for r, ds, fs in os.walk(p):
                    rel = os.path.relpath(r, p)
                    if self._workspace_path_excluded(rel):
                        ds.clear()
                        continue
                    ds[:] = [d for d in ds if not self._workspace_path_excluded(os.path.join(rel, d))]
                    for f in fs:
                        arc_rel = os.path.join('workspaces', name, rel, f) if rel != '.' else os.path.join('workspaces', name, f)
                        if self._workspace_path_excluded(arc_rel):
                            continue
                        fp = os.path.join(r, f)
                        items.append(('ws', fp, arc_rel.replace('\\', '/')))
                        if progress and len(items) % 500 == 0:
                            progress.emit("count", len(items), 0)
        return items

    def _current_user_id(self, db_path):
        """读取数据库里当前登录账号的 user_id（WorkBuddy 界面按此字段过滤显示）。"""
        try:
            if not os.path.exists(db_path):
                return ''
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            uid = ''
            try:
                row = cur.execute(
                    "SELECT user_id FROM sessions "
                    "WHERE user_id IS NOT NULL AND user_id != '' LIMIT 1").fetchone()
                if row and row[0]:
                    uid = str(row[0])
                else:
                    row = cur.execute(
                        "SELECT owner_user_id FROM automations "
                        "WHERE owner_user_id IS NOT NULL AND owner_user_id != '' LIMIT 1").fetchone()
                    if row and row[0]:
                        uid = str(row[0])
            except sqlite3.Error:
                pass
            conn.close()
            return uid
        except Exception as e:
            logging.warning(f"读取账号 user_id 失败: {e}")
            return ''

    def _align_user_ids(self, db_path, target_user_id, progress=None):
        """把恢复进来的对话 / 自动化任务统一归属到当前登录账号，
        否则 WorkBuddy 界面会因 user_id 不匹配而过滤掉、看不到恢复的数据。"""
        if not target_user_id:
            return
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            n_s = n_a = 0
            try:
                cur.execute(
                    "UPDATE sessions SET user_id = ? "
                    "WHERE user_id IS NULL OR user_id != ?",
                    (target_user_id, target_user_id))
                n_s = cur.rowcount or 0
            except sqlite3.Error:
                pass
            try:
                cur.execute(
                    "UPDATE automations SET owner_user_id = ? "
                    "WHERE owner_user_id IS NULL OR owner_user_id != ?",
                    (target_user_id, target_user_id))
                n_a = cur.rowcount or 0
            except sqlite3.Error:
                pass
            conn.commit()
            conn.close()
            if progress:
                progress.emit(
                    "log", f"账号归属对齐：对话 {n_s} 条、自动化 {n_a} 条 → 当前登录账号")
        except Exception as e:
            logging.warning(f"账号归属对齐失败: {e}")

    def _checkpoint_db(self):
        """备份前把 WAL 日志合并进主数据库文件，确保备份包含全部最新数据。"""
        try:
            db = os.path.join(self.wb_dir, 'workbuddy.db')
            if os.path.exists(db):
                conn = sqlite3.connect(db, timeout=3)
                conn.execute("PRAGMA wal_checkpoint(FULL)")
                conn.close()
        except Exception as e:
            logging.warning(f"wal checkpoint 失败（不影响备份继续）: {e}")

    def backup(self, out_path, progress=None, selected_ids=None, selected_ws=None):
        self._checkpoint_db()
        items = self.collect_items(progress, selected_ws)
        total = len(items)
        written = 0
        skipped = 0
        os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else '.', exist_ok=True)
        manifest = {
            "version": APP_VERSION,
            "created_at": datetime.now().isoformat(),
            "source_user": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
            "source_user_id": self._current_user_id(os.path.join(self.wb_dir, 'workbuddy.db')),
            "source_wb_dir": self.wb_dir,
            "source_workspaces_root": self.ws_root,
            "item_count": total,
            "selected_sessions": selected_ids or [],
            "selected_workspaces": selected_ws or [],
        }
        with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('backup_manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
            for i, (kind, src, arc) in enumerate(items):
                if not os.path.isfile(src):
                    skipped += 1
                    continue
                try:
                    zf.write(src, arc)
                    written += 1
                except PermissionError:
                    skipped += 1
                except Exception as e:
                    skipped += 1
                    logging.warning(f"备份跳过 {src}: {e}")
                if progress and i % 200 == 0:
                    progress.emit("progress", i + 1, total)
        if progress:
            progress.emit("progress", total, total)
        return written, skipped, total

    def restore(self, zip_path, progress=None, selected_ids=None, selected_ws=None):
        current_user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
        temp_dir = tempfile.mkdtemp(prefix="wb_restore_")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(temp_dir)
            manifest_path = os.path.join(temp_dir, 'backup_manifest.json')
            old_user, old_wb, old_ws = current_user, self.wb_dir, self.ws_root
            source_uid = ""
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                old_user = manifest.get("source_user", current_user)
                source_uid = manifest.get("source_user_id", "") or ""
                old_wb = manifest.get("source_wb_dir", self.wb_dir)
                old_ws = manifest.get("source_workspaces_root", self.ws_root)
                if not selected_ids:
                    selected_ids = manifest.get("selected_sessions") or None
                if not selected_ws:
                    selected_ws = manifest.get("selected_workspaces") or None

            os.makedirs(self.wb_dir, exist_ok=True)

            # 1) 合并对话索引（仅选中对话）
            src_db = os.path.join(temp_dir, '.workbuddy', 'workbuddy.db')
            dst_db = os.path.join(self.wb_dir, 'workbuddy.db')
            local_uid = self._current_user_id(dst_db)   # 合并前先记录本机账号
            if os.path.exists(src_db):
                if progress:
                    progress.emit("log", "正在合并对话索引 workbuddy.db ...")
                self._merge_sessions_db(src_db, dst_db, selected_ids, progress)
            else:
                if progress:
                    progress.emit("log", "[警告] 备份包内未找到 workbuddy.db，跳过对话索引合并")

            # 1.5) 账号归属对齐：把恢复的数据挂到当前登录账号名下，
            #      否则 WorkBuddy 界面会因 user_id 不匹配而过滤掉、看不到恢复结果
            target_uid = local_uid or source_uid
            if target_uid:
                if progress:
                    progress.emit("log", "正在对齐账号归属（确保界面能显示）...")
                self._align_user_ids(dst_db, target_uid, progress)
            else:
                if progress:
                    progress.emit("log",
                                  "[提示] 本机未检测到账号信息，请先启动并登录 WorkBuddy，"
                                  "再关闭它执行恢复（同账号才能显示恢复的对话与自动化任务）")

            # 2) 复制选中对话正文
            src_sessions = os.path.join(temp_dir, '.workbuddy', 'sessions')
            if os.path.isdir(src_sessions) and selected_ids:
                if progress:
                    progress.emit("log", f"正在恢复 {len(selected_ids)} 个对话内容...")
                dst_sessions = os.path.join(self.wb_dir, 'sessions')
                os.makedirs(dst_sessions, exist_ok=True)
                for sid in selected_ids:
                    s = os.path.join(src_sessions, f"{sid}.json")
                    if os.path.exists(s):
                        try:
                            shutil.copy2(s, os.path.join(dst_sessions, f"{sid}.json"))
                        except Exception as e:
                            logging.warning(f"复制对话 {sid} 失败: {e}")
            elif os.path.isdir(src_sessions) and not selected_ids:
                if progress:
                    progress.emit("log", "正在恢复全部对话内容...")
                dst_sessions = os.path.join(self.wb_dir, 'sessions')
                self._copytree_merge(src_sessions, dst_sessions)

            # 3) 恢复选中项目空间
            src_ws = os.path.join(temp_dir, 'workspaces')
            if os.path.isdir(src_ws):
                if selected_ws:
                    names = selected_ws
                else:
                    names = [d for d in os.listdir(src_ws)
                             if os.path.isdir(os.path.join(src_ws, d))]
                if progress:
                    progress.emit("log", f"正在恢复 {len(names)} 个项目空间...")
                os.makedirs(self.ws_root, exist_ok=True)
                for name in names:
                    s = os.path.join(src_ws, name)
                    d = os.path.join(self.ws_root, name)
                    if os.path.isdir(s):
                        self._copytree_merge(s, d)

            # 4) 路径修复
            if progress:
                progress.emit("log", "正在修复跨设备路径...")
            self._fix_paths(self.wb_dir, self.ws_root, old_user, current_user, old_wb, old_ws, progress)
            if progress:
                progress.emit("log", "恢复完成，请重新启动 WorkBuddy 并登录同一账号。")
            return True
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _merge_sessions_db(self, src_db, dst_db, selected_ids, progress=None):
        """把备份库中的所有业务表合并进本机库（换电脑 100% 无损的关键）：
        - sessions：勾选了哪些就合并哪些对话
        - automations / automation_runs / buddy_snapshots / workspaces / session_usage 等：
          整表合并（INSERT OR REPLACE），保证自动化任务、空间登记、对话快照一并还原
        本机无库则直接写入。"""
        try:
            if not os.path.exists(dst_db):
                shutil.copy2(src_db, dst_db)
                if progress:
                    progress.emit("log", "本机尚无数据表，已直接写入备份库。")
                return True
            bak = f"{dst_db}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                shutil.copy2(dst_db, bak)
                if progress:
                    progress.emit("log", f"已备份当前数据表 -> {os.path.basename(bak)}")
            except Exception as e:
                logging.warning(f"备份当前数据表失败: {e}")

            conn = sqlite3.connect(dst_db)
            try:
                conn.execute("ATTACH DATABASE ? AS src", (src_db,))
                src_tables = [r[0] for r in conn.execute(
                    "SELECT name FROM src.sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%drizzle%'")]
                total_rows = 0
                merged = 0
                for t in src_tables:
                    try:
                        src_cols = [r[1] for r in conn.execute(f'PRAGMA src.table_info("{t}")')]
                        dst_cols = [r[1] for r in conn.execute(f'PRAGMA main.table_info("{t}")')]
                        cols = [c for c in src_cols if c in dst_cols]
                        if not cols:
                            continue
                        collist = ", ".join(f'"{c}"' for c in cols)
                        if t == 'sessions' and selected_ids:
                            ph = ", ".join("?" for _ in selected_ids)
                            sql = (f'INSERT OR REPLACE INTO main.sessions ({collist}) '
                                   f'SELECT {collist} FROM src.sessions WHERE id IN ({ph})')
                            cur = conn.execute(sql, tuple(str(x) for x in selected_ids))
                        else:
                            sql = (f'INSERT OR REPLACE INTO main."{t}" ({collist}) '
                                   f'SELECT {collist} FROM src."{t}"')
                            cur = conn.execute(sql)
                        n = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                        total_rows += n
                        merged += 1
                        if progress:
                            progress.emit("log", f"  合并 {t}：{n} 行")
                    except Exception as e:
                        logging.warning(f"合并表 {t} 失败: {e}")
                        if progress:
                            progress.emit("log", f"[警告] 表 {t} 合并跳过: {e}")
                conn.commit()
                if progress:
                    progress.emit("log", f"已合并 {merged} 张数据表（共 {total_rows} 行）")
                return True
            finally:
                try:
                    conn.execute("DETACH DATABASE src")
                except Exception:
                    pass
                conn.close()
        except Exception as e:
            logging.error(f"合并对话索引失败: {e}")
            if progress:
                progress.emit("log", f"[错误] 合并对话索引失败: {e}")
            return False

    def _copytree_merge(self, src, dst):
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            target_dir = os.path.join(dst, rel) if rel != '.' else dst
            os.makedirs(target_dir, exist_ok=True)
            for f in files:
                s = os.path.join(root, f)
                d = os.path.join(target_dir, f)
                try:
                    shutil.copy2(s, d)
                except Exception as e:
                    logging.warning(f"复制失败 {s} -> {d}: {e}")

    def _fix_paths(self, wb_dir, ws_root, old_user, new_user, old_wb, old_ws, progress):
        # 修复 app/sessions.json
        sessions_json = os.path.join(wb_dir, 'app', 'sessions.json')
        if os.path.exists(sessions_json):
            try:
                with open(sessions_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                changed = False
                for s in data.get("sessions", []):
                    wd = s.get("workDir", "")
                    if old_user in wd or old_ws in wd:
                        s["workDir"] = wd.replace(old_ws, ws_root).replace(f"C:\\Users\\{old_user}\\", f"C:\\Users\\{new_user}\\")
                        changed = True
                if changed:
                    with open(sessions_json, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logging.warning(f"修复 sessions.json 失败: {e}")

        # 修复 workbuddy.db
        db_path = os.path.join(wb_dir, 'workbuddy.db')
        if os.path.exists(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("UPDATE sessions SET cwd = REPLACE(cwd, ?, ?)", (old_ws, ws_root))
                cur.execute("UPDATE sessions SET cwd = REPLACE(cwd, ?, ?)", (f"C:\\Users\\{old_user}\\", f"C:\\Users\\{new_user}\\"))
                cur.execute("UPDATE workspaces SET path = REPLACE(path, ?, ?)", (old_ws, ws_root))
                cur.execute("UPDATE workspaces SET path = REPLACE(path, ?, ?)", (f"C:\\Users\\{old_user}\\", f"C:\\Users\\{new_user}\\"))
                conn.commit()
                conn.close()
            except Exception as e:
                logging.warning(f"修复 workbuddy.db 失败: {e}")

        # 修复 sessions/ 下的每个 json
        sessions_dir = os.path.join(wb_dir, 'sessions')
        if os.path.isdir(sessions_dir):
            for fn in os.listdir(sessions_dir):
                if not fn.endswith('.json'):
                    continue
                fp = os.path.join(sessions_dir, fn)
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        text = f.read()
                    if old_user in text or old_ws in text:
                        text = text.replace(old_ws, ws_root).replace(f"C:\\Users\\{old_user}\\", f"C:\\Users\\{new_user}\\")
                        with open(fp, 'w', encoding='utf-8') as f:
                            f.write(text)
                except Exception as e:
                    logging.warning(f"修复 sessions/{fn} 失败: {e}")

    def get_default_backup_folder(self):
        return os.path.join(self.save_root, "WorkBuddy备份")

    def get_next_backup_path(self):
        folder = self.get_default_backup_folder()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(folder, f"WorkBuddy备份_{ts}.zip")


def is_workbuddy_running():
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WorkBuddy.exe", "/NH"],
            capture_output=True, text=True, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW  # 不弹黑色控制台窗口
        )
        return "WorkBuddy.exe" in result.stdout
    except Exception:
        return False


def scan_local_sessions(wb_dir):
    """扫描本机 WorkBuddy 对话列表，返回 [{'id','title','cwd','updated_at'}]"""
    rows = []
    db_path = os.path.join(wb_dir, 'workbuddy.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT id, title, custom_title, cwd, updated_at, created_at "
                    "FROM sessions WHERE deleted_at IS NULL "
                    "ORDER BY COALESCE(updated_at, created_at) DESC"
                )
            except sqlite3.Error:
                cur.execute(
                    "SELECT id, title, custom_title, cwd, updated_at, created_at FROM sessions"
                )
            for r in cur.fetchall():
                title = (r['custom_title'] or r['title'] or '').strip() or '(无标题对话)'
                rows.append({
                    'id': str(r['id']),
                    'title': title,
                    'cwd': r['cwd'] or '',
                    'updated_at': r['updated_at'] or r['created_at'] or '',
                })
            conn.close()
            if rows:
                return rows
        except Exception as e:
            logging.warning(f"读取本机会话(db)失败: {e}")
    sj = os.path.join(wb_dir, 'app', 'sessions.json')
    if os.path.exists(sj):
        try:
            with open(sj, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for s in data.get('sessions', []):
                cid = s.get('conversationId')
                if not cid:
                    continue
                rows.append({
                    'id': str(cid),
                    'title': s.get('title') or f"对话 {cid}",
                    'cwd': s.get('workDir', ''),
                    'updated_at': s.get('resumedAt') or s.get('startedAt') or '',
                })
        except Exception as e:
            logging.warning(f"读取 app/sessions.json 失败: {e}")
    return rows


def scan_local_workspaces(ws_root):
    """扫描本机项目空间列表，返回 [{'name','path'}]"""
    items = []
    if os.path.isdir(ws_root):
        try:
            for name in sorted(os.listdir(ws_root)):
                p = os.path.join(ws_root, name)
                if os.path.isdir(p):
                    items.append({'name': name, 'path': p})
        except Exception as e:
            logging.warning(f"扫描项目空间失败: {e}")
    return items


def scan_backup_sessions(zip_path):
    """从备份 zip 读取对话列表"""
    rows = []
    tmp = tempfile.mkdtemp(prefix="wb_scan_")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            db_member = None
            for n in zf.namelist():
                if n.endswith('/workbuddy.db') or n == 'workbuddy.db':
                    db_member = n
                    break
            if db_member:
                zf.extract(db_member, tmp)
                wb_dir = os.path.dirname(os.path.join(tmp, db_member))
                rows = scan_local_sessions(wb_dir)
    except Exception as e:
        logging.warning(f"读取备份包会话失败: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


def scan_backup_workspaces(zip_path):
    """从备份 zip 读取项目空间列表"""
    names = set()
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for n in zf.namelist():
                if n.startswith('workspaces/'):
                    parts = n.split('/')
                    if len(parts) >= 2 and parts[1]:
                        names.add(parts[1])
    except Exception as e:
        logging.warning(f"读取备份包项目空间失败: {e}")
    return [{'name': x, 'path': x} for x in sorted(names)]


def scan_workspace_map(db_path):
    """读取 workspaces 表登记的空间路径，返回小写规范化路径集合。
    官方侧边栏的「空间」只认这里登记过的目录；未登记目录下的对话归「任务」。"""
    paths = set()
    if not os.path.exists(db_path):
        return paths
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT path FROM workspaces")
            for (p,) in cur.fetchall():
                if p:
                    paths.add(os.path.normpath(str(p)).lower())
        except sqlite3.Error:
            pass
        conn.close()
    except Exception as e:
        logging.warning(f"读取 workspaces 表失败: {e}")
    return paths


def strip_focus_rect(widget):
    """去掉所有按钮/复选框/下拉框的键盘焦点虚线框（Qt 焦点指示器）。"""
    for w in widget.findChildren(QPushButton):
        w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    for w in widget.findChildren(QCheckBox):
        w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    for w in widget.findChildren(QComboBox):
        w.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class SessionTree(QTreeWidget):
    """对话树交互（不猜测坐标，全部基于 Qt 真实事件结果）：
    - 复选框（对话 / 空间组）：由 Qt 原生切换，itemChanged 信号统一联动
      （组 → 全部子项；子项 → 父节点三态）
    - 组名（任务 / 空间 / 各空间名）：点击收起 / 展开
    - 对话行文字：点击切换勾选
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False   # 批量/程序化设置勾选时抑制联动
        self.itemChanged.connect(self._on_item_changed)
        self._press_item = None
        self._press_state = None
        self._press_expanded = None
        self._press_modifiers = None

    # ── 勾选联动中枢：无论 Qt 在 press 还是 release 切换复选框都能联动 ──
    def _on_item_changed(self, item, column):
        if self._updating or column != 0:
            return
        # 顶层组（任务/空间）无复选框，其状态值无意义（改名等也会触发本信号），忽略
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        self._updating = True
        try:
            if item.childCount() > 0:
                state = item.checkState(0)

                def walk(node):
                    for i in range(node.childCount()):
                        c = node.child(i)
                        if c.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                            c.setCheckState(0, state)
                        walk(c)

                walk(item)
            parent = item.parent()
            if parent is not None and (parent.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                self.sync_parent_state(parent)
        finally:
            self._updating = False

    # ── 鼠标：识别「点击文字」并做出折叠 / 切换动作 ──
    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        item = self.itemAt(pos)
        if item is None or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            self._press_item = None
            return
        self._press_item = item
        self._press_state = item.checkState(0)
        self._press_expanded = item.isExpanded()
        self._press_modifiers = event.modifiers()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        super().mouseReleaseEvent(event)
        if item is None or event.button() != Qt.MouseButton.LeftButton:
            return
        if self._press_item is not item:
            return
        press_state = self._press_state
        press_expanded = self._press_expanded
        modifiers = getattr(self, '_press_modifiers', Qt.KeyboardModifier.NoModifier)
        self._press_item = None
        # Qt 已处理（复选框切换 / 展开箭头）→ itemChanged 已联动，不再干预
        if item.checkState(0) != press_state:
            return
        if item.isExpanded() != press_expanded:
            return
        # 点击的是文字：
        if item.childCount() > 0:
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                # Ctrl + 点项目名：整组勾选 / 取消（项目行与官方一致，不带复选框）
                self.toggle_group_check(item)
            else:
                item.setExpanded(not item.isExpanded())   # 收起 / 展开
        else:
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                new_state = (Qt.CheckState.Unchecked
                             if item.checkState(0) == Qt.CheckState.Checked
                             else Qt.CheckState.Checked)
                item.setCheckState(0, new_state)   # 触发 itemChanged 自动联动父节点

    def toggle_group_check(self, group_item):
        """整组勾选 / 取消（Ctrl+点项目名），递归应用到所有后代。"""
        all_checked = all(
            group_item.child(i).checkState(0) == Qt.CheckState.Checked
            for i in range(group_item.childCount()))
        target = (Qt.CheckState.Unchecked if all_checked
                  else Qt.CheckState.Checked)
        self._updating = True
        try:
            def walk(node):
                for i in range(node.childCount()):
                    c = node.child(i)
                    if c.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                        c.setCheckState(0, target)
                    walk(c)
            walk(group_item)
        finally:
            self._updating = False

    def sync_parent_state(self, parent):
        total = parent.childCount()
        if total == 0:
            return
        checked = sum(1 for i in range(total)
                      if parent.child(i).checkState(0) == Qt.CheckState.Checked)
        if checked == 0:
            parent.setCheckState(0, Qt.CheckState.Unchecked)
        elif checked == total:
            parent.setCheckState(0, Qt.CheckState.Checked)
        else:
            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def apply_group_check(self, item):
        """把组节点当前勾选状态应用到其所有后代。"""
        state = item.checkState(0)

        def walk(node):
            for i in range(node.childCount()):
                c = node.child(i)
                if c.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    c.setCheckState(0, state)
                walk(c)

        walk(item)

    def toggle_item(self, item):
        """叶子对话：切换勾选"""
        if item.childCount() == 0 and (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            new_state = (Qt.CheckState.Unchecked
                         if item.checkState(0) == Qt.CheckState.Checked
                         else Qt.CheckState.Checked)
            item.setCheckState(0, new_state)
        self._sync_up(item)

    def _sync_up(self, item):
        parent = item.parent()
        if parent is not None and (parent.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            self.sync_parent_state(parent)

    def sync_parent_state(self, parent):
        total = parent.childCount()
        if total == 0:
            return
        checked = sum(1 for i in range(total)
                      if parent.child(i).checkState(0) == Qt.CheckState.Checked)
        if checked == 0:
            parent.setCheckState(0, Qt.CheckState.Unchecked)
        elif checked == total:
            parent.setCheckState(0, Qt.CheckState.Checked)
        else:
            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)


# ══════════════════════════════════════════════════════
#  工作线程
# ══════════════════════════════════════════════════════
class BackupWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    done_signal = pyqtSignal(bool, str)

    def __init__(self, mode, engine, path=None, selected_ids=None, selected_ws=None):
        super().__init__()
        self.mode = mode
        self.engine = engine
        self.path = path
        self.selected_ids = selected_ids
        self.selected_ws = selected_ws

    def emit_log(self, msg):
        self.log_signal.emit(msg)

    def emit_progress(self, current, total):
        self.progress_signal.emit(current, total)

    def emit(self, kind, *args):
        if kind == "log":
            self.log_signal.emit(str(args[0]) if args else "")
            return
        cur = int(args[0]) if len(args) > 0 else 0
        tot = int(args[1]) if len(args) > 1 else 0
        self.progress_signal.emit(cur, tot)

    def run(self):
        try:
            if self.mode == "backup":
                if is_workbuddy_running():
                    self.emit_log("[警告] 检测到 WorkBuddy 正在运行，请先关闭 WorkBuddy 再备份，否则部分文件会被跳过。")
                out_path = self.path or self.engine.get_next_backup_path()
                self.emit_log(f"开始备份到: {out_path}")
                self.emit_log(f"WorkBuddy 数据目录: {self.engine.wb_dir}")
                self.emit_log(f"项目工作空间目录: {self.engine.ws_root}")
                written, skipped, total = self.engine.backup(out_path, self, self.selected_ids, self.selected_ws)
                self.emit_log(f"备份完成。成功 {written} 个文件，跳过 {skipped} 个，总计 {total} 个。")
                self.emit_log(f"输出文件: {out_path}")
                if total == 0:
                    self.done_signal.emit(False, "未发现任何可备份文件，请检查设置中的数据目录是否正确")
                    return
                if written == 0:
                    self.done_signal.emit(False, "未写入任何文件，可能被第三方软件占用或路径无权限")
                    return
                self.done_signal.emit(True, out_path)
            elif self.mode == "restore":
                if is_workbuddy_running():
                    self.emit_log("[错误] 检测到 WorkBuddy 正在运行，请先完全关闭 WorkBuddy 再进行恢复。")
                    self.done_signal.emit(False, "WorkBuddy 未关闭")
                    return
                self.emit_log(f"开始恢复备份: {self.path}")
                self.engine.restore(self.path, self, self.selected_ids, self.selected_ws)
                self.emit_log("恢复完成。请重新启动 WorkBuddy 并登录同一账号。")
                self.done_signal.emit(True, "恢复完成")
        except Exception as e:
            logging.error(f"工作线程异常: {e}", exc_info=True)
            self.emit_log(f"[错误] {e}")
            self.done_signal.emit(False, str(e))


# ══════════════════════════════════════════════════════
#  UI 组件
# ══════════════════════════════════════════════════════
class CustomToolTip(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(24)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                color: #000000;
                font-size: 12px;
                font-family: 'Microsoft YaHei';
                background: transparent;
            }
        """)
        layout.addWidget(label)
        self.ensurePolished()
        self.updateGeometry()
        self.resize(self.sizeHint())
        self.opacity = 0.0
        self.setWindowOpacity(self.opacity)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fade_in)
        self.timer.start(10)

    def fade_in(self):
        self.opacity += 0.1
        if self.opacity >= 1.0:
            self.opacity = 1.0
            self.timer.stop()
        self.setWindowOpacity(self.opacity)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.drawRect(self.rect())


class GradientFrame(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        self.setMouseTracking(True)
        self._resize_active = False
        self._dragging = False
        self._drag_start = QPoint()
        self._last_cursor_edge = None

    def _get_main_window(self):
        w = self.window()
        if isinstance(w, TransparentMacWindow):
            return w
        return None

    def mousePressEvent(self, event):
        main = self._get_main_window()
        if main and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapTo(main, event.position().toPoint())
            edge = main._detect_edge(pos)
            if edge:
                self._resize_active = True
                main._resizing = True
                main._resize_edge = edge
                main._resize_start_pos = event.globalPosition().toPoint()
                main._resize_start_geom = main.geometry()
            else:
                self._dragging = True
                self._drag_start = event.position().toPoint()

    def mouseMoveEvent(self, event):
        main = self._get_main_window()
        if not main:
            return
        if self._resize_active and main._resizing:
            main._do_resize(event.globalPosition().toPoint())
        elif self._dragging:
            movement = event.position().toPoint() - self._drag_start
            main.move(main.pos() + movement)
        else:
            pos = self.mapTo(main, event.position().toPoint())
            m = main.RESIZE_MARGIN
            near_edge = (pos.x() < m or pos.x() > main.width() - m or
                         pos.y() < m or pos.y() > main.height() - m)
            if near_edge:
                edge = main._detect_edge(pos)
                if edge != self._last_cursor_edge:
                    self._last_cursor_edge = edge
                    main._apply_edge_cursor(edge)
            elif self._last_cursor_edge is not None:
                self._last_cursor_edge = None
                main.unsetCursor()

    def mouseReleaseEvent(self, event):
        main = self._get_main_window()
        if main and event.button() == Qt.MouseButton.LeftButton:
            if self._resize_active:
                self._resize_active = False
                main._resizing = False
                main._resize_edge = None
                save_window_size(main.width(), main.height())
            self._dragging = False

    def leaveEvent(self, event):
        main = self._get_main_window()
        if main:
            if not self._resize_active and not self._dragging:
                main.unsetCursor()
                self._last_cursor_edge = None

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.eraseRect(self.rect())
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            path = QPainterPath()
            rect = self.rect()
            path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 30, 30)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setClipPath(path)
            paint_background(painter, rect.x(), rect.y(), rect.width(), rect.height(),
                             BG_MODE, BG_COLORS, BG_EFFECTIVE_DIR, BG_RANDOM_PARAMS)
            painter.setClipping(False)
            super().paintEvent(event)
        except Exception as e:
            logging.error(f"GradientFrame paintEvent error: {str(e)}")


class ControlButton(QPushButton):
    def __init__(self, icon, tooltip_text, parent=None):
        super().__init__(icon, parent)
        self.tooltip_text = tooltip_text
        self.tooltip = None
        self.setFixedSize(40, 40)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 51);
                color: rgba(0, 0, 0, 179);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 77);
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 77);
            }
        """)
        self.setMouseTracking(True)

    def enterEvent(self, event):
        if not self.tooltip:
            self.tooltip = CustomToolTip(self.tooltip_text)
            btn_rect = self.rect()
            btn_global_pos = self.mapToGlobal(btn_rect.center())
            tooltip_x = btn_global_pos.x() - self.tooltip.width() // 2
            tooltip_y = btn_global_pos.y() + btn_rect.height() // 2 + 5
            self.tooltip.move(tooltip_x, tooltip_y)
            self.tooltip.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.tooltip:
            self.tooltip.hide()
            self.tooltip.deleteLater()
            self.tooltip = None
        super().leaveEvent(event)


class GradientDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._dragging = False
        self._drag_start = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            movement = event.position().toPoint() - self._drag_start
            self.move(self.pos() + movement)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            rect = self.rect()
            path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 15, 15)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setClipPath(path)
            paint_background(painter, rect.x(), rect.y(), rect.width(), rect.height(),
                             BG_MODE, BG_COLORS, BG_EFFECTIVE_DIR, BG_RANDOM_PARAMS)
            painter.setClipping(False)
            super().paintEvent(event)
        except Exception as e:
            logging.error(f"GradientDialog paintEvent error: {str(e)}")


class ConfirmDialog(GradientDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(500, 250)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        title = QLabel("请选择以下功能")
        title.setStyleSheet("QLabel { font-size: 22px; color: #333; text-align: center; font-weight: bold; }")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        for text in ["是（退出程序）", "否（最小化到托盘）", "取消（取消操作）"]:
            lbl = QLabel(text)
            lbl.setStyleSheet("QLabel { font-size: 16px; color: #555; text-align: center; }")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_layout.addWidget(lbl)
        layout.addLayout(info_layout)
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        exit_btn = QPushButton("是")
        exit_btn.setFixedSize(60, 30)
        exit_btn.setStyleSheet("""
            QPushButton { background-color: #ff5f56; color: white; border-radius: 6px;
                          padding: 2px 8px; font-weight: 600; border: none; font-size: 11px; }
            QPushButton:hover { background-color: #ff3b30; }
        """)
        exit_btn.clicked.connect(self.on_exit)
        minimize_btn = QPushButton("否")
        minimize_btn.setFixedSize(60, 30)
        minimize_btn.setStyleSheet("""
            QPushButton { background-color: #ffbd2e; color: white; border-radius: 6px;
                          padding: 2px 8px; font-weight: 600; border: none; font-size: 11px; }
            QPushButton:hover { background-color: #ffa500; }
        """)
        minimize_btn.clicked.connect(self.on_minimize)
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(60, 30)
        cancel_btn.setStyleSheet("""
            QPushButton { background-color: #e5e5e5; color: #333; border-radius: 6px;
                          padding: 2px 8px; font-weight: 600; border: none; font-size: 11px; }
            QPushButton:hover { background-color: #d4d4d4; }
        """)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(exit_btn)
        buttons_layout.addWidget(minimize_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)
        strip_focus_rect(self)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            rect = self.rect()
            path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 15, 15)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
            painter.drawPath(path)
            super().paintEvent(event)
        except Exception as e:
            logging.error(f"ConfirmDialog paintEvent error: {str(e)}")

    def on_exit(self):
        self.accept()
        QApplication.quit()

    def on_minimize(self):
        self.accept()
        if self.parent() and hasattr(self.parent(), 'hide_to_tray'):
            self.parent().hide_to_tray()


class AppDialog(GradientDialog):
    """与界面统一的自绘消息弹窗，支持 info / warning / error / question / success 五种类型。"""
    _HOVER = {
        "info": "#2563eb", "warning": "#d97706", "error": "#dc2626",
        "question": "#7c3aed", "success": "#16a34a",
    }
    _ICON_COLOR = {
        "info": "#3b82f6", "warning": "#f59e0b", "error": "#ef4444",
        "question": "#8b5cf6", "success": "#22c55e",
    }
    _ICON_TEXT = {
        "info": "ℹ", "warning": "⚠", "error": "✕",
        "question": "?", "success": "✓",
    }

    def __init__(self, parent=None, title="提示", message="", dlg_type="info",
                 ok_text="确定", cancel_text="取消"):
        super().__init__(parent)
        self._dlg_type = dlg_type
        self._result = False
        self._title = title
        self._message = message
        self._ok_text = ok_text
        self._cancel_text = cancel_text
        self.setMinimumWidth(440)
        self.setFixedHeight(230)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 22)
        layout.setSpacing(16)

        top = QHBoxLayout()
        top.setSpacing(14)
        icon = QLabel(self._ICON_TEXT.get(self._dlg_type, "ℹ"))
        icon.setStyleSheet(
            f"QLabel {{ font-size: 26px; color: {self._ICON_COLOR.get(self._dlg_type, '#3b82f6')}; }}"
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(46, 46)
        title_lbl = QLabel(self._title)
        title_lbl.setStyleSheet("QLabel { font-size: 19px; font-weight: bold; color: #333; }")
        top.addWidget(icon)
        top.addWidget(title_lbl, 1)
        layout.addLayout(top)

        msg = QLabel(self._message)
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        msg.setStyleSheet("QLabel { font-size: 14px; color: #555; line-height: 1.6; }")
        layout.addWidget(msg, 1)

        btns = QHBoxLayout()
        btns.setSpacing(12)
        btns.addStretch(1)
        if self._dlg_type == "question":
            cancel_btn = QPushButton(self._cancel_text)
            cancel_btn.setFixedSize(96, 36)
            cancel_btn.setStyleSheet(
                "QPushButton { background-color: rgba(255,255,255,200); color: #333; "
                "border: none; outline: none; border-radius: 9px; font-weight: 600; "
                "font-size: 13px; }"
                "QPushButton:hover { background-color: rgba(255,255,255,255); }"
                "QPushButton:focus { outline: none; border: none; }"
            )
            cancel_btn.clicked.connect(self.on_cancel)
            btns.addWidget(cancel_btn)
        ok_btn = QPushButton(self._ok_text)
        ok_btn.setFixedSize(96, 36)
        color = self._ICON_COLOR.get(self._dlg_type, "#3b82f6")
        hover = self._HOVER.get(self._dlg_type, color)
        ok_btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; border: none; "
            f"outline: none; border-radius: 9px; font-weight: 600; font-size: 13px; padding: 4px 12px; }}"
            f"QPushButton:hover {{ background-color: {hover}; }}"
            f"QPushButton:focus {{ outline: none; border: none; background-color: {hover}; }}"
        )
        ok_btn.clicked.connect(self.on_ok)
        btns.addWidget(ok_btn)
        layout.addLayout(btns)
        strip_focus_rect(self)

    def on_ok(self):
        self._result = True
        self.accept()

    def on_cancel(self):
        self._result = False
        self.reject()

    def result_ok(self):
        return self._result

    @staticmethod
    def show_info(parent, title, message):
        AppDialog(parent, title, message, "info").exec()
        return True

    @staticmethod
    def show_warning(parent, title, message):
        AppDialog(parent, title, message, "warning").exec()
        return True

    @staticmethod
    def show_error(parent, title, message):
        AppDialog(parent, title, message, "error").exec()
        return True

    @staticmethod
    def show_success(parent, title, message):
        AppDialog(parent, title, message, "success").exec()
        return True

    @staticmethod
    def ask_question(parent, title, message, ok_text="确定", cancel_text="取消"):
        d = AppDialog(parent, title, message, "question", ok_text, cancel_text)
        d.exec()
        return d.result_ok()


class ColorSwatch(QPushButton):
    colorChanged = pyqtSignal(int, QColor)
    def __init__(self, index: int, color: QColor, parent=None):
        super().__init__(parent)
        self.index = index
        self._color = color
        self.setFixedSize(44, 44)
        self._apply_style()

    def _apply_style(self):
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgb({r},{g},{b});
                border-radius: 8px;
                border: 2px solid rgba(0,0,0,30);
            }}
            QPushButton:hover {{
                border: 2.5px solid rgba(0,0,0,100);
            }}
        """)

    def set_color(self, color: QColor):
        self._color = color
        self._apply_style()

    def get_color(self) -> QColor:
        return self._color

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            dlg = QColorDialog(self._color, self)
            dlg.setWindowTitle("选择颜色")
            dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel)
            dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
            dlg.setStyleSheet("""
                QColorDialog { background-color: #ffffff; }
                QColorDialog QWidget { background-color: #ffffff; color: #333333; }
                QColorDialog QPushButton {
                    background-color: #f0f0f0;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 4px 12px;
                }
                QColorDialog QPushButton:hover { background-color: #e0e0e0; }
                QColorDialog QLineEdit {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                }
                QColorDialog QSpinBox {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #cccccc;
                }
            """)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                color = dlg.selectedColor()
                if color.isValid():
                    self._color = color
                    self._apply_style()
                    self.colorChanged.emit(self.index, color)
        super().mousePressEvent(event)


class MiniPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 50)
        self._mode = "dual"
        self._colors = BG_COLORS[:]
        self._direction = "diagonal"
        self._params = {}

    def update_preview(self, mode, colors, direction="diagonal", params=None):
        self._mode = mode
        self._colors = colors
        self._direction = direction
        self._params = params or {}
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setClipPath(path)
        paint_background(painter, 0, 0, self.width(), self.height(),
                         self._mode, self._colors, self._direction, self._params)
        painter.setClipping(False)


# ══════════════════════════════════════════════════════
#  备份设置对话框
# ══════════════════════════════════════════════════════
class BackupSettingsDialog(GradientDialog):
    settings_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 尺寸加大以保证内容完整显示；同时按屏幕可用高度自适应，小屏仍可滚动兜底
        scr = QApplication.primaryScreen().availableGeometry()
        width = 720
        height = min(860, int(scr.height() * 0.9))
        self.setFixedSize(width, height)
        self.cfg = load_backup_config()
        self.init_ui()

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(20, 16, 16, 10)
        title_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_label = QLabel("设置")
        title_label.setStyleSheet("""
            QLabel { font-size: 16px; font-weight: bold; color: #333; background: transparent; }
        """)
        title_bar.addWidget(title_label)
        title_bar.addStretch()
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 25);
                color: rgba(0, 0, 0, 150);
                border-radius: 15px;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 50);
                color: rgba(0, 0, 0, 200);
            }
        """)
        close_btn.clicked.connect(self.reject)
        title_bar.addWidget(close_btn)
        root.addLayout(title_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 0px; border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(120,120,120,80); min-height: 30px; border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content = QVBoxLayout(content_widget)
        content.setContentsMargins(24, 6, 24, 10)
        content.setSpacing(7)

        # ── 自动检测结果（点「重新检测」自动刷新到这个框里）──
        content.addWidget(self._section_label("自动检测结果（点「重新检测」自动更新到这里）"))
        detect_row = QHBoxLayout()
        detect_row.setSpacing(8)
        self.detect_box = QTextEdit()
        self.detect_box.setReadOnly(True)
        self.detect_box.setFixedHeight(58)
        self.detect_box.setStyleSheet(self._input_style() + " QTextEdit { font-size: 11px; }")
        self._fill_detect_box()
        detect_row.addWidget(self.detect_box, 1)
        detect_btn = QPushButton("重新检测")
        detect_btn.setFixedHeight(58)
        detect_btn.setFixedWidth(88)
        detect_btn.setStyleSheet(self._btn_style(bg="rgba(255,255,255,180)", fg="#555"))
        detect_btn.clicked.connect(self.on_redetect)
        detect_row.addWidget(detect_btn)
        content.addLayout(detect_row)

        # ── 备份保存位置 ──
        content.addWidget(self._section_label("备份保存位置（备份包存到哪）"))
        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self.save_edit = QLineEdit(self.cfg.get("save_root", "D:\\"))
        self.save_edit.setStyleSheet(self._input_style())
        save_btn = QPushButton("浏览")
        save_btn.setFixedWidth(70)
        save_btn.setStyleSheet(self._btn_style())
        save_btn.clicked.connect(self.browse_save_root)
        save_row.addWidget(self.save_edit)
        save_row.addWidget(save_btn)
        content.addLayout(save_row)
        content.addWidget(self._hint_label(
            "点「备份」后，备份包（zip，内含对话记录 + 源代码）自动存到这里，如 D:\\WorkBuddy备份\\。换电脑时把这个 zip 拷到新电脑即可。"))

        # ── WorkBuddy 数据目录 ──
        content.addWidget(self._section_label("WorkBuddy 数据目录（对话记录、自动化任务存在哪）"))
        wb_row = QHBoxLayout()
        wb_row.setSpacing(8)
        self.wb_edit = QLineEdit(self.cfg.get("workbuddy_dir", os.path.expanduser("~\\.workbuddy")))
        self.wb_edit.setStyleSheet(self._input_style())
        wb_btn = QPushButton("浏览")
        wb_btn.setFixedWidth(70)
        wb_btn.setStyleSheet(self._btn_style())
        wb_btn.clicked.connect(self.browse_wb_dir)
        wb_row.addWidget(self.wb_edit)
        wb_row.addWidget(wb_btn)
        content.addLayout(wb_row)
        content.addWidget(self._hint_label(
            "WorkBuddy 的核心数据目录（默认 C:\\Users\\你\\.workbuddy），对话索引、自动化任务、设置都在这里，恢复时写回这里。一般不用改。"))

        # ── 项目工作空间根目录 ──
        content.addWidget(self._section_label("项目工作空间根目录（源代码存在哪）"))
        ws_row = QHBoxLayout()
        ws_row.setSpacing(8)
        self.ws_edit = QLineEdit(self.cfg.get("workspaces_root", os.path.expanduser("~\\WorkBuddy")))
        self.ws_edit.setStyleSheet(self._input_style())
        ws_btn = QPushButton("浏览")
        ws_btn.setFixedWidth(70)
        ws_btn.setStyleSheet(self._btn_style())
        ws_btn.clicked.connect(self.browse_ws_root)
        ws_row.addWidget(self.ws_edit)
        ws_row.addWidget(ws_btn)
        content.addLayout(ws_row)
        content.addWidget(self._hint_label(
            "所有项目/任务的源代码都在这个目录下（默认 C:\\Users\\你\\WorkBuddy），备份时连同源代码一起打包。一般不用改。"))

        # ── 内置缓存排除（2×2 并排）──
        content.addWidget(self._section_label("WorkBuddy 内置缓存排除（可再生的缓存）"))
        cb_grid = QGridLayout()
        cb_grid.setHorizontalSpacing(16)
        cb_grid.setVerticalSpacing(4)
        self.cb_app_session = QCheckBox("排除 app/session 运行时缓存")
        self.cb_app_session.setChecked(self.cfg.get("wb_exclude_app_session", True))
        self.cb_traces = QCheckBox("排除 traces 调试跟踪")
        self.cb_traces.setChecked(self.cfg.get("wb_exclude_traces", True))
        self.cb_appearance = QCheckBox("排除 appearance-resources 外观缓存")
        self.cb_appearance.setChecked(self.cfg.get("wb_exclude_appearance", True))
        self.cb_connectors = QCheckBox("排除 connectors-marketplace 市场缓存")
        self.cb_connectors.setChecked(self.cfg.get("wb_exclude_connectors_marketplace", True))
        for i, cb in enumerate([self.cb_app_session, self.cb_traces,
                                self.cb_appearance, self.cb_connectors]):
            cb.setStyleSheet("QCheckBox { color: #333; background: transparent; font-size: 12px; }")
            cb_grid.addWidget(cb, i // 2, i % 2)
        content.addLayout(cb_grid)
        content.addWidget(self._hint_label(
            "这四项都是 WorkBuddy 能自动重建的缓存，排除后备份包更小、速度更快，不影响对话和源代码的完整性。保持默认勾选即可。"))

        # ── 源代码备份跳过目录 ──
        content.addWidget(self._section_label("备份源代码时跳过的文件夹（每行一个）"))
        self.excludes_edit = QTextEdit()
        self.excludes_edit.setFixedHeight(52)
        self.excludes_edit.setStyleSheet(self._input_style())
        self.excludes_edit.setPlainText("\n".join(self.cfg.get("excludes", [])))
        content.addWidget(self.excludes_edit)
        content.addWidget(self._hint_label(
            "这些是依赖/构建产物目录（如 node_modules、build），可随时重新生成，跳过它们能大幅减小备份包。你自己写的源代码文件不受任何影响。"))

        content.addStretch()
        scroll.setWidget(content_widget)
        root.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(24, 10, 24, 16)
        btn_row.setSpacing(12)
        reset_btn = QPushButton("恢复默认")
        reset_btn.setFixedHeight(38)
        reset_btn.setStyleSheet(self._btn_style(bg="rgba(255,255,255,160)", fg="#555"))
        reset_btn.clicked.connect(self.on_reset)
        save_btn = QPushButton("保存")
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet(self._btn_style(bg="rgba(80,80,80,200)", fg="white"))
        save_btn.clicked.connect(self.on_save)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)
        strip_focus_rect(self)

    def _hint_label(self, text):
        """设置项下方的灰色小字说明，避免看不懂选项含义。"""
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("""
            QLabel { font-size: 10px; color: rgba(120,120,130,220);
                     background: transparent; padding: 0 2px; line-height: 1.5; }
        """)
        return lbl

    def _fill_detect_box(self):
        """把自动检测到的路径填进检测结果框（点「重新检测」自动刷新）。"""
        install_p = self.cfg.get("install_path", "") or "未检测到"
        self.detect_box.setPlainText(
            f"WorkBuddy 程序：{install_p}\n"
            f"对话数据：{self.cfg.get('workbuddy_dir', '')}\n"
            f"源代码：{self.cfg.get('workspaces_root', '')}"
        )

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("""
            QLabel { font-size: 12px; color: rgba(0,0,0,140); background: transparent;
                     font-weight: 600; letter-spacing: 0.3px; }
        """)
        return lbl

    def _input_style(self):
        return """
            QLineEdit, QTextEdit {
                background-color: rgba(255,255,255,180);
                color: #333;
                border: 1px solid rgba(0,0,0,40);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QTextEdit:focus {
                background-color: rgba(255,255,255,220);
                border: 1px solid rgba(0,0,0,80);
            }
        """

    def _btn_style(self, bg="rgba(255,255,255,180)", fg="#333"):
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border-radius: 8px;
                border: 1px solid rgba(0,0,0,40);
                font-size: 13px;
                font-weight: 600;
                padding: 6px 0;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,220);
            }}
        """

    def browse_save_root(self):
        d = QFileDialog.getExistingDirectory(self, "选择默认保存盘符/目录", self.save_edit.text())
        if d:
            self.save_edit.setText(d)

    def browse_wb_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择 WorkBuddy 数据目录", self.wb_edit.text())
        if d:
            self.wb_edit.setText(d)

    def browse_ws_root(self):
        d = QFileDialog.getExistingDirectory(self, "选择项目工作空间根目录", self.ws_edit.text())
        if d:
            self.ws_edit.setText(d)

    def on_reset(self):
        self.save_edit.setText("D:/")
        self.wb_edit.setText(os.path.expanduser("~\\.workbuddy"))
        self.ws_edit.setText(os.path.expanduser("~\\WorkBuddy"))
        self.cb_app_session.setChecked(True)
        self.cb_traces.setChecked(True)
        self.cb_appearance.setChecked(True)
        self.cb_connectors.setChecked(True)
        self.excludes_edit.setPlainText("\n".join(DEFAULT_BACKUP_CONFIG["excludes"]))

    def on_save(self):
        new_cfg = {
            "save_root": self.save_edit.text().strip() or "D:\\",
            "workbuddy_dir": self.wb_edit.text().strip() or os.path.expanduser("~\\.workbuddy"),
            "workspaces_root": self.ws_edit.text().strip() or os.path.expanduser("~\\WorkBuddy"),
            "excludes": [e.strip() for e in self.excludes_edit.toPlainText().splitlines() if e.strip()],
            "wb_exclude_app_session": self.cb_app_session.isChecked(),
            "wb_exclude_traces": self.cb_traces.isChecked(),
            "wb_exclude_appearance": self.cb_appearance.isChecked(),
            "wb_exclude_connectors_marketplace": self.cb_connectors.isChecked(),
        }
        save_backup_config(new_cfg)
        self.settings_saved.emit()
        self.accept()

    def on_redetect(self):
        """重新检测并把结果直接显示在设置面板里（不再弹窗）。"""
        cfg = auto_adjust_config(self.cfg)
        self.cfg = cfg
        save_backup_config(cfg)
        self.wb_edit.setText(cfg.get("workbuddy_dir", ""))
        self.ws_edit.setText(cfg.get("workspaces_root", ""))
        self._fill_detect_box()
        install_p = cfg.get("install_path", "") or "未检测到"
        if install_p == "未检测到":
            AppDialog.show_warning(
                self, "检测完成",
                "未检测到 WorkBuddy 安装路径，已尽量按默认值填充：\n"
                f"数据目录：{cfg.get('workbuddy_dir', '')}\n"
                f"工作空间：{cfg.get('workspaces_root', '')}")


# ══════════════════════════════════════════════════════
#  主窗口
# ══════════════════════════════════════════════════════
class TransparentMacWindow(QMainWindow):
    RESIZE_MARGIN = 7

    def __init__(self):
        super().__init__()
        self.gradient_frame = None
        self._resizing = False
        self._resize_edge = None
        self._resize_start_pos = QPoint()
        self._resize_start_geom = QRect()
        self.cfg = auto_adjust_config(load_backup_config())
        save_backup_config(self.cfg)
        self.engine = BackupEngine(self.cfg)
        self.worker = None
        self.restore_zip = ""
        self._current_page = 0
        self.setup_window()
        self.init_ui()
        self.setup_tray()
        self.setMouseTracking(True)

    @staticmethod
    def _make_emoji_icon(size: int = 256) -> QIcon:
        # 优先加载打包进 exe / 程序目录的正式图标
        for base in (getattr(sys, '_MEIPASS', ''), get_app_dir()):
            if not base:
                continue
            ico = os.path.join(base, 'WorkBuddyBackup.ico')
            png = os.path.join(base, 'WorkBuddyBackup_icon.png')
            if os.path.exists(ico):
                return QIcon(ico)
            if os.path.exists(png):
                return QIcon(png)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI Emoji", int(size * 0.65))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "💾")
        painter.end()
        return QIcon(pixmap)

    def setup_window(self):
        self.setWindowTitle("WorkBuddy一键备份")
        self.setMinimumSize(960, 700)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowIcon(self._make_emoji_icon(256))

    def setup_tray(self):
        try:
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(self._make_emoji_icon(256))
            self.tray_icon.setToolTip("WorkBuddy一键备份")
            tray_menu = QMenu()
            tray_menu.addAction("显示窗口", self.show_normal)
            tray_menu.addAction("退出程序", self.exit_application)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.on_tray_activated)
            self.tray_icon.show()
        except Exception as e:
            logging.error(f"托盘图标初始化错误: {e}")
            self.tray_icon = None

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_normal()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.gradient_frame = GradientFrame()
        frame_layout = QVBoxLayout(self.gradient_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        # 标题栏：标题放左上角，右侧为控制按钮
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(24, 16, 20, 0)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("WorkBuddy 一键备份")
        title.setStyleSheet("""
            QLabel {
                font-size: 17px;
                color: #2c3e50;
                background: transparent;
                font-weight: bold;
            }
        """)
        subtitle = QLabel("勾选对话即可备份 / 恢复；换电脑登录同一账号即可还原")
        subtitle.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #888;
                background: transparent;
            }
        """)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_bar.addLayout(title_col)
        title_bar.addStretch()
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(15)
        settings_btn = ControlButton("⚙️", "设置")
        settings_btn.clicked.connect(self.show_settings)
        minimize_btn = ControlButton("-", "最小化")
        minimize_btn.clicked.connect(self.showMinimized)
        close_btn = ControlButton("×", "关闭")
        close_btn.clicked.connect(self.show_confirm_dialog)
        controls_layout.addWidget(settings_btn)
        controls_layout.addWidget(minimize_btn)
        controls_layout.addWidget(close_btn)
        title_bar.addLayout(controls_layout)
        frame_layout.addLayout(title_bar)

        # 内容区（压缩上下留白，把空间让给对话列表）
        content = QVBoxLayout()
        content.setContentsMargins(24, 8, 24, 12)
        content.setSpacing(8)

        # 信息条（紧凑）
        info_card = QFrame()
        info_card.setStyleSheet("""
            QFrame {
                background-color: rgba(255,255,255,150);
                border-radius: 10px;
                border: 1px solid rgba(255,255,255,120);
            }
            QLabel { background: transparent; color: #555; font-size: 10px; }
        """)
        info_layout = QGridLayout(info_card)
        info_layout.setContentsMargins(12, 5, 12, 5)
        info_layout.setSpacing(2)
        self.lbl_wb = QLabel(f"数据: {self.engine.wb_dir}")
        self.lbl_ws = QLabel(f"项目: {self.engine.ws_root}")
        self.lbl_save = QLabel(f"保存: {self.engine.get_default_backup_folder()}")
        self.lbl_wb.setWordWrap(True)
        self.lbl_ws.setWordWrap(True)
        self.lbl_save.setWordWrap(True)
        info_layout.addWidget(self.lbl_wb, 0, 0)
        info_layout.addWidget(self.lbl_ws, 0, 1)
        info_layout.addWidget(self.lbl_save, 1, 0, 1, 2)
        content.addWidget(info_card)

        # 界面切换（备份 / 恢复）
        tab_row = QHBoxLayout()
        tab_row.setSpacing(12)
        self.tab_backup_btn = QPushButton("备份")
        self.tab_restore_btn = QPushButton("恢复")
        for _b in (self.tab_backup_btn, self.tab_restore_btn):
            _b.setFixedHeight(38)
            _b.setMinimumWidth(120)
            _b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_backup_btn.clicked.connect(lambda: self.switch_page(0))
        self.tab_restore_btn.clicked.connect(lambda: self.switch_page(1))
        tab_row.addWidget(self.tab_backup_btn)
        tab_row.addWidget(self.tab_restore_btn)
        tab_row.addStretch()
        content.addLayout(tab_row)

        # 双界面容器
        self.stack = QStackedWidget()
        self.page_backup = self._build_backup_page()
        self.page_restore = self._build_restore_page()
        self.stack.addWidget(self.page_backup)
        self.stack.addWidget(self.page_restore)
        content.addWidget(self.stack, 1)

        frame_layout.addLayout(content)
        main_layout.addWidget(self.gradient_frame)

        strip_focus_rect(self)
        self.switch_page(0)
        # 延迟加载数据：窗口先显示出来，避免启动时长时间空白
        QTimer.singleShot(60, self.load_local_sessions)

        self.dragging = False
        self.drag_start = QPoint()

    # ─────────── 双界面：样式与通用组件 ───────────
    def _tab_style(self, active):
        if active:
            return """
                QPushButton {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4facfe, stop:1 #00f2fe);
                    color: white; border: none; border-radius: 12px;
                    font-size: 13px; font-weight: bold; padding: 0 18px;
                }
            """
        return """
            QPushButton {
                background-color: rgba(255,255,255,150); color: #555; border: none;
                border-radius: 12px; font-size: 13px; font-weight: 600; padding: 0 18px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,225); }
        """

    def switch_page(self, idx):
        self._current_page = idx
        self.stack.setCurrentIndex(idx)
        self.tab_backup_btn.setStyleSheet(self._tab_style(idx == 0))
        self.tab_restore_btn.setStyleSheet(self._tab_style(idx == 1))
        if idx == 1:
            self.refresh_zip_list()

    def _small_btn_style(self):
        return """
            QPushButton {
                background-color: rgba(255,255,255,180); color: #444; border: none;
                outline: none; border-radius: 8px; font-size: 12px; font-weight: 600; padding: 0 12px;
            }
            QPushButton:hover { background-color: rgba(255,255,255,235); }
            QPushButton:focus { outline: none; border: none; }
        """

    def _primary_btn_style(self, c1, c2):
        return f"""
            QPushButton {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c1}, stop:1 {c2});
                color: white; border: none; outline: none; border-radius: 12px;
                font-size: 14px; font-weight: bold; padding: 0 18px;
            }}
            QPushButton:pressed {{ background-color: {c1}; }}
            QPushButton:focus {{ outline: none; border: none; background-color: {c1}; }}
        """

    def _make_progress(self):
        p = QProgressBar()
        p.setRange(0, 100)
        p.setValue(0)
        p.setTextVisible(True)
        p.setFixedHeight(18)
        p.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255,255,255,120);
                border-radius: 7px; border: 1px solid rgba(0,0,0,30);
                text-align: center; color: #333; font-size: 10px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4facfe, stop:1 #00f2fe);
                border-radius: 7px;
            }
        """)
        return p

    def _make_log(self):
        box = QTextEdit()
        box.setReadOnly(True)
        box.setFixedHeight(64)
        box.setStyleSheet("""
            QTextEdit {
                background-color: rgba(255,255,255,180); color: #333;
                border-radius: 12px; border: 1px solid rgba(0,0,0,30);
                padding: 6px; font-size: 11px;
                font-family: 'Microsoft YaHei', Consolas, monospace;
            }
        """)
        return box

    def _session_tree(self):
        tree = SessionTree()
        tree.setHeaderLabels(["对话", "更新时间"])
        tree.setRootIsDecorated(True)   # 显示展开/收起箭头
        tree.setIndentation(14)
        tree.setExpandsOnDoubleClick(False)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # 列 0 按内容自适应（时间紧跟标题之后），列 1 拉伸剩余空间
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tree.header().setMaximumSectionSize(620)
        tree.setStyleSheet("""
            QTreeWidget {
                background-color: rgba(255,255,255,185); border-radius: 12px;
                border: 1px solid rgba(0,0,0,30); font-size: 13px; color: #333;
                outline: none;
                alternate-background-color: rgba(255,255,255,110);
            }
            QTreeWidget::item {
                height: 26px; padding: 1px 6px; border: none;
            }
            QTreeWidget::item:hover {
                background-color: rgba(79,172,254,45); border-radius: 6px;
            }
            QTreeWidget::item:focus, QTreeWidget::item:selected {
                outline: none; border: none; background: transparent;
            }
            QTreeWidget::indicator {
                width: 13px; height: 13px;
            }
            QTreeWidget::branch { background: transparent; }
            QTreeWidget::branch:hover {
                background: transparent;
            }
            QHeaderView::section {
                background-color: rgba(255,255,255,210); border: none;
                padding: 4px 6px; font-weight: 600; color: #444; font-size: 12px;
            }
        """)
        return tree

    def _fmt_time(self, v):
        """官方样式相对时间 + 括号内具体时间，如：24天前（2026年9月28日19:43:31）"""
        if v is None or v == '':
            return ''
        s = str(v)
        dt = None
        if s.isdigit():
            n = float(s)
            if n > 1000000000000:
                n = n / 1000.0
            try:
                dt = datetime.fromtimestamp(n)
            except Exception:
                return s
        else:
            try:
                dt = datetime.fromisoformat(s.replace('Z', '').replace('T', ' ')[:19])
            except Exception:
                return s
        if dt is None:
            return s
        detail = f"{dt.year}年{dt.month}月{dt.day}日{dt.hour}:{dt.minute:02d}:{dt.second:02d}"
        diff = datetime.now() - dt
        secs = diff.total_seconds()
        if secs < 60:
            return f"刚刚（{detail}）"
        if secs < 3600:
            return f"{int(secs // 60)}分钟前（{detail}）"
        if secs < 86400:
            return f"{int(secs // 3600)}小时前（{detail}）"
        days = diff.days
        if days < 30:
            return f"{days}天前（{detail}）"
        if days < 365:
            return f"{max(1, days // 30)}个月前（{detail}）"
        return detail

    def _ws_label(self, cwd):
        c = os.path.normpath(str(cwd or ''))
        if not c or c == '.':
            return ''
        parts = c.split(os.sep)
        for j, p in enumerate(parts):
            if p.lower() == 'workbuddy' and j + 1 < len(parts):
                return parts[j + 1]
        return os.path.basename(c) or c

    def _group_key(self, cwd, ws_paths=None):
        """按 cwd 推导对话所属空间（目录名）。
        只有 workspaces 表登记过的目录才算「空间」；其余（旧项目目录）归「任务」组，返回 ''。"""
        c = os.path.normpath(str(cwd or ''))
        if not c or c == '.':
            return ''
        ws_root = os.path.normpath(self.engine.ws_root)
        if c.lower().startswith(ws_root.lower() + os.sep):
            rel = os.path.relpath(c, ws_root)
            top = rel.split(os.sep)[0]
            if ws_paths is not None:
                full = os.path.normpath(os.path.join(ws_root, top)).lower()
                if full in ws_paths:
                    return top
                return ''
            return top
        parts = c.split(os.sep)
        for j, p in enumerate(parts):
            if p.lower() == 'workbuddy' and j + 1 < len(parts):
                top = parts[j + 1]
                if ws_paths is not None:
                    full = os.path.normpath(os.path.join(ws_root, top)).lower()
                    if full not in ws_paths:
                        return ''
                return top
        return ''

    def _ws_display_name(self, top):
        """空间显示名：官方把 automation-* 目录显示为「定时任务-*」。"""
        if not top:
            return ''
        if top.startswith('automation-'):
            return '定时任务-' + top[len('automation-'):]
        return top

    def _make_group_node(self, parent, text, kind, checkable, tooltip=''):
        """创建组节点（对齐官方侧边栏样式）：
        kind='top'：顶层「任务/空间」灰色小字标题，无复选框、无图标；
        kind='space'：空间组，📁 图标 + 常规字重深色文字，带复选框。"""
        it = QTreeWidgetItem(parent)
        if kind == 'space':
            it.setText(0, f"📁 {text}")
        else:
            it.setText(0, text)
        if tooltip:
            it.setToolTip(0, tooltip)
        if checkable:
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked)
        else:
            # QTreeWidgetItem 默认 flags 已含 UserCheckable，必须显式移除才不显示空框
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        f = it.font(0)
        if kind == 'top':
            f.setPixelSize(11)
            f.setBold(True)
            it.setForeground(0, QBrush(QColor(130, 138, 150)))
        else:
            f.setPixelSize(13)
            f.setBold(False)
            it.setForeground(0, QBrush(QColor(35, 45, 60)))
        it.setFont(0, f)
        it.setExpanded(True)
        return it

    def _fill_tree(self, tree, rows, ws_paths=None):
        """按 WorkBuddy 官方侧边栏方式两级分组：
        「任务 (N)」组（不属于任何登记空间的对话，含已删除过滤后）、「空间 (N)」组（下挂登记空间，空间内为对话）。"""
        tree.clear()
        task_root = self._make_group_node(tree, "任务", 'top', False)
        task_root.setToolTip(0, "「任务」= 不属于任何空间的对话（与 WorkBuddy 侧边栏一致）")
        ws_root = self._make_group_node(tree, "空间", 'top', False)
        ws_root.setToolTip(0, "「空间」= WorkBuddy 中打开过的项目空间（源代码按空间打包）")
        ws_groups = {}
        task_count = 0
        for r in rows:
            cwd = str(r.get('cwd') or '')
            top = self._group_key(cwd, ws_paths)
            it = QTreeWidgetItem()
            title = str(r.get('title') or '')
            if len(title) > 30:
                title = title[:30] + '…'
            it.setText(0, title)
            it.setText(1, self._fmt_time(r.get('updated_at')))
            it.setToolTip(0, f"{r.get('title') or ''}\n{cwd}")
            # 官方样式：时间紧跟对话名之后、灰色小字（左对齐，不贴最右）
            it.setForeground(1, QBrush(QColor(150, 155, 165)))
            f = it.font(1)
            f.setPixelSize(11)
            it.setFont(1, f)
            it.setData(0, Qt.ItemDataRole.UserRole, str(r.get('id') or ''))
            it.setData(0, Qt.ItemDataRole.UserRole + 1, cwd)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked)
            if not top:
                task_root.addChild(it)
                task_count += 1
            else:
                disp = self._ws_display_name(top)
                if disp not in ws_groups:
                    # 项目（空间）行与官方一致：不带复选框；Ctrl+点名称可整组勾选
                    g = self._make_group_node(ws_root, disp, 'space', False, tooltip=top)
                    g.setData(0, Qt.ItemDataRole.UserRole + 2, top)  # 记录目录名供整组勾选
                    ws_groups[disp] = g
                ws_groups[disp].addChild(it)
        task_root.setText(0, f"任务 ({task_count})")
        ws_root.setText(0, f"空间 ({len(ws_groups)})")
        tree.resizeColumnToContents(1)

    def _iter_items(self, tree):
        """深度优先遍历树中所有节点（含组节点）。"""
        root = tree.invisibleRootItem()
        stack = [root]
        while stack:
            cur = stack.pop()
            for i in range(cur.childCount()):
                c = cur.child(i)
                yield c
                stack.append(c)

    def _set_all_check(self, tree, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        tree._updating = True
        try:
            for it in self._iter_items(tree):
                if it.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    it.setCheckState(0, state)
        finally:
            tree._updating = False

    def _checked_ids(self, tree):
        ids = []
        for it in self._iter_items(tree):
            sid = it.data(0, Qt.ItemDataRole.UserRole)
            if sid and it.checkState(0) == Qt.CheckState.Checked:
                ids.append(str(sid))
        return ids

    def _ws_names_for(self, tree):
        """根据勾选对话的 cwd 推导所属项目空间名"""
        names = set()
        ws_root = os.path.normpath(self.engine.ws_root)
        for it in self._iter_items(tree):
            if it.checkState(0) != Qt.CheckState.Checked:
                continue
            sid = it.data(0, Qt.ItemDataRole.UserRole)
            if not sid:
                continue
            cwd = str(it.data(0, Qt.ItemDataRole.UserRole + 1) or '').strip()
            if not cwd:
                continue
            c = os.path.normpath(cwd)
            top = ''
            if c.lower().startswith(ws_root.lower()):
                rel = os.path.relpath(c, ws_root)
                top = rel.split(os.sep)[0]
            else:
                parts = c.split(os.sep)
                for j, p in enumerate(parts):
                    if p.lower() == 'workbuddy' and j + 1 < len(parts):
                        top = parts[j + 1]
                        break
                if not top:
                    top = os.path.basename(c)
            if top and top not in ('.', '..'):
                names.add(top)
        return sorted(names)

    # ─────────── 备份页 ───────────
    def _build_backup_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        tip = QLabel("勾选要备份的对话（分组与 WorkBuddy 侧边栏一致；Ctrl+点空间名可整组勾选）：")
        tip.setStyleSheet("QLabel { color:#444; font-size:12px; font-weight:600; background:transparent; }")
        head.addWidget(tip)
        head.addStretch()
        sel_all = QPushButton("全选")
        sel_none = QPushButton("全不选")
        refresh = QPushButton("刷新")
        for b in (sel_all, sel_none, refresh):
            b.setFixedHeight(30)
            b.setStyleSheet(self._small_btn_style())
        sel_all.clicked.connect(lambda: self._set_all_check(self.tree_backup, True))
        sel_none.clicked.connect(lambda: self._set_all_check(self.tree_backup, False))
        refresh.clicked.connect(self.load_local_sessions)
        head.addWidget(sel_all)
        head.addWidget(sel_none)
        head.addWidget(refresh)
        lay.addLayout(head)

        self.tree_backup = self._session_tree()
        lay.addWidget(self.tree_backup, 1)

        self.lbl_bk_count = QLabel("共 0 个对话")
        self.lbl_bk_count.setStyleSheet("QLabel { color:#666; font-size:11px; background:transparent; }")
        lay.addWidget(self.lbl_bk_count)

        btn = QPushButton("备份所选对话")
        btn.setFixedHeight(42)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._primary_btn_style("#4facfe", "#00f2fe"))
        btn.clicked.connect(self.on_backup)
        lay.addWidget(btn)

        self.progress_backup = self._make_progress()
        lay.addWidget(self.progress_backup)
        self.log_box_backup = self._make_log()
        lay.addWidget(self.log_box_backup)
        return w

    # ─────────── 恢复页 ───────────
    def _build_restore_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        pick_row = QHBoxLayout()
        pick_row.setSpacing(8)
        tip_pick = QLabel("备份包：")
        tip_pick.setStyleSheet("QLabel { color:#444; font-size:13px; font-weight:600; background:transparent; }")
        self.zip_combo = QComboBox()
        self.zip_combo.setFixedHeight(32)
        self.zip_combo.setMinimumWidth(320)
        self.zip_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(255,255,255,190); color: #444;
                border: 1px solid rgba(0,0,0,30); border-radius: 8px;
                padding: 0 10px; font-size: 12px;
            }
            QComboBox:focus { outline: none; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox QAbstractItemView {
                background-color: white; color: #333;
                border: 1px solid rgba(0,0,0,40);
                selection-background-color: rgba(79,172,254,70);
                selection-color: #222; outline: none;
            }
        """)
        self.zip_combo.currentIndexChanged.connect(self.on_zip_selected)
        self.lbl_zip = QLabel("未选择备份包")
        self.lbl_zip.setStyleSheet("QLabel { color:#666; font-size:11px; background:transparent; }")
        self.lbl_zip.setWordWrap(True)
        pick_row.addWidget(tip_pick)
        pick_row.addWidget(self.zip_combo, 1)
        lay.addLayout(pick_row)
        lay.addWidget(self.lbl_zip)

        head = QHBoxLayout()
        head.setSpacing(8)
        tip = QLabel("勾选要恢复的对话（自动读取备份包；分组与官方侧边栏一致）：")
        tip.setStyleSheet("QLabel { color:#444; font-size:12px; font-weight:600; background:transparent; }")
        head.addWidget(tip)
        head.addStretch()
        sel_all = QPushButton("全选")
        sel_none = QPushButton("全不选")
        for b in (sel_all, sel_none):
            b.setFixedHeight(30)
            b.setStyleSheet(self._small_btn_style())
        sel_all.clicked.connect(lambda: self._set_all_check(self.tree_restore, True))
        sel_none.clicked.connect(lambda: self._set_all_check(self.tree_restore, False))
        head.addWidget(sel_all)
        head.addWidget(sel_none)
        lay.addLayout(head)

        self.tree_restore = self._session_tree()
        lay.addWidget(self.tree_restore, 1)

        self.lbl_rs_count = QLabel("共 0 个对话")
        self.lbl_rs_count.setStyleSheet("QLabel { color:#666; font-size:11px; background:transparent; }")
        lay.addWidget(self.lbl_rs_count)

        btn = QPushButton("恢复所选对话")
        btn.setFixedHeight(42)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._primary_btn_style("#a18cd1", "#fbc2eb"))
        btn.clicked.connect(self.on_restore)
        lay.addWidget(btn)

        self.progress_restore = self._make_progress()
        lay.addWidget(self.progress_restore)
        self.log_box_restore = self._make_log()
        lay.addWidget(self.log_box_restore)
        return w

    # ─────────── 数据加载 ───────────
    def load_local_sessions(self):
        try:
            rows = scan_local_sessions(self.engine.wb_dir)
            ws_paths = scan_workspace_map(os.path.join(self.engine.wb_dir, 'workbuddy.db'))
            self._fill_tree(self.tree_backup, rows, ws_paths)
            self.lbl_bk_count.setText(f"共 {len(rows)} 个对话（默认全选）")
            self.log(f"已扫描本机对话：{len(rows)} 个")
        except Exception as e:
            logging.error(f"扫描本机会话失败: {e}")
            self.log(f"[错误] 扫描本机会话失败: {e}")

    def refresh_zip_list(self):
        """自动搜索默认备份目录下的所有备份包，按时间倒序填入下拉框并自动加载最新的一个。"""
        combo = getattr(self, 'zip_combo', None)
        if combo is None:
            return
        folder = self.engine.get_default_backup_folder()
        zips = []
        if os.path.isdir(folder):
            try:
                zips = [os.path.join(folder, f) for f in os.listdir(folder)
                        if f.lower().endswith('.zip')]
                zips.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            except Exception as e:
                logging.warning(f"搜索备份包失败: {e}")
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("浏览其他备份包…")
        combo.setItemData(0, "__browse__")
        for z in zips:
            combo.addItem(f"{os.path.basename(z)}", userData=z)
        combo.blockSignals(False)
        if zips:
            combo.setCurrentIndex(1)  # 自动加载最新备份包
            self.load_backup_zip(zips[0])
        else:
            combo.setCurrentIndex(0)
            self.lbl_zip.setText(
                f"未在 {folder} 找到备份包；可下拉选择「浏览其他备份包…」手动指定。")
            self.tree_restore.clear()
            self.lbl_rs_count.setText("共 0 个对话")

    def on_zip_selected(self, index):
        if index <= 0:
            if index == 0 and self.zip_combo.itemData(0) == "__browse__":
                self.on_pick_zip()
            return
        zip_path = self.zip_combo.itemData(index)
        if zip_path:
            self.load_backup_zip(str(zip_path))

    def load_backup_zip(self, zip_path):
        self.restore_zip = zip_path
        self.lbl_zip.setText(zip_path)
        try:
            rows = scan_backup_sessions(zip_path)
            ws_paths = self._scan_backup_ws_map(zip_path)
            self._fill_tree(self.tree_restore, rows, ws_paths)
            self.lbl_rs_count.setText(f"共 {len(rows)} 个对话（默认全选）")
            self.log(f"已读取备份包：{os.path.basename(zip_path)}，含 {len(rows)} 个对话")
        except Exception as e:
            logging.error(f"读取备份包失败: {e}")
            AppDialog.show_error(self, "读取失败", f"无法读取该备份包：\n{e}")

    def _scan_backup_ws_map(self, zip_path):
        """从备份 zip 的 workbuddy.db 读取登记空间路径集合。"""
        tmp = tempfile.mkdtemp(prefix="wb_wsmap_")
        paths = set()
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                db_member = None
                for n in zf.namelist():
                    if n.endswith('/workbuddy.db') or n == 'workbuddy.db':
                        db_member = n
                        break
                if db_member:
                    zf.extract(db_member, tmp)
                    wb_dir = os.path.dirname(os.path.join(tmp, db_member))
                    paths = scan_workspace_map(os.path.join(wb_dir, 'workbuddy.db'))
        except Exception as e:
            logging.warning(f"读取备份包空间名失败: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return paths

    def on_pick_zip(self):
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "选择 WorkBuddy 备份包",
            self.engine.get_default_backup_folder(),
            "ZIP 文件 (*.zip)"
        )
        if not zip_path:
            # 取消选择：恢复下拉框到当前备份包状态
            self.refresh_zip_list()
            return
        # 若所选包在默认目录内，直接选中对应项；否则塞进下拉框
        idx = self.zip_combo.findData(zip_path)
        if idx < 0:
            self.zip_combo.blockSignals(True)
            self.zip_combo.addItem(os.path.basename(zip_path), userData=zip_path)
            idx = self.zip_combo.count() - 1
            self.zip_combo.blockSignals(False)
        self.zip_combo.setCurrentIndex(idx)
        self.load_backup_zip(zip_path)

    def _cur_progress(self):
        return self.progress_restore if getattr(self, '_current_page', 0) == 1 else self.progress_backup

    def _cur_log(self):
        return self.log_box_restore if getattr(self, '_current_page', 0) == 1 else self.log_box_backup

    def _detect_edge(self, pos):
        m = self.RESIZE_MARGIN
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        on_left = x < m
        on_right = x > w - m
        on_top = y < m
        on_bottom = y > h - m
        parts = []
        if on_top: parts.append("top")
        if on_bottom: parts.append("bottom")
        if on_left: parts.append("left")
        if on_right: parts.append("right")
        return "_".join(parts) if parts else None

    _CURSOR_MAP = {
        "left": Qt.CursorShape.SizeHorCursor,
        "right": Qt.CursorShape.SizeHorCursor,
        "top": Qt.CursorShape.SizeVerCursor,
        "bottom": Qt.CursorShape.SizeVerCursor,
        "top_left": Qt.CursorShape.SizeFDiagCursor,
        "bottom_right": Qt.CursorShape.SizeFDiagCursor,
        "top_right": Qt.CursorShape.SizeBDiagCursor,
        "bottom_left": Qt.CursorShape.SizeBDiagCursor,
    }

    def _apply_edge_cursor(self, edge):
        if edge and edge in self._CURSOR_MAP:
            self.setCursor(self._CURSOR_MAP[edge])
        else:
            self.unsetCursor()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._detect_edge(event.position().toPoint())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
            else:
                self.dragging = True
                self.drag_start = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._resizing:
            self._do_resize(event.globalPosition().toPoint())
        elif self.dragging:
            movement = event.position().toPoint() - self.drag_start
            self.move(self.pos() + movement)
        else:
            edge = self._detect_edge(event.position().toPoint())
            self._apply_edge_cursor(edge)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resizing:
                self._resizing = False
                self._resize_edge = None
                save_window_size(self.width(), self.height())
            self.dragging = False

    def _do_resize(self, global_pos):
        delta = global_pos - self._resize_start_pos
        geom = QRect(self._resize_start_geom)
        edge = self._resize_edge
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        if "left" in edge:
            new_left = self._resize_start_geom.left() + delta.x()
            if new_left > geom.right() - min_w + 1:
                new_left = geom.right() - min_w + 1
            geom.setLeft(new_left)
        if "right" in edge:
            new_right = self._resize_start_geom.right() + delta.x()
            if new_right < geom.left() + min_w - 1:
                new_right = geom.left() + min_w - 1
            geom.setRight(new_right)
        if "top" in edge:
            new_top = self._resize_start_geom.top() + delta.y()
            if new_top > geom.bottom() - min_h + 1:
                new_top = geom.bottom() - min_h + 1
            geom.setTop(new_top)
        if "bottom" in edge:
            new_bottom = self._resize_start_geom.bottom() + delta.y()
            if new_bottom < geom.top() + min_h - 1:
                new_bottom = geom.top() + min_h - 1
            geom.setBottom(new_bottom)
        self.setGeometry(geom)

    def closeEvent(self, event):
        save_window_size(self.width(), self.height())
        super().closeEvent(event)

    def refresh_background(self):
        if self.gradient_frame:
            self.gradient_frame.update()

    def show_confirm_dialog(self):
        try:
            dialog = ConfirmDialog(self)
            dialog.exec()
        except Exception as e:
            logging.error(f"显示确认对话框错误: {e}")
            QApplication.quit()

    def hide_to_tray(self):
        if self.tray_icon:
            self.hide()
            self.tray_icon.showMessage(
                "WorkBuddy一键备份",
                "程序已最小化到系统托盘",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self.showMinimized()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def exit_application(self):
        save_window_size(self.width(), self.height())
        if self.tray_icon:
            self.tray_icon.hide()
        QApplication.quit()

    def show_settings(self):
        try:
            dialog = BackupSettingsDialog(self)
            dialog.settings_saved.connect(self.reload_config)
            dialog.exec()
        except Exception as e:
            logging.error(f"显示设置对话框错误: {e}")

    def reload_config(self):
        self.cfg = load_backup_config()
        self.engine = BackupEngine(self.cfg)
        self.lbl_wb.setText(f"WorkBuddy数据: {self.engine.wb_dir}")
        self.lbl_ws.setText(f"项目空间: {self.engine.ws_root}")
        self.lbl_save.setText(f"默认保存: {self.engine.get_default_backup_folder()}")
        self.log(f"设置已更新，默认保存位置: {self.engine.get_default_backup_folder()}")

    def log(self, msg):
        box = self._cur_log()
        box.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        box.verticalScrollBar().setValue(box.verticalScrollBar().maximum())

    def on_progress(self, current, total):
        p = self._cur_progress()
        if total > 0:
            p.setValue(min(100, int(current * 100 / total)))
        else:
            p.setValue(0)

    def on_worker_done(self, ok, msg):
        p = self._cur_progress()
        p.setValue(100 if ok else 0)
        if ok:
            self.log(f"[完成] {msg}")
            AppDialog.show_success(self, "完成", msg)
        else:
            self.log(f"[失败] {msg}")
            AppDialog.show_error(self, "失败", msg)
        self.worker = None

    def on_backup(self):
        if self.worker and self.worker.isRunning():
            AppDialog.show_warning(self, "进行中", "请等待当前任务完成")
            return
        if not os.path.isdir(self.engine.wb_dir) and not os.path.isdir(self.engine.ws_root):
            AppDialog.show_error(
                self, "路径错误",
                f"未找到 WorkBuddy 数据目录：\n{self.engine.wb_dir}\n{self.engine.ws_root}\n\n"
                f"请在「设置」中检查数据路径是否正确。"
            )
            return
        ids = self._checked_ids(self.tree_backup)
        ws = self._ws_names_for(self.tree_backup)
        if not ids:
            AppDialog.show_warning(self, "未选择对话", "请至少勾选一个要备份的对话。")
            return
        if is_workbuddy_running():
            cont = AppDialog.ask_question(
                self, "WorkBuddy 正在运行",
                "检测到 WorkBuddy 正在运行，部分文件可能被占用而跳过。\n\n"
                "建议先完全关闭 WorkBuddy 再备份。\n\n是否仍要继续备份？",
                ok_text="继续备份", cancel_text="取消"
            )
            if not cont:
                return
        folder = self.engine.get_default_backup_folder()
        os.makedirs(folder, exist_ok=True)
        out_path = self.engine.get_next_backup_path()
        tip = f"将备份 {len(ids)} 个对话"
        if ws:
            tip += f"、{len(ws)} 个项目空间"
        tip += f"\n\n输出文件：\n{out_path}\n\n（对话索引与配置会完整备份）\n\n是否继续？"
        if not AppDialog.ask_question(self, "确认备份", tip, ok_text="开始备份", cancel_text="取消"):
            return
        self.progress_backup.setValue(0)
        self.log_box_backup.clear()
        self.log("准备备份...")
        self.worker = BackupWorker("backup", self.engine, out_path, ids, ws)
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.done_signal.connect(self.on_worker_done)
        self.worker.start()

    def on_restore(self):
        if self.worker and self.worker.isRunning():
            AppDialog.show_warning(self, "进行中", "请等待当前任务完成")
            return
        if is_workbuddy_running():
            AppDialog.show_error(
                self, "WorkBuddy 正在运行",
                "检测到 WorkBuddy 正在运行，恢复会写入其数据并可能导致损坏。\n\n"
                "请先完全关闭 WorkBuddy，再执行恢复。"
            )
            return
        zip_path = getattr(self, 'restore_zip', '')
        if not zip_path or not os.path.exists(zip_path):
            AppDialog.show_warning(self, "未选择备份包",
                                   "请先点击「选择备份包」，选择一个之前备份的 zip 文件。")
            return
        ids = self._checked_ids(self.tree_restore)
        if not ids:
            AppDialog.show_warning(self, "未选择对话", "请至少勾选一个要恢复的对话。")
            return
        ws = self._ws_names_for(self.tree_restore)
        tip = f"将从备份包恢复 {len(ids)} 个对话"
        if ws:
            tip += f" 及关联的 {len(ws)} 个项目空间"
        tip += "。\n\n当前数据表会自动备份为 .bak 文件，恢复后请重启 WorkBuddy。\n\n是否继续？"
        if not AppDialog.ask_question(self, "确认恢复", tip, ok_text="开始恢复", cancel_text="取消"):
            return
        self.progress_restore.setValue(0)
        self.log_box_restore.clear()
        self.log("准备恢复...")
        self.worker = BackupWorker("restore", self.engine, zip_path, ids, ws)
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.on_progress)
        self.worker.done_signal.connect(self.on_worker_done)
        self.worker.start()


def save_window_size(width, height):
    global WINDOW_WIDTH, WINDOW_HEIGHT
    WINDOW_WIDTH = max(600, width)
    WINDOW_HEIGHT = max(450, height)
    save_config()


def install_chinese_translator(app: QApplication):
    translator = QTranslator()
    loaded = False
    translations_path = ""
    try:
        translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load("qt_zh_CN", translations_path):
            app.installTranslator(translator)
            loaded = True
    except Exception:
        pass
    if not loaded and translations_path:
        try:
            locale = QLocale(QLocale.Language.Chinese, QLocale.Country.China)
            if translator.load(locale, "qt", "_", translations_path):
                app.installTranslator(translator)
                loaded = True
        except Exception:
            pass
    if not loaded:
        try:
            import PyQt6
            pyqt_dir = os.path.dirname(PyQt6.__file__)
            search_paths = [
                os.path.join(pyqt_dir, "Qt6", "translations"),
                os.path.join(pyqt_dir, "Qt", "translations"),
                os.path.join(os.path.dirname(pyqt_dir), "PyQt6-Qt6", "translations"),
            ]
            for spath in search_paths:
                qm_file = os.path.join(spath, "qt_zh_CN.qm")
                if os.path.exists(qm_file):
                    if translator.load(qm_file):
                        app.installTranslator(translator)
                        loaded = True
                        break
        except Exception:
            pass
    if not loaded:
        logging.warning("未能加载 Qt 中文翻译文件，颜色对话框可能显示英文")


def main():
    try:
        load_config()
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        # 全局禁用焦点虚线框 + 浅色 tooltip（防止系统深色主题弹出黑色提示框）
        app.setStyleSheet("""
            * { outline: none; }
            QPushButton:focus, QCheckBox:focus, QComboBox:focus {
                outline: none; border: none;
            }
            QToolTip {
                background-color: #ffffff; color: #333333;
                border: 1px solid rgba(0,0,0,80); border-radius: 4px;
                padding: 3px 6px; font-size: 11px;
            }
        """)
        install_chinese_translator(app)
        font = QFont()
        font.setFamily("Microsoft YaHei")
        app.setFont(font)
        window = TransparentMacWindow()
        window.show()
        QApplication.processEvents()
        # 主窗口就绪后立即关闭启动画面（onefile 打包时有 splash，脚本模式无此模块）
        try:
            import pyi_splash
            pyi_splash.close()
        except Exception:
            pass
        sys.exit(app.exec())
    except Exception as e:
        logging.error(f"程序崩溃: {e}", exc_info=True)
        AppDialog.show_error(None, "错误", f"程序发生错误：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
