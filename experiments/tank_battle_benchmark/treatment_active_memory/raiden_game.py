#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雷电 (Raiden) —— 经典纵向卷轴射击游戏复刻，仅第一关。

特性
----
* 纵向卷轴宇宙背景：三层视差星空 + 程序化星云 + 掠过行星，全部几何绘制。
* 6 种敌方战机（≥5），各自拥有独立移动轨迹与弹幕：
    scout   侦察机  —— 高速直线俯冲，正弦微摆，不开火/极稀疏
    sine    波形机  —— 横向正弦扫掠下降，三向扇形瞄准弹
    diver   俯冲机  —— 缓慢追踪玩家后高速 φ 俯冲，俯冲瞬间定向点射
    gunner  机枪机  —— 入场驻留后横向往返弹跳，高频率瞄准点射
    turret  炮台机  —— 厚重缓降，到位后悬停，周期性 12 向环形弹幕
    spinner 螺旋机  —— 圆周环绕轨迹，连续螺旋弹流
* 关底 Boss 战舰「赤霄」：三阶段（100%→66%→33%）复合弹幕 + 血条 + 转阶段无敌闪烁
    阶段1 瞄准五向散射 + 旋转环形弹
    阶段2 螺旋弹流 + 双侧机炮下落弹幕
    阶段3 24 向密集爆发 + 高速瞄准三连 + 弹速提升
* 三种升级弹药：
    vulcan 黄色机枪 —— 覆盖面极广的扇形弹幕（3 / 5 / 7 发）
    homing 跟踪导弹 —— 自动转向追踪最近目标（1 / 2 / 3 发）
    laser  直线激光 —— 连续光束，贯穿一条直线（1 / 1 / 3 束，DPS 递增）
* 核心武器规则：同种升级箱连吃三颗 1->2->3 级满级；
  吃到其他种类升级箱 => 立即切换弹药种类并回到该种弹药 1 级（等级不记忆）。
* 通关：击败 Boss 即 MISSION COMPLETE（仅此一关）。
* `--test`：Headless 无界面自检，覆盖背景/敌机/弹幕/Boss/武器/升级规则/胜负。

用法
----
    python3 raiden_game.py             # 游玩（方向键/WASD 移动，Shift 精瞄，空格开火，X 炸弹）
    python3 raiden_game.py --test      # 无界面自检
    python3 raiden_game.py --test --frames 3000
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys

import pygame

W, H = 480, 640
FPS = 60
DT = 1.0 / FPS

PLAYER_R = 5.0                 # 判定圆半径（经典小判定）
PLAYER_SPEED = 236.0
PLAYER_FOCUS_SPEED = 118.0
PLAYER_LIVES = 3
PLAYER_START_BOMBS = 3
PLAYER_MAX_BOMBS = 5
RESPAWN_INVULN = 2.2

WEAPON_KINDS = ("vulcan", "homing", "laser")
POWERUP_KINDS = ("vulcan", "homing", "laser", "bomb", "life")
MAX_WEAPON_LEVEL = 3

C_SPACE = (6, 8, 18)
C_STAR = (235, 240, 255)
C_HUD = (232, 236, 250)
C_DIM = (130, 140, 170)
C_YELLOW = (255, 214, 80)
C_CYAN = (120, 230, 255)
C_RED = (255, 120, 110)
C_LASER = (140, 235, 255)
C_BOSS = (206, 120, 210)
C_BOSS2 = (110, 50, 130)

# 敌机参数表（hp / 分值 / 颜色 / 弹幕类型均不相同）
# stay: 悬停上限（秒）。超过后敌机主动撤离，保证战线总能清空、Boss 必定入场。
ENEMY_SPECS = {
    "scout": dict(hp=2, score=100, radius=11, color=(212, 218, 238), accent=(120, 130, 165),
                  pattern="none", fire=1.9, bullet_speed=175, behavior="dive_weave", stay=9.0),
    "sine": dict(hp=3, score=200, radius=13, color=(130, 222, 255), accent=(48, 138, 190),
                 pattern="spread3", fire=1.7, bullet_speed=185, behavior="sine_sweep", stay=12.0),
    "diver": dict(hp=3, score=250, radius=12, color=(255, 192, 110), accent=(178, 108, 30),
                  pattern="aimed", fire=1.15, bullet_speed=215, behavior="track_then_lunge",
                  stay=10.0),
    "gunner": dict(hp=6, score=350, radius=14, color=(255, 140, 140), accent=(170, 58, 58),
                   pattern="aimed_burst", fire=1.25, bullet_speed=205, behavior="hover_bounce",
                   stay=11.0),
    "turret": dict(hp=10, score=500, radius=18, color=(196, 162, 255), accent=(106, 76, 178),
                   pattern="ring", fire=2.2, bullet_speed=145, behavior="halt_and_ring",
                   stay=11.0),
    "spinner": dict(hp=5, score=400, radius=12, color=(170, 255, 182), accent=(58, 158, 92),
                    pattern="spiral", fire=0.16, bullet_speed=150, behavior="circle_orbit",
                    stay=12.0),
}

BOSS_MAX_HP = 900
BOSS_PHASE_THRESHOLDS = (0.66, 0.33)     # -> 3 个阶段
BOSS_ENTRY_Y = 122.0

# 第一关敌军时间轴：(出现时刻秒, 机型, 数量)
LEVEL1_TIMELINE = (
    (1.6, "scout", 3),
    (4.2, "sine", 2),
    (7.6, "scout", 4),
    (10.4, "gunner", 1),
    (13.8, "diver", 3),
    (17.6, "sine", 3),
    (21.2, "turret", 1),
    (25.0, "spinner", 2),
    (28.6, "scout", 5),
    (32.4, "gunner", 2),
    (36.0, "diver", 4),
    (40.0, "spinner", 2),
    (44.0, "turret", 2),
    (48.0, "sine", 4),
    (52.0, "gunner", 2),
    (56.0, "diver", 4),
    (60.0, "spinner", 3),
    (64.0, "turret", 2),
)
BOSS_SPAWN_DELAY = 3.0          # 时间轴结束且清场后，Boss 入场延迟


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def wrap_angle(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def draw_ship(surf, x, y, r, color, accent, shape="dart", angle=0.0):
    """纯几何战机绘制。"""
    ca, sa = math.cos(angle), math.sin(angle)

    def rot(px, py):
        return (x + px * ca - py * sa, y + px * sa + py * ca)

    if shape == "dart":
        body = [rot(0, -r), rot(r * 0.72, r * 0.55), rot(0, r * 0.72), rot(-r * 0.72, r * 0.55)]
        pygame.draw.polygon(surf, color, body)
        pygame.draw.polygon(surf, accent, body, 2)
        pygame.draw.polygon(surf, accent, [rot(0, -r * 0.45), rot(r * 0.3, r * 0.35),
                                           rot(-r * 0.3, r * 0.35)])
    elif shape == "bat":
        body = [rot(0, -r * 0.9), rot(r, r * 0.2), rot(r * 0.42, r * 0.75),
                rot(0, r * 0.45), rot(-r * 0.42, r * 0.75), rot(-r, r * 0.2)]
        pygame.draw.polygon(surf, color, body)
        pygame.draw.polygon(surf, accent, body, 2)
    elif shape == "disc":
        pygame.draw.circle(surf, color, (int(x), int(y)), int(r))
        pygame.draw.circle(surf, accent, (int(x), int(y)), int(r), 2)
        pygame.draw.circle(surf, accent, (int(x), int(y)), int(r * 0.45))
        for i in range(4):
            a = i * math.pi / 2
            pygame.draw.line(surf, accent, (x, y),
                             (x + math.cos(a) * r * 1.35, y + math.sin(a) * r * 1.35), 2)
    elif shape == "blade":
        body = [rot(0, -r * 1.1), rot(r * 0.55, 0), rot(0, r), rot(-r * 0.55, 0)]
        pygame.draw.polygon(surf, color, body)
        pygame.draw.polygon(surf, accent, body, 2)
    else:                                    # "arrow" 玩家机
        body = [rot(0, -r * 1.25), rot(r * 0.5, r * 0.3), rot(r, r * 0.9),
                rot(0, r * 0.55), rot(-r, r * 0.9), rot(-r * 0.5, r * 0.3)]
        pygame.draw.polygon(surf, color, body)
        pygame.draw.polygon(surf, accent, body, 2)
        pygame.draw.circle(surf, (255, 255, 255), (int(x), int(y - r * 0.15)), max(1, int(r * 0.2)))


ENEMY_SHAPES = {"scout": "dart", "sine": "blade", "diver": "arrow",
                "gunner": "bat", "turret": "disc", "spinner": "arrow"}


class Starfield:
    """三层视差星空 + 程序化星云 + 掠过行星。"""

    def __init__(self, rng):
        self.rng = rng
        self.layers = []
        for count, speed, size, color in ((72, 30.0, 1, (128, 142, 178)),
                                          (44, 68.0, 2, (196, 210, 244)),
                                          (22, 122.0, 2, (255, 255, 255))):
            stars = [[rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.0, 6.28)]
                     for _ in range(count)]
            self.layers.append(dict(speed=speed, size=size, color=color, stars=stars))
        self.nebulae = []
        for i, col in enumerate(((58, 30, 92), (22, 46, 96), (74, 26, 62))):
            self.nebulae.append(dict(x=rng.uniform(0, W), y=rng.uniform(0, H),
                                     r=rng.uniform(70, 130) if i else 150,
                                     color=col, speed=9.0 + 5.0 * i))
        self.planet = dict(x=rng.uniform(60, W - 60), y=-260.0, r=rng.uniform(48, 76),
                           speed=26.0, hue=rng.choice(((90, 70, 140), (60, 100, 140), (120, 80, 90))))

    def update(self, dt):
        for layer in self.layers:
            for s in layer["stars"]:
                s[1] += layer["speed"] * dt
                s[2] += dt * 3.0
                if s[1] > H:
                    s[1] -= H
                    s[0] = self.rng.uniform(0, W)
        for n in self.nebulae:
            n["y"] += n["speed"] * dt
            if n["y"] - n["r"] > H:
                n["y"] = -n["r"]
                n["x"] = self.rng.uniform(0, W)
                n["r"] = self.rng.uniform(70, 140)
                n["color"] = self.rng.choice(((58, 30, 92), (22, 46, 96), (74, 26, 62)))
        p = self.planet
        p["y"] += p["speed"] * dt
        if p["y"] - p["r"] > H:
            p["y"] = -p["r"] - 120
            p["x"] = self.rng.uniform(60, W - 60)
            p["r"] = self.rng.uniform(48, 76)
            p["hue"] = self.rng.choice(((90, 70, 140), (60, 100, 140), (120, 80, 90)))

    def draw(self, surf, overlay):
        overlay.fill((0, 0, 0, 0))
        for n in self.nebulae:
            if -n["r"] < n["y"] < H + n["r"]:
                pygame.draw.circle(overlay, n["color"] + (30,), (int(n["x"]), int(n["y"])), int(n["r"]))
                pygame.draw.circle(overlay, n["color"] + (22,), (int(n["x"]), int(n["y"])), int(n["r"] * 0.6))
        p = self.planet
        if -p["r"] * 2 < p["y"] < H + p["r"] * 2:
            pygame.draw.circle(overlay, p["hue"] + (70,), (int(p["x"]), int(p["y"])), int(p["r"]))
            pygame.draw.circle(overlay, tuple(min(255, c + 40) for c in p["hue"]) + (60,),
                               (int(p["x"]), int(p["y"])), int(p["r"]), max(2, int(p["r"] * 0.08)))
            pygame.draw.ellipse(overlay, p["hue"] + (46,),
                                (int(p["x"] - p["r"] * 1.6), int(p["y"] - p["r"] * 0.22),
                                 int(p["r"] * 3.2), int(p["r"] * 0.44)), max(1, int(p["r"] * 0.06)))
        surf.blit(overlay, (0, 0))
        for layer in self.layers:
            for (sx, sy, _ph) in layer["stars"]:
                if layer["size"] == 1:
                    surf.fill(layer["color"], (int(sx), int(sy), 1, 2))
                else:
                    surf.fill(layer["color"], (int(sx), int(sy), 2, 2))


