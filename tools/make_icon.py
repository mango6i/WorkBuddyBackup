# -*- coding: utf-8 -*-
"""生成 WorkBuddy一键备份 的程序图标 WorkBuddyBackup.ico
风格与界面一致：蓝青渐变圆角方块 + 白色下载(备份)箭头 + 托盘线。
"""
import io
import os
import sys

from PyQt6.QtCore import QBuffer, QRectF, QPointF, Qt
from PyQt6.QtGui import (QBrush, QColor, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QIcon)
from PyQt6.QtWidgets import QApplication
from PIL import Image

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WorkBuddyBackup.ico")


def render(size: int) -> Image.Image:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0

    # 背景圆角方块（渐变 #4facfe -> #00c6fb，与界面按钮一致）
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 58 * s, 58 * s)
    p.setClipPath(path)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0.0, QColor("#4facfe"))
    g.setColorAt(1.0, QColor("#00c6fb"))
    p.fillPath(path, QBrush(g))

    # 白色向下箭头 + 底部托盘线（备份/保存含义）
    pen = QPen(QColor(255, 255, 255, 255), 22 * s,
               Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    cx = size / 2.0
    # 箭杆
    p.drawLine(QPointF(cx, 62 * s), QPointF(cx, 128 * s))
    # 箭头
    p.drawLine(QPointF(cx - 36 * s, 98 * s), QPointF(cx, 138 * s))
    p.drawLine(QPointF(cx, 138 * s), QPointF(cx + 36 * s, 98 * s))
    # 托盘
    p.drawLine(QPointF(cx - 56 * s, 182 * s), QPointF(cx + 56 * s, 182 * s))
    p.end()

    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return Image.open(io.BytesIO(data)).convert("RGBA")


def main():
    app = QApplication(sys.argv)
    base = render(256)
    base.save(OUT, format="ICO",
              sizes=[(s, s) for s in SIZES])
    # 顺带导出 256px PNG，供托盘/窗口加载使用
    base.save(os.path.join(os.path.dirname(OUT), "WorkBuddyBackup_icon.png"), format="PNG")
    print("ICO 已生成:", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
