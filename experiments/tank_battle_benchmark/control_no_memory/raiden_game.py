#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雷电（Raiden）纵向卷轴射击 复刻版 —— 单文件 pygame 实现

功能:
  1. 纵向卷轴宇宙背景（三层视差星空 + 可无缝滚动星云 + 行星）
  2. 6 种敌方战机：侦察机 / 波动机 / 炮台机 / 重型轰炸机 / 俯冲蜂 / 狙击机
     每种都有独立的移动轨迹与弹幕样式
  3. 第一关关底 Boss：三阶段复合弹幕 + 顶部血条 + 死亡爆炸演出
  4. 三种升级弹药：黄色机枪(Vulcan) / 跟踪导弹(Homing) / 直线激光(Laser)
  5. 核心升级规则：同种升级箱连吃 3 颗升满(1→2→3)；
     吃到异种升级箱会切换弹药种类并回到该种弹药的 1 级档位
  6. 只做第一关，击败 Boss 即通关
  7. `python3 raiden_game.py --test` 执行无界面(headless)自检

操作: 方向键/WASD 移动，空格/J 开火（按住连射），P 暂停，R 重开，ESC 退出
"""

import math
import os
import random
import sys

# ------------------------------------------------------------------
# headless 支持：必须在 import pygame 之前设置 SDL 驱动
# ------------------------------------------------------------------
_TEST_MODE = "--test" in sys.argv or os.environ.get("RAIDEN_HEADLESS") == "1"
if _TEST_MODE:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

# ------------------------------------------------------------------
# 常量
# ------------------------------------------------------------------
WIDTH, HEIGHT = 480, 720
FPS = 60

PLAYER_SPEED = 4.7
PLAYER_HIT_R = 5.0          # 玩家判定核心很小（雷电系列传统）
PLAYER_START_LIVES = 3
RESPAWN_INVULN = int(2.0 * FPS)

WEAPON_TYPES = ("mg", "missile", "laser")
MAX_WEAPON_LEVEL = 3
WEAPON_TEXT = {
    "mg": ("黄色机枪", "Vulcan"),
    "missile": ("跟踪导弹", "Homing"),
    "laser": ("直线激光", "Laser"),
}
WEAPON_COLOR = {
    "mg": (255, 214, 64),
    "missile": (120, 235, 140),
    "laser": (120, 195, 255),
}

BOSS_TIME = 72.0            # 第一关固定时长（秒），之后 Boss 进场
BOSS_MAX_HP = 560

MISSION_TEXT = "STAGE 1  ·  雷 神 作 战"


def L(zh, en):
    """中文字体不可用时回退英文。"""
    return zh if FONTS_OK else en


FONTS_OK = False
_FONT_CACHE = {}


# ------------------------------------------------------------------
# 字体
# ------------------------------------------------------------------
def load_fonts():
    """挑选系统中文字体；找不到就回退默认字体并置 FONTS_OK=False。"""
    global FONTS_OK
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/msyh.ttc",
    ]
    pygame.font.init()
    for path in candidates:
        if os.path.exists(path):
            try:
                f = pygame.font.Font(path, 18)
                if f.render("雷", True, (255, 255, 255)).get_width() > 4:
                    FONTS_OK = True
                    return path
            except Exception:
                continue
    FONTS_OK = False
    return None


def font(size, bold=False):
    key = (size, bold)
    if key not in _FONT_CACHE:
        path = _FONT_PATH
        f = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
        f.set_bold(bold)
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


_FONT_PATH = None


def text(surface, s, x, y, size=18, color=(255, 255, 255), center=False,
         bold=False, shadow=True):
    f = font(size, bold)
    if shadow:
        sh = f.render(s, True, (0, 0, 0))
        r = sh.get_rect()
        if center:
            r.center = (x + 1, y + 1)
        else:
            r.topleft = (x + 1, y + 1)
        surface.blit(sh, r)
    img = f.render(s, True, color)
    r = img.get_rect()
    if center:
        r.center = (x, y)
    else:
        r.topleft = (x, y)
    surface.blit(img, r)
    return r


# ------------------------------------------------------------------
# 数学工具
# ------------------------------------------------------------------
def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def angle_to(x1, y1, x2, y2):
    """返回角度（度），0=右，90=下。"""
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def vel_from_angle(ang, speed):
    r = math.radians(ang)
    return math.cos(r) * speed, math.sin(r) * speed


def dist2(x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    return dx * dx + dy * dy


def circles_hit(x1, y1, r1, x2, y2, r2):
    rr = r1 + r2
    return dist2(x1, y1, x2, y2) <= rr * rr


# ------------------------------------------------------------------
# 卷轴宇宙背景
# ------------------------------------------------------------------
class Starfield:
    """三层视差星空 + 无缝滚动的星云 + 缓慢下移的行星。"""

    def __init__(self, rng):
        self.rng = rng
        self.layers = []
        specs = [
            (70, 0.55, 1, (96, 104, 150)),
            (46, 1.35, 2, (150, 160, 205)),
            (22, 2.60, 2, (232, 236, 255)),
        ]
        for count, speed, size, color in specs:
            stars = []
            for _ in range(count):
                stars.append([
                    rng.uniform(0, WIDTH),
                    rng.uniform(0, HEIGHT),
                    speed * rng.uniform(0.85, 1.15),
                    size + (rng.random() < 0.15),
                    color,
                ])
            self.layers.append(stars)

        self.planets = []
        for _ in range(2):
            self.planets.append([
                rng.uniform(60, WIDTH - 60),
                rng.uniform(-HEIGHT, HEIGHT),
                rng.uniform(28, 52),
                rng.uniform(0.35, 0.7),
                rng.choice([(58, 78, 140), (120, 70, 130), (60, 120, 130)]),
            ])

        self.nebula_scroll = 0.0
        self.nebula_surf = None
        self._nebula_rng = random.Random(rng.randrange(1 << 30))
        self.total_scroll = 0.0

    # ------------------------------------------------------------
    def _build_nebula(self):
        """生成可垂直无缝拼接的星云贴图。

        注意：这里必须用普通 alpha 混合而不是 BLEND_ADD——pygame 的
        BLEND_ADD 会把源 RGB 原样相加（不受 alpha 影响），多团星云叠加后
        整屏会爆成全白。
        """
        w, h = WIDTH, HEIGHT
        surf = pygame.Surface((w, h)).convert()
        surf.fill((6, 8, 22))
        rng = self._nebula_rng
        blobs = []
        for _ in range(9):
            blobs.append((rng.uniform(0, w), rng.uniform(0, h),
                          rng.uniform(70, 190), rng.choice(
                              [(40, 30, 90), (70, 26, 80), (18, 50, 96),
                               (30, 20, 70)])))
        for bx, by, br, col in blobs:
            for oy in (-h, 0, h):            # 上下各画一份 → 可无缝平铺
                for ring in range(11, 0, -1):
                    r = int(br * ring / 11.0)
                    if r <= 0:
                        continue
                    a = int(3 + 16 * (1.0 - ring / 12.0))
                    s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                    pygame.draw.circle(s, (col[0], col[1], col[2], a), (r, r), r)
                    surf.blit(s, (int(bx - r), int(by + oy - r)))
        self.nebula_surf = surf

    # ------------------------------------------------------------
    def update(self, dt_frames=1.0):
        for layer in self.layers:
            for s in layer:
                s[1] += s[2] * dt_frames
                if s[1] > HEIGHT:
                    s[1] -= HEIGHT + self.rng.uniform(0, 40)
                    s[0] = self.rng.uniform(0, WIDTH)
                elif s[1] < -4:
                    s[1] += HEIGHT
        for p in self.planets:
            p[1] += p[3] * dt_frames
            if p[1] - p[2] > HEIGHT:
                p[1] = -p[2] - self.rng.uniform(40, 320)
                p[0] = self.rng.uniform(60, WIDTH - 60)
                p[3] = self.rng.uniform(0.35, 0.7)
        self.nebula_scroll = (self.nebula_scroll + 0.30 * dt_frames) % HEIGHT
        self.total_scroll += 0.30 * dt_frames

    # ------------------------------------------------------------
    def draw(self, surface):
        if self.nebula_surf is None:
            self._build_nebula()
        off = int(self.nebula_scroll)
        surface.blit(self.nebula_surf, (0, off))
        surface.blit(self.nebula_surf, (0, off - HEIGHT))

        for p in self.planets:
            x, y, r, _, col = p
            if -r * 2 < y < HEIGHT + r * 2:
                pygame.draw.circle(surface, (col[0] // 3, col[1] // 3, col[2] // 3),
                                   (int(x), int(y)), int(r))
                pygame.draw.circle(surface, col, (int(x - r * 0.25), int(y - r * 0.25)),
                                   int(r * 0.82))
                pygame.draw.circle(surface, (col[0] + 40, col[1] + 40, col[2] + 40),
                                   (int(x - r * 0.35), int(y - r * 0.35)), max(2, int(r * 0.34)))

        for layer in self.layers:
            for x, y, _, size, color in layer:
                if size <= 1:
                    surface.set_at((int(x) % WIDTH, int(y) % HEIGHT), color)
                else:
                    pygame.draw.rect(surface, color,
                                     (int(x) % WIDTH, int(y) % HEIGHT,
                                      int(size), int(size) + 1))


# ------------------------------------------------------------------
# 爆炸
# ------------------------------------------------------------------
class Explosion:
    def __init__(self, x, y, radius=26, duration=24, color=(255, 190, 80), small=False):
        self.x, self.y = x, y
        self.radius = radius
        self.duration = duration
        self.t = 0
        self.small = small
        self.color = color
        self.alive = True
        self.seed = random.randrange(1000)

    def update(self):
        self.t += 1
        if self.t >= self.duration:
            self.alive = False

    def draw(self, surface):
        k = self.t / float(self.duration)
        r = self.radius * (0.35 + 0.9 * k)
        a = int(220 * (1.0 - k))
        if a <= 0:
            return
        s = pygame.Surface((int(r * 2) + 2, int(r * 2) + 2), pygame.SRCALPHA)
        cx = cy = s.get_width() // 2
        pygame.draw.circle(s, (255, 255, 220, a), (cx, cy), max(1, int(r * 0.45)))
        pygame.draw.circle(s, self.color + (max(0, a - 40),), (cx, cy), max(1, int(r * 0.8)), 3)
        pygame.draw.circle(s, (255, 120, 40, max(0, a - 100)), (cx, cy), max(1, int(r)), 2)
        surface.blit(s, (int(self.x - cx), int(self.y - cy)))


# ------------------------------------------------------------------
# 子弹
# ------------------------------------------------------------------
class PlayerBullet:
    """玩家子弹：机枪弹 / 跟踪导弹。"""

    def __init__(self, x, y, ang, speed, damage, kind, color, size=4,
                 homing=False, turn=0.13):
        self.x, self.y = x, y
        self.ang = ang
        self.vx, self.vy = vel_from_angle(ang, speed)
        self.speed = speed
        self.damage = damage
        self.kind = kind
        self.color = color
        self.r = size
        self.homing = homing
        self.turn = turn
        self.alive = True
        self.age = 0

    def update(self, game):
        self.age += 1
        if self.homing:
            target = game.nearest_enemy(self.x, self.y)
            if target is not None:
                want = angle_to(self.x, self.y, target.x, target.y)
                diff = (want - self.ang + 180.0) % 360.0 - 180.0
                step = clamp(diff, -self.turn * 57.2958, self.turn * 57.2958)
                self.ang += step
                self.vx, self.vy = vel_from_angle(self.ang, self.speed)
        self.x += self.vx
        self.y += self.vy
        if (self.y < -24 or self.y > HEIGHT + 24 or
                self.x < -24 or self.x > WIDTH + 24 or self.age > 480):
            self.alive = False

    def draw(self, surface):
        if self.kind == "missile":
            tail = (self.x - self.vx * 1.6, self.y - self.vy * 1.6)
            pygame.draw.line(surface, (255, 170, 60), (self.x, self.y), tail, 2)
            pygame.draw.circle(surface, (245, 245, 245), (int(self.x), int(self.y)), int(self.r))
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), max(1, int(self.r) - 2))
        else:
            pygame.draw.ellipse(surface, (255, 255, 255),
                                (self.x - self.r * 0.6, self.y - self.r * 1.5,
                                 self.r * 1.2, self.r * 3.0))
            pygame.draw.ellipse(surface, self.color,
                                (self.x - self.r * 0.35, self.y - self.r * 1.1,
                                 self.r * 0.7, self.r * 2.2))


class EnemyBullet:
    def __init__(self, x, y, ang, speed, r=5.0, color=(255, 110, 110),
                 damage=1, accel=0.0, curve=0.0, life=900):
        self.x, self.y = x, y
        self.ang = ang
        self.speed = speed
        self.vx, self.vy = vel_from_angle(ang, speed)
        self.r = r
        self.color = color
        self.damage = damage
        self.accel = accel
        self.curve = curve
        self.life = life
        self.alive = True
        self.age = 0

    def update(self):
        self.age += 1
        if self.curve:
            self.ang += self.curve
            self.vx, self.vy = vel_from_angle(self.ang, self.speed)
        if self.accel:
            self.speed += self.accel
            ux, uy = vel_from_angle(self.ang, 1.0)
            self.vx, self.vy = ux * self.speed, uy * self.speed
        self.x += self.vx
        self.y += self.vy
        if (self.age > self.life or self.y < -30 or self.y > HEIGHT + 30 or
                self.x < -30 or self.x > WIDTH + 30):
            self.alive = False

    def draw(self, surface):
        r = int(self.r)
        pygame.draw.circle(surface, (20, 10, 30), (int(self.x), int(self.y)), r + 1)
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), r)
        pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), max(1, r - 2))


class LaserBeam:
    """玩家的直线激光：贯穿一切目标，按帧结算伤害。"""

    def __init__(self, x, y_top, y_bottom, width, dps):
        self.x = x
        self.y_top = y_top
        self.y_bottom = y_bottom
        self.width = width
        self.dps = dps
        self.flicker = 0

    def update(self):
        self.flicker += 1

    @property
    def left(self):
        return self.x - self.width * 0.5

    @property
    def right(self):
        return self.x + self.width * 0.5

    def hits(self, ex, ey, er):
        if ey + er < self.y_top or ey - er > self.y_bottom:
            return False
        return (ex + er) >= self.left and (ex - er) <= self.right

    def damage_per_frame(self):
        return self.dps / float(FPS)

    def draw(self, surface):
        w = self.width
        a = 40 + int(18 * math.sin(self.flicker * 0.9))
        glow = pygame.Surface((int(w * 3.0) + 4, int(self.y_bottom - self.y_top) + 4),
                              pygame.SRCALPHA)
        glow.fill((90, 170, 255, max(20, a)))
        surface.blit(glow, (int(self.x - w * 1.5), int(self.y_top)),
                     special_flags=pygame.BLEND_ADD)
        pygame.draw.rect(surface, (150, 210, 255),
                         (int(self.x - w * 0.5), int(self.y_top), int(w),
                          int(self.y_bottom - self.y_top)))
        pygame.draw.rect(surface, (255, 255, 255),
                         (int(self.x - w * 0.22), int(self.y_top), max(2, int(w * 0.44)),
                          int(self.y_bottom - self.y_top)))


# ------------------------------------------------------------------
# 武器系统（三种弹药 × 三级）
# ------------------------------------------------------------------
def weapon_plan(kind, level):
    """
    返回 (冷却帧数, 子弹参数列表)。
    子弹参数: dict(ang, offset, dmg, speed, homing)
    """
    level = int(clamp(level, 1, MAX_WEAPON_LEVEL))
    if kind == "mg":
        if level == 1:
            return 7, [dict(ang=0, offset=-6, dmg=1, speed=13.0),
                       dict(ang=0, offset=6, dmg=1, speed=13.0)]
        if level == 2:
            return 7, [dict(ang=0, offset=0, dmg=1, speed=13.5),
                       dict(ang=-7, offset=-9, dmg=1, speed=13.0),
                       dict(ang=7, offset=9, dmg=1, speed=13.0)]
        return 8, [dict(ang=0, offset=0, dmg=1, speed=14.0),
                   dict(ang=-11, offset=-8, dmg=1, speed=13.5),
                   dict(ang=11, offset=8, dmg=1, speed=13.5),
                   dict(ang=-23, offset=-14, dmg=1, speed=12.5),
                   dict(ang=23, offset=14, dmg=1, speed=12.5)]
    if kind == "missile":
        if level == 1:
            return 20, [dict(ang=-90, offset=0, dmg=4, speed=7.5, homing=True)]
        if level == 2:
            return 22, [dict(ang=-90, offset=-11, dmg=4, speed=7.5, homing=True),
                        dict(ang=-90, offset=11, dmg=4, speed=7.5, homing=True)]
        return 24, [dict(ang=-90, offset=-15, dmg=4, speed=8.0, homing=True),
                    dict(ang=-90, offset=-5, dmg=4, speed=8.0, homing=True),
                    dict(ang=-90, offset=5, dmg=4, speed=8.0, homing=True),
                    dict(ang=-90, offset=15, dmg=4, speed=8.0, homing=True)]
    if kind == "laser":
        # 激光虽然持续命中、无视闪避，但单发伤害仍需与机枪同量级，
        # 否则玩家吃到激光会从 17dps 直接倒回 0.6dps（开局就输的负体验）
        table = {1: (9.0, 15.0), 2: (17.0, 26.0), 3: (27.0, 38.0)}
        w, dps = table[level]
        return 0, [dict(beam=True, width=w, dps=dps)]
    raise ValueError("未知弹药种类: %r" % (kind,))


def weapon_dps(kind, level):
    """粗略的每秒伤害，用于平衡与测试。"""
    cool, plan = weapon_plan(kind, level)
    if kind == "laser":
        return plan[0]["dps"]
    per = sum(p["dmg"] for p in plan) * FPS / float(max(1, cool))
    return per


# ------------------------------------------------------------------
# 玩家
# ------------------------------------------------------------------
class Player:
    def __init__(self, x=None, y=None, lives=PLAYER_START_LIVES):
        self.x = WIDTH * 0.5 if x is None else x
        self.y = HEIGHT - 90 if y is None else y
        self.hit_r = PLAYER_HIT_R
        self.lives = lives
        self.alive = True
        self.invincible = RESPAWN_INVULN
        self.weapon = "mg"
        self.weapon_level = 1
        self.bombs = 2
        self.bomb_cool = 0
        self.fire_cool = 0
        self.firing = False
        self.flame = 0.0
        self.tilt = 0.0
        self.powerup_flash = 0

    # ------------------------------------------------------------
    @property
    def r(self):
        return self.hit_r

    def reset_position(self):
        self.x = WIDTH * 0.5
        self.y = HEIGHT - 90

    # ------------------------------------------------------------
    def update(self, game, inp):
        if not self.alive:
            return
        if self.invincible > 0:
            self.invincible -= 1
        if self.powerup_flash > 0:
            self.powerup_flash -= 1
        if self.bomb_cool > 0:
            self.bomb_cool -= 1

        dx = clamp(inp.dx, -1.0, 1.0)
        dy = clamp(inp.dy, -1.0, 1.0)
        if dx and dy:
            dx *= 0.7071
            dy *= 0.7071
        self.x = clamp(self.x + dx * PLAYER_SPEED, 14, WIDTH - 14)
        self.y = clamp(self.y + dy * PLAYER_SPEED, 40, HEIGHT - 18)
        self.tilt += (dx * 0.35 - self.tilt) * 0.25
        self.flame = (self.flame + 0.6) % 1000.0

        if inp.bomb and self.bombs > 0 and self.bomb_cool <= 0:
            self.use_bomb(game)

        self.firing = bool(inp.fire)
        if self.fire_cool > 0:
            self.fire_cool -= 1
        if self.firing and self.fire_cool <= 0:
            self.fire(game)

    def use_bomb(self, game):
        """释放保险炸弹：清屏消弹、全场敌机重创、震屏爆炸。"""
        if self.bombs <= 0 or self.bomb_cool > 0:
            return False
        self.bombs -= 1
        self.bomb_cool = int(0.9 * FPS)
        game.clear_enemy_bullets()
        game.add_explosion(WIDTH * 0.5, HEIGHT * 0.5, 200, 40, (255, 230, 120))
        game.add_explosion(self.x, self.y, 90, 30, (255, 255, 200))
        for e in game.enemies:
            if e.alive:
                e.hit(game, 24.0)
        if game.boss is not None and game.boss.alive and not game.boss.entering:
            game.boss.hit(game, 60.0)
        game.stats["bombs_used"] = game.stats.get("bombs_used", 0) + 1
        return True

    # ------------------------------------------------------------
    def fire(self, game):
        cool, plan = weapon_plan(self.weapon, self.weapon_level)
        if plan and plan[0].get("beam"):
            self.fire_cool = 1
            game.set_laser(self)
            return
        self.fire_cool = cool
        for spec in plan:
            bx = self.x + spec["offset"]
            by = self.y - 14
            if spec.get("homing"):
                b = PlayerBullet(bx, by, spec["ang"], spec["speed"], spec["dmg"],
                                 "missile", WEAPON_COLOR["missile"], size=5,
                                 homing=True, turn=0.135)
            else:
                b = PlayerBullet(bx, by, -90 + spec["ang"], spec["speed"], spec["dmg"],
                                 "mg", WEAPON_COLOR["mg"], size=3 + self.weapon_level // 2)
            game.pbullets.append(b)
        game.stats["shots"] += len(plan)

    # ------------------------------------------------------------
    def pickup(self, game, kind):
        """核心升级规则：同种 3 连满级；异种切换种类并回到 1 级。"""
        if kind not in WEAPON_TYPES:
            raise ValueError("未知升级箱: %r" % (kind,))
        if kind == self.weapon:
            if self.weapon_level < MAX_WEAPON_LEVEL:
                self.weapon_level += 1
                game.stats["upgrades"] += 1
                game.add_score(500)
        else:
            self.weapon = kind
            self.weapon_level = 1
            game.stats["switches"] += 1
            game.add_score(200)
        self.powerup_flash = int(0.45 * FPS)
        return self.weapon, self.weapon_level

    # ------------------------------------------------------------
    def hit(self, game):
        if not self.alive or self.invincible > 0:
            return False
        self.lives -= 1
        self.weapon = "mg"
        self.weapon_level = 1
        game.stats["deaths"] += 1
        game.add_explosion(self.x, self.y, 46, 34, (255, 170, 70))
        game.clear_enemy_bullets()
        game.player_laser = None
        if self.lives <= 0:
            self.alive = False
            game.state = "game_over"
        else:
            self.invincible = RESPAWN_INVULN
            self.reset_position()
        return True

    # ------------------------------------------------------------
    def draw(self, surface):
        if not self.alive:
            return
        if self.invincible > 0 and (self.invincible // 4) % 2 == 0:
            return                                    # 无敌闪烁
        x, y = self.x, self.y
        tilt = self.tilt
        # 尾焰
        fl = 8 + int(4 * math.sin(self.flame))
        pygame.draw.polygon(surface, (255, 160, 40),
                            [(x - 5, y + 12), (x + 5, y + 12), (x, y + 12 + fl)])
        pygame.draw.polygon(surface, (255, 240, 170),
                            [(x - 2.5, y + 12), (x + 2.5, y + 12), (x, y + 10 + fl * 0.6)])
        # 机翼
        pygame.draw.polygon(surface, (70, 130, 210),
                            [(x - 16 + tilt * 6, y + 6), (x + 16 + tilt * 6, y + 6),
                             (x + 9 + tilt * 3, y - 2), (x - 9 + tilt * 3, y - 2)])
        pygame.draw.polygon(surface, (110, 190, 255),
                            [(x - 13, y + 2), (x + 13, y + 2), (x + 6, y - 6), (x - 6, y - 6)])
        # 机身
        pygame.draw.polygon(surface, (215, 235, 255),
                            [(x, y - 20), (x + 7, y + 4), (x + 4, y + 12),
                             (x - 4, y + 12), (x - 7, y + 4)])
        pygame.draw.polygon(surface, (60, 110, 190),
                            [(x, y - 16), (x + 3.5, y + 3), (x - 3.5, y + 3)])
        # 核心（判定点）
        pygame.draw.circle(surface, (60, 255, 220), (int(x), int(y)), 3)
        if self.invincible > 0:
            rr = 20 + int(2 * math.sin(self.flame * 2))
            pygame.draw.circle(surface, (120, 230, 255), (int(x), int(y)), rr, 2)


# ------------------------------------------------------------------
# 敌方战机
# ------------------------------------------------------------------
ENEMY_TYPES = {
    "scout": dict(
        hp=3, r=12, score=100, speed=2.7, color=(232, 96, 84),
        fire_cd=(78, 118), drop=0.10,
        name=("侦察机", "Scout"),
        desc=("直线俯冲", "Straight dive"),
    ),
    "wave": dict(
        hp=5, r=14, score=160, speed=1.25, color=(110, 200, 250),
        fire_cd=(96, 150), drop=0.14,
        name=("波动机", "Weaver"),
        desc=("正弦横摆 + 三向散射", "Sine weave + 3-way"),
    ),
    "gunner": dict(
        hp=9, r=16, score=220, speed=1.5, color=(242, 192, 88),
        fire_cd=(64, 100), drop=0.30,
        name=("炮台机", "Gunner"),
        desc=("下降到阵位后横向巡航 + 瞄准连射", "Hold line + aimed burst"),
    ),
    "bomber": dict(
        hp=20, r=23, score=420, speed=0.85, color=(172, 124, 232),
        fire_cd=(112, 160), drop=0.65,
        name=("重型轰炸机", "Bomber"),
        desc=("缓慢悬停 + 环形弹幕", "Hover + radial ring"),
    ),
    "diver": dict(
        hp=4, r=12, score=150, speed=2.2, color=(118, 232, 152),
        fire_cd=(92, 140), drop=0.12,
        name=("俯冲蜂", "Diver"),
        desc=("追踪玩家俯冲 + 五向扇形", "Homing dive + 5-way fan"),
    ),
    "sniper": dict(
        hp=7, r=14, score=260, speed=1.6, color=(250, 138, 200),
        fire_cd=(70, 104), drop=0.34,
        name=("狙击机", "Sniper"),
        desc=("高速横移 + 快速三连狙击", "Fast strafe + triple snipe"),
    ),
}


class Enemy:
    def __init__(self, x, y, kind, game=None, rng=None):
        if kind not in ENEMY_TYPES:
            raise ValueError("未知敌机类型: %r" % (kind,))
        st = ENEMY_TYPES[kind]
        self.kind = kind
        self.x, self.y = float(x), float(y)
        self.hp = float(st["hp"])
        self.max_hp = float(st["hp"])
        self.r = float(st["r"])
        self.score = st["score"]
        self.speed = st["speed"]
        self.color = st["color"]
        self.alive = True
        self.t = 0
        self.flash = 0
        self.base_x = float(x)
        self.dir = 1
        self.homing_error = None
        rng = rng or random
        lo, hi = st["fire_cd"]
        self.fire_timer = rng.randint(lo, hi) // 2
        self.burst_left = 0
        self.burst_cd = 0
        self.fire_lo, self.fire_hi = lo, hi
        self.rng = rng

    # ------------------------------------------------------------
    def update(self, game):
        if not self.alive:
            return
        self.t += 1
        if self.flash > 0:
            self.flash -= 1
        self._move(game)
        self._shoot(game)
        if (self.y > HEIGHT + 50 or self.y < -220 or
                self.x < -80 or self.x > WIDTH + 80):
            self.alive = False

    # ------------------------------------------------------------
    def _move(self, game):
        k = self.kind
        if k == "scout":
            self.y += self.speed
            self.x += 0.55 * self.dir
            if self.x < 20 or self.x > WIDTH - 20:
                self.dir *= -1
        elif k == "wave":
            self.y += self.speed
            self.x = self.base_x + 74 * math.sin(self.t * 0.042)
        elif k == "gunner":
            if self.y < 168:
                self.y += self.speed
            else:
                self.x += 1.45 * self.dir
                if self.x < 34 or self.x > WIDTH - 34:
                    self.dir *= -1
                    self.x = clamp(self.x, 34, WIDTH - 34)
        elif k == "bomber":
            if self.y < 132:
                self.y += self.speed
            else:
                self.x += 0.42 * self.dir
                self.y = 132 + 9 * math.sin(self.t * 0.026)
                if self.x < 52 or self.x > WIDTH - 52:
                    self.dir *= -1
                    self.x = clamp(self.x, 52, WIDTH - 52)
        elif k == "diver":
            if self.y < 190:
                self.y += self.speed
            else:
                if game is not None and getattr(game, "player", None) is not None:
                    want = game.player.x
                    self.x += clamp((want - self.x) * 0.075, -3.4, 3.4)
                    if self.homing_error is None:
                        self.homing_error = abs(want - self.x)
                    else:
                        self.homing_error = min(self.homing_error, abs(want - self.x))
                self.y += self.speed * 1.2
        elif k == "sniper":
            if self.y < 82:
                self.y += self.speed * 2.3
            else:
                self.x += 3.3 * self.dir
                if self.x < 30 or self.x > WIDTH - 30:
                    self.dir *= -1
                    self.x = clamp(self.x, 30, WIDTH - 30)

    # ------------------------------------------------------------
    def _shoot(self, game):
        if game is None:
            return
        if self.y < 16:      # 未进入画面不开火（避免屏外冷枪）
            return
        if self.burst_left > 0:
            self.burst_cd -= 1
            if self.burst_cd <= 0:
                self._volley(game)
                self.burst_left -= 1
                self.burst_cd = 8 if self.kind == "gunner" else 6
            return
        self.fire_timer -= 1
        if self.fire_timer <= 0:
            self.fire_timer = self.rng.randint(self.fire_lo, self.fire_hi)
            if self.kind in ("gunner", "sniper"):
                self.burst_left = 3
                self.burst_cd = 1
            else:
                self._volley(game)
            game.stats["enemy_volleys"] += 1

    # ------------------------------------------------------------
    def _volley(self, game):
        """一次齐射；(gunner/sniper 的连发中每一发都会调用)。"""
        k = self.kind
        px = game.player.x if getattr(game, "player", None) else WIDTH * 0.5
        py = game.player.y if getattr(game, "player", None) else HEIGHT
        aim = angle_to(self.x, self.y + 12, px, py)
        if k == "scout":
            game.add_enemy_bullet(self.x, self.y + 12, aim, 3.4, r=5)
        elif k == "wave":
            for d in (-20, 0, 20):
                game.add_enemy_bullet(self.x, self.y + 12, 90 + d, 3.1, r=4.5,
                                      color=(150, 220, 255))
        elif k == "gunner":
            for d in (-9, 0, 9):
                game.add_enemy_bullet(self.x, self.y + 12, aim + d, 3.7, r=5,
                                      color=(255, 200, 110))
        elif k == "bomber":
            for i in range(12):
                game.add_enemy_bullet(self.x, self.y, i * 30.0, 2.5, r=6,
                                      color=(210, 130, 255))
        elif k == "diver":
            for d in (-42, -21, 0, 21, 42):
                game.add_enemy_bullet(self.x, self.y + 10, 90 + d, 3.3, r=5,
                                      color=(140, 255, 180))
        elif k == "sniper":
            game.add_enemy_bullet(self.x, self.y + 12, aim, 6.2, r=4,
                                  color=(255, 150, 210))

    # ------------------------------------------------------------
    def hit(self, game, dmg):
        if not self.alive:
            return False
        self.hp -= dmg
        self.flash = 3
        if self.hp <= 0:
            self.alive = False
            game.add_explosion(self.x, self.y, self.r * 2.4, 26)
            game.add_score(self.score)
            game.stats["kills"] += 1
            game.stats["kills_by_type"][self.kind] = \
                game.stats["kills_by_type"].get(self.kind, 0) + 1
            game.maybe_drop_powerup(self)
            return True
        return False

    # ------------------------------------------------------------
    def draw(self, surface):
        x, y = int(self.x), int(self.y)
        col = (255, 255, 255) if self.flash > 0 else self.color
        dark = (col[0] // 2, col[1] // 2, col[2] // 2)
        k = self.kind
        if k == "scout":
            pygame.draw.polygon(surface, dark, [(x, y + 14), (x - 12, y - 10), (x + 12, y - 10)])
            pygame.draw.polygon(surface, col, [(x, y + 16), (x - 9, y - 4), (x + 9, y - 4)])
            pygame.draw.circle(surface, (255, 255, 255), (x, y + 2), 3)
        elif k == "wave":
            pygame.draw.polygon(surface, dark, [(x, y + 14), (x - 16, y), (x, y - 12), (x + 16, y)])
            pygame.draw.polygon(surface, col, [(x, y + 11), (x - 12, y), (x, y - 8), (x + 12, y)])
            pygame.draw.circle(surface, (255, 255, 255), (x, y), 4)
        elif k == "gunner":
            pygame.draw.rect(surface, dark, (x - 18, y - 10, 36, 22), border_radius=4)
            pygame.draw.rect(surface, col, (x - 15, y - 8, 30, 17), border_radius=4)
            pygame.draw.rect(surface, (60, 50, 30), (x - 9, y + 6, 5, 8))
            pygame.draw.rect(surface, (60, 50, 30), (x + 4, y + 6, 5, 8))
            pygame.draw.circle(surface, (255, 255, 255), (x, y), 5)
        elif k == "bomber":
            pygame.draw.polygon(surface, dark, [(x - 26, y - 6), (x + 26, y - 6),
                                                (x + 20, y + 12), (x - 20, y + 12)])
            pygame.draw.rect(surface, col, (x - 20, y - 14, 40, 24), border_radius=6)
            pygame.draw.polygon(surface, (90, 60, 140), [(x - 30, y - 2), (x + 30, y - 2),
                                                         (x + 20, y + 8), (x - 20, y + 8)])
            for dx in (-12, 0, 12):
                pygame.draw.circle(surface, (255, 230, 160), (x + dx, y + 12), 4)
            pygame.draw.circle(surface, (255, 255, 255), (x, y - 4), 6)
        elif k == "diver":
            pygame.draw.polygon(surface, dark, [(x, y + 16), (x - 13, y - 6), (x + 13, y - 6)])
            pygame.draw.polygon(surface, col, [(x, y + 14), (x - 9, y - 4), (x + 9, y - 4)])
            pygame.draw.polygon(surface, (255, 255, 255), [(x, y + 8), (x - 3, y), (x + 3, y)])
        else:  # sniper
            pygame.draw.polygon(surface, dark, [(x - 18, y - 8), (x + 18, y - 8),
                                                (x + 12, y + 8), (x - 12, y + 8)])
            pygame.draw.polygon(surface, col, [(x, y + 16), (x - 12, y - 6), (x + 12, y - 6)])
            pygame.draw.rect(surface, (255, 255, 255), (x - 2, y - 16, 4, 12))
            pygame.draw.circle(surface, (255, 255, 255), (x, y), 4)
        # 小血条（受伤后显示）
        if self.hp < self.max_hp:
            w = int(self.r * 2.2)
            pygame.draw.rect(surface, (30, 20, 30), (x - w // 2, y - self.r - 10, w, 4))
            pygame.draw.rect(surface, (120, 255, 120),
                             (x - w // 2, y - self.r - 10,
                              int(w * max(0.0, self.hp / self.max_hp)), 4))


# ------------------------------------------------------------------
# 道具
# ------------------------------------------------------------------
class PowerUp:
    KINDS = WEAPON_TYPES

    def __init__(self, x, y, kind, speed=1.9):
        if kind not in WEAPON_TYPES:
            raise ValueError("未知道具: %r" % (kind,))
        self.x, self.y = float(x), float(y)
        self.kind = kind
        self.speed = speed
        self.t = 0
        self.alive = True
        self.r = 12
        self.color = WEAPON_COLOR[kind]

    def update(self, game):
        self.t += 1
        if self.t < 34:                      # 出场：先横向飘出
            self.y += 0.4
            self.x += 1.1 * (1 if (self.x < WIDTH / 2) else -1)
        else:
            self.y += self.speed
        if self.y > HEIGHT + 20:
            self.alive = False

    def draw(self, surface):
        x, y = int(self.x), int(self.y)
        bob = math.sin(self.t * 0.14) * 3
        y2 = int(y + bob)
        s = pygame.Surface((34, 34), pygame.SRCALPHA)
        pygame.draw.circle(s, self.color + (55,), (17, 17), 16)
        surface.blit(s, (x - 17, y2 - 17))
        pygame.draw.rect(surface, (250, 250, 250), (x - 11, y2 - 11, 22, 22), border_radius=4)
        pygame.draw.rect(surface, self.color, (x - 9, y2 - 9, 18, 18), border_radius=3)
        letter = {"mg": "P", "missile": "M", "laser": "L"}[self.kind]
        text(surface, letter, x, y2, 16, (20, 20, 30), center=True, bold=True, shadow=False)


# ------------------------------------------------------------------
# Boss：旗舰「雷神」
# ------------------------------------------------------------------
class Boss:
    NAME = ("旗舰「雷神」", "Flagship THOR")
    PHASE_TEXT = (("第一阶段", "PHASE 1"), ("第二阶段", "PHASE 2"), ("第三阶段", "PHASE 3"))

    def __init__(self, x=None, y=-150, hp=BOSS_MAX_HP):
        self.x = WIDTH * 0.5 if x is None else float(x)
        self.y = float(y)
        self.max_hp = float(hp)
        self.hp = float(hp)
        self.r = 66.0
        self.t = 0
        self.phase = 1
        self.entering = True
        self.dying = False
        self.dying_timer = 0
        self.alive = True
        self.flash = 0
        self.attack_timer = 70
        self.ring_timer = 150
        self.spiral = 0.0
        self.aim_timer = 46
        self.phase_banner = 0
        self.rng = random.Random(20240)

    # ------------------------------------------------------------
    @property
    def hp_ratio(self):
        return max(0.0, self.hp / self.max_hp)

    def phase_for(self, ratio=None):
        if ratio is None:
            ratio = self.hp_ratio
        if ratio > 0.66:
            return 1
        if ratio > 0.33:
            return 2
        return 3

    # ------------------------------------------------------------
    def update(self, game):
        self.t += 1
        if self.flash > 0:
            self.flash -= 1
        if self.phase_banner > 0:
            self.phase_banner -= 1

        if self.dying:
            self.dying_timer -= 1
            if self.dying_timer % 5 == 0:
                ex = self.x + self.rng.uniform(-self.r, self.r)
                ey = self.y + self.rng.uniform(-self.r * 0.7, self.r * 0.7)
                game.add_explosion(ex, ey, self.rng.uniform(24, 52), 30,
                                   (255, 200, 90))
            if self.dying_timer <= 0:
                self.alive = False
                game.on_boss_dead()
            return

        if self.entering:
            self.y += 1.7
            if self.y >= 118:
                self.y = 118
                self.entering = False
                self.phase_banner = 70
            return

        # 阶段判定
        ph = self.phase_for()
        if ph != self.phase:
            self.phase = ph
            self.phase_banner = 80
            self.attack_timer = 20
            self.ring_timer = 40
            self.aim_timer = 20
            game.clear_enemy_bullets()
            game.add_explosion(self.x, self.y, 90, 30, (120, 220, 255))
            game.stats["boss_phases"] = max(game.stats.get("boss_phases", 1), ph)

        # 移动：左右扫动，阶段越高越快
        sp = {1: 0.0125, 2: 0.0185, 3: 0.026}[self.phase]
        amp = {1: 118.0, 2: 140.0, 3: 158.0}[self.phase]
        self.x = WIDTH * 0.5 + amp * math.sin(self.t * sp)
        self.y = 118 + 12 * math.sin(self.t * 0.03)

        self._attack(game)

    # ------------------------------------------------------------
    def _attack(self, game):
        px = game.player.x if getattr(game, "player", None) else WIDTH * 0.5
        py = game.player.y if getattr(game, "player", None) else HEIGHT
        aim = angle_to(self.x, self.y + 40, px, py)
        ph = self.phase
        muzzle_y = self.y + 44

        # --- 扇形 / 瞄准弹 -------------------------------------
        self.attack_timer -= 1
        if self.attack_timer <= 0:
            if ph == 1:
                self.attack_timer = 78
                for d in (-36, -24, -12, 0, 12, 24, 36):
                    game.add_enemy_bullet(self.x, muzzle_y, aim + d, 3.9, r=6,
                                          color=(255, 150, 120))
            elif ph == 2:
                self.attack_timer = 56
                for d in (-46, -30, -15, 0, 15, 30, 46):
                    game.add_enemy_bullet(self.x, muzzle_y, aim + d, 4.4, r=6,
                                          color=(255, 120, 180))
            else:
                self.attack_timer = 40
                for d in (-56, -38, -19, 0, 19, 38, 56):
                    game.add_enemy_bullet(self.x, muzzle_y, aim + d, 5.0, r=6,
                                          color=(255, 90, 140))

        # --- 环形弹幕 ------------------------------------------
        self.ring_timer -= 1
        if self.ring_timer <= 0:
            if ph == 1:
                self.ring_timer = 190
                n, spd = 14, 2.9
            elif ph == 2:
                self.ring_timer = 150
                n, spd = 20, 3.2
            else:
                self.ring_timer = 118
                n, spd = 24, 3.6
            off = self.rng.uniform(0, 360.0 / n)
            for i in range(n):
                game.add_enemy_bullet(self.x, self.y, off + i * 360.0 / n, spd, r=6,
                                      color=(190, 140, 255))

        # --- 螺旋弹幕（二阶段起）-------------------------------
        if ph >= 2:
            step = 15.0 if ph == 2 else 11.0
            arms = 2 if ph == 2 else 3
            every = 5 if ph == 2 else 4
            if self.t % every == 0:
                self.spiral = (self.spiral + step) % 360.0
                for a in range(arms):
                    game.add_enemy_bullet(self.x, self.y,
                                          self.spiral + a * (360.0 / arms),
                                          3.3 if ph == 2 else 3.9, r=5.5,
                                          color=(150, 220, 255))

        # --- 快速瞄准点射（三阶段）-----------------------------
        if ph == 3:
            self.aim_timer -= 1
            if self.aim_timer <= 0:
                self.aim_timer = 34
                for j in range(3):
                    game.add_enemy_bullet(self.x, muzzle_y, aim + (j - 1) * 7.0,
                                          7.0, r=4.5, color=(255, 255, 160))

        # --- 侧翼炮台在二阶段后追加直射 ------------------------
        if ph >= 2 and self.t % 26 == 0:
            for sx in (-52, 52):
                game.add_enemy_bullet(self.x + sx, self.y + 20, 90 + 12 * (1 if sx > 0 else -1),
                                      4.2, r=5, color=(255, 190, 120))

    # ------------------------------------------------------------
    def hit(self, game, dmg):
        if not self.alive or self.dying or self.entering:
            return False
        self.hp -= dmg
        self.flash = 2
        if self.hp <= 0:
            self.hp = 0.0
            self.start_dying(game)
            return True
        return False

    def start_dying(self, game):
        self.dying = True
        self.dying_timer = 150
        game.clear_enemy_bullets()
        game.stats["boss_killed"] = 1
        game.add_score(50000)
        game.add_explosion(self.x, self.y, 110, 40, (255, 230, 140))

    def hits(self, x, y, r):
        """命中检测：主体圆 + 两翼矩形。"""
        if circles_hit(x, y, r, self.x, self.y, self.r * 0.72):
            return True
        if abs(y - self.y - 18) < 30 and abs(x - self.x) < 74:
            return True
        return False

    # ------------------------------------------------------------
    def draw(self, surface):
        x, y = int(self.x), int(self.y)
        body = (255, 255, 255) if self.flash > 0 else (150, 168, 210)
        accent = [(90, 210, 255), (255, 160, 90), (255, 90, 120)][self.phase - 1]
        # 侧翼
        for sx in (-1, 1):
            pygame.draw.polygon(surface, (70, 78, 110), [
                (x + sx * 26, y - 26), (x + sx * 92, y + 2),
                (x + sx * 78, y + 36), (x + sx * 30, y + 30)])
            pygame.draw.polygon(surface, (110, 122, 165), [
                (x + sx * 30, y - 20), (x + sx * 82, y + 4),
                (x + sx * 70, y + 28), (x + sx * 32, y + 24)])
            pygame.draw.circle(surface, accent, (x + sx * 60, y + 12), 9)
            pygame.draw.circle(surface, (30, 30, 40), (x + sx * 60, y + 12), 5)
        # 主体
        pygame.draw.polygon(surface, (58, 64, 92), [
            (x, y - 62), (x + 42, y - 16), (x + 34, y + 46),
            (x - 34, y + 46), (x - 42, y - 16)])
        pygame.draw.polygon(surface, body, [
            (x, y - 54), (x + 34, y - 12), (x + 26, y + 38),
            (x - 26, y + 38), (x - 34, y - 12)])
        # 中央核心（阶段变色，闪烁）
        pulse = 15 + int(5 * math.sin(self.t * (0.14 + 0.11 * self.phase)))
        pygame.draw.circle(surface, accent, (x, y - 2), pulse + 6)
        pygame.draw.circle(surface, (255, 255, 255), (x, y - 2), max(4, pulse - 4))
        # 炮口
        for sx in (-1, 1):
            pygame.draw.rect(surface, (40, 44, 66), (x + sx * 20 - 5, y + 26, 10, 22))
        if self.dying:
            pygame.draw.circle(surface, (255, 230, 160),
                               (x, y), int(self.r * (0.4 + 0.6 * (1 - self.dying_timer / 150.0))), 3)


# ------------------------------------------------------------------
# 第一关关卡脚本
# ------------------------------------------------------------------
STAGE1_SCRIPT = [
    (1.2,  "scout",  4, "line",   16),
    (5.0,  "wave",   3, "column", 26),
    (9.0,  "diver",  5, "vshape", 14),
    (13.0, "gunner", 2, "line",   44),
    (16.5, "scout",  6, "column", 12),
    (20.5, "sniper", 2, "line",   50),
    (24.0, "wave",   5, "line",   18),
    (28.0, "bomber", 1, "line",   30),
    (31.5, "diver",  6, "vshape", 12),
    (35.0, "gunner", 3, "line",   32),
    (39.5, "bomber", 2, "line",   64),
    (44.0, "sniper", 4, "line",   30),
    (48.0, "wave",   6, "line",   15),
    (52.0, "diver",  8, "vshape", 10),
    (56.0, "gunner", 4, "line",   26),
    (60.0, "bomber", 3, "line",   52),
    (65.5, "scout",  8, "column", 10),
]


def build_stage1_events():
    """把关卡脚本展开成 (时间秒, 类型, x, y) 事件列表。"""
    events = []
    for t0, kind, count, formation, gap in STAGE1_SCRIPT:
        for i in range(count):
            t = t0 + i * gap / float(FPS)
            if formation == "line":
                span = 300.0
                x = WIDTH * 0.5 + (i - (count - 1) / 2.0) * min(74.0, span / max(1, count))
                y = -40.0
            elif formation == "column":
                x = WIDTH * 0.5 + ((i % 3) - 1) * 110.0
                y = -40.0 - i * 0.0
            else:  # vshape
                x = WIDTH * 0.5 + ((i % 2) * 2 - 1) * (30 + (i // 2) * 46)
                y = -40.0 - (i // 2) * 34.0
            x = clamp(x, 34, WIDTH - 34)
            events.append((t, kind, x, y))
    events.sort(key=lambda e: e[0])
    return events


# ------------------------------------------------------------------
# 输入
# ------------------------------------------------------------------
class InputState:
    __slots__ = ("dx", "dy", "fire", "pause", "bomb")

    def __init__(self, dx=0.0, dy=0.0, fire=False, pause=False, bomb=False):
        self.dx = dx
        self.dy = dy
        self.fire = fire
        self.pause = pause
        self.bomb = bomb


def read_input(keys, prev_pause=False):
    dx = dy = 0.0
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        dx -= 1.0
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        dx += 1.0
    if keys[pygame.K_UP] or keys[pygame.K_w]:
        dy -= 1.0
    if keys[pygame.K_DOWN] or keys[pygame.K_s]:
        dy += 1.0
    fire = bool(keys[pygame.K_SPACE] or keys[pygame.K_j] or keys[pygame.K_z])
    pause = bool(keys[pygame.K_p])
    bomb = bool(keys[pygame.K_x] or keys[pygame.K_k])
    return InputState(dx, dy, fire, pause and not prev_pause, bomb)


# ------------------------------------------------------------------
# 游戏主体
# ------------------------------------------------------------------
class Game:
    def __init__(self, seed=None, lives=PLAYER_START_LIVES):
        self.seed = seed
        self.rng = random.Random(seed)
        self.stars = Starfield(self.rng)
        self.player = Player(lives=lives)
        self.enemies = []
        self.pbullets = []
        self.ebullets = []
        self.powerups = []
        self.explosions = []
        self.player_laser = None
        self.boss = None
        self.boss_spawned = False
        self.boss_defeated = False
        self.events = build_stage1_events()
        self.event_idx = 0
        self.time = 0.0
        self.state = "playing"
        self.score = 0
        self.stats = {
            "shots": 0, "kills": 0, "deaths": 0, "upgrades": 0,
            "switches": 0, "pickups": 0, "enemy_volleys": 0,
            "kills_by_type": {}, "boss_phases": 0, "boss_killed": 0,
            "spawned": 0,
        }
        self.banner = 2.4 * FPS
        self.best_score = 0

    # ------------------------------------------------------------
    # 基础工具
    # ------------------------------------------------------------
    def add_score(self, n):
        self.score += int(n)
        self.best_score = max(self.best_score, self.score)

    def add_explosion(self, x, y, radius=26, duration=24, color=(255, 190, 80)):
        self.explosions.append(Explosion(x, y, radius, duration, color))

    def add_enemy_bullet(self, x, y, ang, speed, r=5.0, color=(255, 110, 110),
                         accel=0.0, curve=0.0):
        b = EnemyBullet(x, y, ang, speed, r=r, color=color, accel=accel, curve=curve)
        self.ebullets.append(b)
        return b

    def clear_enemy_bullets(self):
        self.ebullets = []

    def nearest_enemy(self, x, y):
        best, bd = None, None
        for e in self.enemies:
            if not e.alive:
                continue
            d = dist2(x, y, e.x, e.y)
            if bd is None or d < bd:
                best, bd = e, d
        if self.boss is not None and self.boss.alive and not self.boss.entering:
            d = dist2(x, y, self.boss.x, self.boss.y)
            if bd is None or d < bd:
                best = self.boss
        return best

    def set_laser(self, player):
        _, plan = weapon_plan(player.weapon, player.weapon_level)
        spec = plan[0]
        self.player_laser = LaserBeam(player.x, 0, player.y - 8,
                                      spec["width"], spec["dps"])

    def maybe_drop_powerup(self, enemy):
        """敌机掉落升级箱。

        由于「吃到异种弹药会把档位重置为 1 级」是硬性规则，三种道具若完全
        等概率出现，玩家几乎永远停在 1 级。因此这里做成自适应掉落：60% 概
        率掉当前所用弹药（奖励坚持同一种打法的玩家），40% 掉另外两种之一
        （保留「切枪重置」的赌性）。
        """
        st = ENEMY_TYPES[enemy.kind]
        if self.rng.random() <= st["drop"]:
            cur = self.player.weapon if self.player is not None else "mg"
            if self.rng.random() < 0.60:
                kind = cur
            else:
                others = [k for k in WEAPON_TYPES if k != cur]
                kind = self.rng.choice(others)
            self.powerups.append(PowerUp(enemy.x, enemy.y, kind))

    def apply_powerup(self, kind):
        """外部/测试调用入口。"""
        return self.player.pickup(self, kind)

    # ------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------
    def update(self, inp=None):
        if inp is None:
            inp = InputState()
        if self.state != "playing":
            self._update_effects()
            return
        self.time += 1.0
        self.stars.update()

        if self.banner > 0:
            self.banner -= 1

        self._spawn_stage()
        self._check_boss_spawn()

        if self.player is not None and self.player.alive:
            self.player.update(self, inp)
            if not self.player.firing or self.player.weapon != "laser":
                self.player_laser = None
        else:
            self.player_laser = None

        for e in self.enemies:
            e.update(self)
        if self.boss is not None:
            self.boss.update(self)

        self._update_player_bullets()
        self._update_laser()
        self._update_enemy_bullets()
        self._collide()
        self._update_powerups()
        self._update_effects()
        self._cleanup()

    # ------------------------------------------------------------
    def _update_effects(self):
        for ex in self.explosions:
            ex.update()
        self.explosions = [e for e in self.explosions if e.alive]

    def _spawn_stage(self):
        t_sec = self.time / float(FPS)
        while self.event_idx < len(self.events) and self.events[self.event_idx][0] <= t_sec:
            _, kind, x, y = self.events[self.event_idx]
            self.event_idx += 1
            self.enemies.append(Enemy(x, y, kind, self, self.rng))
            self.stats["spawned"] += 1

    def _check_boss_spawn(self):
        if self.boss_spawned:
            return
        t_sec = self.time / float(FPS)
        if t_sec >= BOSS_TIME:
            self.boss_spawned = True
            self.boss = Boss()
            self.clear_enemy_bullets()
            self.banner = 2.4 * FPS

    # ------------------------------------------------------------
    def _update_player_bullets(self):
        for b in self.pbullets:
            b.update(self)
        self.pbullets = [b for b in self.pbullets if b.alive]

    def _update_laser(self):
        if self.player_laser is None:
            return
        self.player_laser.x = self.player.x
        self.player_laser.y_bottom = self.player.y - 8
        self.player_laser.update()
        dmg = self.player_laser.damage_per_frame()
        for e in self.enemies:
            if e.alive and self.player_laser.hits(e.x, e.y, e.r * 0.9):
                e.hit(self, dmg)
        if self.boss is not None and self.boss.alive and not self.boss.entering:
            if self.player_laser.hits(self.boss.x, self.boss.y, self.boss.r * 0.72):
                self.boss.hit(self, dmg)

    def _update_enemy_bullets(self):
        for b in self.ebullets:
            b.update()
        self.ebullets = [b for b in self.ebullets if b.alive]

    def _update_powerups(self):
        for p in self.powerups:
            p.update(self)
        self.powerups = [p for p in self.powerups if p.alive]

    # ------------------------------------------------------------
    def _collide(self):
        # 玩家子弹 → 敌机 / Boss
        for b in self.pbullets:
            if not b.alive:
                continue
            for e in self.enemies:
                if e.alive and circles_hit(b.x, b.y, b.r, e.x, e.y, e.r):
                    b.alive = False
                    e.hit(self, b.damage)
                    break
            if b.alive and self.boss is not None and self.boss.alive \
                    and not self.boss.dying and not self.boss.entering:
                if self.boss.hits(b.x, b.y, b.r):
                    b.alive = False
                    self.boss.hit(self, b.damage)
        self.pbullets = [b for b in self.pbullets if b.alive]

        # 玩家 ← 敌弹
        p = self.player
        if p is not None and p.alive and p.invincible <= 0:
            for b in self.ebullets:
                if b.alive and circles_hit(b.x, b.y, b.r * 0.85, p.x, p.y, p.hit_r):
                    b.alive = False
                    if p.hit(self):
                        break
            self.ebullets = [b for b in self.ebullets if b.alive]
            # 撞机
            if p.alive and p.invincible <= 0:
                for e in self.enemies:
                    if e.alive and circles_hit(e.x, e.y, e.r * 0.9, p.x, p.y, p.hit_r):
                        e.hit(self, 100)
                        p.hit(self)
                        break

        # 道具拾取
        if p is not None and p.alive:
            for pu in list(self.powerups):
                if pu.alive and circles_hit(pu.x, pu.y, pu.r + 4, p.x, p.y, 16):
                    pu.alive = False
                    p.pickup(self, pu.kind)
                    self.stats["pickups"] += 1
                    self.add_explosion(pu.x, pu.y, 22, 18, WEAPON_COLOR[pu.kind])

    # ------------------------------------------------------------
    def _cleanup(self):
        self.enemies = [e for e in self.enemies if e.alive]
        if self.boss is not None and not self.boss.alive:
            self.boss = None

    # ------------------------------------------------------------
    # 状态切换
    # ------------------------------------------------------------
    def on_boss_dead(self):
        self.boss_defeated = True
        self.clear_enemy_bullets()
        self.enemies = []
        self.state = "cleared"
        self.add_explosion(WIDTH // 2, HEIGHT // 2, 120, 40, (255, 230, 160))

    @property
    def enemies_remaining(self):
        return len(self.enemies) + max(0, len(self.events) - self.event_idx)


# ------------------------------------------------------------------
# 渲染
# ------------------------------------------------------------------
def draw_bullets(surface, bullets):
    for b in bullets:
        b.draw(surface)


def draw_frame(game, surface):
    game.stars.draw(surface)

    for e in game.enemies:
        e.draw(surface)
    if game.boss is not None:
        game.boss.draw(surface)
    for pu in game.powerups:
        pu.draw(surface)
    if game.player_laser is not None:
        game.player_laser.draw(surface)
    draw_bullets(surface, game.pbullets)
    draw_bullets(surface, game.ebullets)
    if game.player is not None:
        game.player.draw(surface)
    for ex in game.explosions:
        ex.draw(surface)
    draw_hud(game, surface)


def draw_hud(game, surface):
    # 顶部
    text(surface, "%08d" % game.score, 12, 8, 22, (255, 255, 255), bold=True)
    text(surface, "SCORE", 12, 32, 12, (170, 190, 230))

    # 剩余生命
    for i in range(max(0, game.player.lives - 1)):
        cx = WIDTH - 22 - i * 22
        pygame.draw.polygon(surface, (140, 200, 255),
                            [(cx, 12), (cx + 8, 30), (cx - 8, 30)])
    text(surface, "LIVES", WIDTH - 12, 34, 12, (170, 190, 230), center=False)

    # 当前武器 & 等级
    col = WEAPON_COLOR[game.player.weapon]
    name = WEAPON_TEXT[game.player.weapon]
    text(surface, L(name[0], name[1]), 12, HEIGHT - 30, 16, col, bold=True)
    for i in range(MAX_WEAPON_LEVEL):
        rx = 150 + i * 22
        rect = pygame.Rect(rx, HEIGHT - 28, 16, 14)
        pygame.draw.rect(surface, (40, 46, 70), rect, border_radius=3)
        if i < game.player.weapon_level:
            pygame.draw.rect(surface, col, rect, border_radius=3)
        else:
            pygame.draw.rect(surface, (90, 100, 130), rect, 1, border_radius=3)

    # 保险炸弹数量
    for i in range(max(0, game.player.bombs)):
        bx = 236 + i * 18
        pygame.draw.circle(surface, (255, 70, 70), (bx, HEIGHT - 21), 6)
        pygame.draw.circle(surface, (255, 230, 100), (bx, HEIGHT - 21), 3)
    text(surface, "BOMB", 236, HEIGHT - 33, 11, (255, 150, 150), center=False)

    # Boss 血条
    if game.boss is not None and not game.boss.entering:
        b = game.boss
        bw = WIDTH - 80
        bx, by = 40, 56
        pygame.draw.rect(surface, (18, 20, 34), (bx - 2, by - 2, bw + 4, 16), border_radius=4)
        ratio = b.hp_ratio
        fcol = [(90, 220, 255), (255, 170, 90), (255, 80, 110)][b.phase - 1]
        pygame.draw.rect(surface, (70, 70, 90), (bx, by, bw, 12), border_radius=3)
        pygame.draw.rect(surface, fcol, (bx, by, int(bw * ratio), 12), border_radius=3)
        for frac in (0.66, 0.33):     # 阶段分界
            sx = bx + int(bw * frac)
            pygame.draw.line(surface, (245, 245, 245), (sx, by - 2), (sx, by + 14), 1)
        nm = Boss.NAME
        text(surface, L(nm[0], nm[1]), WIDTH // 2, by - 14, 14, fcol, center=True, bold=True)
        ph = Boss.PHASE_TEXT[b.phase - 1]
        text(surface, L(ph[0], ph[1]), WIDTH - 26, by, 14, (255, 255, 255), center=False)

    # 开场横幅
    if game.banner > 0:
        a = min(1.0, game.banner / 40.0)
        s = pygame.Surface((WIDTH, 64), pygame.SRCALPHA)
        s.fill((0, 0, 20, int(150 * a)))
        surface.blit(s, (0, HEIGHT // 2 - 32))
        text(surface, L(MISSION_TEXT, "STAGE 1  ·  THOR ASSAULT"),
             WIDTH // 2, HEIGHT // 2 - 6, 26, (255, 240, 180), center=True, bold=True)

    if game.boss is not None and game.boss.phase_banner > 0:
        ph = Boss.PHASE_TEXT[game.boss.phase - 1]
        text(surface, L(ph[0] + "·攻击模式变更", ph[1] + " PATTERN CHANGE"),
             WIDTH // 2, 110, 20, (255, 120, 120), center=True, bold=True)


def draw_overlay(game, surface):
    if game.state == "cleared":
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.fill((0, 10, 40, 170))
        surface.blit(s, (0, 0))
        text(surface, L("任务完成", "MISSION COMPLETE"), WIDTH // 2, HEIGHT // 2 - 90,
             40, (255, 235, 140), center=True, bold=True)
        text(surface, L("第一关 通关！", "STAGE 1 CLEARED"), WIDTH // 2, HEIGHT // 2 - 40,
             22, (200, 230, 255), center=True)
        text(surface, L("最终得分", "FINAL SCORE"), WIDTH // 2, HEIGHT // 2 + 14,
             18, (170, 190, 230), center=True)
        text(surface, "%d" % game.score, WIDTH // 2, HEIGHT // 2 + 44, 30,
             (255, 255, 255), center=True, bold=True)
        text(surface, L("按 R 重新挑战 · ESC 退出", "R restart  ·  ESC quit"),
             WIDTH // 2, HEIGHT // 2 + 110, 16, (200, 210, 230), center=True)
    elif game.state == "game_over":
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.fill((30, 0, 0, 180))
        surface.blit(s, (0, 0))
        text(surface, L("任务失败", "GAME OVER"), WIDTH // 2, HEIGHT // 2 - 40,
             40, (255, 120, 120), center=True, bold=True)
        text(surface, "%d" % game.score, WIDTH // 2, HEIGHT // 2 + 20, 26,
             (255, 255, 255), center=True)
        text(surface, L("按 R 重新挑战 · ESC 退出", "R restart  ·  ESC quit"),
             WIDTH // 2, HEIGHT // 2 + 80, 16, (230, 210, 210), center=True)
    elif game.state == "paused":
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.fill((0, 0, 0, 130))
        surface.blit(s, (0, 0))
        text(surface, L("暂停", "PAUSED"), WIDTH // 2, HEIGHT // 2, 36,
             (255, 255, 255), center=True, bold=True)
        text(surface, L("P 继续", "P to resume"), WIDTH // 2, HEIGHT // 2 + 50, 18,
             (200, 210, 230), center=True)


# ------------------------------------------------------------------
# 自检框架
# ------------------------------------------------------------------
class Tester:
    def __init__(self, verbose=True):
        self.results = []
        self.verbose = verbose

    def run(self, name, fn):
        try:
            fn(self)
            ok, detail = True, ""
        except AssertionError as exc:
            ok, detail = False, str(exc) or "断言失败"
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, "%s: %s" % (type(exc).__name__, exc)
        self.results.append({"name": name, "ok": ok, "detail": detail})
        if self.verbose:
            tag = "PASS" if ok else "FAIL"
            line = "  [%s] %s" % (tag, name)
            if not ok:
                line += "  -> " + detail
            print(line)

    def check(self, cond, msg=""):
        if not cond:
            raise AssertionError(msg or "断言失败")

    @property
    def passed(self):
        return sum(1 for r in self.results if r["ok"])

    @property
    def failed(self):
        return len(self.results) - self.passed


# ------------------------------------------------------------------
# 测试用辅助
# ------------------------------------------------------------------
class _StubPlayer:
    x = WIDTH / 2.0
    y = HEIGHT - 90.0
    alive = True


class _StubGame:
    """隔离测试敌机行为用的桩对象。"""

    def __init__(self, px=WIDTH / 2.0, py=HEIGHT - 90.0):
        self.player = _StubPlayer()
        self.player.x = px
        self.player.y = py
        self.ebullets = []
        self.stats = {"enemy_volleys": 0}
        self.explosions = []

    def add_enemy_bullet(self, x, y, ang, speed, **kw):
        b = EnemyBullet(x, y, ang, speed, **kw)
        self.ebullets.append(b)
        return b

    def add_explosion(self, *a, **kw):
        pass


def _new_game(seed=7, lives=PLAYER_START_LIVES):
    return Game(seed=seed, lives=lives)


def _step(game, n=1, inp=None):
    for _ in range(n):
        game.update(inp if inp is not None else InputState())


# ------------------------------------------------------------------
# 测试
# ------------------------------------------------------------------
def test_background(t):
    g = _new_game(1)
    y0 = [s[1] for s in g.stars.layers[0]]
    n0 = g.stars.nebula_scroll
    _step(g, 30)
    y1 = [s[1] for s in g.stars.layers[0]]
    t.check(any(a < b for a, b in zip(y0, y1)), "星空未向下滚动")
    t.check(g.stars.nebula_scroll > n0, "星云未滚动")
    t.check(len(g.stars.layers) >= 3, "视差层数不足")
    speeds = [l[0][2] for l in g.stars.layers]
    t.check(speeds[0] < speeds[1] < speeds[2], "三层视差速度未递增")
    # 越界回卷
    for l in g.stars.layers:
        for s in l:
            s[1] = HEIGHT + 5
    _step(g, 1)
    for l in g.stars.layers:
        for s in l:
            t.check(-60 <= s[1] <= HEIGHT + 60, "星星未正确回卷: %s" % s[1])
    g.stars._build_nebula()
    t.check(g.stars.nebula_surf.get_size() == (WIDTH, HEIGHT), "星云贴图尺寸错误")
    # 回归防护：星云曾因 BLEND_ADD 叠加把整屏刷成白色（太空应为暗底）
    nb = g.stars.nebula_surf
    vals = [max(nb.get_at((x, y))[:3]) for x in range(0, WIDTH, 4)
            for y in range(0, HEIGHT, 4)]
    avg = sum(vals) / float(len(vals))
    t.check(avg < 80, "星云背景过亮（平均亮度 %.1f），深空应为暗背景" % avg)
    t.check(sum(1 for v in vals if v >= 200) / float(len(vals)) < 0.02,
            "星云存在大面积过曝像素")


def test_player_movement(t):
    g = _new_game(2)
    g.player.invincible = 0
    x0, y0 = g.player.x, g.player.y
    _step(g, 30, InputState(dx=-1, dy=0))
    t.check(g.player.x < x0, "左移无效")
    _step(g, 300, InputState(dx=-1, dy=-1))
    t.check(g.player.x >= 14 - 0.01, "左边界未生效 (%.2f)" % g.player.x)
    t.check(g.player.y >= 40 - 0.01, "上边界未生效 (%.2f)" % g.player.y)
    _step(g, 400, InputState(dx=1, dy=1))
    t.check(g.player.x <= WIDTH - 14 + 0.01, "右边界未生效")
    t.check(g.player.y <= HEIGHT - 18 + 0.01, "下边界未生效")
    t.check(g.player.hit_r <= 6, "玩家判定点应远小于机体")


def test_enemy_catalog(t):
    t.check(len(ENEMY_TYPES) >= 5, "敌机种类不足 5 种，实际 %d" % len(ENEMY_TYPES))
    for kind, st in ENEMY_TYPES.items():
        for key in ("hp", "r", "speed", "score", "fire_cd", "name"):
            t.check(key in st, "%s 缺少属性 %s" % (kind, key))
        t.check(st["hp"] > 0 and st["r"] > 0, "%s 属性非法" % kind)
    hps = sorted(st["hp"] for st in ENEMY_TYPES.values())
    t.check(len(set(hps)) >= 4, "敌机血量过于单一")
    # 每种敌机都能被创建并正常受击致死
    for kind in ENEMY_TYPES:
        g = _new_game(3)
        e = Enemy(WIDTH // 2, 40, kind, g, g.rng)
        e.hit(g, 10 ** 6)
        t.check(not e.alive, "%s 未被击杀" % kind)
        t.check(g.stats["kills"] == 1, "%s 击杀未计数" % kind)


def test_enemy_movement(t):
    prof = {}
    for kind in ENEMY_TYPES:
        stub = _StubGame()
        e = Enemy(WIDTH * 0.5 - 120, 60, kind, stub, random.Random(11))
        xs, ys = [], []
        reversals = 0
        last_sign = 0
        for f in range(220):
            if not e.alive:
                break
            e.update(stub)
            if xs:
                d = e.x - xs[-1]
                if abs(d) > 0.4:
                    sgn = 1 if d > 0 else -1
                    if last_sign and sgn != last_sign:
                        reversals += 1
                    last_sign = sgn
            xs.append(e.x)
            ys.append(e.y)
        tail = ys[-60:]
        y_stop = (max(tail) - min(tail)) < 26
        prof[kind] = dict(x_rev=reversals,
                          y_stop=y_stop,
                          x_travel=max(xs) - min(xs),
                          y_final=ys[-1],
                          x_last=xs[-1])
    t.check(prof["scout"]["x_rev"] <= 1, "侦察机应基本直线俯冲")
    t.check(prof["wave"]["x_rev"] >= 2, "波动机应正弦横摆 (rev=%d)" % prof["wave"]["x_rev"])
    t.check(prof["gunner"]["y_stop"], "炮台机应下降到位后停住")
    t.check(prof["bomber"]["y_stop"], "轰炸机应悬停")
    t.check(prof["sniper"]["x_travel"] > prof["bomber"]["x_travel"],
            "狙击机横移幅度应大于轰炸机")
    # 俯冲蜂追踪玩家 x
    stub = _StubGame(px=WIDTH - 40)
    e = Enemy(WIDTH * 0.5 - 160, 60, "diver", stub, random.Random(5))
    start = abs(WIDTH - 40 - e.x)
    for _ in range(220):
        if not e.alive:
            break
        e.update(stub)
    t.check(abs(WIDTH - 40 - e.x) < start, "俯冲蜂未追踪玩家")
    # 轨迹签名两两不同
    sig = {k: (round(v["y_final"] / 40.0), round(v["x_rev"] / 2.0),
               round(v["x_travel"] / 60.0)) for k, v in prof.items()}
    t.check(len(set(sig.values())) == len(sig),
            "存在轨迹完全相同的敌机: %s" % sig)


def test_enemy_bullets(t):
    sigs = {}
    for kind in ENEMY_TYPES:
        stub = _StubGame()
        e = Enemy(200, 100, kind, stub, random.Random(3))
        e._volley(stub)
        shots = [(round(b.vx, 1), round(b.vy, 1), round(b.r, 1)) for b in stub.ebullets]
        t.check(len(shots) > 0, "%s 不会开火" % kind)
        speeds = sorted({round(math.hypot(a, b), 1) for a, b, _ in shots})
        angs = {int(math.degrees(math.atan2(b.vy, b.vx))) % 360 // 15 for b in stub.ebullets}
        sigs[kind] = (len(shots), len(speeds), round(speeds[0], 1), len(angs))
    t.check(len(set(sigs.values())) == len(sigs),
            "存在弹幕完全相同的敌机: %s" % sigs)
    t.check(len({s[0] for s in sigs.values()}) >= 4, "弹幕密度过于雷同: %s" % sigs)
    # 轰炸机环形弹幕覆盖全向
    stub = _StubGame()
    e = Enemy(WIDTH / 2, 132, "bomber", stub, random.Random(3))
    e._volley(stub)
    angs = sorted({int(math.degrees(math.atan2(b.vy, b.vx))) % 360 // 30
                   for b in stub.ebullets})
    t.check(len(stub.ebullets) == 12, "轰炸机应为 12 发环形弹幕")
    t.check(len(angs) >= 10, "轰炸机应为环形弹幕，实际角度桶 %d" % len(angs))
    # 俯冲蜂五向扇形
    stub = _StubGame()
    e = Enemy(WIDTH / 2, 200, "diver", stub, random.Random(3))
    e._volley(stub)
    t.check(len(stub.ebullets) == 5, "俯冲蜂应为五向扇形，实际 %d" % len(stub.ebullets))
    # 狙击机为高速单发；炮台机为三连发射击
    stub = _StubGame()
    e = Enemy(WIDTH / 2, 90, "sniper", stub, random.Random(3))
    e._volley(stub)
    t.check(len(stub.ebullets) == 1 and stub.ebullets[0].vy > 6.0,
            "狙击弹应为高速单发")
    stub = _StubGame()
    e = Enemy(WIDTH / 2, 90, "gunner", stub, random.Random(3))
    e.fire_timer = 0
    cnt = 0
    for _ in range(40):
        e.update(stub)
        cnt += len(stub.ebullets)
        stub.ebullets = []
    t.check(cnt >= 6, "炮台机连发未生效 (cnt=%d)" % cnt)


def test_weapons(t):
    t.check(len(WEAPON_TYPES) == 3, "应有三种升级弹药")
    for kind in WEAPON_TYPES:
        dps = []
        counts = []
        for lv in (1, 2, 3):
            cool, plan = weapon_plan(kind, lv)
            t.check(len(plan) >= 1, "%s L%d 无开火方案" % (kind, lv))
            dps.append(weapon_dps(kind, lv))
            counts.append(len(plan))
        if kind == "laser":
            t.check(dps[0] < dps[1] < dps[2], "激光伤害未随等级提升: %s" % dps)
            t.check(all(weapon_plan(kind, lv)[1][0].get("beam") for lv in (1, 2, 3)),
                    "激光应为持续光束")
        else:
            t.check(dps[0] < dps[1] < dps[2] or counts[0] < counts[2],
                    "%s 输出未随等级提升: dps=%s counts=%s" % (kind, dps, counts))
        t.check(dps[2] > dps[0], "%s 满级未强于 1 级" % kind)
    # 机枪覆盖面最广（子弹数最多）
    t.check(len(weapon_plan("mg", 3)[1]) >= 5, "满级机枪覆盖面不足")
    t.check(all(p.get("homing") for p in weapon_plan("missile", 3)[1]), "导弹应全部追踪")


def test_powerup_rule(t):
    g = _new_game(4)
    p = g.player
    t.check(p.weapon == "mg" and p.weapon_level == 1, "初始应为机枪 1 级")
    p.pickup(g, "mg")
    t.check((p.weapon, p.weapon_level) == ("mg", 2), "同种第 1 颗应升到 2 级")
    p.pickup(g, "mg")
    t.check((p.weapon, p.weapon_level) == ("mg", 3), "同种第 2 颗应升到 3 级（满级）")
    p.pickup(g, "mg")
    t.check((p.weapon, p.weapon_level) == ("mg", 3), "满级后不应超过 3 级")
    # 异种切换
    p.pickup(g, "laser")
    t.check((p.weapon, p.weapon_level) == ("laser", 1), "异种道具应切枪且回到 1 级")
    p.pickup(g, "laser")
    t.check((p.weapon, p.weapon_level) == ("laser", 2), "同种继续升到 2 级")
    p.pickup(g, "missile")
    t.check((p.weapon, p.weapon_level) == ("missile", 1), "切到导弹应为 1 级")
    p.pickup(g, "mg")
    t.check((p.weapon, p.weapon_level) == ("mg", 1), "切回机枪应重置为 1 级")
    # 三连满级的完整链
    g2 = _new_game(5)
    for _ in range(3):
        g2.player.pickup(g2, "laser")
    t.check((g2.player.weapon, g2.player.weapon_level) == ("laser", 3),
            "连吃三颗同种应满级")
    # 世界内拾取（真正走碰撞流程）
    g3 = _new_game(6)
    g3.powerups.append(PowerUp(g3.player.x, g3.player.y, "missile"))
    _step(g3, 1)
    t.check(g3.player.weapon == "missile" and g3.player.weapon_level == 1,
            "场景拾取未生效")
    t.check(g3.stats["pickups"] >= 1, "拾取统计未更新")
    for bad in ("bomb", "xx", ""):
        try:
            g3.player.pickup(g3, bad)
            t.check(False, "非法道具 %r 未被拒绝" % bad)
        except ValueError:
            pass


def test_powerup_drop(t):
    g = _new_game(8)
    total = 0
    for kind in ENEMY_TYPES:
        for _ in range(60):
            e = Enemy(100, 40, kind, g, g.rng)
            before = len(g.powerups)
            e.hit(g, 10 ** 6)
            total += len(g.powerups) - before
    t.check(total > 0, "敌机从不掉落升级箱")
    t.check(total < 60 * len(ENEMY_TYPES), "掉落率异常")
    t.check(all(pu.kind in WEAPON_TYPES for pu in g.powerups), "掉落了非法道具")
    # 道具会向下飘落并最终消失
    pu = PowerUp(100, -10, "mg")
    for _ in range(2000):
        pu.update(g)
    t.check(not pu.alive, "道具飞出屏幕后未回收")


def test_hit_detection(t):
    # 机枪弹命中
    g = _new_game(9)
    e = Enemy(200, 120, "scout", g, g.rng)
    g.enemies.append(e)
    g.pbullets.append(PlayerBullet(200, 400, -90, 14, 1, "mg", (255, 220, 60)))
    _step(g, 40, InputState(fire=False))
    t.check(e.hp < ENEMY_TYPES["scout"]["hp"], "机枪弹未命中敌机")
    t.check(g.pbullets == [] or e.hp <= 0, "子弹未被消耗")
    # 跟踪导弹能转向并命中侧向目标（注意：9 血的炮台机不会被单发导弹秒杀）
    g = _new_game(10)
    e = Enemy(WIDTH - 60, 200, "gunner", g, g.rng)
    e.y = 200
    g.enemies.append(e)
    hp0 = e.hp
    m = PlayerBullet(WIDTH / 2, 600, -90, 7.5, 3, "missile", (120, 235, 140),
                     size=5, homing=True)
    g.pbullets.append(m)
    ang0 = m.ang
    hit = False
    for _ in range(180):
        g.update(InputState())
        if e.hp < hp0 or not e.alive:
            hit = True
            break
    t.check(m.ang != ang0, "导弹未转向")
    t.check(hit, "跟踪导弹未能命中侧向目标")
    t.check(not m.alive, "导弹命中后应被消耗")
    # 激光贯穿：一发激光同时打多个目标
    g = _new_game(11)
    g.player.x = WIDTH / 2
    g.player.weapon = "laser"
    g.player.weapon_level = 3
    for i in range(3):
        e = Enemy(WIDTH / 2, 100 + i * 60, "bomber", g, g.rng)
        e.y = 100 + i * 60
        g.enemies.append(e)
    hp0 = [e.hp for e in g.enemies]
    _step(g, 20, InputState(fire=True))
    hurt = sum(1 for i, e in enumerate(g.enemies) if e.hp < hp0[i])
    t.check(hurt >= 2, "激光未贯穿多个目标 (hurt=%d)" % hurt)
    t.check(g.player_laser is not None, "开火时未生成激光光束")
    _step(g, 1, InputState(fire=False))
    t.check(g.player_laser is None, "松开后激光未消失")
    # 敌弹命中玩家
    g = _new_game(12)
    g.player.invincible = 0
    g.add_enemy_bullet(g.player.x, g.player.y - 40, 90, 5)
    _step(g, 20, InputState())
    t.check(g.player.lives == 2, "玩家未被敌弹击伤 (lives=%d)" % g.player.lives)


def test_player_lifecycle(t):
    g = _new_game(13, lives=3)
    p = g.player
    t.check(p.lives == 3, "初始命数错误")
    t.check(p.bombs == 2, "初始炸弹数应为 2")
    # 先把武器设为激光 3 级
    p.weapon = "laser"
    p.weapon_level = 3
    p.invincible = 0
    p.hit(g)
    t.check(p.lives == 2 and p.invincible > 0, "受击后未进入无敌")
    t.check((p.weapon, p.weapon_level) == ("mg", 1), "阵亡复活后弹药未重置为初始机枪 1 级")
    t.check(p.hit(g) is False, "无敌帧内不应再次扣命")
    t.check(len(g.ebullets) == 0, "受击后应清空敌弹(子弹地狱礼仪)")
    # 测试保险炸弹
    g_bomb = _new_game(14)
    g_bomb.add_enemy_bullet(100, 100, 90, 3)
    t.check(len(g_bomb.ebullets) == 1, "子弹未生成")
    _step(g_bomb, 1, InputState(bomb=True))
    t.check(g_bomb.player.bombs == 1, "释放炸弹未扣减数量")
    t.check(len(g_bomb.ebullets) == 0, "保险炸弹未清屏消弹")
    # 复活位置
    p.x, p.y = 10, 10
    p.invincible = 0
    p.hit(g)
    t.check(abs(p.x - WIDTH / 2) < 1 and p.y > HEIGHT / 2, "复活位置未复位")
    p.invincible = 0
    p.hit(g)
    t.check(p.lives == 0 and not p.alive, "命数耗尽未阵亡")
    t.check(g.state == "game_over", "未进入 GameOver")
    t.check(p.weapon in WEAPON_TYPES and 1 <= p.weapon_level <= 3, "武器档位越界")


def test_boss_phases(t):
    g = _new_game(14)
    g.player.invincible = 10 ** 9      # Boss 弹幕密度极高，测试中保证玩家不中途阵亡
    g.time = int(BOSS_TIME * FPS) - 1
    _step(g, 3)
    t.check(g.boss is not None, "到点未出现 Boss")
    b = g.boss
    t.check(b.phase_for(1.0) == 1 and b.phase_for(0.5) == 2 and b.phase_for(0.1) == 3,
            "Boss 阶段划分错误")
    t.check(b.max_hp >= 400, "Boss 血量过低")
    for _ in range(200):        # 进场
        g.update(InputState())
        if not b.entering:
            break
    t.check(not b.entering, "Boss 未进场")
    # 逐阶段打掉
    seen = []
    for _ in range(60 * 90):
        g.update(InputState())
        if g.boss is None:
            break
        seen.append(g.boss.phase)
        if len(seen) > 400:
            g.boss.hit(g, 40)
    t.check(1 in seen and 2 in seen and 3 in seen,
            "未经历三个阶段，实际 %s" % sorted(set(seen)))
    # 收尾：若 Boss 还没死透就补上一发
    if g.boss is not None and not g.boss.dying:
        g.boss.hp = 1
        g.boss.hit(g, 5)
    t.check(g.boss is None or g.boss.dying or g.boss.hp <= 0, "Boss 未被击杀流程覆盖")
    for _ in range(300):
        if g.state == "cleared":
            break
        g.update(InputState())
    t.check(g.state == "cleared", "Boss 死亡后未通关 (state=%s)" % g.state)
    t.check(g.stats["boss_killed"] == 1, "Boss 击杀未记录")
    t.check(g.ebullets == [], "通关后应清空敌弹")
    t.check(g.score >= 50000, "Boss 击破得分未计入")


def test_boss_barrage(t):
    counts = {}
    for phase_ratio in (1.0, 0.55, 0.2):
        g = _new_game(15)
        b = Boss()
        g.boss = b
        g.boss_spawned = True
        b.entering = False
        b.y = 118
        b.hp = b.max_hp * phase_ratio
        b.phase = b.phase_for()
        b.attack_timer = 1
        b.ring_timer = 1
        b.aim_timer = 1
        n0 = 0
        for i in range(240):
            g.update(InputState())
            n0 = len(g.ebullets)
            if n0 > 30:
                break
        counts[b.phase] = n0
        t.check(n0 > 10, "阶段 %d 未产生足够弹幕 (%d)" % (b.phase, n0))
    t.check(counts.get(3, 0) >= counts.get(1, 0),
            "三阶段弹幕密度应不低于一阶段: %s" % counts)
    # 螺旋弹幕角度连续
    g = _new_game(16)
    b = Boss()
    g.boss = b
    b.entering = False
    b.hp = b.max_hp * 0.5
    b.phase = 2
    b.t = 0
    for _ in range(40):
        b.update(g)
    angs = sorted(math.degrees(math.atan2(bb.vy, bb.vx)) % 360 for bb in g.ebullets)
    t.check(len(angs) > 12, "螺旋弹幕数量不足")


def test_stage_flow(t):
    g = _new_game(17)
    types_seen = set()
    frames = 0
    g.player.invincible = 10 ** 9      # 保证测试期间不会因失误中断
    while g.state == "playing" and frames < 60 * 130:
        g.update(InputState(dx=maybe_sign(frames), fire=True))
        for e in g.enemies:
            types_seen.add(e.kind)
        frames += 1
        # 大幅加速清场，验证"波次 → Boss → 通关"的完整链路
        if g.enemies and frames % 2 == 0:
            for e in list(g.enemies):
                e.hit(g, 4)
        if g.boss is not None and not g.boss.dying and frames % 2 == 0:
            g.boss.hit(g, 6)
    t.check(g.boss_spawned, "第一关未出现 Boss")
    t.check(types_seen == set(ENEMY_TYPES),
            "第一关中未出现全部敌机类型，缺失 %s" % (set(ENEMY_TYPES) - types_seen))
    t.check(g.state == "cleared", "流程未以通关结束 (state=%s, t=%.1fs)" % (g.state, frames / FPS))
    t.check(g.score > 50000, "通关得分异常: %d" % g.score)
    t.check(len(g.events) > 40, "关卡事件过少: %d" % len(g.events))


def maybe_sign(f):
    return 1 if (f // 90) % 2 == 0 else -1


def test_long_simulation(t):
    g = _new_game(18)
    g.player.invincible = 10 ** 9
    max_eb = 0
    for f in range(60 * 120):
        g.update(InputState(dx=maybe_sign(f), dy=-1 if f % 260 < 40 else 1,
                            fire=True))
        max_eb = max(max_eb, len(g.ebullets))
        if g.state != "playing":
            break
        for e in (g.enemies + ([g.boss] if g.boss else [])):
            ename = getattr(e, "kind", "boss")
            t.check(-400 <= e.x <= WIDTH + 400, "实体 x 越界: %s %.1f" % (ename, e.x))
            t.check(-500 <= e.y <= HEIGHT + 400, "实体 y 越界: %s %.1f" % (ename, e.y))
        for b in g.pbullets:
            t.check(-60 <= b.x <= WIDTH + 60 and -60 <= b.y <= HEIGHT + 60,
                    "玩家子弹越界 %.1f,%.1f" % (b.x, b.y))
        if f % 600 == 0:
            t.check(len(g.pbullets) < 400, "玩家子弹泄漏: %d" % len(g.pbullets))
            t.check(len(g.ebullets) < 1200, "敌弹泄漏: %d" % len(g.ebullets))
            t.check(len(g.explosions) < 400, "爆炸泄漏: %d" % len(g.explosions))
    t.check(g.time > 60 * 60, "长时间模拟过早结束 (%.1fs)" % (g.time / FPS))
    t.check(g.player.alive, "无敌玩家不应阵亡")
    t.check(g.boss_spawned, "长时间模拟中 Boss 未出现")
    t.check(g.boss is not None or g.state == "cleared", "长时间模拟中 Boss 状态异常")


def test_render(t, surface):
    g = _new_game(19)
    g.player.invincible = 10 ** 9
    frames = [0, 400, 60 * 40]
    for _ in range(max(frames)):
        g.update(InputState(dx=1 if (g.time // 30) % 2 else -1, fire=True))
    g.boss = Boss()
    g.boss_spawned = True
    g.boss.entering = False
    g.boss.y = 118
    for _ in range(20):
        g.update(InputState(fire=True))
    surface.fill((0, 0, 0))
    draw_frame(g, surface)
    raw = pygame.image.tostring(surface, "RGB")
    t.check(max(raw) > 0, "渲染结果全黑")
    colors = len({raw[i:i + 3] for i in range(0, len(raw), 3)})
    t.check(colors > 200, "渲染颜色过少 (%d)" % colors)
    # 三种覆盖层
    for st in ("paused", "game_over", "cleared"):
        g.state = st
        draw_overlay(g, surface)
    draw_hud(g, surface)
    # 各武器绘制不报错
    for kind in WEAPON_TYPES:
        for lv in (1, 2, 3):
            g.player.weapon, g.player.weapon_level = kind, lv
            g.update(InputState(fire=True))
            draw_frame(g, surface)
    # 各敌机与道具绘制
    for kind in ENEMY_TYPES:
        e = Enemy(200, 300, kind, g, g.rng)
        e.draw(surface)
    for kind in WEAPON_TYPES:
        PowerUp(100, 100, kind).draw(surface)
    g.state = "playing"


def test_full_run_headless(t):
    """模拟一次"标准通关"路径：不加速清场，只靠玩家火力打完 Boss。"""
    g = _new_game(20)
    g.player.invincible = 10 ** 9
    bot_frames = 0
    while g.state == "playing" and bot_frames < 60 * 200:
        # 简单自动驾驶：优先对准最近的敌人/Boss
        target = g.nearest_enemy(g.player.x, g.player.y)
        dx = 0.0
        if target is not None:
            dx = clamp((target.x - g.player.x) / 60.0, -1.0, 1.0)
        g.update(InputState(dx=dx, fire=True))
        bot_frames += 1
    t.check(g.boss_spawned, "标准流程未触发 Boss")
    t.check(g.state in ("cleared", "game_over"), "流程未结束 (%.1fs)" % (bot_frames / FPS))
    if g.state == "cleared":
        t.check(g.boss_defeated, "通关但 Boss 未标记")
    t.check(g.stats["shots"] > 100, "玩家几乎没开火: %d" % g.stats["shots"])


def test_visual_readability(t, surface):
    """画面可读性：暗背景 + 主体高对比（防止“背景刷白/机体看不见”类回归）。"""
    g = _new_game(21)
    surface.fill((0, 0, 0))
    g.stars.draw(surface)
    bg = [max(surface.get_at((x, y))[:3]) for x in range(0, WIDTH, 8)
          for y in range(0, HEIGHT, 8)]
    bg_avg = sum(bg) / float(len(bg))
    t.check(bg_avg < 80, "背景平均亮度 %.1f 过高，主角与弹幕会淹没在背景里" % bg_avg)

    def brightest(cx, cy, rad):
        return max(max(surface.get_at((int(cx) + dx, int(cy) + dy))[:3])
                   for dx in range(-rad, rad + 1) for dy in range(-rad, rad + 1))

    def bright_count(cx, cy, rad, thr=150):
        return sum(1 for dx in range(-rad, rad + 1) for dy in range(-rad, rad + 1)
                   if max(surface.get_at((int(cx) + dx, int(cy) + dy))[:3]) > thr)

    # 自机（无敌闪烁为可见帧）
    p = Player()
    p.invincible = 5
    p.draw(surface)
    t.check(brightest(p.x, p.y, 8) >= 200, "自机本体与背景对比不足")
    t.check(bright_count(p.x, p.y, 20) >= 20, "自机可见像素过少")
    t.check(brightest(p.x, p.y - 20, 3) > 120, "机首不易识别")

    # 各类敌机
    for i, kind in enumerate(ENEMY_TYPES):
        e = Enemy(70 + i * 68, 300, kind, g, g.rng)
        e.draw(surface)
        t.check(brightest(e.x, e.y, 12) >= 180, "敌机 %s 与背景对比不足" % kind)
    # Boss
    b = Boss()
    b.entering = False
    b.y = 118
    b.hp = b.max_hp * 0.5
    b.draw(surface)
    t.check(brightest(b.x, b.y - 10, 20) >= 200, "Boss 本体对比不足")
    t.check(brightest(b.x - 60, b.y + 12, 6) >= 150, "Boss 侧翼炮台对比不足")

    # 弹幕 / 道具 / 爆炸
    for kind in WEAPON_TYPES:
        for lv in (1, 2, 3):
            plan = weapon_plan(kind, lv)[1]
            if plan[0].get("beam"):
                beam = LaserBeam(WIDTH * 0.5, 100, 400, plan[0]["width"], plan[0]["dps"])
                beam.flicker = 0
                beam.draw(surface)
                t.check(brightest(WIDTH * 0.5, 250, 3) >= 200,
                        "激光 L%d 亮度不足" % lv)
            else:
                for spec in plan:
                    col = WEAPON_COLOR["missile"] if spec.get("homing") else WEAPON_COLOR["mg"]
                    bb = PlayerBullet(300, 300, -90, 10, 1,
                                      "missile" if spec.get("homing") else "mg", col,
                                      size=5 if spec.get("homing") else 4)
                    bb.draw(surface)
                t.check(brightest(300, 294, 8) >= 180, "%s L%d 子弹不可见" % (kind, lv))
    eb = EnemyBullet(240, 300, 90, 4, r=6)
    eb.draw(surface)
    t.check(brightest(240, 300, 4) >= 200, "敌弹不可见")
    for kind in WEAPON_TYPES:
        PowerUp(150, 300, kind).draw(surface)
        t.check(brightest(150, 300, 8) >= 180, "道具 %s 不可见" % kind)
    ex = Explosion(200, 300, 30, 24)
    ex.t = 10
    ex.draw(surface)
    t.check(brightest(200, 300, 12) >= 150, "爆炸特效不可见")
    # 中文字形不是豆腐块/空白
    img = font(28).render(L("任务完成", "MISSION"), True, (255, 255, 255))
    n = img.get_width() * img.get_height()
    ink = sum(1 for x in range(img.get_width()) for y in range(img.get_height())
              if img.get_at((x, y))[3] > 60)
    t.check(0.05 < ink / float(n) < 0.65,
            "文字墨迹率异常 %.3f（0 为空白，1 为实心方块）" % (ink / float(n)))


# ------------------------------------------------------------------
# 运行测试
# ------------------------------------------------------------------
def run_tests(verbose=True):
    surf = pygame.display.get_surface()
    t = Tester(verbose)
    if verbose:
        print("=" * 62)
        print("雷电 Raiden 复刻 自检 (headless) | pygame %s | SDL_VIDEODRIVER=%s"
              % (pygame.version.ver, os.environ.get("SDL_VIDEODRIVER")))
        print("=" * 62)
        print("中文字体: %s" % ("可用" if FONTS_OK else "不可用（回退英文）"))
    t.run("卷轴宇宙背景（视差星空/星云/行星）", test_background)
    t.run("玩家移动与边界", test_player_movement)
    t.run("敌方战机目录（≥5 种，属性各异）", test_enemy_catalog)
    t.run("敌方移动轨迹差异", test_enemy_movement)
    t.run("敌方弹幕差异", test_enemy_bullets)
    t.run("三种升级弹药与等级", test_weapons)
    t.run("核心升级规则（同种三连满级/异种切换回 1 级）", test_powerup_rule)
    t.run("升级箱掉落与回收", test_powerup_drop)
    t.run("命中判定（机枪/跟踪导弹/贯穿激光）", test_hit_detection)
    t.run("玩家受击/无敌/命数与 GameOver", test_player_lifecycle)
    t.run("Boss 三阶段与血条", test_boss_phases)
    t.run("Boss 复合弹幕", test_boss_barrage)
    t.run("第一关流程（波次→Boss→通关）", test_stage_flow)
    t.run("长时间模拟不变量", test_long_simulation)
    t.run("渲染管线", lambda tt: test_render(tt, surf))
    t.run("画面可读性（暗背景/主体对比/中文字形）", lambda tt: test_visual_readability(tt, surf))
    t.run("标准通关路径 headless 全流程", test_full_run_headless)

    if verbose:
        print("-" * 62)
        print("自检结果: %d/%d 通过, %d 失败" % (t.passed, len(t.results), t.failed))
    return t


# ------------------------------------------------------------------
# GUI
# ------------------------------------------------------------------
def run_gui(args):
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("雷 电 RAIDEN —— Stage 1")
    clock = pygame.time.Clock()
    game = Game(seed=args.seed, lives=args.lives)
    paused = False
    prev_pause = False
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_r:
                    game = Game(seed=args.seed, lives=args.lives)
                    paused = False
        keys = pygame.key.get_pressed()
        inp = read_input(keys, prev_pause)
        prev_pause = bool(keys[pygame.K_p])
        if inp.pause:
            paused = not paused

        if not paused:
            game.update(inp)

        draw_frame(game, screen)
        if paused and game.state == "playing":
            game.state = "paused"
            draw_overlay(game, screen)
            game.state = "playing"
        else:
            draw_overlay(game, screen)
        pygame.display.flip()
        clock.tick(FPS)
    pygame.quit()


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------
def parse_args(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="雷电 Raiden 复刻（Stage 1）")
    ap.add_argument("--test", action="store_true", help="运行 headless 自检并退出")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--lives", type=int, default=PLAYER_START_LIVES, help="初始命数")
    ap.add_argument("--frames", type=int, default=0,
                    help="无界面跑 N 帧后退出（配合 --headless 调试用）")
    return ap.parse_args(argv)


def main(argv=None):
    global _FONT_PATH
    args = parse_args(argv)
    pygame.init()
    pygame.display.set_mode((WIDTH, HEIGHT))
    _FONT_PATH = load_fonts()

    if args.test:
        tester = run_tests(verbose=True)
        import json
        payload = {
            "mode": "test",
            "pygame": pygame.version.ver,
            "headless": True,
            "game": "raiden_stage1",
            "total": len(tester.results),
            "passed": tester.passed,
            "failed": tester.failed,
            "results": tester.results,
        }
        print(json.dumps(payload, ensure_ascii=False))
        print("=" * 62)
        if tester.failed:
            print("自检失败 ✘")
            pygame.quit()
            return 1
        print("自检全部通过 ✔")
        pygame.quit()
        return 0

    if args.frames:
        game = Game(seed=args.seed, lives=args.lives)
        for i in range(args.frames):
            game.update(InputState(dx=maybe_sign(i), fire=True))
        print("headless 运行 %d 帧, state=%s, score=%d, boss=%s"
              % (args.frames, game.state, game.score, game.boss is not None))
        pygame.quit()
        return 0

    run_gui(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