class Bullet:
    """通用弹丸：直线 / 瞄准 / 环形 / 螺旋 / 追踪。"""

    __slots__ = ("x", "y", "vx", "vy", "damage", "is_player", "owner", "radius",
                 "color", "life", "kind", "homing", "turn_rate", "speed", "alive", "trail")

    def __init__(self, x, y, vx, vy, damage=1, is_player=False, owner=None, radius=4,
                 color=(255, 255, 255), life=7.0, kind="straight", homing=False,
                 turn_rate=7.5):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.damage = damage
        self.is_player = is_player
        self.owner = owner
        self.radius = radius
        self.color = color
        self.life = life
        self.kind = kind
        self.homing = homing
        self.turn_rate = turn_rate
        self.speed = max(1e-6, math.hypot(vx, vy))
        self.alive = True
        self.trail = []

    def update(self, dt, targets=()):
        if self.homing and targets:
            tx, ty = min(targets, key=lambda p: (p[0] - self.x) ** 2 + (p[1] - self.y) ** 2)
            desired = math.atan2(ty - self.y, tx - self.x)
            current = math.atan2(self.vy, self.vx)
            delta = wrap_angle(desired - current)
            max_turn = self.turn_rate * dt
            current += clamp(delta, -max_turn, max_turn)
            self.vx = math.cos(current) * self.speed
            self.vy = math.sin(current) * self.speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        m = 40
        if self.life <= 0 or self.x < -m or self.x > W + m or self.y < -m or self.y > H + m:
            self.alive = False

    def draw(self, surf):
        if self.kind == "missile":
            ang = math.atan2(self.vy, self.vx)
            pygame.draw.line(surf, (255, 220, 140),
                             (self.x - math.cos(ang) * 9, self.y - math.sin(ang) * 9),
                             (self.x, self.y), 3)
            pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), int(self.radius))
            pygame.draw.circle(surf, (255, 255, 255), (int(self.x), int(self.y)), max(1, int(self.radius * 0.45)))
            return
        pygame.draw.circle(surf, tuple(int(c * 0.45) for c in self.color),
                           (int(self.x), int(self.y)), int(self.radius) + 2)
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), int(self.radius))
        if self.radius >= 6:
            pygame.draw.circle(surf, (255, 255, 255), (int(self.x), int(self.y)), int(self.radius * 0.4))


class Beam:
    """直线激光光束：连续伤害，可贯穿同一直线上的多个目标。"""

    __slots__ = ("offset", "width", "dps", "level", "phase")

    def __init__(self, offset=0.0, width=12.0, dps=60.0, level=1):
        self.offset = offset
        self.width = width
        self.dps = dps
        self.level = level
        self.phase = 0.0

    def rect(self, player):
        w = self.width
        return pygame.Rect(int(player.x + self.offset - w / 2), 0, int(w), int(player.y))

    def update(self, dt):
        self.phase += dt * 22.0

    def draw(self, surf, player):
        r = self.rect(player)
        core = pygame.Rect(int(r.x + r.w * 0.32), 0, max(1, int(r.w * 0.36)), r.h)
        glow = pygame.Surface((r.w + 8, 6), pygame.SRCALPHA)
        glow.fill((90, 200, 255, 70))
        surf.blit(glow, (r.x - 4, player.y - 14))
        surf.fill((70, 140, 220), r)
        surf.fill(C_LASER, core)
        for i in range(6):                       # 能量流动条纹
            yy = int((self.phase * 60 + i * 110) % r.h)
            surf.fill((255, 255, 255), (core.x, yy, core.w, 3))


class PowerUp:
    """升级箱：vulcan / homing / laser / bomb / life。"""

    __slots__ = ("kind", "x", "y", "t", "radius", "vy")

    def __init__(self, kind, x, y):
        self.kind = kind
        self.x = float(x)
        self.y = float(y)
        self.t = 0.0
        self.radius = 13.0
        self.vy = 58.0

    def update(self, dt):
        self.t += dt
        self.y += self.vy * dt
        self.x += math.sin(self.t * 2.2) * 26.0 * dt

    def draw(self, surf):
        x, y, r = int(self.x), int(self.y), int(self.radius)
        col = {"vulcan": (250, 205, 60), "homing": (110, 225, 140), "laser": (120, 220, 255),
               "bomb": (255, 130, 120), "life": (240, 240, 250)}[self.kind]
        pygame.draw.circle(surf, (18, 20, 30), (x, y), r)
        pygame.draw.circle(surf, col, (x, y), r, 2)
        pygame.draw.circle(surf, tuple(int(c * 0.5) for c in col), (x, y), r - 3, 1)
        if self.kind in WEAPON_KINDS:
            ch = {"vulcan": "W", "homing": "M", "laser": "L"}[self.kind]
            pygame.draw.line(surf, col, (x - 4, y - 5), (x + 4, y - 5), 2)
            pygame.draw.line(surf, col, (x + 4, y - 5), (x, y + 5), 2)
            pygame.draw.line(surf, col, (x, y + 5), (x - 4, y - 5), 2)
            _ = ch
        elif self.kind == "bomb":
            pygame.draw.circle(surf, col, (x, y + 1), 6)
            pygame.draw.line(surf, (255, 255, 255), (x, y - 6), (x + 3, y - 1), 2)
        else:
            pygame.draw.circle(surf, col, (x, y), 4)
            pygame.draw.line(surf, col, (x - 6, y), (x + 6, y), 2)
            pygame.draw.line(surf, col, (x, y - 6), (x, y + 6), 2)


class Explosion:
    __slots__ = ("x", "y", "t", "dur", "r", "hue")

    def __init__(self, x, y, r=22.0, dur=0.34, hue=(255, 200, 90)):
        self.x, self.y = x, y
        self.t = 0.0
        self.dur = dur
        self.r = r
        self.hue = hue

    def update(self, dt):
        self.t += dt
        return self.t < self.dur

    @property
    def progress(self):
        return clamp(self.t / self.dur, 0.0, 1.0)

    def draw(self, surf):
        p = self.progress
        rr = int(self.r * (0.35 + p * 0.85))
        if rr <= 0:
            return
        fade = 1.0 - p
        pygame.draw.circle(surf, (255, int(self.hue[1] * fade), int(self.hue[2] * fade * 0.4)),
                           (int(self.x), int(self.y)), rr)
        if rr > 4:
            pygame.draw.circle(surf, (255, 255, 255), (int(self.x), int(self.y)),
                               max(1, int(rr * 0.4)))

# 敌机
# ---------------------------------------------------------------------------

class Enemy:
    """6 种敌机，各自独立的移动轨迹 + 弹幕模式。"""

    def __init__(self, kind, x, y, rng):
        spec = ENEMY_SPECS[kind]
        self.kind = kind
        self.spec = spec
        self.behavior = spec["behavior"]
        self.pattern = spec["pattern"]
        self.x, self.y = float(x), float(y)
        self.base_x = float(x)
        self.hp = self.max_hp = spec["hp"]
        self.r = spec["radius"]
        self.score = spec["score"]
        self.color = spec["color"]
        self.accent = spec["accent"]
        self.shape = ENEMY_SHAPES[kind]
        self.fire_interval = spec["fire"]
        self.bullet_speed = spec["bullet_speed"]
        self.stay_time = spec["stay"]
        self.retreat = False
        self.fire_timer = rng.uniform(0.5, 1.0)
        self.t = 0.0
        self.alive = True
        self.state = "enter"
        self.dir_x = 1 if x < W / 2 else -1
        self.spin_ang = rng.uniform(0.0, math.tau)
        self.ring_ang = 0.0
        self.volley = 0
        self.hit_flash = 0.0
        self.lunge_dir = (0.0, 1.0)
        self.score_awarded = False

    # -- 更新 -------------------------------------------------------------
    def update(self, game, dt):
        self.t += dt
        if self.hit_flash > 0:
            self.hit_flash -= dt
        if self.t > self.stay_time:
            self.retreat = True                     # 悬停超时 -> 撤离，战线必定能清空
        if self.retreat:
            self.y += 168.0 * dt
        elif self.y > -20 and self.y < H + 20:
            self.move(game, dt)
        else:
            self.y += 40.0 * dt
        if self.y > H + 70 or self.x < -120 or self.x > W + 120:
            self.alive = False
            return
        if self.y > -6 and not self.retreat:
            self.fire_timer -= dt
            if self.fire_timer <= 0:
                self.fire_timer = self.fire_interval
                self.shoot(game)

    # -- 轨迹 -------------------------------------------------------------
    def move(self, game, dt):
        b = self.behavior
        if b == "dive_weave":                       # 侦察机：高速俯冲 + 微摆
            self.y += 196.0 * dt
            self.x += math.sin(self.t * 3.4) * 78.0 * dt
        elif b == "sine_sweep":                     # 波形机：横向正弦扫掠
            self.y += 52.0 * dt
            self.x = self.base_x + 76.0 * math.sin(self.t * 1.55)
        elif b == "track_then_lunge":               # 俯冲机：追踪 -> φ 冲刺
            if self.state == "enter":
                tgt = game.player
                if tgt is not None:
                    self.x += clamp((tgt.x - self.x) * 2.4, -96.0, 96.0) * dt
                self.y += 46.0 * dt
                if self.t > 2.0 or self.y > 172.0:
                    self.state = "lunge"
                    self.lunge_dir = game.aim_from(self.x, self.y)
                    self.shoot(game, lunge=True)
            else:
                self.x += self.lunge_dir[0] * 336.0 * dt
                self.y += self.lunge_dir[1] * 336.0 * dt
        elif b == "hover_bounce":                   # 机枪机：驻留 + 横向弹跳
            if self.y < 96.0:
                self.y += 92.0 * dt
            else:
                self.y = 96.0
                self.x += self.dir_x * 124.0 * dt
                if self.x < 34.0:
                    self.x, self.dir_x = 34.0, 1
                elif self.x > W - 34.0:
                    self.x, self.dir_x = W - 34.0, -1
        elif b == "halt_and_ring":                  # 炮台机：缓降悬停
            if self.y < 150.0:
                self.y += 32.0 * dt
            else:
                self.y = 150.0 + math.sin(self.t * 1.2) * 6.0
        elif b == "circle_orbit":                   # 螺旋机：圆周环绕并缓降
            cx = self.base_x
            self.x = cx + 64.0 * math.cos(1.85 * self.t)
            self.y = 66.0 + 30.0 * math.sin(1.85 * self.t) + 30.0 * self.t
        else:
            self.y += 60.0 * dt

    # -- 弹幕 -------------------------------------------------------------
    def shoot(self, game, lunge=False):
        p = self.pattern
        if p == "none":
            return 0
        if p == "spread3":
            ax, ay = game.aim_from(self.x, self.y)
            base = math.atan2(ay, ax)
            for off in (-0.32, 0.0, 0.32):
                game.enemy_bullet(self.x, self.y + 8, base + off, self.bullet_speed,
                                  radius=4, color=(150, 235, 255))
            return 3
        if p == "aimed":
            if not lunge:
                return 0
            ax, ay = self.lunge_dir
            game.enemy_bullet(self.x, self.y + 8, math.atan2(ay, ax), self.bullet_speed * 1.1,
                              radius=5, color=(255, 200, 120))
            for off in (-0.26, 0.26):
                game.enemy_bullet(self.x, self.y + 8, math.atan2(ay, ax) + off,
                                  self.bullet_speed * 0.9, radius=4, color=(255, 170, 90))
            return 3
        if p == "aimed_burst":
            self.volley += 1
            side = -1.0 if self.volley % 2 else 1.0
            ax, ay = game.aim_from(self.x, self.y)
            base = math.atan2(ay, ax)
            for off in (-0.12, 0.12):
                game.enemy_bullet(self.x + side * 12, self.y + 10, base + off, self.bullet_speed,
                                  radius=4, color=(255, 150, 150))
            return 2
        if p == "ring":
            self.ring_ang += 0.26
            n = 12
            for i in range(n):
                a = self.ring_ang + i * math.tau / n
                game.enemy_bullet(self.x, self.y, a, self.bullet_speed, radius=5,
                                  color=(205, 170, 255))
            return n
        if p == "spiral":
            self.spin_ang += 0.5
            a = self.spin_ang + math.sin(self.t * 2.0) * 0.5
            game.enemy_bullet(self.x, self.y, a, self.bullet_speed, radius=4, color=(170, 255, 190))
            return 1
        return 0

    def damage(self, amount):
        self.hp -= amount
        self.hit_flash = 0.08
        return self.hp <= 0

    def draw(self, surf):
        col = (255, 255, 255) if self.hit_flash > 0 else self.color
        draw_ship(surf, self.x, self.y, self.r, col, self.accent, self.shape,
                  angle=math.pi if self.kind in ("scout", "diver") else 0.0)
        if self.max_hp > 3:                        # 厚重机型显示血条
            w = self.r * 2
            ratio = clamp(self.hp / self.max_hp, 0.0, 1.0)
            pygame.draw.rect(surf, (40, 30, 40), (int(self.x - w / 2), int(self.y - self.r - 9), int(w), 4))
            pygame.draw.rect(surf, (120, 240, 140), (int(self.x - w / 2), int(self.y - self.r - 9),
                                                     int(w * ratio), 4))


