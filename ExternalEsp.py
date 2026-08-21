

import sys
import math
import struct
import re
import requests
import pymem
import pymem.process

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui     import QPainter, QPen, QColor, QFont, QFontMetrics, QBrush
from PyQt6.QtCore    import Qt, QTimer, QPointF, QRectF

import win32api
import win32con
import win32gui

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────

MAX_DIST_M      = 120.0
POLL_MS         = 8

C_BOX_VIS       = QColor(0,   255,  80,  220)
C_BOX_HID       = QColor(255,  50,  50,  220)
C_SKELETON      = QColor(255, 255, 255, 170)

# ── HP bar
HPBAR_W         = 3      
HPBAR_GAP       = 3    
C_HP_BG         = QColor(30,  30,  30,  180) 
C_HP_FILL       = QColor(60,  220,  80,  230)  


FONT_DIST_SIZE  = 8      
C_DIST_TEXT     = QColor(255, 255, 255, 255)
C_DIST_SHADOW   = QColor(0,   0,   0,   180)   

BOX_THICKNESS   = 2
SKEL_THICKNESS  = 2
CORNER_BOX      = True

SKEL_PAIRS = [
    (7, 6), (6, 23), (23, 1),           
    (23, 8), (8, 9), (9, 10), (10, 11), 
    (23, 12), (12, 13), (13, 14), (14, 15), 
    (1, 17), (17, 18), (18, 19),        
    (1, 20), (20, 21), (21, 22)  
]
NEEDED_BONES = frozenset(b for pair in SKEL_PAIRS for b in pair)


# ─────────────────────────────────────────────
#  FETCH OFFSETS
# ─────────────────────────────────────────────

def fetch_offsets() -> dict | None:
    base = "https://raw.githubusercontent.com/a2x/cs2-dumper/refs/heads/main/output"
    try:
        global_off = requests.get(f"{base}/offsets.json",   timeout=5).json()
        client_hpp = requests.get(f"{base}/client_dll.hpp", timeout=5).text
    except requests.RequestException as e:
        print(f"[OFFSET] fetch failed: {e}")
        return None

    member_off = {
        name: int(val, 16)
        for name, val in re.findall(
            r'constexpr\s+std::ptrdiff_t\s+(\w+)\s*=\s*(0x[0-9A-Fa-f]+);',
            client_hpp
        )
    }
    merged = {**global_off.get("client.dll", {}), **member_off}
    merged.setdefault("m_entitySpottedState", 0x22A8)
    merged.setdefault("m_bSpotted",           0x8)
    print(f"[OFFSET] loaded {len(merged)} entries")
    return merged


# ─────────────────────────────────────────────
#  ATTACH
# ─────────────────────────────────────────────

def attach_to_cs2():
    try:
        pm     = pymem.Pymem("cs2.exe")
        client = pymem.process.module_from_name(
            pm.process_handle, "client.dll"
        ).lpBaseOfDll
        print(f"[ATTACH] client.dll @ 0x{client:X}")
        return pm, client
    except pymem.exception.ProcessNotFound:
        print("[ATTACH] cs2.exe not found")
        sys.exit(1)
    except pymem.exception.ModuleNotFound:
        print("[ATTACH] client.dll not found")
        sys.exit(1)


# ─────────────────────────────────────────────
#  MATHS
# ─────────────────────────────────────────────

def world_to_screen(
    mtx: tuple,
    pos: tuple,
    sw:  int,
    sh:  int
) -> QPointF | None:
    x, y, z = pos
    w = mtx[12]*x + mtx[13]*y + mtx[14]*z + mtx[15]
    if w < 0.001:
        return None
    inv_w = 1.0 / w
    nx = (mtx[0]*x + mtx[1]*y + mtx[2]*z + mtx[3])  * inv_w
    ny = (mtx[4]*x + mtx[5]*y + mtx[6]*z + mtx[7])  * inv_w
    return QPointF((sw / 2.0) * (1.0 + nx), (sh / 2.0) * (1.0 - ny))


# ─────────────────────────────────────────────
#  SNAPSHOT
# ─────────────────────────────────────────────

class PawnSnapshot:
    __slots__ = ("head_s", "foot_s", "bones_s", "is_visible", "dist_m", "health")

    def __init__(self, head_s, foot_s, bones_s, is_visible, dist_m, health):
        self.head_s     = head_s
        self.foot_s     = foot_s
        self.bones_s    = bones_s
        self.is_visible = is_visible
        self.dist_m     = dist_m
        self.health     = health  


