import numpy as np
import cv2
import os
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                             QFrame, QGridLayout, QLabel, QTextEdit, QSizePolicy, QSlider)
from PyQt6.QtCore import Qt, pyqtSlot, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QImage, QPixmap, QFont, QBrush, QIcon
from core.data_link import DataReceiver
from core.sync_engine import SyncEngine
from config import PORT_VIDEO, PORT_THERMAL

# === 翻译字典 ===
TRANS = {
    "EN": {
        "title": "ELL-4D Reconstruction Terminal",
        "btn_start": "SYSTEM START",
        "btn_stop": "SYSTEM HALT",
        "mode_locked": "MODE: LOCKED",
        "mode_adjust": "MODE: ADJUST",
        "check": "CHECKER PATTERN",
        "rot": "ROTATION",
        "scale": "SCALE (X)",
        "fine": "FINE TUNE",
        "lang": "LANG: EN",
        "hud_main": "FUSION OPTIC",
        "hud_sub1": "THERMAL SENSOR",
        "hud_sub2": "EVENT TRACKER"
    },
    "CN": {
        "title": "极弱光4D重建终端",
        "btn_start": "系统启动",
        "btn_stop": "系统终止",
        "mode_locked": "模式: 锁定",
        "mode_adjust": "模式: 校准",
        "check": "棋盘对比",
        "rot": "旋转修正",
        "scale": "缩放调整",
        "fine": "精细微调",
        "lang": "语言: 中文",
        "hud_main": "融合主视野",
        "hud_sub1": "热成像传感器",
        "hud_sub2": "事件流传感器"
    }
}

SLIDER_STYLE = """
QSlider::groove:horizontal { border: 1px solid #004400; height: 8px; background: #001100; margin: 2px 0; }
QSlider::handle:horizontal { background: #00ff00; border: 1px solid #00ff00; width: 18px; height: 18px; margin: -6px 0; border-radius: 2px; }
"""