# ---------------------------------------------------------------------------
# 关底 Boss：赤霄（三阶段复合弹幕）
# ---------------------------------------------------------------------------

class Boss:
    def __init__(self, x=W / 2, y=-90.0):
        self.x, self.y = float(x), float(y)
        self.r = 60.0
        self.max_hp = BOSS_MAX_HP
        self.hp = BOSS_MAX_HP
        self.t = 0.0
        self.state = "enter"            # enter -> fight -> dying -> dead
        self.phase = 1
        self.invuln = 0.0
        self.hit_flash = 0.0
        self.t_aim = 1.4
        self.t_ring = 2.0
        self.t_spiral = 0.3
        self.t_side = 1.0
        self.t_burst = 2.0
        self.spiral_ang = 0.0
        self.shots_fired = 0
        self.phase_events = []
        self.death_timer = 0.0

    @property
    def hp_ratio(self):
        return clamp(self.hp / self.max_hp, 0.0, 1.0)

    def phase_for(self, ratio):
        return 1 + sum(1 for t in BOSS_PHASE_THRESHOLDS if ratio <= t)

    def update(self, game, dt):
        self.t += dt
        if self.hit_flash > 0:
            self.hit_flash -= dt
        if self.invuln > 0:
            self.invuln -= dt

        if self.state == "dying":
            self.death_timer -= dt
            if game.rng.random() < 0.5:
                game.explosions.append(Explosion(
                    self.x + game.rng.uniform(-self.r, self.r),
                    self.y + game.rng.uniform(-self.r * 0.6, self.r * 0.6),
                    r=game.rng.uniform(14, 34), dur=0.4))
            if self.death_timer <= 0:
                self.state = "dead"
                game.explosions.append(Explosion(self.x, self.y, r=110, dur=0.9))
            return

        if self.state == "enter":
            self.y += 72.0 * dt
            if self.y >= BOSS_ENTRY_Y:
                self.y = BOSS_ENTRY_Y
                self.state = "fight"
            else:
                self.fire(game, dt)             # 入场途中就已开火（经典雷电手感）
            return

        # 战斗巡航
        self.x = W / 2 + 152.0 * math.sin(self.t * 0.55)
        self.y = BOSS_ENTRY_Y + 16.0 * math.sin(self.t * 1.3)

        ratio = self.hp_ratio
        new_phase = self.phase_for(ratio)
        if new_phase != self.phase:
            self.phase = new_phase
            self.invuln = 1.3
            self.phase_events.append(new_phase)
            game.explosions.append(Explosion(self.x, self.y, r=70, dur=0.5, hue=(160, 220, 255)))
            for i in range(18):                    # 转阶段爆发环
                a = i * math.tau / 18
                game.enemy_bullet(self.x, self.y, a, 150, radius=6, color=(255, 210, 255))

        if self.invuln > 0:
            return
        self.fire(game, dt)

    def fire(self, game, dt):
        p = self.phase
        if p == 1:
            self.t_aim -= dt
            self.t_ring -= dt
            if self.t_aim <= 0:
                self.t_aim = 1.15
                ax, ay = game.aim_from(self.x, self.y)
                base = math.atan2(ay, ax)
                for off in (-0.60, -0.30, 0.0, 0.30, 0.60):
                    game.enemy_bullet(self.x, self.y + 30, base + off, 186, radius=5,
                                      color=(255, 160, 200))
                self.shots_fired += 5
            if self.t_ring <= 0:
                self.t_ring = 2.4
                n = 14
                for i in range(n):
                    game.enemy_bullet(self.x, self.y, i * math.tau / n + self.t * 0.4, 132,
                                      radius=5, color=(230, 170, 255))
                self.shots_fired += n
        elif p == 2:
            self.t_spiral -= dt
            self.t_side -= dt
            if self.t_spiral <= 0:
                self.t_spiral = 0.11
                self.spiral_ang += 0.62
                game.enemy_bullet(self.x, self.y + 18, self.spiral_ang, 172, radius=5,
                                  color=(255, 220, 150))
                game.enemy_bullet(self.x, self.y + 18, self.spiral_ang + math.pi, 172, radius=5,
                                  color=(255, 220, 150))
                self.shots_fired += 2
            if self.t_side <= 0:
                self.t_side = 0.5
                for sx in (self.x - self.r * 0.86, self.x + self.r * 0.86):
                    game.enemy_bullet(sx, self.y + 24, math.pi / 2 - 0.16, 224, radius=5,
                                      color=(160, 210, 255))
                    game.enemy_bullet(sx, self.y + 24, math.pi / 2 + 0.16, 224, radius=5,
                                      color=(160, 210, 255))
                self.shots_fired += 4
        else:
            self.t_burst -= dt
            self.t_aim -= dt
            if self.t_burst <= 0:
                self.t_burst = 1.7
                n = 24
                for i in range(n):
                    game.enemy_bullet(self.x, self.y, i * math.tau / n + self.t * 0.9, 152,
                                      radius=6, color=(255, 130, 180))
                self.shots_fired += n
            if self.t_aim <= 0:
                self.t_aim = 0.55
                ax, ay = game.aim_from(self.x, self.y)
                base = math.atan2(ay, ax)
                for off in (-0.22, 0.0, 0.22):
                    game.enemy_bullet(self.x, self.y + 30, base + off, 262, radius=5,
                                      color=(255, 100, 120))
                self.shots_fired += 3

    def damage(self, amount, game=None):
        if self.invuln > 0 and self.state != "dying":
            return False
        self.hp -= amount
        self.hit_flash = 0.07
        if self.hp <= 0 and self.state != "dying":
            self.hp = 0
            self.state = "dying"
            self.death_timer = 2.2
        return self.hp <= 0

    def draw(self, surf):
        x, y, r = self.x, self.y, self.r
        hull = [(x, y + r * 0.95), (x + r * 0.55, y + r * 0.5), (x + r * 1.25, y - r * 0.1),
                (x + r * 0.85, y - r * 0.62), (x, y - r * 0.82), (x - r * 0.85, y - r * 0.62),
                (x - r * 1.25, y - r * 0.1), (x - r * 0.55, y + r * 0.5)]
        body = (255, 255, 255) if self.hit_flash > 0 else C_BOSS
        if self.invuln > 0 and int(self.t * 14) % 2 == 0:
            body = (255, 255, 255)
        pygame.draw.polygon(surf, C_BOSS2, hull)
        pygame.draw.polygon(surf, body, hull, 3)
        pygame.draw.polygon(surf, C_BOSS2,
                            [(x, y + r * 0.2), (x + r * 0.42, y - r * 0.3),
                             (x, y - r * 0.55), (x - r * 0.42, y - r * 0.3)])
        pygame.draw.circle(surf, body, (int(x), int(y + r * 0.05)), int(r * 0.3), 2)
        pygame.draw.circle(surf, (255, 240, 160), (int(x), int(y + r * 0.05)), int(r * 0.12))
        for sx in (x - r * 0.86, x + r * 0.86):          # 侧舷炮塔
            pygame.draw.circle(surf, body, (int(sx), int(y + r * 0.18)), int(r * 0.19), 2)
            pygame.draw.circle(surf, (255, 190, 220), (int(sx), int(y + r * 0.18)), int(r * 0.08))
        for i in range(3):                               # 引擎尾焰
            fl = 12 + 8 * math.sin(self.t * 9 + i)
            pygame.draw.polygon(surf, (120, 200, 255),
                                [(x - 14 + i * 14, y + r * 0.86), (x - 7 + i * 14, y + r * 0.86),
                                 (x - 10.5 + i * 14, y + r * 0.86 + fl)])
        pf = pygame.font.Font(None, 16)
        surf.blit(pf.render("PHASE %d" % self.phase, True, (255, 220, 240)),
                  (int(x - 26), int(y - r - 26)))


# ---------------------------------------------------------------------------

# 玩家武器 / 玩家
# ---------------------------------------------------------------------------

