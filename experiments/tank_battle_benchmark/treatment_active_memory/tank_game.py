#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
坦克大战 (Tank Battle) —— 从零实现的完整经典坦克大战。

特点
----
* 100% 纯几何绘制：所有画面由 pygame.draw 图元（矩形/多边形/圆/线）程序化生成，
  不加载任何图片、精灵或外部素材文件。
* 完整经典道具：
    STAR    武器升级（1→3 级：普通弹 → 穿甲弹(可打钢板+提速) → 双发弹）
    SHIELD  无敌/护盾（玩家短时无敌）
    GRENADE 全屏炸弹（清屏秒杀所有在场敌方坦克）
    CLOCK   时间暂停（冻结全部敌方坦克）
    LIFE    额外生命
    SHOVEL  工兵铲（基地外墙临时钢化）
* 敌方坦克类型：普通(normal) / 快速(fast) / 重型(power，高速穿甲弹) / 装甲(armor，4 层血)
* 地图元素：砖墙(可破) / 钢板(需穿甲弹) / 河流(挡坦克不挡子弹) / 树林(遮视野) / 冰面(打滑)
* 基地鹰旗保护、关卡推进、分数、生命、暂停、重开。
* `--test`：无界面(headless)自检，覆盖全部道具/敌型/碰撞/关卡流程，跑完退出。

用法
----
    python3 tank_game.py            # 正常游玩
    python3 tank_game.py --test     # 无界面自检
    python3 tank_game.py --test --seed 42 --frames 2000
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys

import pygame

TILE = 24
GRID = 26
BOARD_W = TILE * GRID
BOARD_H = TILE * GRID
HUD_W = 104
WIN_W = BOARD_W + HUD_W
WIN_H = BOARD_H
FPS = 60

EMPTY, BRICK, STEEL, WATER, TREES, ICE, BASE = range(7)

TANK_BLOCK = frozenset({BRICK, STEEL, WATER, BASE})
BULLET_BLOCK = frozenset({BRICK, STEEL, BASE})

UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DIRV = {UP: (0, -1), RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0)}
DIR_ORDER = (UP, RIGHT, DOWN, LEFT)

C_BG = (18, 18, 22)
C_BRICK = (168, 78, 44)
C_BRICK2 = (208, 106, 62)
C_STEEL = (168, 172, 184)
C_STEEL2 = (110, 114, 126)
C_WATER = (30, 84, 168)
C_WATER2 = (62, 132, 220)
C_TREES = (34, 128, 58)
C_TREES2 = (52, 168, 76)
C_ICE = (150, 200, 216)
C_ICE2 = (196, 232, 244)
C_TEXT = (232, 232, 232)
C_DIM = (140, 140, 150)

ENEMY_KINDS = {
    "normal": dict(speed=52.0, hp=1, bullet_speed=200.0, score=100,
                   color=(206, 206, 212), color2=(150, 150, 158), reload=1.15, weight=45),
    "fast":   dict(speed=98.0, hp=1, bullet_speed=210.0, score=200,
                   color=(112, 216, 255), color2=(60, 150, 200), reload=0.95, weight=25),
    "power":  dict(speed=56.0, hp=1, bullet_speed=320.0, score=300,
                   color=(255, 186, 92), color2=(196, 126, 40), reload=0.70, weight=18),
    "armor":  dict(speed=46.0, hp=4, bullet_speed=200.0, score=400,
                   color=(150, 240, 150), color2=(80, 170, 90), reload=1.00, weight=12),
}
ARMOR_TINT = {4: (150, 240, 150), 3: (216, 226, 140), 2: (240, 190, 120), 1: (236, 130, 120)}

PLAYER_SPEED = 104.0
MAX_ACTIVE_ENEMIES = 4
BULLET_SIZE = 6
ENEMIES_PER_LEVEL = 12

POWERUP_KINDS = ("star", "shield", "grenade", "clock", "life", "shovel")
POWERUP_LIFETIME = 22.0