# ─────────────────────────────────────────────
#  READER
# ─────────────────────────────────────────────

def read_bone_positions(pm, b_ptr, v_mtx, sw, sh) -> dict:
    if not b_ptr:
        return {}
    max_bone = max(NEEDED_BONES) + 1
    try:
        raw = pm.read_bytes(b_ptr, max_bone * 32)
    except Exception:
        return {}
    bones = {}
    for bone_id in NEEDED_BONES:
        off = bone_id * 32
        try:
            bx, by, bz = struct.unpack_from("fff", raw, off)
        except struct.error:
            continue
        pt = world_to_screen(v_mtx, (bx, by, bz), sw, sh)
        if pt is not None:
            bones[bone_id] = pt
    return bones


def read_entity_list(pm, client, offsets, v_mtx, local_pawn, l_pos, sw, sh):
    snapshots = []
    try:
        ent_list = pm.read_longlong(client + offsets["dwEntityList"])
    except Exception:
        return snapshots

    for i in range(1, 64):
        try:
            chunk      = pm.read_longlong(ent_list + 0x8 * (i >> 9) + 0x10)
            if not chunk: continue
            controller = pm.read_longlong(chunk + 0x70 * (i & 0x1FF))
            if not controller: continue

            pawn_handle = pm.read_uint(controller + offsets["m_hPlayerPawn"])
            pawn_chunk  = pm.read_longlong(
                ent_list + 0x8 * ((pawn_handle & 0x7FFF) >> 9) + 0x10
            )
            pawn = pm.read_longlong(pawn_chunk + 0x70 * (pawn_handle & 0x1FF))
            if not pawn or pawn == local_pawn: continue

            health = pm.read_int(pawn + offsets["m_iHealth"])
            if health <= 0: continue

            ex, ey, ez = struct.unpack(
                "fff", pm.read_bytes(pawn + offsets["m_vOldOrigin"], 12)
            )
            lx, ly, _ = l_pos
            dist_m = math.hypot(lx - ex, ly - ey) / 39.37
            if dist_m > MAX_DIST_M: continue

            gs    = pm.read_longlong(pawn + offsets["m_pGameSceneNode"])
            b_ptr = pm.read_longlong(gs   + offsets["m_modelState"] + 0x80)
            bones = read_bone_positions(pm, b_ptr, v_mtx, sw, sh)

            head_s = world_to_screen(v_mtx, (ex, ey, ez + 72.0), sw, sh)
            foot_s = world_to_screen(v_mtx, (ex, ey, ez),        sw, sh)
            if head_s is None or foot_s is None: continue

            is_vis = pm.read_bool(
                pawn + offsets["m_entitySpottedState"] + offsets["m_bSpotted"]
            )

            snapshots.append(PawnSnapshot(
                head_s=head_s, foot_s=foot_s, bones_s=bones,
                is_visible=is_vis, dist_m=round(dist_m, 1),
                health=max(0, min(100, health))
            ))
        except Exception:
            continue

    return snapshots


# ─────────────────────────────────────────────
#  DRAW HELPERS
# ─────────────────────────────────────────────

def _box_rect(head: QPointF, foot: QPointF) -> QRectF | None:
    """Calcule le QRectF de la box à partir de head/foot screen coords."""
    h = foot.y() - head.y()
    if h < 4:
        return None
    w = h / 2.0
    return QRectF(head.x() - w / 2.0, head.y(), w, h)


def draw_full_box(p: QPainter, rect: QRectF, color: QColor):
    p.setPen(QPen(color, BOX_THICKNESS))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(rect)


def draw_corner_box(p: QPainter, rect: QRectF, color: QColor):
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    cx, cy = w * 0.25, h * 0.25
    pen = QPen(color, BOX_THICKNESS + 1)
    p.setPen(pen)
    p.drawLine(QPointF(x,   y),   QPointF(x+cx, y))
    p.drawLine(QPointF(x,   y),   QPointF(x,    y+cy))
    p.drawLine(QPointF(x+w, y),   QPointF(x+w-cx,y))
    p.drawLine(QPointF(x+w, y),   QPointF(x+w,  y+cy))
    p.drawLine(QPointF(x,   y+h), QPointF(x+cx, y+h))
    p.drawLine(QPointF(x,   y+h), QPointF(x,    y+h-cy))
    p.drawLine(QPointF(x+w, y+h), QPointF(x+w-cx,y+h))
    p.drawLine(QPointF(x+w, y+h), QPointF(x+w,  y+h-cy))