class HUDDisplay(QLabel):
    clicked = pyqtSignal(str)
    dragged = pyqtSignal(int, int)

    def __init__(self, name_key, color_hex, is_main=False, offline_text="NO SIGNAL"):
        super().__init__()
        self.name_key = name_key
        self.display_name = name_key
        self.color = QColor(color_hex)
        self.is_main = is_main
        self.offline_text = offline_text

        self.setMinimumSize(320, 240)
        self.setStyleSheet("background-color: #050505;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.info = {}
        self.raw_thermal = None
        self.hover_temp = None
        self.last_mouse = None
        self.content_type = "NONE"

        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_display_name(self, name):
        self.display_name = name
        self.update()

    def update_frame(self, cv_img, content_type, info=None, raw_t=None):
        self.content_type = content_type
        if info: self.info = info
        if raw_t is not None: self.raw_thermal = raw_t

        if cv_img is None: return
        if cv_img.shape[0] == 0 or cv_img.shape[1] == 0: return

        if not cv_img.flags['C_CONTIGUOUS']: cv_img = np.ascontiguousarray(cv_img)
        h, w = cv_img.shape[:2]
        if len(cv_img.shape) == 2:
            fmt = QImage.Format.Format_Grayscale8; bpl = w
        else:
            fmt = QImage.Format.Format_RGB888
            cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            if not cv_img.flags['C_CONTIGUOUS']: cv_img = np.ascontiguousarray(cv_img)
            bpl = cv_img.strides[0]
        q_img = QImage(cv_img.data, w, h, bpl, fmt)
        self.setPixmap(QPixmap.fromImage(q_img).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.FastTransformation))
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.last_mouse = e.pos()
            self.clicked.emit(self.name_key)

    def mouseMoveEvent(self, e):
        self.last_mouse_pos_for_paint = e.pos()

        if self.content_type == "THERMAL" and self.raw_thermal is not None and self.pixmap():
            pix = self.pixmap()
            off_x = (self.width() - pix.width()) // 2
            off_y = (self.height() - pix.height()) // 2
            x = e.pos().x() - off_x;
            y = e.pos().y() - off_y
            if 0 <= x < pix.width() and 0 <= y < pix.height():
                h_r, w_r = self.raw_thermal.shape
                rx = int((x / pix.width()) * w_r);
                ry = int((y / pix.height()) * h_r)
                if 0 <= rx < w_r and 0 <= ry < h_r:
                    val = self.raw_thermal[ry, rx]
                    self.hover_temp = float(val) / 64.0 - 273.15
        else:
            self.hover_temp = None

        if self.content_type == "FUSION" and self.last_mouse is not None:
            delta = e.pos() - self.last_mouse
            self.last_mouse = e.pos()
            scale_factor = 1280 / self.width()
            self.dragged.emit(int(delta.x() * scale_factor), int(delta.y() * scale_factor))
        self.update()

    def mouseReleaseEvent(self, e):
        self.last_mouse = None

    def paintEvent(self, event):
        p = QPainter(self);
        p.fillRect(self.rect(), QColor(0, 0, 0))

        if self.pixmap() and not self.pixmap().isNull() and self.pixmap().width() > 10:
            pix = self.pixmap()
            x = (self.width() - pix.width()) // 2
            y = (self.height() - pix.height()) // 2
            p.drawPixmap(x, y, pix)

            pen = QPen(self.color);
            pen.setWidth(3 if self.is_main else 2);
            p.setPen(pen)
            r = QRect(x, y, pix.width(), pix.height()).adjusted(0, 0, -1, -1);
            l = 20
            p.drawLine(r.left(), r.top(), r.left() + l, r.top());
            p.drawLine(r.left(), r.top(), r.left(), r.top() + l)
            p.drawLine(r.right(), r.top(), r.right() - l, r.top());
            p.drawLine(r.right(), r.top(), r.right(), r.top() + l)
            p.drawLine(r.right(), r.bottom(), r.right() - l, r.bottom());
            p.drawLine(r.right(), r.bottom(), r.right(), r.bottom() - l)
            p.drawLine(r.left(), r.bottom(), r.left() + l, r.bottom());
            p.drawLine(r.left(), r.bottom(), r.left(), r.bottom() - l)

            p.setPen(QColor(255, 255, 255));
            p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            p.drawText(r.left() + 5, r.top() + 18, self.display_name)

            # 温度跟随 (半透明HUD风格)
            if self.hover_temp is not None and hasattr(self, 'last_mouse_pos_for_paint'):
                mx = self.last_mouse_pos_for_paint.x()
                my = self.last_mouse_pos_for_paint.y()
                t_str = f"{self.hover_temp:.1f}C"

                bg_rect = QRect(mx + 15, my - 25, 60, 20)
                p.fillRect(bg_rect, QColor(0, 0, 0, 180))
                p.setPen(QColor(0, 255, 0));
                p.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
                p.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, t_str)
        else:
            p.setPen(QColor(80, 80, 80));
            p.setFont(QFont("Consolas", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.offline_text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cur_lang = "EN"
        if os.path.exists("images/logo.ico"): self.setWindowIcon(QIcon("images/logo.ico"))
        self.setWindowTitle(TRANS[self.cur_lang]["title"])
        self.resize(1600, 900)
        self.setStyleSheet(
            "QMainWindow { background: #080808; } QLabel { color: #0f0; font-family: Consolas; } QTextEdit { background: #000; border: 1px solid #333; color: #0f0; }")

        self.win_state = {"hud_main": "FUSION", "hud_sub1": "THERMAL", "hud_sub2": "EVENT"}
        self.align_controls = []
        self.init_ui()
        self.update_ui_text()

    def init_ui(self):
        base = QWidget();
        self.setCentralWidget(base)
        layout = QHBoxLayout(base);
        layout.setContentsMargins(10, 10, 10, 10);
        layout.setSpacing(10)

        self.hud_main = HUDDisplay("hud_main", "#00ff00", True, offline_text="SYSTEM OFFLINE")
        self.hud_main.clicked.connect(self.handle_swap)
        self.hud_main.dragged.connect(self.handle_drag)

        right_panel = QWidget();
        r_lay = QVBoxLayout(right_panel);
        r_lay.setContentsMargins(0, 0, 0, 0)
        self.hud_sub1 = HUDDisplay("hud_sub1", "#ff5500", False, offline_text="USB1 DISCONNECTED")
        self.hud_sub1.clicked.connect(self.handle_swap)
        self.hud_sub2 = HUDDisplay("hud_sub2", "#00ffff", False, offline_text="USB2 DISCONNECTED")
        self.hud_sub2.clicked.connect(self.handle_swap)

        self.align_frame = QFrame();
        self.align_frame.setStyleSheet("border:1px solid #004400; background:transparent;")
        ag = QGridLayout(self.align_frame);
        ag.setSpacing(10);
        ag.setContentsMargins(10, 10, 10, 10)

        self.btn_mode = QPushButton("MODE")
        self.btn_mode.setStyleSheet("background:#112211; color:#0f0; padding:6px; border:1px solid #050;")
        self.btn_mode.clicked.connect(self.toggle_mode);
        self.btn_mode.setEnabled(False)

        self.btn_check = QPushButton("CHECK")
        self.btn_check.setStyleSheet("background:#112211; color:#0f0; padding:6px; border:1px solid #050;")
        self.btn_check.clicked.connect(self.toggle_checker);
        self.btn_check.setEnabled(False)

        self.btn_lang = QPushButton("LANG")
        self.btn_lang.setStyleSheet("background:#001133; color:#0ff; padding:6px; border:1px solid #005577;")
        self.btn_lang.clicked.connect(self.toggle_lang)

        ag.addWidget(self.btn_mode, 0, 0);
        ag.addWidget(self.btn_check, 0, 1);
        ag.addWidget(self.btn_lang, 0, 2)

        self.lbl_rot = QLabel("ROT");
        self.sld_rot = QSlider(Qt.Orientation.Horizontal)
        self.sld_rot.setRange(-20, 20);
        self.sld_rot.setStyleSheet(SLIDER_STYLE)
        self.sld_rot.valueChanged.connect(lambda v: self.eng.update_align_params(set_angle=v))
        ag.addWidget(self.lbl_rot, 1, 0);
        ag.addWidget(self.sld_rot, 1, 1, 1, 2)

        self.lbl_sc = QLabel("SCALE");
        self.sld_sc = QSlider(Qt.Orientation.Horizontal)
        self.sld_sc.setRange(5, 50);
        self.sld_sc.setValue(25);
        self.sld_sc.setStyleSheet(SLIDER_STYLE)
        self.sld_sc.valueChanged.connect(lambda v: self.eng.update_align_params(set_scale=v / 10.0))
        ag.addWidget(self.lbl_sc, 2, 0);
        ag.addWidget(self.sld_sc, 2, 1, 1, 2)

        self.lbl_sf = QLabel("FINE");
        self.sld_sf = QSlider(Qt.Orientation.Horizontal)
        self.sld_sf.setRange(-20, 20);
        self.sld_sf.setValue(0);
        self.sld_sf.setStyleSheet(SLIDER_STYLE)
        ag.addWidget(self.lbl_sf, 3, 0);
        ag.addWidget(self.sld_sf, 3, 1, 1, 2)

        self.align_controls = [self.lbl_rot, self.sld_rot, self.lbl_sc, self.sld_sc, self.lbl_sf, self.sld_sf,
                               self.btn_check]
        self.set_align_visible(False)

        self.log_v = QTextEdit();
        self.log_v.setReadOnly(True);
        self.log_v.setFixedHeight(80)
        self.btn_start = QPushButton("START")
        self.btn_start.setStyleSheet("background: #003300; border: 1px solid #0f0; font-size:14px; padding:10px;")
        self.btn_start.clicked.connect(self.start)

        r_lay.addWidget(self.hud_sub1, 3);
        r_lay.addWidget(self.hud_sub2, 3)
        r_lay.addWidget(self.align_frame, 0);
        r_lay.addWidget(self.log_v, 1);
        r_lay.addWidget(self.btn_start, 0)
        layout.addWidget(self.hud_main, 70);
        layout.addWidget(right_panel, 30)

    def toggle_lang(self):
        self.cur_lang = "CN" if self.cur_lang == "EN" else "EN"
        self.update_ui_text();
        self.log(f"Language switched to {self.cur_lang}")

    def update_ui_text(self):
        t = TRANS[self.cur_lang]
        self.setWindowTitle(t["title"])
        if hasattr(self, 'eng') and self.eng.isRunning():
            self.btn_start.setText(t["btn_stop"])
        else:
            self.btn_start.setText(t["btn_start"])
        if "ADJUST" in self.btn_mode.text() or "校准" in self.btn_mode.text():
            self.btn_mode.setText(t["mode_adjust"])
        else:
            self.btn_mode.setText(t["mode_locked"])
        self.btn_check.setText(t["check"]);
        self.btn_lang.setText(t["lang"])
        self.lbl_rot.setText(t["rot"]);
        self.lbl_sc.setText(t["scale"]);
        self.lbl_sf.setText(t["fine"])
        for hud in [self.hud_main, self.hud_sub1, self.hud_sub2]: hud.set_display_name(
            t.get(hud.name_key, hud.name_key))

    def set_align_visible(self, vis):
        for w in self.align_controls: w.setVisible(vis)

    def log(self, m):
        self.log_v.append(f"> {m}")

    def start(self):
        from collections import deque
        self.qv = deque(maxlen=2);
        self.qt = deque(maxlen=2)
        self.th_v = DataReceiver(PORT_VIDEO, self.qv, "video");
        self.th_v.start()
        self.th_t = DataReceiver(PORT_THERMAL, self.qt, "thermal");
        self.th_t.start()
        self.eng = SyncEngine(self.qv, self.qt)
        self.eng.update_signal.connect(self.update_displays);
        self.eng.log_signal.connect(self.log)
        self.eng.start()
        self.btn_start.setDisabled(True);
        self.btn_mode.setEnabled(True)
        # === 核心修复：按钮解锁 ===
        self.btn_check.setEnabled(True)

        t = TRANS[self.cur_lang]
        self.eng.set_mode("ADJUST");
        self.btn_mode.setText(t["mode_adjust"]);
        self.set_align_visible(True);
        self.btn_start.setText(t["btn_stop"])

    def toggle_mode(self):
        t = TRANS[self.cur_lang]
        is_adj = "ADJUST" in self.btn_mode.text() or "校准" in self.btn_mode.text()
        if is_adj:
            nm, txt = "LOCKED", t["mode_locked"]; self.set_align_visible(False)
        else:
            nm, txt = "ADJUST", t["mode_adjust"]; self.set_align_visible(True)
        self.btn_mode.setText(txt);
        self.eng.set_mode(nm)

    def toggle_checker(self):
        self.eng.update_align_params(toggle_checker=True)

    def handle_drag(self, dx, dy):
        is_adj = "ADJUST" in self.btn_mode.text() or "校准" in self.btn_mode.text()
        if self.win_state["hud_main"] == "FUSION" and is_adj: self.eng.update_align_params(dx=dx, dy=dy)

    def handle_swap(self, clicked_key):
        if clicked_key == "hud_main": return
        c_clk = self.win_state[clicked_key];
        c_main = self.win_state["hud_main"]
        self.win_state["hud_main"] = c_clk;
        self.win_state[clicked_key] = c_main
        self.log(f"SWAP: MAIN shows {c_clk}");
        self.update_ui_text()

    @pyqtSlot(np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict)
    def update_displays(self, fus, raw_therm, raw_evt, raw_data, info):
        content_map = {"FUSION": (fus, None), "THERMAL": (raw_therm, raw_data), "EVENT": (raw_evt, None)}
        for hud, key in [(self.hud_main, "hud_main"), (self.hud_sub1, "hud_sub1"), (self.hud_sub2, "hud_sub2")]:
            c_type = self.win_state[key]
            img, data = content_map[c_type]
            hud.update_frame(img, c_type, info, data)

    def closeEvent(self, e):
        try:
            self.eng.stop(); self.th_v.stop(); self.th_t.stop()
        except:
            pass