# 每级弹幕形状（角度为相对正上方的偏移，单位弧度）
VULCAN_SPECS = {
    1: (-0.10, 0.0, 0.10),
    2: (-0.24, -0.12, 0.0, 0.12, 0.24),
    3: (-0.44, -0.29, -0.145, 0.0, 0.145, 0.29, 0.44),
}
HOMING_SPECS = {
    1: ((0.0, 0.0),),
    2: ((-10.0, 0.0), (10.0, 0.0)),
    3: ((-16.0, -0.12), (0.0, 0.0), (16.0, 0.12)),
}
# (横向偏移, 光束宽度, DPS)
LASER_SPECS = {
    1: ((0.0, 12.0, 60.0),),
    2: ((0.0, 20.0, 95.0),),
    3: ((-16.0, 10.0, 45.0), (0.0, 18.0, 60.0), (16.0, 10.0, 45.0)),
}
VULCAN_COOLDOWN = 0.11
HOMING_COOLDOWN = 0.33


class Weapon:
    __slots__ = ("kind", "level", "cooldown")

    def __init__(self, kind="vulcan", level=1):
        self.kind = kind
        self.level = level
        self.cooldown = 0.0

    @property
    def label(self):
        return "%s-%d" % (self.kind.upper(), self.level)

    def cd_for_level(self):
        if self.kind == "homing":
            return HOMING_COOLDOWN - 0.04 * (self.level - 1)
        return VULCAN_COOLDOWN


class Player:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.r = PLAYER_R
        self.alive = True
        self.invuln = RESPAWN_INVULN
        self.hit_flash = 0.0
        self.roll = 0.0

    def move(self, game, dt, inp):
        spd = PLAYER_FOCUS_SPEED if inp.get("focus") else PLAYER_SPEED
        dx = (1 if inp.get("right") else 0) - (1 if inp.get("left") else 0)
        dy = (1 if inp.get("down") else 0) - (1 if inp.get("up") else 0)
        if dx and dy:
            k = math.sqrt(0.5)
            dx, dy = dx * k, dy * k
        self.x = clamp(self.x + dx * spd * dt, 18.0, W - 18.0)
        self.y = clamp(self.y + dy * spd * dt, 34.0, H - 22.0)
        self.roll += dx * dt * 8.0
        if not dx:
            self.roll *= max(0.0, 1.0 - dt * 9.0)
        if self.invuln > 0:
            self.invuln -= dt
        if self.hit_flash > 0:
            self.hit_flash -= dt

    def draw(self, surf):
        if self.invuln > 0 and int(self.invuln * 12) % 2 == 0 and self.invuln > 0.25:
            pass                                     # 无敌闪烁
        else:
            draw_ship(surf, self.x, self.y, 15.0, (150, 235, 255), (40, 120, 180),
                      "arrow", angle=self.roll)
        # 引擎尾焰
        fl = 8 + 4 * math.sin(pygame.time.get_ticks() / 70.0)
        pygame.draw.polygon(surf, (255, 200, 120),
                            [(self.x - 5, self.y + 11), (self.x + 5, self.y + 11),
                             (self.x, self.y + 11 + fl)])
        if self.invuln > 0:
            pygame.draw.circle(surf, (140, 220, 255), (int(self.x), int(self.y)), 19, 1)


# ---------------------------------------------------------------------------
# 主游戏
# ---------------------------------------------------------------------------

class Game:
    """雷电第一关：时间轴刷怪 -> 清场 -> Boss 赤霄 -> MISSION COMPLETE。"""

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.reset()

    # -- 初始化 -----------------------------------------------------------
    def reset(self):
        self.bg = Starfield(self.rng)
        self.level = 1
        self.score = 0
        self.lives = PLAYER_LIVES
        self.bombs = PLAYER_START_BOMBS
        self.weapon = Weapon()
        self.player = Player(W / 2, H - 78)
        self.enemies = []
        self.bullets = []
        self.beams = []
        self.powerups = []
        self.explosions = []
        self.boss = None
        self.boss_spawned = False
        self.boss_intro_timer = 0.0
        self.t = 0.0
        self.timeline_index = 0
        self.state = "playing"          # playing / victory / game_over
        self.state_timer = 0.0
        self.paused = False
        self.respawn_timer = 0.0
        self.bomb_flash = 0.0
        self.kills = 0
        self.drop_counter = 0
        self.enemy_shots_fired = 0
        self._bomb_prev = False
        self.max_bullets_seen = 0
        self.phase_log = []

    # -- 工具 -------------------------------------------------------------
    def aim_from(self, x, y):
        p = self.player
        if p is None or not p.alive:
            return 0.0, 1.0
        dx, dy = p.x - x, p.y - y
        d = math.hypot(dx, dy) or 1.0
        return dx / d, dy / d

    def enemy_bullet(self, x, y, angle, speed, radius=4, color=(255, 180, 180), damage=1):
        b = Bullet(x, y, math.cos(angle) * speed, math.sin(angle) * speed,
                   damage=damage, is_player=False, radius=radius, color=color)
        self.enemy_shots_fired += 1
        self.bullets.append(b)
        return b

    def player_bullet(self, x, y, angle, speed, radius=3, color=C_YELLOW,
                      damage=1, kind="shot", homing=False, turn_rate=7.5):
        b = Bullet(x, y, math.cos(angle) * speed, math.sin(angle) * speed,
                   damage=damage, is_player=True, radius=radius, color=color,
                   kind=kind, homing=homing, turn_rate=turn_rate)
        self.bullets.append(b)
        return b

    def targets_for_homing(self):
        out = [(e.x, e.y) for e in self.enemies if e.alive]
        if self.boss is not None and self.boss.state in ("enter", "fight"):
            out.append((self.boss.x, self.boss.y))
        return out

    def spawn_enemy(self, kind, x=None, y=None):
        if x is None:
            if kind == "sine":
                x = self.rng.choice((78.0, W - 78.0)) + self.rng.uniform(-26, 26)
            elif kind == "spinner":
                x = self.rng.uniform(96.0, W - 96.0)
            elif kind == "turret":
                x = self.rng.uniform(76.0, W - 76.0)
            else:
                x = self.rng.uniform(44.0, W - 44.0)
        if y is None:
            y = -34.0
        e = Enemy(kind, x, y, self.rng)
        self.enemies.append(e)
        return e

    def spawn_wave(self):
        if self.timeline_index >= len(LEVEL1_TIMELINE):
            return False
        when, kind, count = LEVEL1_TIMELINE[self.timeline_index]
        if self.t < when:
            return False
        self.timeline_index += 1
        for i in range(count):
            x = None
            if kind == "sine":
                x = 78.0 + (W - 156.0) * ((i + 0.5) / count)
            elif kind == "scout":
                x = 40.0 + (W - 80.0) * ((i + 0.5) / count)
            self.spawn_enemy(kind, x=x, y=-34.0 - i * 52.0)
        return True

    def spawn_powerup(self, kind=None, x=None, y=None):
        if kind is None:
            kind = self._cycle_weapon_drop()
        pu = PowerUp(kind, x if x is not None else self.rng.uniform(60, W - 60),
                     y if y is not None else -16.0)
        self.powerups.append(pu)
        return pu

    def _cycle_weapon_drop(self):
        """第 1~3 个武器箱依次是 vulcan/homing/laser，第 4 个为炸弹或加命，如此循环。"""
        m = (max(1, self.drop_counter) - 1) % 4
        if m == 3:
            return self.rng.choice(("bomb", "life"))
        return WEAPON_KINDS[m]

    # -- 道具 / 升级规则 ---------------------------------------------------
    def apply_powerup(self, kind):
        """同种箱连吃三颗 1->2->3；异种箱切换种类并回到该种 1 级。"""
        if kind in WEAPON_KINDS:
            w = self.weapon
            if w.kind == kind:
                w.level = min(MAX_WEAPON_LEVEL, w.level + 1)
            else:
                w.kind = kind
                w.level = 1
            return w.kind, w.level
        if kind == "bomb":
            self.bombs = min(PLAYER_MAX_BOMBS, self.bombs + 1)
            return "bomb", self.bombs
        if kind == "life":
            self.lives += 1
            return "life", self.lives
        return "unknown", 0

    def use_bomb(self):
        if self.bombs <= 0 or self.state != "playing":
            return False
        self.bombs -= 1
        self.bomb_flash = 0.45
        cleared = len([b for b in self.bullets if not b.is_player])
        self.bullets = [b for b in self.bullets if b.is_player]
        for e in list(self.enemies):
            if e.alive:
                self.damage_enemy(e, 10.0)
        if self.boss is not None and self.boss.state in ("enter", "fight"):
            self.boss.damage(60.0)
        self.explosions.append(Explosion(self.player.x, self.player.y, r=200, dur=0.45,
                                         hue=(160, 220, 255)))
        return cleared

    # -- 伤害 -------------------------------------------------------------
    def damage_enemy(self, enemy, amount):
        if not enemy.alive:
            return False
        if enemy.damage(amount):
            self.destroy_enemy(enemy)
            return True
        return False

    def destroy_enemy(self, enemy):
        if not enemy.alive:
            return
        enemy.alive = False
        if enemy in self.enemies:                   # 立即移出战场，清场判定才准确
            self.enemies.remove(enemy)
        self.kills += 1
        self.score += enemy.score
        self.explosions.append(Explosion(enemy.x, enemy.y, r=enemy.r + 12))
        self.drop_counter += 1
        if enemy.kind == "turret" or self.drop_counter % 3 == 0:
            self.spawn_powerup(x=enemy.x, y=enemy.y)

    def hit_player(self):
        p = self.player
        if p is None or not p.alive or p.invuln > 0:
            return False
        p.alive = False
        self.lives -= 1
        self.explosions.append(Explosion(p.x, p.y, r=34, dur=0.5))
        if self.lives < 0:
            self.state = "game_over"
            self.player = None
        else:
            self.player = None
            self.respawn_timer = 1.3
        return True

    def damage_boss(self, amount):
        if self.boss is None:
            return False
        self.boss.damage(amount, self)
        return self.boss.state == "dying"

    # -- 武器 -------------------------------------------------------------
    def _fire_weapon(self, dt, inp=None):
        p = self.player
        if p is None or not p.alive:
            self.beams = []
            return
        held = bool((inp or {}).get("fire"))
        w = self.weapon
        if w.kind == "laser":                       # 按住开火键 -> 持续光束
            if not held:
                self.beams = []
                return
            self.beams = [Beam(off, wid, dps, w.level) for (off, wid, dps) in LASER_SPECS[w.level]]
            for bm in self.beams:
                bm.update(dt)
            return
        self.beams = []
        if not held:
            w.cooldown = min(w.cooldown, 0.0)
            return
        w.cooldown -= dt
        if w.cooldown > 0:
            return
        w.cooldown = w.cd_for_level()
        up = -math.pi / 2
        if w.kind == "vulcan":
            for off in VULCAN_SPECS[w.level]:
                self.player_bullet(p.x, p.y - 14, up + off, 585, radius=3,
                                   color=C_YELLOW, damage=1, kind="shot")
        elif w.kind == "homing":
            turn = 6.5 + 1.6 * w.level
            for (dx, off) in HOMING_SPECS[w.level]:
                self.player_bullet(p.x + dx, p.y - 8, up + off, 330, radius=5,
                                   color=(120, 240, 150), damage=2, kind="missile",
                                   homing=True, turn_rate=turn)

    def _apply_laser_damage(self, dt):
        if not self.beams:
            return
        p = self.player
        if p is None or not p.alive:
            return
        for bm in self.beams:
            rect = bm.rect(p)
            for e in list(self.enemies):
                if not e.alive:
                    continue
                cx = clamp(e.x, rect.left, rect.right)
                cy = clamp(e.y, rect.top, rect.bottom)
                if (e.x - cx) ** 2 + (e.y - cy) ** 2 <= e.r ** 2:
                    self.damage_enemy(e, bm.dps * dt)
            if self.boss is not None and self.boss.state in ("enter", "fight"):
                bo = self.boss
                if rect.left - bo.r * 0.85 <= bo.x <= rect.right + bo.r * 0.85 and bo.y < p.y:
                    self.damage_boss(bm.dps * dt)

    # -- 碰撞 -------------------------------------------------------------
    def _collide(self):
        p = self.player
        targets = [e for e in self.enemies if e.alive]
        for b in self.bullets:
            if not b.alive:
                continue
            if b.is_player:
                for e in targets:
                    if not e.alive:
                        continue
                    if (b.x - e.x) ** 2 + (b.y - e.y) ** 2 <= (e.r + b.radius) ** 2:
                        b.alive = False
                        self.damage_enemy(e, b.damage)
                        break
                else:
                    bo = self.boss
                    if bo is not None and bo.state in ("enter", "fight"):
                        if abs(b.x - bo.x) < bo.r * 0.95 and abs(b.y - bo.y) < bo.r * 0.95:
                            b.alive = False
                            self.damage_boss(b.damage)
            else:
                if p is not None and p.alive and p.invuln <= 0:
                    if (b.x - p.x) ** 2 + (b.y - p.y) ** 2 <= (p.r + b.radius) ** 2:
                        b.alive = False
                        self.hit_player()
        # 机体碰撞
        if p is not None and p.alive and p.invuln <= 0:
            for e in targets:
                if (p.x - e.x) ** 2 + (p.y - e.y) ** 2 <= (e.r + p.r) ** 2:
                    self.damage_enemy(e, 6)
                    self.hit_player()
                    break
            bo = self.boss
            if bo is not None and bo.state in ("enter", "fight") and \
                    (p.x - bo.x) ** 2 + (p.y - bo.y) ** 2 <= (bo.r * 0.8 + p.r) ** 2:
                self.hit_player()

    # -- 主循环 -----------------------------------------------------------
    def update(self, dt, inp=None):
        dt = min(dt, 0.05)
        inp = inp or {}
        if self.state in ("victory", "game_over"):
            self.state_timer += dt
            self.explosions = [e for e in self.explosions if e.update(dt)]
            self.bg.update(dt)
            return
        if self.paused:
            return

        self.t += dt
        self.bg.update(dt)
        if self.bomb_flash > 0:
            self.bomb_flash = max(0.0, self.bomb_flash - dt)

        # 刷怪时间轴
        if self.spawn_wave():
            pass
        while self.spawn_wave():
            pass

        # 玩家
        if self.player is None:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0 and self.lives >= 0:
                self.player = Player(W / 2, H - 78)
                self.weapon.level = 1                  # 阵亡后弹药降为 1 级（保留种类）
        else:
            bomb_held = bool(inp.get("bomb"))
            if bomb_held and not self._bomb_prev:
                self.use_bomb()
            self._bomb_prev = bomb_held
            self.player.move(self, dt, inp)
        self._fire_weapon(dt, inp)
        self._apply_laser_damage(dt)

        # 敌机 / Boss
        for e in self.enemies:
            if e.alive:
                e.update(self, dt)
        self.enemies = [e for e in self.enemies if e.alive]
        if self.boss is not None:
            self.boss.update(self, dt)
            if self.boss.phase not in self.phase_log:
                self.phase_log.append(self.boss.phase)
            if self.boss.state == "dead":
                self.state = "victory"
                self.state_timer = 0.0
                self.score += 5000
                self.boss = None

        # Boss 入场
        if not self.boss_spawned and self.timeline_index >= len(LEVEL1_TIMELINE) and not self.enemies:
            self.boss_intro_timer += dt
            if self.boss_intro_timer >= BOSS_SPAWN_DELAY:
                self.boss = Boss()
                self.boss_spawned = True

        # 弹丸
        homing_targets = self.targets_for_homing()
        for b in self.bullets:
            b.update(dt, homing_targets)
        self.bullets = [b for b in self.bullets if b.alive]
        self.max_bullets_seen = max(self.max_bullets_seen, len(self.bullets))
        self._collide()

        # 道具
        for pu in self.powerups:
            pu.update(dt)
        if self.player is not None and self.player.alive:
            for pu in list(self.powerups):
                if (pu.x - self.player.x) ** 2 + (pu.y - self.player.y) ** 2 <= \
                        (pu.radius + 15) ** 2:
                    self.apply_powerup(pu.kind)
                    self.powerups.remove(pu)
        self.powerups = [pu for pu in self.powerups if pu.y < H + 30]

        self.explosions = [e for e in self.explosions if e.update(dt)]

    # -- 调试 / 测试钩子 ---------------------------------------------------
    def skip_to_boss(self):
        """跳过时间轴，直接进入 Boss 战（测试与调试用）。"""
        self.timeline_index = len(LEVEL1_TIMELINE)
        for e in self.enemies:
            e.alive = False
        self.enemies = []
        self.bullets = []
        self.boss = Boss()
        self.boss_spawned = True
        return self.boss