def draw_skeleton(p: QPainter, bones: dict):
    p.setPen(QPen(C_SKELETON, SKEL_THICKNESS))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for a, b in SKEL_PAIRS:
        if a in bones and b in bones:
            p.drawLine(bones[a], bones[b])


def draw_health_bar(p: QPainter, rect: QRectF, health: int):

    x      = rect.x()
    y_top  = rect.bottom() + HPBAR_GAP
    w      = rect.width()
    h      = float(HPBAR_W)


    bg_rect = QRectF(x, y_top, w, h)
    p.setPen(QPen(QColor(0, 0, 0, 220), 1))
    p.setBrush(QBrush(C_HP_BG))
    p.drawRect(bg_rect)

    fill_w = max(0.0, (health / 100.0) * w)
    if fill_w > 0:
        fill_rect = QRectF(x, y_top, fill_w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(C_HP_FILL))
        p.drawRect(fill_rect)


def draw_dist_label(
    p:      QPainter,
    rect:   QRectF,
    dist_m: float,
    fm:     QFontMetrics
):

    txt  = f"{dist_m}m"
    tx   = int(rect.x())

    ty   = int(rect.y()) - 2 


    p.setPen(QPen(C_DIST_SHADOW, 1))
    p.drawText(tx + 1, ty + 1, txt)


    p.setPen(QPen(C_DIST_TEXT, 1))
    p.drawText(tx, ty, txt)


# ─────────────────────────────────────────────
#  OVERLAY
# ─────────────────────────────────────────────

class ESP(QMainWindow):

    def __init__(self, pm, client, offsets):
        super().__init__()
        self.pm      = pm
        self.client  = client
        self.offsets = offsets

        self.sw = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        self.sh = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint   |
            Qt.WindowType.WindowStaysOnTopHint  |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(0, 0, self.sw, self.sh)

        self._font = QFont("Consolas", FONT_DIST_SIZE, QFont.Weight.Bold)
        self._fm   = QFontMetrics(self._font)

        self.render_data: list[PawnSnapshot] = []

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._logic_loop)
        self.timer.start(POLL_MS)
        print(f"[ESP] {self.sw}×{self.sh} — poll {POLL_MS}ms")

    def _apply_win32_flags(self):
        hwnd = int(self.winId())
        win32gui.SetWindowLong(
            hwnd, win32con.GWL_EXSTYLE,
            win32con.WS_EX_LAYERED     |
            win32con.WS_EX_TRANSPARENT |
            win32con.WS_EX_TOPMOST     |
            win32con.WS_EX_TOOLWINDOW
        )

    def _logic_loop(self):
        self._apply_win32_flags()

        hwnd_cs2 = win32gui.FindWindow(None, "Counter-Strike 2")
        if win32gui.GetForegroundWindow() != hwnd_cs2:
            self.render_data = []
            self.update()
            return

        try:
            v_mtx = struct.unpack(
                "f" * 16,
                self.pm.read_bytes(self.client + self.offsets["dwViewMatrix"], 64)
            )
            local_pawn = self.pm.read_longlong(
                self.client + self.offsets["dwLocalPlayerPawn"]
            )
            l_pos = struct.unpack(
                "fff",
                self.pm.read_bytes(local_pawn + self.offsets["m_vOldOrigin"], 12)
            )
        except Exception:
            self.render_data = []
            self.update()
            return

        self.render_data = read_entity_list(
            self.pm, self.client, self.offsets,
            v_mtx, local_pawn, l_pos,
            self.sw, self.sh
        )
        self.update()

    def paintEvent(self, _event):
        if not self.render_data:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setFont(self._font)  
        for snap in self.render_data:
            rect = _box_rect(snap.head_s, snap.foot_s)
            if rect is None:
                continue

            color = C_BOX_VIS if snap.is_visible else C_BOX_HID

            if CORNER_BOX:
                draw_corner_box(p, rect, color)
            else:
                draw_full_box(p, rect, color)


            draw_skeleton(p, snap.bones_s)


            draw_health_bar(p, rect, snap.health)

            draw_dist_label(p, rect, snap.dist_m, self._fm)

        p.end()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

def main():
    offsets = fetch_offsets()
    if offsets is None:
        print("[FATAL] offsets unavailable")
        sys.exit(1)

    pm, client = attach_to_cs2()

    app     = QApplication(sys.argv)
    overlay = ESP(pm, client, offsets)
    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()