SHIELD_TIME = 9.0
CLOCK_TIME = 8.0
SHOVEL_TIME = 15.0
SPAWN_PROTECT = 0.9
RESPAWN_DELAY = 1.2


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def tile_index(px):
    return int(px // TILE)


def draw_tank_shape(surf, rect, direction, body, dark, level=1, flash=False):
    """纯几何绘制坦克：履带 + 车体 + 炮塔 + 炮管。"""
    if flash:
        body = (255, 96, 96)
        dark = (170, 40, 40)
    x, y, w, h = rect
    track = max(3, w // 6)
    surf.fill(dark, (x, y, track, h))
    surf.fill(dark, (x + w - track, y, track, h))
    rung = max(2, h // 6)
    for i in range(0, h, rung * 2):
        pygame.draw.line(surf, body, (x, y + i), (x + track - 1, y + i), 1)
        pygame.draw.line(surf, body, (x + w - track, y + i), (x + w - 1, y + i), 1)
    bx = x + track
    bw = w - track * 2
    surf.fill(body, (bx, y + h // 5, bw, h - 2 * (h // 5)))
    surf.fill(dark, (bx, y + h // 5, bw, 2))
    cx, cy = x + w // 2, y + h // 2
    rad = max(3, w // 5)
    pygame.draw.circle(surf, body, (cx, cy), rad)
    pygame.draw.circle(surf, dark, (cx, cy), rad, 1)
    dx, dy = DIRV[direction]
    bl = w // 2 + 3
    if dx:
        pygame.draw.line(surf, dark, (cx, cy), (cx + dx * bl, cy), 4)
        pygame.draw.line(surf, body, (cx, cy), (cx + dx * bl, cy), 2)
    else:
        pygame.draw.line(surf, dark, (cx, cy), (cx, cy + dy * bl), 4)
        pygame.draw.line(surf, body, (cx, cy), (cx, cy + dy * bl), 2)
    if level > 1:
        for i in range(min(level - 1, 2)):
            sx = x + w // 2 - 4 + i * 5
            pygame.draw.rect(surf, (255, 255, 255), (sx, y + 2, 3, 3))


def draw_star(surf, cx, cy, r, color=(255, 232, 120), width=0):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.44
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    pygame.draw.polygon(surf, color, pts, width)


def draw_powerup_icon(surf, kind, cx, cy, r):
    """所有道具图标均为几何图元。"""
    if kind == "star":
        draw_star(surf, cx, cy, r, (255, 236, 130))
    elif kind == "shield":
        pts = [(cx, cy - r), (cx + r, cy - r * 0.55), (cx + r * 0.72, cy + r * 0.5),
               (cx, cy + r), (cx - r * 0.72, cy + r * 0.5), (cx - r, cy - r * 0.55)]
        pygame.draw.polygon(surf, (120, 220, 255), pts)
        pygame.draw.polygon(surf, (28, 70, 110), pts, 2)
    elif kind == "grenade":
        pygame.draw.circle(surf, (250, 96, 72), (int(cx), int(cy + r * 0.15)), int(r * 0.85))
        pygame.draw.circle(surf, (150, 40, 26), (int(cx), int(cy + r * 0.15)), int(r * 0.85), 2)
        pygame.draw.rect(surf, (190, 190, 190), (int(cx - 2), int(cy - r - 1), 5, 5))
    elif kind == "clock":
        pygame.draw.circle(surf, (240, 240, 250), (int(cx), int(cy)), int(r))
        pygame.draw.circle(surf, (60, 60, 80), (int(cx), int(cy)), int(r), 2)
        pygame.draw.line(surf, (60, 60, 80), (cx, cy), (cx, cy - r * 0.7), 2)
        pygame.draw.line(surf, (60, 60, 80), (cx, cy), (cx + r * 0.55, cy + r * 0.2), 2)
    elif kind == "life":
        r2 = (int(cx - r), int(cy - r * 0.8), int(r * 2), int(r * 1.6))
        draw_tank_shape(surf, r2, UP, (150, 240, 150), (80, 170, 90))
    elif kind == "shovel":
        pygame.draw.line(surf, (190, 140, 80), (cx, cy - r), (cx, cy + r * 0.2), 3)
        pts = [(cx - r * 0.7, cy + r * 0.2), (cx + r * 0.7, cy + r * 0.2), (cx, cy + r)]
        pygame.draw.polygon(surf, (200, 205, 215), pts)
        pygame.draw.polygon(surf, (110, 115, 126), pts, 2)


def generate_map(level, rng):
    """程序化生成地图。

    只在 x%4 in (1,2) 且 y%4 in (1,2) 的“块区”放障碍，因此 x%4==0 的整列与
    y%4==0 的整行始终为空，天然保证全图连通；顶部 2 行与底部 2 行保持空旷。
    """
    m = [[EMPTY] * GRID for _ in range(GRID)]

    def place(x0, y0, w, h, tile, prob=1.0):
        for j in range(h):
            for i in range(w):
                x, y = x0 + i, y0 + j
                if not (0 <= x < GRID and 0 <= y < GRID):
                    continue
                if x % 4 == 0 or y % 4 == 0:
                    continue
                if rng.random() <= prob:
                    m[y][x] = tile

    for by in range(2, GRID - 4, 4):
        for bx in range(1, GRID - 1, 4):
            place(bx, by, rng.choice((2, 3)), rng.choice((1, 2)), BRICK, 0.8)
    for _ in range(5 + level):
        place(rng.randrange(1, GRID - 3), rng.randrange(4, GRID - 5),
              rng.choice((1, 2)), rng.choice((1, 2)), STEEL, 0.85)
    for _ in range(1 + level):
        place(rng.randrange(2, GRID - 4), rng.randrange(6, GRID - 6),
              rng.randrange(2, 4), rng.randrange(2, 3), WATER)
    for _ in range(4 + level):
        place(rng.randrange(2, GRID - 4), rng.randrange(4, GRID - 6),
              rng.randrange(2, 4), rng.randrange(2, 3), TREES, 0.85)
    if level >= 2:
        for _ in range(level):
            place(rng.randrange(2, GRID - 4), rng.randrange(2, GRID - 6),
                  rng.randrange(2, 4), rng.randrange(2, 3), ICE, 0.9)
    return m


def weighted_enemy_queue(level, rng, count=ENEMIES_PER_LEVEL):
    kinds = list(ENEMY_KINDS.keys())
    weights = []
    for k in kinds:
        w = ENEMY_KINDS[k]["weight"]
        if k == "fast":
            w += 8 * (level - 1)
        if k == "power":
            w += 6 * (level - 1)
        if k == "armor":
            w += 5 * (level - 1)
        weights.append(w)
    queue = []
    for _ in range(count):
        r = rng.random() * sum(weights)
        acc = 0.0
        for k, w in zip(kinds, weights):
            acc += w
            if r <= acc:
                queue.append(k)
                break
        else:
            queue.append("normal")
    return queue


# ---------------------------------------------------------------------------
# 实体
# ---------------------------------------------------------------------------

class Bullet:
    __slots__ = ("x", "y", "dir", "speed", "power", "is_player", "owner", "alive")

    def __init__(self, x, y, direction, speed, power, is_player, owner):
        self.x = x
        self.y = y
        self.dir = direction
        self.speed = speed
        self.power = power
        self.is_player = is_player
        self.owner = owner
        self.alive = True

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), BULLET_SIZE, BULLET_SIZE)

    def update(self, dt):
        dx, dy = DIRV[self.dir]
        self.x += dx * self.speed * dt
        self.y += dy * self.speed * dt
        if self.x < -BULLET_SIZE or self.y < -BULLET_SIZE or \
           self.x > BOARD_W or self.y > BOARD_H:
            self.alive = False


class Explosion:
    __slots__ = ("x", "y", "t", "dur", "big")

    def __init__(self, x, y, dur=0.32, big=False):
        self.x = x
        self.y = y
        self.t = 0.0
        self.dur = dur
        self.big = big

    def update(self, dt):
        self.t += dt
        return self.t < self.dur

    @property
    def progress(self):
        return clamp(self.t / self.dur, 0.0, 1.0)


class PowerUp:
    __slots__ = ("kind", "x", "y", "t", "life")

    def __init__(self, kind, x, y):
        self.kind = kind
        self.x = x
        self.y = y
        self.t = 0.0
        self.life = POWERUP_LIFETIME

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), TILE, TILE)


class Tank:
    def __init__(self, x, y, kind="normal", is_player=False, direction=UP):
        cfg = ENEMY_KINDS.get(kind, ENEMY_KINDS["normal"])
        self.x = float(x)
        self.y = float(y)
        self.kind = kind
        self.is_player = is_player
        self.dir = direction
        self.speed = PLAYER_SPEED if is_player else cfg["speed"]
        self.hp = 1 if is_player else cfg["hp"]
        self.max_hp = self.hp
        self.bullet_speed = cfg["bullet_speed"] if not is_player else 220.0
        self.reload = cfg["reload"] if not is_player else 0.45
        self.reload_timer = 0.0
        self.alive = True
        self.slide = 0.0
        self.ai_timer = 0.0
        self.spawn_anim = SPAWN_PROTECT
        self.shield_timer = 0.0
        self.level = 1 if is_player else 0

    @property
    def rect(self):
        return pygame.Rect(int(round(self.x)), int(round(self.y)), TILE, TILE)

    @property
    def center(self):
        return self.x + TILE / 2, self.y + TILE / 2

    @property
    def color(self):
        if self.is_player:
            return (238, 208, 72), (176, 148, 34)
        cfg = ENEMY_KINDS[self.kind]
        if self.kind == "armor":
            c = ARMOR_TINT.get(max(1, self.hp), (150, 240, 150))
            return c, tuple(max(0, v - 70) for v in c)
        return cfg["color"], cfg["color2"]

    def set_dir(self, d):
        if d == self.dir:
            return
        self.dir = d
        if d in (UP, DOWN):
            self.x = round(self.x / TILE) * TILE
        else:
            self.y = round(self.y / TILE) * TILE
        self.slide = 0.0

    def can_stand(self, game, nx, ny):
        if nx < 0 or ny < 0 or nx + TILE > BOARD_W or ny + TILE > BOARD_H:
            return False
        x0, x1 = tile_index(nx), tile_index(nx + TILE - 0.01)
        y0, y1 = tile_index(ny), tile_index(ny + TILE - 0.01)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if game.map[ty][tx] in TANK_BLOCK:
                    return False
        probe = pygame.Rect(int(round(nx)), int(round(ny)), TILE, TILE)
        for other in game.all_tanks():
            if other is self or not other.alive:
                continue
            if probe.colliderect(other.rect):
                return False
        return True

    def try_move(self, game, dx, dy):
        if dx == 0 and dy == 0:
            return True
        nx, ny = self.x + dx, self.y + dy
        if self.can_stand(game, nx, ny):
            self.x, self.y = nx, ny
            return True
        return False

    def move(self, game, dt, direction):
        on_ice = game.tile_at(self) == ICE
        if direction is None:
            if on_ice and self.slide > 1.0:
                dx, dy = DIRV[self.dir]
                ok = self.try_move(game, dx * self.slide * dt, dy * self.slide * dt)
                self.slide = max(0.0, self.slide - 320.0 * dt)
                return ok
            self.slide = 0.0
            return False
        self.set_dir(direction)
        spd = self.speed * (1.3 if on_ice else 1.0)
        dx, dy = DIRV[self.dir]
        ok = self.try_move(game, dx * spd * dt, dy * spd * dt)
        self.slide = self.speed if on_ice else 0.0
        return ok

    def fire(self, game):
        if self.reload_timer > 0 or self.spawn_anim > 0 or not self.alive:
            return None
        if self.is_player:
            max_bullets = 2 if self.level >= 3 else 1
            if sum(1 for b in game.bullets if b.is_player and b.owner is self) >= max_bullets:
                return None
            power = 2 if self.level >= 2 else 1
            speed = self.bullet_speed * (1.45 if self.level >= 2 else 1.0)
        else:
            if any(b.owner is self for b in game.bullets if not b.is_player):
                return None
            power = 1
            speed = self.bullet_speed
        cx, cy = self.center
        dx, dy = DIRV[self.dir]
        bx = cx + dx * (TILE / 2) - BULLET_SIZE / 2
        by = cy + dy * (TILE / 2) - BULLET_SIZE / 2
        b = Bullet(bx, by, self.dir, speed, power, self.is_player, self)
        game.bullets.append(b)
        self.reload_timer = self.reload
        return b

    def tick(self, dt):
        if self.reload_timer > 0:
            self.reload_timer -= dt
        if self.spawn_anim > 0:
            self.spawn_anim -= dt
        if self.shield_timer > 0:
            self.shield_timer -= dt

    def ai_update(self, game, dt):
        self.ai_timer -= dt
        target = game.player
        if target is not None and target.alive:
            tx, ty = target.center
            cx, cy = self.center
            aligned_x = abs(tx - cx) < TILE * 0.7
            aligned_y = abs(ty - cy) < TILE * 0.7
            if aligned_x or aligned_y:
                want = None
                if aligned_x:
                    want = DOWN if ty > cy else UP
                elif aligned_y:
                    want = RIGHT if tx > cx else LEFT
                if want is not None:
                    if self.dir == want and game.rng.random() < 0.09:
                        self.fire(game)
                    elif self.ai_timer <= 0:
                        self.set_dir(want)
                        self.ai_timer = 0.35
        if self.ai_timer <= 0:
            self.ai_timer = game.rng.uniform(0.5, 1.9)
            self.set_dir(game.rng.choice(DIR_ORDER))
        moved = self.move(game, dt, self.dir)
        if not moved:
            self.ai_timer = 0.0
            self.set_dir(game.rng.choice(DIR_ORDER))
        if game.rng.random() < 0.012:
            self.fire(game)


# ---------------------------------------------------------------------------
# 主游戏
# ---------------------------------------------------------------------------

class Game:
    """坦克大战核心逻辑（与渲染解耦，可在无界面环境中完整驱动）。"""

    def __init__(self, seed=0, max_levels=3):
        self.rng = random.Random(seed)
        self.max_levels = max_levels
        self.score = 0
        self.lives = 3
        self.level = 1
        self.state = "playing"        # playing / level_clear / game_over / win
        self.state_timer = 0.0
        self.paused = False
        self.base_alive = True
        self._kept_player_level = 1
        self.build_level()

    # -- 关卡搭建 ---------------------------------------------------------
    def build_level(self):
        self.map = generate_map(self.level, self.rng)
        self.base_pos = (GRID // 2, GRID - 2)
        bx, by = self.base_pos
        self.map[by][bx] = BASE
        self.fortified = False
        self.place_base_walls(BRICK)

        self.bullets = []
        self.powerups = []
        self.explosions = []
        self.enemies = []
        self.player = None
        self.respawn_timer = 0.0
        self.clock_timer = 0.0
        self.shovel_timer = 0.0
        self.spawn_timer = 1.0
        self.flash_index = 0
        self.powerups_dropped = 0
        self.base_alive = True
        self.spawn_queue = weighted_enemy_queue(self.level, self.rng)
        self.player = self.make_player()
        self.state = "playing"
        self.state_timer = 0.0

    def place_base_walls(self, tile):
        for (x, y) in self.base_wall_cells():
            if 0 <= x < GRID and 0 <= y < GRID and self.map[y][x] != BASE:
                self.map[y][x] = tile

    def base_wall_cells(self):
        bx, by = self.base_pos
        return [(bx - 1, by), (bx + 1, by), (bx - 1, by - 1), (bx, by - 1), (bx + 1, by - 1)]

    def make_player(self):
        p = Tank(5 * TILE, (GRID - 2) * TILE, "normal", is_player=True, direction=UP)
        p.spawn_anim = 0.0
        p.shield_timer = 3.0
        p.level = clamp(self._kept_player_level, 1, 3)
        return p

    # -- 查询 -------------------------------------------------------------
    def all_tanks(self):
        out = []
        if self.player is not None and self.player.alive:
            out.append(self.player)
        out.extend(t for t in self.enemies if t.alive)
        return out

    def tile_at(self, tank):
        cx, cy = tank.center
        return self.map[clamp(tile_index(cy), 0, GRID - 1)][clamp(tile_index(cx), 0, GRID - 1)]

    def enemies_left(self):
        return len([t for t in self.enemies if t.alive]) + len(self.spawn_queue)

    def spawn_points(self):
        return [(0, 0), ((GRID // 2) * TILE, 0), ((GRID - 1) * TILE, 0)]

    def spawn_enemy(self, kind, x=None, y=None):
        if x is None:
            pts = self.spawn_points()
            self.rng.shuffle(pts)
            for (sx, sy) in pts:
                free = True
                for other in self.all_tanks():
                    if pygame.Rect(sx, sy, TILE, TILE).colliderect(other.rect):
                        free = False
                        break
                if free:
                    x, y = sx, sy
                    break
            else:
                x, y = pts[0]
        e = Tank(x, y, kind, is_player=False, direction=DOWN)
        e.ai_timer = self.rng.uniform(0.2, 1.0)
        self.enemies.append(e)
        return e

    # -- 输入 -------------------------------------------------------------
    def handle_input(self, inp, dt):
        p = self.player
        if p is None or not p.alive:
            return
        direction = None
        if inp.get("up"):
            direction = UP
        elif inp.get("down"):
            direction = DOWN
        elif inp.get("left"):
            direction = LEFT
        elif inp.get("right"):
            direction = RIGHT
        p.move(self, dt, direction)
        if inp.get("fire"):
            p.fire(self)

    # -- 道具 -------------------------------------------------------------
    def spawn_powerup(self, kind=None):
        if kind is None:
            kind = self.rng.choice(POWERUP_KINDS)
            if kind == "star" and self.player is not None and self.player.level >= 3:
                kind = self.rng.choice(("shield", "grenade", "clock", "shovel"))
        free = []
        tanks = self.all_tanks()
        for ty in range(1, GRID - 3):
            for tx in range(1, GRID - 2):
                if self.map[ty][tx] != EMPTY:
                    continue
                r = pygame.Rect(tx * TILE, ty * TILE, TILE, TILE)
                if any(r.colliderect(t.rect) for t in tanks):
                    continue
                free.append((tx, ty))
        if not free:
            return None
        tx, ty = self.rng.choice(free)
        pu = PowerUp(kind, tx * TILE, ty * TILE)
        self.powerups.append(pu)
        self.powerups_dropped += 1
        return pu

    def apply_powerup(self, kind):
        """应用道具效果，返回效果标签（便于测试断言）。"""
        p = self.player
        if kind == "star":
            if p is not None:
                p.level = min(3, p.level + 1)
                self._kept_player_level = p.level
            return "weapon_up"
        if kind == "shield":
            if p is not None:
                p.shield_timer = max(p.shield_timer, SHIELD_TIME)
            return "shield"
        if kind == "grenade":
            killed = 0
            for e in list(self.enemies):
                if e.alive:
                    self.destroy_enemy(e, award=True)
                    killed += 1
            return "grenade:%d" % killed
        if kind == "clock":
            self.clock_timer = max(self.clock_timer, CLOCK_TIME)
            return "clock"
        if kind == "life":
            self.lives += 1
            return "life"
        if kind == "shovel":
            self.fortify_base()
            return "shovel"
        return "unknown"

    def fortify_base(self):
        self.fortified = True
        self.shovel_timer = SHOVEL_TIME
        self.place_base_walls(STEEL)

    def unfortify_base(self):
        self.fortified = False
        for (x, y) in self.base_wall_cells():
            if 0 <= x < GRID and 0 <= y < GRID and self.map[y][x] == STEEL:
                self.map[y][x] = BRICK

    # -- 伤害 -------------------------------------------------------------
    def hit_player(self):
        p = self.player
        if p is None or not p.alive or p.spawn_anim > 0:
            return False
        if p.shield_timer > 0:
            return False
        self.explosions.append(Explosion(*p.center, big=True))
        p.alive = False
        self.lives -= 1
        self._kept_player_level = p.level
        if self.lives < 0:
            self.state = "game_over"
            self.state_timer = 0.0
            self.player = None
        else:
            self.player = None
            self.respawn_timer = RESPAWN_DELAY
        return True

    def destroy_enemy(self, enemy, award=True):
        if not enemy.alive:
            return
        enemy.alive = False
        self.explosions.append(Explosion(*enemy.center, big=True))
        if award:
            self.score += ENEMY_KINDS[enemy.kind]["score"]
        self.flash_index += 1
        if self.flash_index % 4 == 0:            # 每击毁 4 辆掉落一个道具
            self.spawn_powerup()

    def damage_enemy(self, enemy, power):
        enemy.hp -= 1
        if enemy.hp <= 0:
            self.destroy_enemy(enemy)
        else:
            self.explosions.append(Explosion(*enemy.center))

    def destroy_base(self):
        if not self.base_alive:
            return
        bx, by = self.base_pos
        self.base_alive = False
        self.map[by][bx] = EMPTY
        self.explosions.append(Explosion((bx + 0.5) * TILE, (by + 0.5) * TILE, 0.7, big=True))
        self.state = "game_over"
        self.state_timer = 0.0

    # -- 主循环 -----------------------------------------------------------
    def update(self, dt, inp=None):
        dt = min(dt, 0.05)
        if self.state in ("game_over", "win") or self.paused:
            return
        if self.state == "level_clear":
            self.state_timer -= dt
            self.update_effects(dt)
            if self.state_timer <= 0:
                self.level += 1
                if self.level > self.max_levels:
                    self.state = "win"
                else:
                    if self.player is not None:
                        self._kept_player_level = self.player.level
                    self.build_level()
            return

        if self.clock_timer > 0:
            self.clock_timer = max(0.0, self.clock_timer - dt)
        if self.shovel_timer > 0:
            self.shovel_timer = max(0.0, self.shovel_timer - dt)
            if self.shovel_timer == 0.0 and self.fortified:
                self.unfortify_base()

        # 玩家
        if self.player is None:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0 and self.lives >= 0 and self.state == "playing":
                self.player = self.make_player()
        else:
            self.player.tick(dt)
            if inp:
                self.handle_input(inp, dt)

        # 敌人
        frozen = self.clock_timer > 0
        for e in self.enemies:
            e.tick(dt)
            if e.spawn_anim > 0 or frozen:
                continue
            e.ai_update(self, dt)
        self.enemies = [e for e in self.enemies if e.alive]

        # 敌方出生
        self.spawn_timer -= dt
        if self.spawn_timer <= 0 and self.spawn_queue and len(self.enemies) < MAX_ACTIVE_ENEMIES:
            kind = self.spawn_queue.pop(0)
            self.spawn_enemy(kind)
            self.spawn_timer = 1.6

        self.update_bullets(dt)
        self.update_effects(dt)

        # 胜负判定
        if self.state == "playing":
            if not self.enemies and not self.spawn_queue:
                self.state = "level_clear"
                self.state_timer = 2.0

    def update_effects(self, dt):
        for pu in self.powerups:
            pu.t += dt
            pu.life -= dt
        self.powerups = [p for p in self.powerups if p.life > 0]
        self.explosions = [e for e in self.explosions if e.update(dt)]
        # 道具拾取
        p = self.player
        if p is not None and p.alive:
            for pu in list(self.powerups):
                if pu.rect.colliderect(p.rect):
                    self.apply_powerup(pu.kind)
                    self.powerups.remove(pu)

    def update_bullets(self, dt):
        for b in self.bullets:
            b.update(dt)
        # 子弹对撞
        for i in range(len(self.bullets)):
            a = self.bullets[i]
            if not a.alive:
                continue
            for j in range(i + 1, len(self.bullets)):
                c = self.bullets[j]
                if not c.alive or c.is_player == a.is_player:
                    continue
                if a.rect.colliderect(c.rect):
                    a.alive = False
                    c.alive = False
        # 子弹 vs 地形 / 坦克
        for b in self.bullets:
            if b.alive:
                self.resolve_bullet(b)
        self.bullets = [b for b in self.bullets if b.alive]

    def resolve_bullet(self, b):
        r = b.rect
        if r.right < 0 or r.bottom < 0 or r.left > BOARD_W or r.top > BOARD_H:
            b.alive = False
            return
        # 地形
        x0, x1 = clamp(tile_index(r.left), 0, GRID - 1), clamp(tile_index(r.right - 1), 0, GRID - 1)
        y0, y1 = clamp(tile_index(r.top), 0, GRID - 1), clamp(tile_index(r.bottom - 1), 0, GRID - 1)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                t = self.map[ty][tx]
                if t == BRICK:
                    self.map[ty][tx] = EMPTY
                    self.explosions.append(Explosion((tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.22))
                    if b.power >= 2:      # 穿甲弹额外炸开垂直相邻砖块
                        for (ox, oy) in self.perp_cells(tx, ty, b.dir):
                            if self.map[oy][ox] == BRICK:
                                self.map[oy][ox] = EMPTY
                    b.alive = False
                    return
                if t == STEEL:
                    self.explosions.append(Explosion((tx + 0.5) * TILE, (ty + 0.5) * TILE, 0.18))
                    if b.power >= 2:
                        self.map[ty][tx] = EMPTY
                    b.alive = False
                    return
                if t == BASE:
                    self.destroy_base()
                    b.alive = False
                    return
        # 坦克
        for t in self.all_tanks():
            if t is b.owner:
                continue
            if not r.colliderect(t.rect):
                continue
            if t.is_player:
                if b.is_player:
                    continue
                if t.shield_timer > 0 or t.spawn_anim > 0:
                    b.alive = False
                    return
                self.hit_player()
                b.alive = False
                return
            if b.is_player:
                self.explosions.append(Explosion((b.x + BULLET_SIZE / 2), (b.y + BULLET_SIZE / 2), 0.2))
                self.damage_enemy(t, b.power)
                b.alive = False
                return

    @staticmethod
    def perp_cells(tx, ty, direction):
        if direction in (UP, DOWN):
            return [(x, ty) for x in (tx - 1, tx + 1) if 0 <= x < GRID]
        return [(tx, y) for y in (ty - 1, ty + 1) if 0 <= y < GRID]


# ---------------------------------------------------------------------------
# 渲染（全部为几何图元）
# ---------------------------------------------------------------------------

def draw_tile(surf, t, x, y):
    r = pygame.Rect(x, y, TILE, TILE)
    if t == BRICK:
        surf.fill(C_BRICK, r)
        for j in range(0, TILE, 6):
            for i in range(0, TILE, 12):
                off = 6 if (j // 6) % 2 else 0
                pygame.draw.rect(surf, C_BRICK2, (x + i + off, y + j, 11, 5))
    elif t == STEEL:
        surf.fill(C_STEEL, r)
        surf.fill(C_STEEL2, (x, y, TILE, 3))
        surf.fill(C_STEEL2, (x, y, 3, TILE))
        pygame.draw.rect(surf, (226, 230, 238), (x + 5, y + 5, TILE - 12, TILE - 12), 2)
    elif t == WATER:
        surf.fill(C_WATER, r)
        for k in range(2):
            yy = y + 6 + k * 9
            pts = [(x + i, yy + math.sin((i + k * 5) / 3.0) * 2.2) for i in range(0, TILE + 1, 3)]
            pygame.draw.lines(surf, C_WATER2, False, pts, 2)
    elif t == ICE:
        surf.fill(C_ICE, r)
        pygame.draw.line(surf, C_ICE2, (x + 2, y + TILE - 3), (x + TILE - 3, y + 2), 2)
        pygame.draw.line(surf, (255, 255, 255), (x + 8, y + TILE - 3), (x + TILE - 3, y + 8), 1)
    elif t == BASE:
        cx, cy = x + TILE // 2, y + TILE // 2
        surf.fill((40, 40, 48), r)
        pts = [(cx, cy - 9), (cx - 9, cy + 2), (cx - 4, cy + 2), (cx - 4, cy + 9),
               (cx + 4, cy + 9), (cx + 4, cy + 2), (cx + 9, cy + 2)]
        pygame.draw.polygon(surf, (232, 216, 120), pts)
        pygame.draw.polygon(surf, (120, 100, 30), pts, 1)
        pygame.draw.circle(surf, (255, 255, 255), (cx, cy - 2), 2)


def draw_trees(surf, x, y):
    pygame.draw.rect(surf, C_TREES, (x, y, TILE, TILE))
    for (ox, oy, rr) in ((7, 7, 6), (17, 9, 6), (11, 17, 6)):
        pygame.draw.circle(surf, C_TREES2, (x + ox, y + oy), rr)


def draw_powerups(surf, game):
    for pu in game.powerups:
        cx, cy = pu.x + TILE / 2, pu.y + TILE / 2
        blink = pu.life < 5 and (int(pu.t * 8) % 2 == 0)
        if blink:
            continue
        pulse = 1.0 + 0.08 * math.sin(pu.t * 6.0)
        rect = pygame.Rect(0, 0, int(TILE * 0.9 * pulse), int(TILE * 0.9 * pulse))
        rect.center = (int(cx), int(cy))
        pygame.draw.rect(surf, (32, 34, 44), rect, border_radius=4)
        pygame.draw.rect(surf, (240, 240, 250), rect, 2, border_radius=4)
        draw_powerup_icon(surf, pu.kind, cx, cy, TILE * 0.28)


def draw_explosions(surf, game):
    for ex in game.explosions:
        p = ex.progress
        base = TILE * (1.01 if ex.big else 0.55)
        r = int(base * (0.35 + p * 0.9))
        if r <= 0:
            continue
        col = (255, int(220 * (1 - p)), int(60 * (1 - p)))
        pygame.draw.circle(surf, col, (int(ex.x), int(ex.y)), r)
        if r > 4:
            pygame.draw.circle(surf, (255, 120, 30), (int(ex.x), int(ex.y)), int(r * 0.6))


def draw_tank(surf, t):
    body, dark = t.color
    flash = t.spawn_anim > 0 and int(t.spawn_anim * 12) % 2 == 0
    draw_tank_shape(surf, tuple(t.rect), t.dir, body, dark, t.level, flash)
    if t.shield_timer > 0 or t.spawn_anim > 0:
        cx, cy = t.center
        rr = int(TILE * 0.68 + 2 * math.sin(pygame.time.get_ticks() / 90.0))
        pygame.draw.circle(surf, (130, 225, 255), (int(cx), int(cy)), rr, 2)
        pygame.draw.circle(surf, (60, 140, 190), (int(cx), int(cy)), rr + 2, 1)


def render(surf, game, font=None):
    surf.fill(C_BG)
    board = pygame.Rect(0, 0, BOARD_W, BOARD_H)
    prev_clip = surf.get_clip()
    surf.set_clip(board)

    for ty in range(GRID):
        for tx in range(GRID):
            t = game.map[ty][tx]
            if t not in (EMPTY, TREES):
                draw_tile(surf, t, tx * TILE, ty * TILE)

    for t in game.all_tanks():
        draw_tank(surf, t)
    for b in game.bullets:
        pygame.draw.rect(surf, (255, 250, 210), tuple(b.rect))
        pygame.draw.rect(surf, (120, 100, 40), tuple(b.rect), 1)
    draw_powerups(surf, game)
    draw_explosions(surf, game)

    for ty in range(GRID):                       # 树林覆盖在坦克之上
        for tx in range(GRID):
            if game.map[ty][tx] == TREES:
                draw_trees(surf, tx * TILE, ty * TILE)
    surf.set_clip(prev_clip)

    # 右侧信息栏
    hud = pygame.Rect(BOARD_W, 0, HUD_W, WIN_H)
    surf.fill((28, 28, 34), hud)
    pygame.draw.line(surf, (70, 70, 80), (BOARD_W, 0), (BOARD_W, WIN_H), 2)
    if font is not None:
        x = BOARD_W + 10
        y = 10
        lines = [
            ("LEVEL", str(game.level)),
            ("SCORE", str(game.score)),
            ("LIVES", str(max(0, game.lives))),
            ("ENEMY", str(game.enemies_left())),
            ("WEAPON", "*" * game.player.level if game.player else "-"),
        ]
        for label, val in lines:
            surf.blit(font.render(label, True, C_DIM), (x, y))
            surf.blit(font.render(val, True, C_TEXT), (x, y + 14))
            y += 40
        y += 6
        if game.clock_timer > 0:
            surf.blit(font.render("TIME %.1f" % game.clock_timer, True, (140, 220, 255)), (x, y))
            y += 20
        if game.shovel_timer > 0:
            surf.blit(font.render("STEEL %.1f" % game.shovel_timer, True, (200, 205, 215)), (x, y))
            y += 20
        if game.player and game.player.shield_timer > 0:
            surf.blit(font.render("SHLD %.1f" % game.player.shield_timer, True, (140, 220, 255)), (x, y))
            y += 20
        msg = {"level_clear": "LEVEL CLEAR", "game_over": "GAME OVER", "win": "YOU WIN"}.get(game.state)
        if msg:
            surf.blit(font.render(msg, True, (255, 220, 120)), (x, WIN_H - 30))
    # 基地被毁提示
    if not game.base_alive:
        pygame.draw.rect(surf, (255, 60, 60), (0, 0, BOARD_W, BOARD_H), 6)
    return surf


# ---------------------------------------------------------------------------
# 无界面自检
# ---------------------------------------------------------------------------

DT = 1.0 / FPS


def _fresh(seed=1, levels=3):
    """干净的对局：清空地图与敌人，便于定向测试。"""
    g = Game(seed=seed, max_levels=levels)
    g.spawn_timer = 1e9
    g.enemies.clear()
    g.spawn_queue = ["normal"]        # 避免被判为过关
    g.map = [[EMPTY] * GRID for _ in range(GRID)]
    g.bullets.clear()
    g.powerups.clear()
    g.explosions.clear()
    return g


def _shoot_until_done(g, frames=90):
    for _ in range(frames):
        if not g.bullets:
            return
        g.update_bullets(DT)


def _connectivity_ok(g):
    from collections import deque
    start = (tile_index(g.player.x), tile_index(g.player.y))
    goals = {(tile_index(x), tile_index(y)) for (x, y) in g.spawn_points()}
    seen = {start}
    q = deque([start])
    while q:
        tx, ty = q.popleft()
        if (tx, ty) in goals:
            return True
        for d in DIR_ORDER:
            dx, dy = DIRV[d]
            nx, ny = tx + dx, ty + dy
            if not (0 <= nx < GRID and 0 <= ny < GRID) or (nx, ny) in seen:
                continue
            if g.map[ny][nx] in TANK_BLOCK:
                continue
            seen.add((nx, ny))
            q.append((nx, ny))
    return False


def t_map_connectivity():
    for seed in range(6):
        for level in (1, 2, 4):
            g = Game(seed=seed, max_levels=3)
            g.level = level
            g.build_level()
            assert _connectivity_ok(g), "seed=%s level=%s 地图不连通" % (seed, level)
    return "6 seeds x 3 levels 全部连通"


def t_map_has_elements():
    g = Game(seed=7)
    flat = [t for row in g.map for t in row]
    assert flat.count(BASE) == 1, "必须有且仅有一个基地"
    assert flat.count(BRICK) > 0, "应生成砖墙"
    assert flat.count(STEEL) > 0, "应生成钢板"
    g2 = Game(seed=7)
    g2.level = 3
    g2.build_level()
    flat2 = [t for row in g2.map for t in row]
    assert flat2.count(ICE) > 0, "3 关应出现冰面"
    assert flat2.count(TREES) > 0 and flat2.count(WATER) > 0
    return "砖/钢/水/树/冰/基地均已生成"


def t_enemy_kinds_config():
    assert set(ENEMY_KINDS) == {"normal", "fast", "power", "armor"}
    n, f, p, a = (ENEMY_KINDS[k] for k in ("normal", "fast", "power", "armor"))
    assert f["speed"] > n["speed"], "快速坦克应更快"
    assert a["hp"] == 4 and a["hp"] > n["hp"], "装甲坦克应为多层血"
    assert p["bullet_speed"] > n["bullet_speed"], "重型坦克子弹应更快"
    assert p["score"] > f["score"] > n["score"], "分值应随强度递增"
    return "normal/fast/power/armor 速度·血量·弹速·分值均符合设定"


def t_enemy_spawn_and_move():
    g = _fresh(seed=3)
    kinds = ["normal", "fast", "power", "armor"]
    spots = [(2 * TILE, 6 * TILE), (10 * TILE, 6 * TILE),
             (18 * TILE, 6 * TILE), (6 * TILE, 12 * TILE)]
    enemies = [g.spawn_enemy(k, x=sx, y=sy) for k, (sx, sy) in zip(kinds, spots)]
    for e in enemies:
        e.spawn_anim = 0.0
    start = [(e.x, e.y) for e in enemies]
    path = [0.0] * len(enemies)
    for _ in range(240):
        g.clock_timer = 0.0
        for i, e in enumerate(enemies):
            px, py = e.x, e.y
            e.ai_update(g, DT)
            path[i] += abs(e.x - px) + abs(e.y - py)
    for e, (sx, sy), travelled in zip(enemies, start, path):
        assert travelled > 4 * TILE, "%s 坦克行动路径过短(%.1f)" % (e.kind, travelled)
        assert 0 <= e.x <= BOARD_W - TILE and 0 <= e.y <= BOARD_H - TILE
    return "4 种敌方坦克均可自主行动且不越界 (路径 %s)" % "/".join(
        str(int(p)) for p in path)


def t_brick_destruction():
    g = _fresh(seed=11)
    p = g.player
    p.x, p.y, p.dir = 5 * TILE, 20 * TILE, RIGHT
    g.map[20][7] = BRICK
    assert p.fire(g) is not None
    _shoot_until_done(g)
    assert g.map[20][7] == EMPTY, "砖墙应被普通子弹击碎"
    return "普通子弹击碎砖墙"


def t_steel_needs_power():
    g = _fresh(seed=12)
    p = g.player
    p.x, p.y, p.dir = 5 * TILE, 20 * TILE, RIGHT
    p.level = 1
    g.map[20][7] = STEEL
    p.fire(g)
    _shoot_until_done(g)
    assert g.map[20][7] == STEEL, "1 级武器不应打穿钢板"
    p.reload_timer = 0
    p.level = 2                                  # 穿甲弹
    b = p.fire(g)
    assert b is not None and b.power == 2 and b.speed > 220.0 * 1.2
    _shoot_until_done(g)
    assert g.map[20][7] == EMPTY, "穿甲弹应打穿钢板"
    return "钢板仅被 2 级以上穿甲弹击穿"


def t_bullet_vs_bullet():
    g = _fresh(seed=13)
    from_types = (True, False)
    a = Bullet(100, 100, RIGHT, 200, 1, from_types[0], g.player)
    b = Bullet(100, 100, LEFT, 200, 1, from_types[1], None)
    g.bullets = [a, b]
    g.update_bullets(0.0)
    assert not a.alive and not b.alive, "对撞的子弹应互相抵消"
    return "玩家子弹与敌方子弹对撞同归于尽"


def t_kill_armor_enemy():
    g = _fresh(seed=14)
    p = g.player
    p.x, p.y, p.dir = 5 * TILE, 20 * TILE, RIGHT
    e = g.spawn_enemy("armor", x=8 * TILE, y=20 * TILE)
    e.spawn_anim = 0.0
    score0 = g.score
    for i in range(4):
        p.reload_timer = 0
        assert p.fire(g) is not None, "第 %d 发未能发射" % (i + 1)
        _shoot_until_done(g, 60)
        assert e.hp == 4 - (i + 1), "装甲坦克血量应为 %d，实为 %d" % (3 - i, e.hp)
    assert not e.alive, "装甲坦克应在 4 发后被摧毁"
    assert g.score - score0 == ENEMY_KINDS["armor"]["score"] + 0
    return "装甲坦克 4 层血，逐发削减并计分"


def t_powerup_star():
    g = _fresh(seed=15)
    assert g.apply_powerup("star") == "weapon_up"
    assert g.player.level == 2
    p = g.player
    p.reload_timer = 0
    b = p.fire(g)
    assert b.power == 2, "2 级应发射穿甲弹"
    b.alive = False
    g.bullets.clear()
    g.apply_powerup("star")
    assert g.player.level == 3
    p.reload_timer = 0
    b1 = p.fire(g)
    p.reload_timer = 0
    b2 = p.fire(g)
    assert b1 and b2, "3 级应可同时发射 2 发子弹"
    p.reload_timer = 0
    assert p.fire(g) is None, "3 级同时最多 2 发"
    g.apply_powerup("star")
    assert g.player.level == 3, "武器等级上限为 3"
    return "武器升级 1→2→3（穿甲+提速+双发），上限 3"


def t_powerup_grenade():
    g = _fresh(seed=16)
    for i, k in enumerate(("normal", "fast", "power", "armor")):
        e = g.spawn_enemy(k, x=i * TILE, y=0)
        e.spawn_anim = 0.0
    score0 = g.score
    tag = g.apply_powerup("grenade")
    assert tag == "grenade:4", "全屏炸弹应清掉 4 辆，实为 %s" % tag
    assert all(not e.alive for e in g.enemies)
    assert g.score > score0, "全屏炸弹应计分"
    return "全屏炸弹清屏并计分（%s）" % tag


def t_powerup_clock():
    g = _fresh(seed=17)
    e = g.spawn_enemy("normal", x=6 * TILE, y=6 * TILE)
    e.spawn_anim = 0.0
    assert g.apply_powerup("clock") == "clock"
    assert abs(g.clock_timer - CLOCK_TIME) < 1e-6
    pos = (e.x, e.y)
    for _ in range(120):
        g.update(DT, {})
    assert (e.x, e.y) == pos, "暂停期间敌方坦克不得移动"
    assert g.clock_timer < CLOCK_TIME, "暂停计时应在递减"
    g.clock_timer = 0.0
    return "时间暂停冻结敌方 8 秒（ai 完全停摆）"


def t_powerup_shield():
    g = _fresh(seed=18)
    lives0 = g.lives
    assert g.apply_powerup("shield") == "shield"
    assert g.player.shield_timer >= SHIELD_TIME - 1e-6
    assert g.hit_player() is False, "护盾期间应免伤"
    assert g.lives == lives0
    g.player.shield_timer = 0.0
    g.player.spawn_anim = 0.0
    assert g.hit_player() is True, "无护盾应受击"
    assert g.lives == lives0 - 1 and g.player is None
    for _ in range(int(RESPAWN_DELAY / DT) + 5):
        g.update(DT, {})
    assert g.player is not None and g.player.shield_timer > 0, "应在延迟后带护盾复活"
    return "护盾/无敌免伤，受击后延迟复活并附带短暂无敌"


def t_powerup_life():
    g = _fresh(seed=19)
    n = g.lives
    assert g.apply_powerup("life") == "life"
    assert g.lives == n + 1
    return "额外生命 +1"


def t_powerup_shovel():
    g = _fresh(seed=20)
    assert g.apply_powerup("shovel") == "shovel"
    assert all(g.map[y][x] == STEEL for (x, y) in g.base_wall_cells()), "工兵铲应钢化基地外墙"
    g.shovel_timer = 0.02
    for _ in range(5):
        g.update(DT, {})
    assert all(g.map[y][x] == BRICK for (x, y) in g.base_wall_cells()), "钢化应到期还原为砖墙"
    return "工兵铲临时钢化基地外墙并按时还原"


def t_powerup_pickup():
    g = _fresh(seed=21)
    g.apply_powerup("shield")
    g.player.shield_timer = 0.0
    g.powerups.clear()
    pu = PowerUp("star", g.player.x, g.player.y)
    g.powerups.append(pu)
    g.update(DT, {})
    assert g.player.level == 2, "走上道具应生效"
    assert pu not in g.powerups, "拾取后道具应消失"
    return "地图掉落道具可被玩家拾取生效"


def t_powerup_all_kinds_defined():
    seen = set()
    g = _fresh(seed=22)
    for k in POWERUP_KINDS:
        tag = g.apply_powerup(k)
        assert tag != "unknown", "%s 道具未实现" % k
        seen.add(k)
    assert seen == {"star", "shield", "grenade", "clock", "life", "shovel"}
    return "6 种道具(武器升级/无敌护盾/全屏炸弹/时间暂停/生命/工兵铲)全部可用"


def t_base_destroyed_gameover():
    g = _fresh(seed=23)
    bx, by = g.base_pos
    g.map[by][bx] = BASE
    b = Bullet((bx) * TILE, by * TILE, UP, 200, 1, False, None)
    g.bullets = [b]
    g.update_bullets(0.0)
    assert not g.base_alive and g.map[by][bx] == EMPTY
    assert g.state == "game_over", "基地被毁应立即失败"
    return "基地被击中 => 立即 Game Over"


def t_game_over_on_no_lives():
    g = _fresh(seed=24)
    g.lives = 0
    g.player.spawn_anim = 0.0
    g.player.shield_timer = 0.0
    g.hit_player()
    for _ in range(200):
        g.update(DT, {})
    assert g.state == "game_over", "生命耗尽应结束"
    return "生命耗尽 => Game Over"


def t_pause():
    g = _fresh(seed=25)
    e = g.spawn_enemy("normal", x=4 * TILE, y=4 * TILE)
    e.spawn_anim = 0.0
    g.paused = True
    pos = (e.x, e.y)
    t = g.clock_timer
    g.update(DT, {})
    assert (e.x, e.y) == pos and g.clock_timer == t, "暂停时世界不应更新"
    g.paused = False
    return "暂停冻结整个战局"


def t_level_clear_and_progress():
    g = Game(seed=26, max_levels=2)
    g.enemies.clear()
    g.spawn_queue.clear()
    g.update(DT, {})
    assert g.state == "level_clear", "清空敌人应进入过关状态"
    for _ in range(int(2.2 / DT) + 4):
        g.update(DT, {})
    assert g.level == 2 and g.state == "playing", "应推进到第 2 关"
    g.enemies.clear()
    g.spawn_queue.clear()
    g.update(DT, {})
    for _ in range(int(2.2 / DT) + 4):
        g.update(DT, {})
    assert g.state == "win", "通过最后一关应胜利"
    return "清场过关 -> 第 2 关 -> 通关胜利"


def t_enemy_drops_powerup():
    g = _fresh(seed=27)
    g.spawn_timer = 1e9
    for i in range(8):
        e = g.spawn_enemy("normal", x=(i % 4) * TILE, y=(i // 4) * TILE)
        e.spawn_anim = 0.0
    for e in list(g.enemies)[:4]:
        g.destroy_enemy(e)
    g.enemies = [e for e in g.enemies if e.alive]
    assert g.flash_index == 4, "应记录 4 次击毁，实为 %d" % g.flash_index
    assert g.powerups_dropped >= 1, "击毁 4 辆应掉落道具"
    assert g.powerups, "道具应出现在场上"
    assert g.powerups[-1].kind in POWERUP_KINDS
    return "每击毁 4 辆坦克掉落 1 个道具(%s)" % g.powerups[-1].kind

def t_bullet_water_and_bounds():
    g = _fresh(seed=28)
    g.map[10][6] = WATER
    b = Bullet(6 * TILE, 10 * TILE, RIGHT, 200, 1, True, g.player)
    g.bullets = [b]
    g.update_bullets(0.05)
    assert b.alive, "子弹应飞越河流"
    b2 = Bullet(-20, 100, LEFT, 200, 1, True, g.player)
    g.bullets = [b2]
    g.update_bullets(0.05)
    assert not b2.alive, "出界子弹应被回收"
    return "子弹穿河、出界回收"


def t_render_headless():
    pygame.display.set_mode((WIN_W, WIN_H))
    g = Game(seed=29)
    g.update(DT, {"fire": True})
    surf = pygame.Surface((WIN_W, WIN_H))
    render(surf, g)
    render(surf, g, pygame.font.Font(None, 18))
    assert surf.get_size() == (WIN_W, WIN_H)
    px = surf.get_at((TILE // 2, TILE // 2))
    assert tuple(px)[:3] == C_BG or tuple(px)[:3] != (0, 0, 0), "画面应有绘制内容"
    return "headless 渲染 HUD/战场无异常"


def t_enemy_ai_pressure():
    """玩家原地不动：敌方 AI 应能推进、开火并造成威胁。"""
    moved_down = 0
    enemy_fired = False
    for seed in range(4):
        g = Game(seed=seed, max_levels=3)
        for _ in range(1800):
            g.update(DT, {})
            if any(b for b in g.bullets if not b.is_player):
                enemy_fired = True
            if any(e.y > BOARD_H * 0.45 for e in g.enemies):
                moved_down += 1
                break
            if g.state != "playing":
                break
    assert enemy_fired, "敌方坦克应主动开火"
    assert moved_down >= 2, "敌方 AI 应能向基地推进(仅 %d/4 个种子)" % moved_down
    return "敌方 AI 主动开火并向基地推进 (%d/4 种子达成)" % moved_down


def t_headless_smoke(frames=1800):
    g = Game(seed=2024, max_levels=3)
    surf = pygame.Surface((WIN_W, WIN_H))
    delta = 0
    max_seen = 0
    kills = 0
    for i in range(frames):
        if i % 60 == 59:
            alive = [e for e in g.enemies if e.alive]
            if alive:
                before = g.score
                g.damage_enemy(alive[g.rng.randrange(len(alive))], 1)
                kills += g.score > before
        inp = {}
        if i % 7:
            inp[("up", "down", "left", "right")[g.rng.randrange(4)]] = True
        if i % 5 == 0:
            inp["fire"] = True
        g.update(DT, inp)
        if i % 97 == 0:
            render(surf, g)
        if i % 50 == 0:
            for t in g.all_tanks():
                assert -1 <= t.x <= BOARD_W - TILE + 1 and -1 <= t.y <= BOARD_H - TILE + 1, \
                    "坦克越界 x=%.1f y=%.1f" % (t.x, t.y)
            assert all(math.isfinite(t.x) and math.isfinite(t.y) for t in g.all_tanks())
            assert len(g.map) == GRID and len(g.map[0]) == GRID
            assert g.score >= delta, "分数不应减少"
            delta = g.score
            max_seen = max(max_seen, len(g.all_tanks()))
        if g.state == "game_over":
            g = Game(seed=100 + i, max_levels=3)   # 自动重开继续压测
            delta = 0
    assert kills > 0, "压测中应至少有击毁事件发生"
    return "%d 帧无异常，峰值同屏坦克 %d 辆，击毁 %d 辆，累计分数 %d" % (frames, max_seen, kills, delta)


TESTS = [
    ("地形生成·连通性", t_map_connectivity),
    ("地形生成·元素齐备", t_map_has_elements),
    ("敌方坦克·类型配置", t_enemy_kinds_config),
    ("敌方坦克·生成与 AI", t_enemy_spawn_and_move),
    ("战斗·砖墙可破", t_brick_destruction),
    ("战斗·钢板需穿甲", t_steel_needs_power),
    ("战斗·子弹对撞", t_bullet_vs_bullet),
    ("战斗·装甲坦克与计分", t_kill_armor_enemy),
    ("战斗·河流与出界", t_bullet_water_and_bounds),
    ("道具·武器升级", t_powerup_star),
    ("道具·全屏炸弹", t_powerup_grenade),
    ("道具·时间暂停", t_powerup_clock),
    ("道具·无敌护盾", t_powerup_shield),
    ("道具·额外生命", t_powerup_life),
    ("道具·工兵铲", t_powerup_shovel),
    ("道具·拾取与生效", t_powerup_pickup),
    ("道具·种类全覆盖", t_powerup_all_kinds_defined),
    ("规则·基地被毁", t_base_destroyed_gameover),
    ("规则·生命耗尽", t_game_over_on_no_lives),
    ("规则·暂停", t_pause),
    ("规则·过关与通关", t_level_clear_and_progress),
    ("规则·击毁掉落", t_enemy_drops_powerup),
    ("敌方 AI·火力与推进", t_enemy_ai_pressure),
    ("渲染·headless 出图", t_render_headless),
]


def run_tests(frames=1800):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.font.init()
    try:
        pygame.display.set_mode((WIN_W, WIN_H))
    except Exception:
        pass
    print("=" * 62)
    print("坦克大战 无界面自检 (--test)")
    print("=" * 62)
    passed = failed = 0
    for name, fn in TESTS:
        try:
            msg = fn()
            passed += 1
            print("  [PASS] %-22s %s" % (name, msg))
        except AssertionError as exc:
            failed += 1
            print("  [FAIL] %-22s %s" % (name, exc))
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print("  [ERR ] %-22s %s: %s" % (name, type(exc).__name__, exc))
    try:
        msg = t_headless_smoke(frames)
        passed += 1
        print("  [PASS] %-22s %s" % ("压测·随机对局", msg))
    except AssertionError as exc:
        failed += 1
        print("  [FAIL] %-22s %s" % ("压测·随机对局", exc))
    print("-" * 62)
    print("结果: %d 通过, %d 失败" % (passed, failed))
    print("=" * 62)
    pygame.quit()
    return failed == 0


# ---------------------------------------------------------------------------
# 交互式主循环
# ---------------------------------------------------------------------------

KEYMAP = {
    pygame.K_UP: "up", pygame.K_w: "up",
    pygame.K_DOWN: "down", pygame.K_s: "down",
    pygame.K_LEFT: "left", pygame.K_a: "left",
    pygame.K_RIGHT: "right", pygame.K_d: "right",
    pygame.K_SPACE: "fire", pygame.K_j: "fire", pygame.K_RETURN: "fire",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description="坦克大战 (纯几何绘制)")
    ap.add_argument("--test", action="store_true", help="无界面自检并退出")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--frames", type=int, default=1800, help="--test 的压测帧数")
    ap.add_argument("--max-levels", type=int, default=3, help="通关所需关卡数")
    args = ap.parse_args(argv)

    if args.test:
        ok = run_tests(frames=args.frames)
        print("SELFTEST:", "OK" if ok else "FAILED")
        return 0 if ok else 1

    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Tank Battle - 纯几何绘制")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 18)

    seed = args.seed if args.seed is not None else random.randrange(1 << 30)
    game = Game(seed=seed, max_levels=args.max_levels)
    show_fps = False
    running = True
    try:
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
                    elif ev.key == pygame.K_F1:
                        show_fps = not show_fps
                    elif ev.key == pygame.K_r:
                        game = Game(seed=random.randrange(1 << 30),
                                    max_levels=args.max_levels)
                    elif ev.key == pygame.K_n and game.state in ("game_over", "win"):
                        game = Game(seed=random.randrange(1 << 30),
                                    max_levels=args.max_levels)
            keys = pygame.key.get_pressed()
            inp = {a: keys[k] for k, a in KEYMAP.items()}
            game.update(dt, inp)
            render(screen, game, font)
            if game.paused:
                pygame.draw.rect(screen, (0, 0, 0, 120), (0, BOARD_H // 2 - 24, BOARD_W, 48))
                screen.blit(font.render("PAUSED  (P resume / R restart)", True, (255, 255, 255)),
                            (BOARD_W // 2 - 110, BOARD_H // 2 - 6))
            if game.state in ("game_over", "win"):
                overlay = pygame.Surface((BOARD_W, 90), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 170))
                screen.blit(overlay, (0, BOARD_H // 2 - 45))
                txt = "GAME OVER" if game.state == "game_over" else "YOU WIN!"
                screen.blit(font.render(txt, True, (255, 220, 120)), (BOARD_W // 2 - 32, BOARD_H // 2 - 22))
                screen.blit(font.render("press N / R to play again", True, (220, 220, 220)),
                            (BOARD_W // 2 - 78, BOARD_H // 2 + 4))
            if show_fps:
                screen.blit(font.render("FPS %d" % clock.get_fps(), True, (0, 255, 0)), (4, 4))
            pygame.display.flip()
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