# ---------------------------------------------------------------------------

# 渲染（全部几何图元 + 程序化背景）
# ---------------------------------------------------------------------------

def draw_hud(surf, game, font):
    bar = pygame.Rect(0, 0, W, 30)
    strip = pygame.Surface((W, 30), pygame.SRCALPHA)
    strip.fill((0, 0, 0, 130))
    surf.blit(strip, (0, 0))
    pygame.draw.line(surf, (70, 90, 130), (0, 30), (W, 30), 1)

    for i in range(max(0, game.lives)):                  # 剩余机体
        draw_ship(surf, 14 + i * 17, 15, 7.0, (150, 235, 255), (40, 120, 180), "arrow")
    for i in range(game.bombs):                          # 剩余炸弹
        bx = W - 18 - i * 15
        pygame.draw.circle(surf, (255, 130, 120), (bx, 15), 5)
        pygame.draw.circle(surf, (255, 240, 220), (bx, 15), 5, 1)
    if font is not None:
        surf.blit(font.render("SCORE %07d" % game.score, True, C_HUD), (104, 4))
        wcol = {"vulcan": C_YELLOW, "homing": (120, 240, 150), "laser": C_LASER}[game.weapon.kind]
        surf.blit(font.render("WEAPON %s" % game.weapon.label, True, wcol), (104, 17))
        surf.blit(font.render("STAGE 1-1", True, C_DIM), (W - 96, 17))

    if game.boss is not None:                            # Boss 血条
        bo = game.boss
        bw = W - 96
        bx = 48
        by = 36
        pygame.draw.rect(surf, (26, 20, 30), (bx - 2, by - 2, bw + 4, 14))
        pygame.draw.rect(surf, (90, 70, 100), (bx - 2, by - 2, bw + 4, 14), 1)
        ratio = bo.hp_ratio
        col = (240, 90, 200) if ratio > 0.33 else (255, 90, 90)
        pygame.draw.rect(surf, col, (bx, by, int(bw * ratio), 10))
        pygame.draw.rect(surf, (255, 220, 255), (bx, by, int(bw * ratio), 3))
        for th in BOSS_PHASE_THRESHOLDS:                 # 阶段刻度
            tx = bx + int(bw * th)
            pygame.draw.line(surf, (20, 10, 20), (tx, by), (tx, by + 9), 2)
        if font is not None:
            surf.blit(font.render("赤霄 CHIXIAO", True, (255, 210, 245)), (bx, by + 12))
            surf.blit(font.render("PHASE %d/3" % bo.phase, True, (255, 210, 245)),
                      (bx + bw - 62, by + 12))


