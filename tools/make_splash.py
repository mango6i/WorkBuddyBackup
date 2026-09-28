# -*- coding: utf-8 -*-
"""生成 PyInstaller 启动画面 splash.png（与程序风格一致的渐变 + 图标）"""
import io
import os

from PyQt6.QtCore import QBuffer, QRectF, QPointF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QIcon)
from PyQt6.QtWidgets import QApplication
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 440, 240
OUT = os.path.join(HERE, "splash.png")


def draw(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), 58 * s, 58 * s)
    p.setClipPath(path)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0.0, QColor("#4facfe"))
    g.setColorAt(1.0, QColor("#00c6fb"))
    p.fillPath(path, QBrush(g))
    pen = QPen(QColor(255, 255, 255, 255), 22 * s, Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    cx = size / 2.0
    p.drawLine(QPointF(cx, 62 * s), QPointF(cx, 128 * s))
    p.drawLine(QPointF(cx - 36 * s, 98 * s), QPointF(cx, 138 * s))
    p.drawLine(QPointF(cx, 138 * s), QPointF(cx + 36 * s, 98 * s))
    p.drawLine(QPointF(cx - 56 * s, 182 * s), QPointF(cx + 56 * s, 182 * s))
    p.end()
    return pm


def main():
    app = QApplication([])
    canvas = QPixmap(W, H)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # 背景：圆角渐变
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, W, H), 18, 18)
    p.setClipPath(path)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0.0, QColor("#dff1ff"))
    g.setColorAt(1.0, QColor("#eef6ff"))
    p.fillPath(path, QBrush(g))
    # 图标
    icon_pm = draw(112)
    p.drawPixmap(int(W / 2 - 56), 24, icon_pm)
    # 标题
    p.setPen(QPen(QColor(40, 60, 80), 1))
    f = QFont("Microsoft YaHei", 13)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 152, W, 28), Qt.AlignmentFlag.AlignCenter,
               "WorkBuddy 一键备份")
    f2 = QFont("Microsoft YaHei", 9)
    f2.setBold(False)
    p.setFont(f2)
    p.setPen(QPen(QColor(130, 140, 155), 1))
    p.drawText(QRectF(0, 182, W, 24), Qt.AlignmentFlag.AlignCenter, "正在启动，请稍候…")
    p.end()

    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    canvas.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    Image.open(io.BytesIO(data)).convert("RGBA").save(OUT, format="PNG")
    print("splash 已生成:", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