def render(surf, game, font=None):
    surf.fill(C_SPACE)
    if game.bomb_flash > 0:
        surf.fill((40, 50, 80))
    overlay = getattr(game, "_overlay", None)
    if overlay is None:
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        game._overlay = overlay
    game.bg.draw(surf, overlay)

    for pu in game.powerups:
        pu.draw(surf)
    for e in game.enemies:
        e.draw(surf)
    if game.boss is not None:
        game.boss.draw(surf)
    for b in game.bullets:
        b.draw(surf)
    for bm in game.beams:
        if game.player is not None:
            bm.draw(surf, game.player)
    if game.player is not None:
        game.player.draw(surf)
    for ex in game.explosions:
        ex.draw(surf)

    draw_hud(surf, game, font)

    if game.bomb_flash > 0:                              # 炸弹白闪
        flash = pygame.Surface((W, H), pygame.SRCALPHA)
        flash.fill((200, 230, 255, int(150 * min(1.0, game.bomb_flash / 0.45))))
        surf.blit(flash, (0, 0))
    if game.paused:
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        surf.blit(dim, (0, 0))
        if font is not None:
            surf.blit(font.render("PAUSE  (P 继续)", True, (255, 255, 255)), (W // 2 - 52, H // 2))
    if game.state in ("victory", "game_over"):
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 130))
        surf.blit(dim, (0, 0))
        if font is not None:
            big = pygame.font.Font(None, 44)
            msg = "MISSION COMPLETE" if game.state == "victory" else "GAME OVER"
            col = (255, 230, 140) if game.state == "victory" else (255, 130, 130)
            surf.blit(big.render(msg, True, col), (W // 2 - big.size(msg)[0] // 2, H // 2 - 40))
            surf.blit(font.render("SCORE %07d" % game.score, True, C_HUD),
                      (W // 2 - 48, H // 2 + 4))
            surf.blit(font.render("press R to retry", True, C_DIM), (W // 2 - 48, H // 2 + 26))
    return surf


# ---------------------------------------------------------------------------

# 自检（--test，无界面）
# ---------------------------------------------------------------------------

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def _quiet(game):
    """抑制时间轴刷怪与 Boss 自动入场，便于单点观测。"""
    game.timeline_index = len(LEVEL1_TIMELINE)
    game.boss_spawned = True
    return game


def _step(game, frames, inp=None):
    for _ in range(frames):
        game.update(DT, inp or {})


def _track(kind, frames, x=W / 2, seed=11, player_x=W / 2):
    g = _quiet(Game(seed=seed))
    g.enemies = []
    g.player.x = player_x
    e = g.spawn_enemy(kind, x=x, y=-34.0)
    pts = []
    for _ in range(frames):
        g.update(DT, {})
        pts.append((e.x, e.y))
    return g, e, pts


def _signature(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    path = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
               for i in range(1, len(pts)))
    steps = [math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
             for i in range(1, len(pts))]
    return dict(xrange=max(xs) - min(xs), yrange=max(ys) - min(ys), path=path,
                top=max(steps) if steps else 0.0,
                avg_vy=(ys[-1] - ys[0]) / max(1e-6, (len(pts) - 1) * DT))


def _enemy_bullets(game):
    return [b for b in game.bullets if not b.is_player]


@test
def t_background_parallax():
    g = Game(seed=3)
    layers = g.bg.layers
    assert len(layers) >= 3, "需要至少 3 层视差星空，实际 %d" % len(layers)
    speeds = [l["speed"] for l in layers]
    assert speeds == sorted(speeds) and speeds[0] < speeds[-1], "层速应递增: %s" % speeds
    total = sum(len(l["stars"]) for l in layers)
    assert total >= 40, "星点太少: %d" % total
    before = [[s[1] for s in l["stars"]] for l in layers]
    neb_y = [n["y"] for n in g.bg.nebulae]
    planet_y = g.bg.planet["y"]
    for _ in range(60):
        g.bg.update(DT)
    for li, l in enumerate(layers):
        deltas = [(s[1] - b) % H for s, b in zip(l["stars"], before[li])]
        avg = sum(deltas) / len(deltas)
        expect = l["speed"] * DT * 60
        assert abs(avg - expect) < expect * 0.3 + 2.0, \
            "层%d 平均位移 %.2f != %.2f" % (li, avg, expect)
    assert all(0.0 <= s[1] <= H and 0.0 <= s[0] <= W for l in layers for s in l["stars"]), \
        "星点越界"
    assert all(n["y"] > ny for n, ny in zip(g.bg.nebulae, neb_y)), "星云未下移"
    assert g.bg.planet["y"] > planet_y, "行星未下移"
    return "3 层视差 (%s px/s) + %d 星点 + 星云/行星滚动均正常" % \
           ("/".join("%.0f" % s for s in speeds), total)


@test
def t_enemy_types_variety():
    assert len(ENEMY_SPECS) >= 5, "敌机种类不足 5: %d" % len(ENEMY_SPECS)
    behavior = set()
    pattern = set()
    look = set()
    for kind, spec in ENEMY_SPECS.items():
        behavior.add(spec["behavior"])
        pattern.add(spec["pattern"])
        look.add((spec["hp"], spec["radius"], spec["color"]))
        assert spec["hp"] >= 1 and spec["score"] > 0 and spec["radius"] > 4
    assert len(behavior) == len(ENEMY_SPECS), "移动轨迹不唯一: %s" % behavior
    assert len(pattern) == len(ENEMY_SPECS), "弹幕模式不唯一: %s" % pattern
    assert len(look) == len(ENEMY_SPECS), "外观/血量不唯一"
    return "%d 种敌机，%d 种轨迹，%d 种弹幕，血量/外观互不相同" % (
        len(ENEMY_SPECS), len(behavior), len(pattern))


@test
def t_enemy_movement_patterns():
    frames = {"scout": 220, "sine": 480, "diver": 220, "gunner": 480,
              "turret": 480, "spinner": 480}
    sig = {}
    for kind in ENEMY_SPECS:
        g, e, pts = _track(kind, frames[kind],
                           x=60.0 if kind == "diver" else W / 2, player_x=W / 2)
        s = _signature(pts)
        sig[kind] = s
        assert s["path"] > 40.0, "%s 几乎没有移动 (%.1f)" % (kind, s["path"])

    assert sig["scout"]["avg_vy"] > 150, "侦察机应高速俯冲: %.1f" % sig["scout"]["avg_vy"]
    assert sig["scout"]["xrange"] < 90, "侦察机只做微摆: %.1f" % sig["scout"]["xrange"]
    assert sig["sine"]["xrange"] >= 110, "波形机横向扫掠不足: %.1f" % sig["sine"]["xrange"]
    assert 30 < sig["sine"]["avg_vy"] < 80, "波形机下降速度异常: %.1f" % sig["sine"]["avg_vy"]
    assert sig["diver"]["top"] > 4.5, "俯冲机缺少 φ 冲刺: %.2f px/帧" % sig["diver"]["top"]
    assert sig["diver"]["xrange"] > 70, \
        "俯冲机未追踪玩家: %.1f" % sig["diver"]["xrange"]
    g_g, e_g, pts_g = _track("gunner", 480)
    assert abs(pts_g[-1][1] - 96.0) < 8.0, "机枪机应驻留 y≈96: %.1f" % pts_g[-1][1]
    rev = sum(1 for i in range(2, len(pts_g))
              if (pts_g[i][0] - pts_g[i - 1][0]) * (pts_g[i - 1][0] - pts_g[i - 2][0]) < 0)
    assert sig["gunner"]["xrange"] > 120 and rev >= 2, \
        "机枪机应在横向弹跳 (宽度%.1f, 反向%d)" % (sig["gunner"]["xrange"], rev)
    g_t, e_t, pts_t = _track("turret", 480)
    assert abs(pts_t[-1][1] - 150.0) < 12.0, "炮台机应停在 y≈150: %.1f" % pts_t[-1][1]
    tail = _signature(pts_t[-120:])
    assert tail["path"] < 60.0 and sig["turret"]["xrange"] < 25.0, \
        "炮台机到位后应基本静止 (尾段%.1f, 横移%.1f)" % (tail["path"], sig["turret"]["xrange"])
    assert sig["spinner"]["xrange"] > 100, "螺旋机应做圆周环绕: %.1f" % sig["spinner"]["xrange"]

    keys = [(round(s["avg_vy"] / 20.0), round(s["xrange"] / 20.0), round(s["top"], 1))
            for s in sig.values()]
    assert len(set(keys)) == len(keys), "各机型轨迹特征重复: %s" % keys
    return "轨迹特征互异 侦察%.0fpx/s 波形±%.0fpx 俯冲%.1fpx/帧 机枪弹跳%d次 炮台静止 螺旋环绕%.0fpx" % (
        sig["scout"]["avg_vy"], sig["sine"]["xrange"] / 2, sig["diver"]["top"], rev,
        sig["spinner"]["xrange"])


@test
def t_enemy_retreat_clears_field():
    """悬停型敌机也会超时撤离，战线必定清空 -> Boss 必定能入场（不会卡关）。"""
    g = _quiet(Game(seed=3))
    g.player.invuln = 99.0
    for kind in ENEMY_SPECS:
        g.spawn_enemy(kind, x=W / 2, y=-20)
    assert len(g.enemies) == len(ENEMY_SPECS), "刷怪失败"
    _step(g, 16 * FPS)
    assert not g.enemies, "敌机未在悬停超时后撤离: %s" % \
        [(e.kind, round(e.y), round(e.t, 1)) for e in g.enemies]
    return "%d 种机型悬停超时后都会撤离（<16s 清场，杜绝卡关）" % len(ENEMY_SPECS)


@test
def t_enemy_bullet_patterns():
    frames = 480
    total = {}
    volley = {}
    bins = {}
    for kind in ("scout", "sine", "diver", "gunner", "turret", "spinner"):
        g = _quiet(Game(seed=5))
        g.enemies = []
        g.player.invuln = 99.0
        g.spawn_enemy(kind, x=W / 2, y=-20)
        prev_shots = g.enemy_shots_fired
        vols = []
        angs = set()
        for _ in range(frames):
            g.update(DT, {})
            fired = g.enemy_shots_fired - prev_shots      # 每帧真实开火数（不受弹丸寿命影响）
            if fired:
                vols.append(fired)
            prev_shots = g.enemy_shots_fired
            for b in _enemy_bullets(g):
                angs.add(round(math.atan2(b.vy, b.vx) / (math.pi / 6)))
        total[kind] = g.enemy_shots_fired
        volley[kind] = max(vols) if vols else 0
        bins[kind] = len(angs)

    assert total["scout"] == 0, "侦察机不应开火: %d" % total["scout"]
    assert volley["sine"] == 3 and total["sine"] >= 6, \
        "波形机应为三向扇形: volley=%d total=%d" % (volley["sine"], total["sine"])
    assert volley["diver"] >= 1 and total["diver"] == 3, \
        "俯冲机应俯冲瞬间三连点射: %d" % total["diver"]
    assert volley["gunner"] == 2 and total["gunner"] >= 8, \
        "机枪机应为双发高频点射: %d/%d" % (volley["gunner"], total["gunner"])
    assert volley["turret"] >= 10 and bins["turret"] >= 8, \
        "炮台机应为环形弹幕: volley=%d 方向%d" % (volley["turret"], bins["turret"])
    assert total["spinner"] >= 12 and bins["spinner"] >= 6, \
        "螺旋机应为旋转弹流: total=%d 方向%d" % (total["spinner"], bins["spinner"])
    return "弹幕各具特色 三向扇形/俯冲三段/双发点射/12向环形/旋转螺旋"

@test
def t_weapon_vulcan_wide():
    counts = []
    spreads = []
    for lvl in (1, 2, 3):
        g = _quiet(Game(seed=1))
        g.weapon = Weapon("vulcan", lvl)
        g.weapon.cooldown = 0.0
        g.bullets = []
        g._fire_weapon(DT, {"fire": True})
        shots = [b for b in g.bullets if b.is_player]
        angs = sorted(math.atan2(b.vy, b.vx) for b in shots)
        counts.append(len(shots))
        spreads.append(angs[-1] - angs[0])
        assert all(b.kind == "shot" and b.color == C_YELLOW for b in shots), "机枪弹外观异常"
    assert counts == [3, 5, 7], "黄色机枪子弹数应为 3/5/7: %s" % counts
    assert spreads[0] < spreads[1] < spreads[2], "覆盖角度应递增: %s" % spreads
    g = _quiet(Game(seed=1))
    g.weapon = Weapon("vulcan", 3)
    g.weapon.cooldown = 0.0
    g.bullets = []
    g._fire_weapon(DT, {"fire": True})
    n1 = len(g.bullets)
    g._fire_weapon(DT, {"fire": True})
    assert len(g.bullets) == n1, "同一帧不应重复射击（冷却生效）"
    return "黄色机枪 3/5/7 发，覆盖 %.2f/%.2f/%.2f rad" % tuple(spreads)


@test
def t_weapon_homing_tracks():
    for lvl, want in ((1, 1), (2, 2), (3, 3)):
        g = _quiet(Game(seed=1))
        g.weapon = Weapon("homing", lvl)
        g.weapon.cooldown = 0.0
        g.bullets = []
        g._fire_weapon(DT, {"fire": True})
        shots = [b for b in g.bullets if b.is_player]
        assert len(shots) == want, "跟踪导弹数量 %d != %d" % (len(shots), want)
        assert all(b.homing and b.kind == "missile" for b in shots), "导弹属性异常"

    g = _quiet(Game(seed=1))
    g.weapon = Weapon("homing", 1)
    g.weapon.cooldown = 0.0
    g.bullets = []
    g.player.invuln = 99.0
    g._fire_weapon(DT, {"fire": True})
    m = [b for b in g.bullets if b.is_player][0]
    m0x = m.x
    ctrl = g.player_bullet(m.x, m.y, -math.pi / 2, 330, kind="shot")   # 同速直射对照弹
    e = g.spawn_enemy("turret", x=g.player.x + 130, y=150)             # 悬停靶机
    for _ in range(90):
        g.update(DT, {})
    drift = m.x - ctrl.x                              # 追踪弹相对直射弹的横向偏转
    assert abs(drift) > 40.0, "导弹未转向目标（横向偏转 %.1f px）" % drift
    assert abs(ctrl.x - m0x) < 2.0, "对照直射弹不应偏转"
    assert e.hp < e.max_hp or not e.alive, "导弹未命中目标 (hp=%s)" % e.hp
    return "跟踪导弹 1/2/3 发，锁定偏转 %.0fpx 并命中" % abs(drift)


@test
def t_weapon_laser_pierce():
    dps = []
    widths = []
    for lvl in (1, 2, 3):
        g = _quiet(Game(seed=1))
        g.weapon = Weapon("laser", lvl)
        g.update(DT, {"fire": True})
        assert len(g.beams) == len(LASER_SPECS[lvl]), "激光束数异常 lvl%d" % lvl
        dps.append(sum(b.dps for b in g.beams))
        widths.append(max(b.width for b in g.beams))
        assert all(b.level == lvl for b in g.beams)
    assert dps[0] < dps[1] < dps[2], "激光 DPS 应递增: %s" % dps
    assert widths[1] > widths[0], "二级激光应更粗: %s" % widths

    g = _quiet(Game(seed=1))
    g.weapon = Weapon("laser", 2)
    g.player.invuln = 99.0
    g.bullets = []
    e1 = g.spawn_enemy("turret", x=g.player.x, y=200)
    e2 = g.spawn_enemy("turret", x=g.player.x, y=360)
    g.update(DT, {"fire": True})
    assert e1.hp < e1.max_hp and e2.hp < e2.max_hp, \
        "激光应贯穿一条直线上的多个目标 (%.1f/%.1f)" % (e1.hp, e2.hp)
    g.weapon = Weapon("laser", 3)
    g.update(DT, {"fire": False})
    assert g.beams == [], "松开开火键后光束应消失"
    return "激光 DPS %s，一级贯穿 2 个目标" % ("/".join("%.0f" % d for d in dps))


@test
def t_upgrade_rule_three_same():
    g = _quiet(Game(seed=1))
    assert (g.weapon.kind, g.weapon.level) == ("vulcan", 1), "初始武器应为 vulcan-1"
    seq = [
        ("vulcan", ("vulcan", 2)),
        ("vulcan", ("vulcan", 3)),
        ("vulcan", ("vulcan", 3)),          # 满级封顶
        ("homing", ("homing", 1)),          # 换种类 -> 回到 1 级
        ("homing", ("homing", 2)),
        ("homing", ("homing", 3)),
        ("laser", ("laser", 1)),
        ("laser", ("laser", 2)),
        ("vulcan", ("vulcan", 1)),          # 切回旧种类也必须从 1 级开始
        ("vulcan", ("vulcan", 2)),
        ("laser", ("laser", 1)),
    ]
    for kind, want in seq:
        got = g.apply_powerup(kind)
        assert got == want, "吃 %s 后应为 %s，实际 %s" % (kind, want, got)
    assert MAX_WEAPON_LEVEL == 3
    return "同种 3 连吃满级(1->2->3)，异种切换归 1 级，切回不记忆 (共 %d 步)" % len(seq)


@test
def t_powerup_drop_cycle_and_pickup():
    g = _quiet(Game(seed=1))
    g.enemies = []
    g.drop_counter = 0
    kinds = []
    for _ in range(3):
        g.drop_counter += 1
        kinds.append(g._cycle_weapon_drop())
    assert set(kinds) == set(WEAPON_KINDS), "前 3 个箱子应覆盖三种升级: %s" % kinds
    g.drop_counter = 3
    g.drop_counter += 1
    assert g._cycle_weapon_drop() in ("bomb", "life"), "第 4 个应为炸弹/加命"

    g = _quiet(Game(seed=1))
    g.enemies = []
    turret = g.spawn_enemy("turret", x=120, y=200)
    g.damage_enemy(turret, 99)
    assert len(g.powerups) == 1, "炮台机应必掉道具"
    assert g.powerups[0].kind in WEAPON_KINDS

    g = _quiet(Game(seed=1))
    g.enemies = []
    g.powerups = []
    for i in range(3):
        e = g.spawn_enemy("scout", x=60 + i * 40, y=120)
        g.damage_enemy(e, 99)
    assert len(g.powerups) == 1, "每 3 杀应掉落 1 个道具，实际 %d" % len(g.powerups)

    # 真实拾取：把箱子放到玩家身上
    g = _quiet(Game(seed=1))
    g.powerups = []
    box = g.spawn_powerup("laser", x=g.player.x, y=g.player.y)
    g.player.invuln = 99.0
    g.update(DT, {})
    assert box not in g.powerups, "碰到箱子应被拾取"
    assert (g.weapon.kind, g.weapon.level) == ("laser", 1), \
        "拾取后武器应为 laser-1，实际 %s" % (g.weapon.kind,)
    return "掉落循环覆盖三系升级 + 炮台必掉 + 3 杀 1 掉 + 实体拾取生效"


@test
def t_powerup_bomb_and_life():
    g = _quiet(Game(seed=1))
    g.bombs = 2
    assert g.apply_powerup("bomb") == ("bomb", 3)
    assert g.apply_powerup("bomb") == ("bomb", 4)
    assert g.apply_powerup("bomb") == ("bomb", 5)
    assert g.apply_powerup("bomb") == ("bomb", PLAYER_MAX_BOMBS), "炸弹上限 %d" % PLAYER_MAX_BOMBS
    lives0 = g.lives
    assert g.apply_powerup("life") == ("life", lives0 + 1)
    return "炸弹上限 %d，加命道具生效" % PLAYER_MAX_BOMBS


@test
def t_bomb_clears_screen():
    g = _quiet(Game(seed=1))
    g.enemies = []
    g.bullets = []
    g.player.invuln = 99.0
    for i in range(30):
        g.enemy_bullet(20 + i * 12, 120, math.pi / 2, 150)
    for i in range(3):
        g.player_bullet(g.player.x, g.player.y - 10, -math.pi / 2, 500)
    e = g.spawn_enemy("scout", x=100, y=200)
    g.bullets.append(Bullet(0, 0, 0, 0, is_player=True))       # 混合弹幕
    bombs0 = g.bombs
    cleared = g.use_bomb()
    assert cleared == 30, "应清空 30 发敌弹，实际 %d" % cleared
    assert e not in g.enemies and not e.alive, "炸弹应击杀脆皮敌机"
    assert g.bombs == bombs0 - 1, "炸弹数量应 -1"
    assert g.bomb_flash > 0, "炸弹应产生白闪"
    assert sum(1 for b in g.bullets if b.is_player) == 4, "己方弹幕不应被清除"
    g.bombs = 0
    assert g.use_bomb() is False, "无炸弹时不应生效"
    return "全屏炸弹：清除 30 发敌弹、秒杀杂兵、留下己方弹幕、数量 -1"


@test
def t_player_damage_lives_invuln():
    g = _quiet(Game(seed=1))
    p = g.player
    p.invuln = 0.0
    g.enemy_bullet(p.x, p.y, 0.0, 120)
    g.update(DT, {})
    assert g.lives == PLAYER_LIVES - 1, "中弹应掉命: %d" % g.lives
    assert g.player is None, "中弹后应进入复活等待"
    _step(g, 120)
    assert g.player is not None, "应在约 1.3s 后复活"
    assert g.player.invuln > 0, "复活后应有短暂无敌"
    assert g.weapon.level == 1, "阵亡复活后弹药应降为 1 级"

    lives = g.lives
    assert g.player is not None
    g.enemy_bullet(g.player.x, g.player.y, 0.0, 120)
    g.update(DT, {})
    assert g.lives == lives and g.player is not None, "无敌时间内不应再次中弹"

    guard = 0
    while g.state == "playing" and guard < 4000:
        guard += 1
        if g.player is None:
            _step(g, 2)
            continue
        g.player.invuln = 0.0
        g.enemy_bullet(g.player.x, g.player.y, 0.0, 120)
        g.update(DT, {})
    assert g.state == "game_over", "生命耗尽应 game over（lives=%d）" % g.lives
    assert g.lives < 0 and g.player is None
    return "3 条命 + 复活无敌 %.1fs + 生命耗尽 game over" % RESPAWN_INVULN


@test
def t_boss_spawns_from_timeline_and_win():
    assert all(LEVEL1_TIMELINE[i][0] < LEVEL1_TIMELINE[i + 1][0]
               for i in range(len(LEVEL1_TIMELINE) - 1)), "时间轴必须严格递增"
    g = Game(seed=9)
    kinds = set()
    boss_frame = None
    win_frame = None
    shots_ok = True
    for f in range(9000):
        inp = {"fire": True}
        if (f // 23) % 4 == 0:
            inp["left"] = True
        elif (f // 31) % 4 == 1:
            inp["right"] = True
        g.update(DT, inp)
        kinds.update(e.kind for e in g.enemies)
        if g.player is not None:
            g.player.invuln = max(g.player.invuln, 5.0)
            g.lives = max(g.lives, 1)
        if g.boss is not None and boss_frame is None:
            boss_frame = f
        if boss_frame is not None and g.boss is not None:
            if g.boss.state == "fight":             # 只砸已入场的 Boss，避免它未入场就被秒
                if not g.boss.shots_fired:
                    shots_ok = False
                g.damage_boss(6.0)
        if g.state == "victory":
            win_frame = f
            break
    assert boss_frame is not None, "时间轴清场后 Boss 未自动入场"
    assert win_frame is not None, "未能通关（state=%s, boss=%s）" % (g.state, g.boss)
    assert shots_ok, "Boss 入场后应立即开火"
    assert g.boss is None, "Boss 击破后应清空"
    assert {2, 3}.issubset(set(g.phase_log)), "应经历 2、3 阶段: %s" % g.phase_log
    assert len(kinds) >= 5, "第一关应出现至少 5 种敌机，实际 %s" % sorted(kinds)
    assert g.level == 1, "只应存在第一关"
    return "时间轴 %d 波 -> Boss 自然入场(第 %d 帧) -> 三阶段 -> 通关(第 %d 帧, %.1fs)" % (
        len(LEVEL1_TIMELINE), boss_frame, win_frame, win_frame * DT)


@test
def t_boss_three_phases():
    g = Game(seed=4)
    bo = g.skip_to_boss()
    g.player.invuln = 1e9
    assert bo.max_hp == BOSS_MAX_HP and bo.hp == BOSS_MAX_HP
    assert bo.phase_for(1.0) == 1 and bo.phase_for(0.66) == 2, "阶段阈值应为 66%%"
    assert bo.phase_for(0.33) == 3 and bo.phase_for(0.01) == 3
    _step(g, 240, {})
    assert bo.state == "fight", "Boss 应完成入场: %s" % bo.state
    assert bo.phase == 1

    def probe(frames):
        g.bullets = []
        maxvol = 0
        for _ in range(frames):
            prev = len(_enemy_bullets(g))
            g.update(DT, {})
            maxvol = max(maxvol, len(_enemy_bullets(g)) - prev)
        eb = _enemy_bullets(g)
        return dict(maxvol=maxvol, n=len(eb),
                    colors=set(tuple(b.color) for b in eb),
                    speed=max([math.hypot(b.vx, b.vy) for b in eb] or [0.0]))

    p1 = probe(300)
    assert p1["maxvol"] >= 12 and p1["n"] >= 14, \
        "阶段1 应为瞄准散射 + 14 向环形: volley=%d n=%d" % (p1["maxvol"], p1["n"])

    bo.hp = int(BOSS_MAX_HP * 0.60)
    g.update(DT, {})
    assert bo.phase == 2 and bo.state == "fight", "血量 60%% 应进入阶段2"
    assert bo.invuln > 0, "转阶段应有短暂无敌"
    p2 = probe(300)
    assert p2["maxvol"] >= 3 and p2["n"] >= 20, \
        "阶段2 应为螺旋弹流 + 侧舷下落弹: volley=%d n=%d" % (p2["maxvol"], p2["n"])

    bo.hp = int(BOSS_MAX_HP * 0.30)
    g.update(DT, {})
    assert bo.phase == 3, "血量 30%% 应进入阶段3"
    p3 = probe(400)
    assert p3["maxvol"] >= 20, "阶段3 应有 24 向密集爆发: volley=%d" % p3["maxvol"]

    assert p1["colors"] and p2["colors"] and p3["colors"]
    assert p1["colors"] != p2["colors"] != p3["colors"], "各阶段弹幕应不同配色/模式"
    assert p1["speed"] < p2["speed"] < p3["speed"], \
        "阶段越高弹速越快: %s" % [p1["speed"], p2["speed"], p3["speed"]]
    assert bo.phase_events == [2, 3], "转阶段事件应为 [2,3]: %s" % bo.phase_events
    return "Boss 三阶段：环+散射 -> 螺旋+侧舷 -> 24向爆发，弹速 %.0f/%.0f/%.0f" % (
        p1["speed"], p2["speed"], p3["speed"])


@test
def t_boss_health_bar_render():
    surf = pygame.display.get_surface()
    g = Game(seed=2)
    bo = g.skip_to_boss()
    bo.state = "fight"
    bo.y = BOSS_ENTRY_Y
    font = pygame.font.Font(None, 18)

    def bar_pixels():
        render(surf, g, font)
        n = 0
        y = 41
        for x in range(48, W - 48, 2):
            c = surf.get_at((x, y))
            if c.r > 180 and c.b > 140:
                n += 1
        return n

    bo.hp = bo.max_hp
    full = bar_pixels()
    bo.hp = int(bo.max_hp * 0.3)
    low = bar_pixels()
    assert full > 50, "满血血条应可见: %d" % full
    assert low < full * 0.6, "低血血条应明显变短: %d vs %d" % (low, full)
    return "Boss 血条随血量收缩：满血 %d px -> 30%% %d px（含阶段刻度）" % (full, low)


@test
def t_boss_defeat_victory():
    g = Game(seed=2)
    bo = g.skip_to_boss()
    bo.state = "fight"
    bo.y = BOSS_ENTRY_Y
    g.player.invuln = 1e9
    score0 = g.score
    g.damage_boss(1e6)
    assert bo.state == "dying", "血量归零应进入爆炸序列: %s" % bo.state
    guard = 0
    while g.state != "victory" and guard < 600:
        guard += 1
        g.update(DT, {})
    assert g.state == "victory", "Boss 爆炸后应通关: %s" % g.state
    assert g.boss is None and g.level == 1
    assert g.score == score0 + 5000, "击破 Boss 应加分: %d" % (g.score - score0)
    _step(g, 300, {"fire": True})
    assert g.state == "victory", "通关后不应再进入下一关/重置"
    return "Boss 击破 -> 爆炸序列 -> MISSION COMPLETE (+5000 分，无第二关)"


@test
def t_only_one_stage():
    assert len(LEVEL1_TIMELINE) >= 10, "第一关波次过少"
    assert max(t for t, _k, _c in LEVEL1_TIMELINE) < 80.0, "第一关时间轴过长"
    mod = sys.modules[__name__]
    assert not hasattr(mod, "LEVEL2_TIMELINE") and not hasattr(mod, "LEVEL2"), \
        "本作仅实现第一关，不应存在第二关数据"
    g = Game(seed=6)
    g.skip_to_boss()
    g.player.invuln = 1e9
    g.damage_boss(1e6)
    _step(g, 400, {})
    assert g.state == "victory" and g.level == 1
    return "仅第一关：%d 波敌军 + Boss，通关即结束" % len(LEVEL1_TIMELINE)


@test
def t_render_headless():
    surf = pygame.display.get_surface()
    font = pygame.font.Font(None, 18)
    g = Game(seed=5)
    g.player.invuln = 1e9
    g.spawn_enemy("turret", x=150, y=210)
    g.spawn_enemy("scout", x=110, y=90)
    g.spawn_enemy("spinner", x=330, y=150)
    g.spawn_powerup("laser", x=300, y=210)
    g.spawn_powerup("bomb", x=350, y=260)
    g.weapon = Weapon("laser", 3)
    g.update(DT, {"fire": True})
    g.explosions.append(Explosion(240, 330, r=26))
    render(surf, g, font)
    colors = set()
    fg = 0
    for x in range(0, W, 6):
        for y in range(0, H, 6):
            c = surf.get_at((x, y))
            colors.add((c.r, c.g, c.b))
            if abs(c.r - C_SPACE[0]) + abs(c.g - C_SPACE[1]) + abs(c.b - C_SPACE[2]) > 24:
                fg += 1
    total = len(range(0, W, 6)) * len(range(0, H, 6))
    assert len(colors) >= 10, "画面颜色过少: %d" % len(colors)
    assert fg / total > 0.02, "前景内容占比过低: %.3f" % (fg / total)
    hud = sum(1 for x in range(0, W, 4)
              if sum(surf.get_at((x, 15))[:3]) > 200)
    assert hud > 20, "HUD 区域应有内容: %d" % hud
    for state in ("playing", "victory", "game_over"):
        g.state = state
        g.paused = (state == "playing")
        render(surf, g, font)
    g.paused = False
    return "无界面渲染：%d 种颜色、前景占比 %.1f%%、HUD 与各状态均正常" % (
        len(colors), fg / total * 100)


@test
def t_headless_smoke():
    rng = random.Random(1234)
    g = Game(seed=7)
    frames = SMOKE_FRAMES
    score = 0
    max_bullets = 0
    max_enemies = 0
    for f in range(frames):
        inp = {"fire": True,
               "left": rng.random() < 0.14, "right": rng.random() < 0.14,
               "up": rng.random() < 0.1, "down": rng.random() < 0.1,
               "bomb": rng.random() < 0.004}
        g.update(DT, inp)
        assert g.score >= score, "分数不应减少"
        score = g.score
        assert len(g.bullets) < 800, "弹幕泄漏: %d" % len(g.bullets)
        assert len(g.enemies) <= 40, "敌机数量异常: %d" % len(g.enemies)
        max_bullets = max(max_bullets, len(g.bullets))
        max_enemies = max(max_enemies, len(g.enemies))
        if g.player is not None:
            assert 0 <= g.player.x <= W and 0 <= g.player.y <= H, "玩家越界"
        for b in g.bullets:
            assert math.isfinite(b.x) and math.isfinite(b.y), "弹丸坐标 NaN"
        for e in g.enemies:
            assert math.isfinite(e.x) and math.isfinite(e.y), "敌机坐标 NaN"
    g.skip_to_boss()
    for _ in range(900):
        g.update(DT, {"fire": True})
        if g.boss is not None:
            g.damage_boss(6.0)
        if g.state == "victory":
            break
    assert g.state == "victory", "极限输入后仍应可由 Boss 收尾：%s" % g.state
    return "无界面冒烟 %d 帧：峰值弹幕 %d / 敌机 %d，分数 %d，最终通关" % (
        frames, max_bullets, max_enemies, g.score)


# ---------------------------------------------------------------------------
# 测试驱动 / 主程序
# ---------------------------------------------------------------------------

SMOKE_FRAMES = 3000


def run_tests(frames=3000):
    global SMOKE_FRAMES
    SMOKE_FRAMES = max(600, int(frames))
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((W, H))
    print("=" * 74)
    print("  RAIDEN 雷电复刻 —— Headless 自检（pygame %s / python %s）"
          % (pygame.version.ver, sys.version.split()[0]))
    print("=" * 74)
    passed = 0
    failed = []
    for fn in TESTS:
        name = fn.__name__
        try:
            msg = fn()
            passed += 1
            print("  [PASS] %-34s %s" % (name, msg))
        except AssertionError as exc:
            failed.append((name, str(exc)))
            print("  [FAIL] %-34s %s" % (name, exc))
        except Exception as exc:                     # noqa: BLE001
            import traceback
            failed.append((name, "%s: %s" % (type(exc).__name__, exc)))
            print("  [ERR ] %-34s %s: %s" % (name, type(exc).__name__, exc))
            traceback.print_exc()
    print("-" * 74)
    print("  测试统计: %d passed, %d failed, 共 %d 项" % (passed, len(failed), len(TESTS)))
    if failed:
        for name, msg in failed:
            print("    x %s -> %s" % (name, msg))
        print("SELFTEST: FAILED")
        pygame.quit()
        return 1
    print("SELFTEST: OK")
    pygame.quit()
    return 0


def read_input(keys):
    return {
        "left": bool(keys[pygame.K_LEFT] or keys[pygame.K_a]),
        "right": bool(keys[pygame.K_RIGHT] or keys[pygame.K_d]),
        "up": bool(keys[pygame.K_UP] or keys[pygame.K_w]),
        "down": bool(keys[pygame.K_DOWN] or keys[pygame.K_s]),
        "fire": bool(keys[pygame.K_SPACE] or keys[pygame.K_j] or keys[pygame.K_RETURN]),
        "bomb": bool(keys[pygame.K_x] or keys[pygame.K_k]),
        "focus": bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="雷电 Raiden 复刻（仅第一关）")
    ap.add_argument("--test", action="store_true", help="Headless 无界面自检")
    ap.add_argument("--frames", type=int, default=3000, help="冒烟测试帧数")
    ap.add_argument("--seed", type=int, default=0, help="随机种子")
    args = ap.parse_args(argv)
    if args.test:
        return run_tests(args.frames)

    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("RAIDEN - STAGE 1: 赤霄")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 18)
    game = Game(seed=args.seed)
    show_fps = False
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_p:
                    game.paused = not game.paused
                elif ev.key in (pygame.K_r, pygame.K_n):
                    game.reset()
                elif ev.key == pygame.K_F1:
                    show_fps = not show_fps
        game.update(dt, read_input(pygame.key.get_pressed()))
        render(screen, game, font)
        if show_fps:
            screen.blit(font.render("%.0f fps" % clock.get_fps(), True, C_HUD), (W - 54, H - 16))
        pygame.display.flip()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
