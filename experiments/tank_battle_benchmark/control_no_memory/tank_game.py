#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
坦克大战 (Tank Battle) —— 单文件完整实现
=========================================

经典 Battle City 玩法，包含：

* 地形：砖墙(可击碎) / 钢墙(需三级武器) / 河流(挡车不挡弹) / 树林(遮挡视线) / 基地(老鹰)
* 敌方坦克 4 种：
    - 普通坦克 normal : 均衡
    - 快速坦克 fast   : 速度快、脆
    - 重型坦克 heavy  : 3 段血量
    - 加农炮坦克 power: 2 段血量、弹速快、可双发
* 道具 6 种（全部经典道具）：
    - star   武器升级（星）   -> 弹速↑ / 双发 / 破钢墙
    - shield 无敌护盾（定时无敌）
    - bomb   全屏炸弹（清屏）
    - clock  时间暂停（冻结敌人）
    - life   额外生命
    - shovel 基地加固（基地外墙变钢墙，限时）
* 关卡推进、生命、计分、HUD 面板、暂停 / 重开

运行方式
--------
    python3 tank_game.py              # 图形界面正常游戏
    python3 tank_game.py --test       # 无界面自检（headless），跑完自动退出
    python3 tank_game.py --stage 3    # 从第 3 关开始
    python3 tank_game.py --seed 42    # 固定随机种子

操作：方向键 / WASD 移动，空格 / J 开火，P 暂停，R 重开，ESC 退出
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections import deque

# ---------------------------------------------------------------------------
# 无界面模式：必须在 import pygame 之前设置 SDL 驱动
# ---------------------------------------------------------------------------
_TEST_MODE = any(a == "--test" or a.startswith("--test=") for a in sys.argv[1:])
if _TEST_MODE:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

# ---------------------------------------------------------------------------
# 全局常量
# ---------------------------------------------------------------------------
TILE = 24                     # 单个格子像素
COLS = 25                     # 横向格数
ROWS = 25                     # 纵向格数
FIELD_W = COLS * TILE         # 战场宽 600
FIELD_H = ROWS * TILE         # 战场高 600
PANEL_W = 150                 # 右侧信息面板
SCREEN_W = FIELD_W + PANEL_W
SCREEN_H = FIELD_H
FPS = 60

# 地块类型
EMPTY, BRICK, STEEL, WATER, FOREST, BASE, BASE_DEAD = 0, 1, 2, 3, 4, 5, 6
BLOCKING_TILES = frozenset((BRICK, STEEL, WATER, BASE, BASE_DEAD))   # 阻挡坦克
BULLET_BLOCKING = frozenset((BRICK, STEEL, BASE))                    # 阻挡子弹

# 方向
UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DIRV = {UP: (0, -1), RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0)}
ALL_DIRS = (UP, RIGHT, DOWN, LEFT)

# 道具
POWERUP_KINDS = ("star", "shield", "bomb", "clock", "life", "shovel")
POWERUP_TEXT = {
    "star":   ("武器升级", "Weapon Star"),
    "shield": ("无敌护盾", "Shield"),
    "bomb":   ("全屏炸弹", "Bomb"),
    "clock":  ("时间暂停", "Time Stop"),
    "life":   ("额外生命", "Extra Life"),
    "shovel": ("基地加固", "Fortify"),
}
SHIELD_FRAMES = 10 * FPS
FREEZE_FRAMES = 8 * FPS
SHOVEL_FRAMES = 15 * FPS
SPAWN_PROTECT_FRAMES = 3 * FPS
RESPAWN_DELAY = int(1.2 * FPS)
POWERUP_LIFETIME = int(14 * FPS)

# 是否允许玩家自己的炮弹摧毁自家基地（经典街机为 True，此处默认关闭，避免开场误射自毁）
PLAYER_CAN_DESTROY_BASE = False

# 敌方坦克属性表
ENEMY_STATS = {
    "normal": dict(speed=0.95, hp=1, bullet_speed=3.6, score=100, max_bullets=1,
                   fire_cd=(70, 150), color=(205, 205, 212), name=("普通坦克", "Basic")),
    "fast":   dict(speed=1.85, hp=1, bullet_speed=3.9, score=200, max_bullets=1,
                   fire_cd=(70, 160), color=(80, 205, 240), name=("快速坦克", "Fast")),
    "heavy":  dict(speed=0.62, hp=3, bullet_speed=4.1, score=400, max_bullets=1,
                   fire_cd=(80, 170), color=(160, 95, 225), name=("重型坦克", "Heavy")),
    "power":  dict(speed=1.15, hp=2, bullet_speed=5.6, score=300, max_bullets=2,
                   fire_cd=(40, 85), color=(235, 130, 60), name=("加农炮坦克", "Power")),
}

COLORS = {
    "bg": (14, 14, 18),
    "field": (26, 26, 32),
    "grid": (34, 34, 42),
    "brick": (176, 74, 44),
    "brick_line": (120, 46, 26),
    "steel": (176, 182, 194),
    "steel_line": (104, 110, 124),
    "water": (28, 78, 190),
    "water_lite": (66, 128, 226),
    "forest": (24, 112, 48),
    "forest_dark": (16, 78, 34),
    "panel": (30, 30, 38),
    "panel_line": (58, 58, 70),
    "text": (238, 238, 242),
    "dim": (150, 150, 162),
    "yellow": (244, 206, 66),
    "red": (222, 72, 60),
    "white": (250, 250, 250),
    "base": (230, 196, 96),
}

CJK_FONT = False
FONT_TINY = FONT_SMALL = FONT_MED = FONT_BIG = None


def L(zh, en):
    """中文字体可用时输出中文，否则回退英文。"""
    return zh if CJK_FONT else en


def load_fonts():
    """加载支持中文的字体（找不到则回退默认字体 + 英文文案）。"""
    global FONT_TINY, FONT_SMALL, FONT_MED, FONT_BIG, CJK_FONT
    if not pygame.font.get_init():
        pygame.font.init()
    path = pygame.font.match_font(
        "pingfangsc,pingfang,heitisc,stheiti,hiraginosansgb,"
        "notosanscjksc,notosanssc,microsoftyahei,simhei,arialunicodems"
    )
    CJK_FONT = bool(path)
    FONT_TINY = pygame.font.Font(path, 12)
    FONT_SMALL = pygame.font.Font(path, 15)
    FONT_MED = pygame.font.Font(path, 19)
    FONT_BIG = pygame.font.Font(path, 30)


def darker(color, factor=0.62):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def lighter(color, factor=1.25):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


# ---------------------------------------------------------------------------
# 子弹
# ---------------------------------------------------------------------------
class Bullet:
    """子弹：faction 为 'player' / 'enemy'，power==2 时可摧毁钢墙。"""

    def __init__(self, x, y, direction, speed, faction, power=1, owner=None, size=6):
        self.x = float(x)
        self.y = float(y)
        self.dir = direction
        self.speed = float(speed)
        self.faction = faction
        self.power = power
        self.owner = owner
        self.size = size
        self.alive = True
        self.hit_something = False

    @property
    def rect(self):
        half = self.size // 2
        return pygame.Rect(int(round(self.x)) - half, int(round(self.y)) - half,
                           self.size, self.size)

    def update(self, game):
        """分步推进，避免高速穿透。返回是否仍存活。"""
        if not self.alive:
            return False
        dx, dy = DIRV[self.dir]
        remaining = self.speed
        while remaining > 0.0 and self.alive:
            step = min(4.0, remaining)
            remaining -= step
            self.x += dx * step
            self.y += dy * step

            if not (0 <= self.x <= FIELD_W and 0 <= self.y <= FIELD_H):
                self.alive = False
                game.add_explosion(self.x, self.y, small=True)
                break

            hits = self._tile_hits(game.tm)
            if hits:
                self._resolve_tiles(game, hits)
                break
        return self.alive

    def _tile_hits(self, tm):
        r = self.rect
        c0 = max(0, r.left // TILE)
        c1 = min(COLS - 1, (r.right - 1) // TILE)
        r0 = max(0, r.top // TILE)
        r1 = min(ROWS - 1, (r.bottom - 1) // TILE)
        out = []
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                tile = tm.grid[row][col]
                if tile in BULLET_BLOCKING:
                    out.append((row, col, tile))
        return out

    def _resolve_tiles(self, game, hits):
        self.alive = False
        broke = False
        for row, col, tile in hits:
            if tile == BRICK:
                game.tm.grid[row][col] = EMPTY
                game.add_explosion(col * TILE + TILE / 2, row * TILE + TILE / 2, small=True)
                broke = True
            elif tile == STEEL:
                if self.power >= 2:
                    game.tm.grid[row][col] = EMPTY
                    game.add_explosion(col * TILE + TILE / 2, row * TILE + TILE / 2)
                    broke = True
                else:
                    game.add_explosion(col * TILE + TILE / 2, row * TILE + TILE / 2, small=True)
            elif tile == BASE:
                if self.faction == "enemy" or PLAYER_CAN_DESTROY_BASE:
                    game.destroy_base()
                else:
                    game.add_explosion(col * TILE + TILE / 2, row * TILE + TILE / 2,
                                       small=True)
                    broke = True
        if not broke:
            game.add_explosion(self.x, self.y, small=True)


# ---------------------------------------------------------------------------
# 坦克基类
# ---------------------------------------------------------------------------
class Tank:
    faction = "neutral"
    kind = "tank"

    def __init__(self, x, y, direction=DOWN, speed=1.0, hp=1, size=TILE):
        self.x = float(x)
        self.y = float(y)
        self.size = size
        self.dir = direction
        self.speed = float(speed)
        self.hp = hp
        self.max_hp = hp
        self.alive = True
        self.spawn_timer = 0            # >0 表示出场动画中（不可碰撞、不可动）
        self.shield = 0                 # 无敌帧
        self.bullets_out = 0
        self.max_bullets = 1
        self.bullet_speed = 5.0
        self.bullet_power = 1
        self.cool = 0
        self.fire_cd = 15
        self.moving = False
        self.score = 0

    # -- 基础几何 ---------------------------------------------------------
    @property
    def rect(self):
        return pygame.Rect(int(round(self.x)), int(round(self.y)), self.size, self.size)

    @property
    def center(self):
        return (self.x + self.size / 2.0, self.y + self.size / 2.0)

    @property
    def col(self):
        return int((self.x + self.size / 2) // TILE)

    @property
    def row(self):
        return int((self.y + self.size / 2) // TILE)

    def body_color(self):
        return COLORS["yellow"]

    # -- 运动 -------------------------------------------------------------
    def can_be_at(self, game, x, y):
        if x < 0 or y < 0 or x + self.size > FIELD_W or y + self.size > FIELD_H:
            return False
        r0 = int(y // TILE)
        c0 = int(x // TILE)
        r1 = int((y + self.size - 0.01) // TILE)
        c1 = int((x + self.size - 0.01) // TILE)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if game.tm.grid[r][c] in BLOCKING_TILES:
                    return False
        rect = pygame.Rect(int(round(x)), int(round(y)), self.size, self.size)
        for other in game.all_tanks():
            if other is self or not other.alive or other.spawn_timer > 0:
                continue
            if rect.colliderect(other.rect):
                return False
        return True

    def move(self, game, direction):
        """沿 direction 移动一小步；被挡时尝试对齐网格。返回是否真正前进。"""
        self.dir = direction
        dx, dy = DIRV[direction]
        step = self.speed
        nx, ny = self.x + dx * step, self.y + dy * step
        if self.can_be_at(game, nx, ny):
            self.x = max(0.0, min(FIELD_W - self.size, nx))
            self.y = max(0.0, min(FIELD_H - self.size, ny))
            self.moving = True
            return True

        # 自动对齐：垂直方向贴到最近的格子中心，便于穿过 1 格宽走廊
        if dx != 0:
            axis, base = "y", self.y + self.size / 2.0
        else:
            axis, base = "x", self.x + self.size / 2.0
        k = math.floor((base - TILE / 2.0) / TILE + 0.5)
        target = k * TILE + TILE / 2.0
        delta = target - base
        if abs(delta) > 0.5:
            shift = max(-step, min(step, delta))
            if axis == "y":
                if self.can_be_at(game, self.x, self.y + shift):
                    self.y += shift
                    self.moving = True
                    return False
            else:
                if self.can_be_at(game, self.x + shift, self.y):
                    self.x += shift
                    self.moving = True
                    return False
        self.moving = False
        return False

    # -- 开火 -------------------------------------------------------------
    def fire(self, game):
        if self.cool > 0 or self.spawn_timer > 0:
            return None
        if self.bullets_out >= self.max_bullets:
            return None
        d = DIRV[self.dir]
        bx = self.x + self.size / 2.0 + d[0] * self.size * 0.56
        by = self.y + self.size / 2.0 + d[1] * self.size * 0.56
        bullet = Bullet(bx, by, self.dir, self.bullet_speed, self.faction,
                        self.bullet_power, owner=self)
        self.bullets_out += 1
        self.cool = self.fire_cd
        game.bullets.append(bullet)
        game.stats["shots"] = game.stats.get("shots", 0) + 1
        game.add_explosion(bx, by, small=True, color=(255, 244, 190))
        return bullet

    # -- 受伤 -------------------------------------------------------------
    def hurt(self, game, power=1):
        if not self.alive or self.spawn_timer > 0:
            return False
        if self.shield > 0:
            return False
        self.hp -= power
        if self.hp <= 0:
            self.alive = False
            return True
        return False

    def tick(self):
        if self.cool > 0:
            self.cool -= 1
        if self.shield > 0:
            self.shield -= 1
        if self.spawn_timer > 0:
            self.spawn_timer -= 1
        self.moving = False


# ---------------------------------------------------------------------------
# 玩家坦克
# ---------------------------------------------------------------------------
class PlayerTank(Tank):
    """玩家坦克：level 0->3 依次为 基础 / 弹速提升 / 双发 / 破钢墙。"""

    faction = "player"
    kind = "player"

    def __init__(self, x, y):
        super().__init__(x, y, direction=UP, speed=1.75, hp=1)
        self.level = 0
        self.fire_cd = 12
        self.bullet_speed = 6.0
        self.bullet_power = 1
        self.max_bullets = 1
        self.shield = SPAWN_PROTECT_FRAMES
        self.spawn_timer = 0

    def body_color(self):
        return lighter(COLORS["yellow"], 1.0 + 0.05 * self.level)

    def upgrade(self):
        """武器升级（星星道具）。"""
        if self.level < 3:
            self.level += 1
        self.apply_level()

    def apply_level(self):
        self.bullet_speed = 8.2 if self.level >= 1 else 6.0
        self.max_bullets = 2 if self.level >= 2 else 1
        self.bullet_power = 2 if self.level >= 3 else 1
        self.fire_cd = 10 if self.level >= 2 else 12

    def update(self, game, inp):
        if not self.alive:
            return
        self.tick()
        if inp.dir is not None:
            self.move(game, inp.dir)
        else:
            self.moving = False
        if inp.fire:
            self.fire(game)


# ---------------------------------------------------------------------------
# 敌方坦克
# ---------------------------------------------------------------------------
class EnemyTank(Tank):
    faction = "enemy"

    def __init__(self, x, y, kind, rng):
        stats = ENEMY_STATS[kind]
        super().__init__(x, y, direction=DOWN, speed=stats["speed"], hp=stats["hp"])
        self.kind = kind
        self.stats = stats
        self.rng = rng
        self.score = stats["score"]
        self.bullet_speed = stats["bullet_speed"]
        self.max_bullets = stats["max_bullets"]
        self.fire_cd = stats["fire_cd"][1]
        self.think_timer = 20
        self.spawn_timer = int(0.8 * FPS)

    # 名字 / 颜色
    def display_name(self):
        return self.stats["name"][0] if CJK_FONT else self.stats["name"][1]

    def body_color(self):
        base = self.stats["color"]
        if self.max_hp > 1:
            ratio = max(0.35, self.hp / float(self.max_hp))
            return darker(base, 0.5 + 0.5 * ratio)
        return base

    def update(self, game):
        if not self.alive:
            return
        self.tick()
        if self.spawn_timer > 0:
            return
        if game.freeze_timer > 0:           # 时间暂停
            self.moving = False
            return

        self.think_timer -= 1
        if self.think_timer <= 0 or not self.moving:
            self.choose_direction(game)
            lo, hi = self.stats["fire_cd"]
            self.think_timer = self.rng.randint(int(lo * 0.5), int(hi * 0.9))

        moved = self.move(game, self.dir)
        if not moved:
            self.think_timer = 0

        if self.rng.random() < 0.035:
            self.fire(game)

    def choose_direction(self, game):
        r = self.rng.random()
        target = None
        if r < 0.40 and game.tm.base_alive:
            target = (game.tm.base_col * TILE + TILE / 2.0,
                      game.tm.base_row * TILE + TILE / 2.0)
        elif r < 0.75 and game.player is not None and game.player.alive:
            target = game.player.center
        if target is not None:
            cx, cy = self.center
            dx, dy = target[0] - cx, target[1] - cy
            if abs(dx) > abs(dy):
                self.dir = RIGHT if dx > 0 else LEFT
            else:
                self.dir = DOWN if dy > 0 else UP
        else:
            self.dir = self.rng.choice(ALL_DIRS)


# ---------------------------------------------------------------------------
# 道具
# ---------------------------------------------------------------------------
class PowerUp:
    def __init__(self, col, row, kind):
        self.kind = kind
        self.col = col
        self.row = row
        self.size = 20
        self.life = POWERUP_LIFETIME
        self.alive = True
        self.phase = 0

    @property
    def rect(self):
        return pygame.Rect(self.col * TILE + (TILE - self.size) // 2,
                           self.row * TILE + (TILE - self.size) // 2,
                           self.size, self.size)

    @property
    def center(self):
        return self.rect.center

    def update(self):
        self.phase = (self.phase + 1) % 120
        self.life -= 1
        if self.life <= 0:
            self.alive = False

    @property
    def blinking(self):
        return self.life < 4 * FPS and (self.life // 6) % 2 == 0


class Explosion:
    def __init__(self, x, y, small=False, color=None):
        self.x, self.y = x, y
        self.small = small
        self.duration = 14 if small else 26
        self.t = self.duration
        self.color = color or ((255, 214, 120) if small else (255, 170, 60))

    @property
    def alive(self):
        return self.t > 0

    def update(self):
        self.t -= 1


# ---------------------------------------------------------------------------
# 地图
# ---------------------------------------------------------------------------
class TileMap:
    # 基地护墙（两层层砖墙，dcol/drow）
    BASE_WALL_OFFSETS = ((-1, 0), (1, 0), (0, -1), (-1, -1), (1, -1),
                         (-1, -2), (0, -2), (1, -2))

    def __init__(self):
        self.grid = [[EMPTY] * COLS for _ in range(ROWS)]
        self.base_col = COLS // 2
        self.base_row = ROWS - 2
        self.base_alive = True
        self.wall_cells = []
        self.shovel_timer = 0

    # -- 生成 -------------------------------------------------------------
    def generate(self, stage=1, rng=None):
        rng = rng or random.Random()
        for _ in range(80):
            grid = self._random_layout(stage, rng)
            self._place_base(grid)
            if self.check_connectivity(grid):
                self.grid = grid
                self.base_alive = True
                self.shovel_timer = 0
                return True
        self.grid = self._fallback_layout()
        self._place_base(self.grid)
        self.base_alive = True
        self.shovel_timer = 0
        return False

    def _clear_zones(self, grid):
        # 外圈走廊（保证连通 + 出生点干净）
        for c in range(COLS):
            grid[0][c] = EMPTY
            grid[ROWS - 1][c] = EMPTY
        for r in range(ROWS):
            grid[r][0] = EMPTY
            grid[r][COLS - 1] = EMPTY
        # 基地附近区域（留出两层层护墙的空间）
        for r in range(ROWS - 4, ROWS):
            for c in range(self.base_col - 6, self.base_col + 4):
                if 0 <= r < ROWS and 0 <= c < COLS:
                    grid[r][c] = EMPTY
        # 敌方出生点
        for c in (0, self.base_col, COLS - 1):
            for r in range(0, 2):
                grid[r][c] = EMPTY

    def _random_layout(self, stage, rng):
        grid = [[EMPTY] * COLS for _ in range(ROWS)]
        density = min(0.34 + stage * 0.04, 0.56)
        palette = (BRICK, BRICK, BRICK, STEEL, WATER, FOREST)
        for r in range(1, ROWS - 1):
            for c in range(1, COLS - 1):
                if rng.random() < density:
                    tile = rng.choice(palette)
                    grid[r][c] = tile
                    # 180° 旋转对称，保证地图平衡
                    grid[ROWS - 1 - r][COLS - 1 - c] = tile
        self._clear_zones(grid)
        return grid

    def _fallback_layout(self):
        grid = [[EMPTY] * COLS for _ in range(ROWS)]
        for r in range(2, ROWS - 2, 2):
            for c in range(2, COLS - 2, 2):
                grid[r][c] = BRICK
                grid[r][c + 1] = BRICK
        self._clear_zones(grid)
        return grid

    def _place_base(self, grid):
        bc, br = self.base_col, self.base_row
        self.wall_cells = []
        for dc, dr in self.BASE_WALL_OFFSETS:
            c, r = bc + dc, br + dr
            if 0 <= c < COLS and 0 <= r < ROWS:
                grid[r][c] = BRICK
                self.wall_cells.append((r, c))
        grid[br][bc] = BASE

    def check_connectivity(self, grid):
        """从 3 个敌方出生点出发，是否都能到达基地（砖墙视为可打通）。"""
        targets = {(self.base_row, self.base_col)}
        for dc, dr in self.BASE_WALL_OFFSETS:
            c, r = self.base_col + dc, self.base_row + dr
            if 0 <= c < COLS and 0 <= r < ROWS:
                targets.add((r, c))
        for start in ((0, 0), (0, self.base_col), (0, COLS - 1)):
            if not self._bfs(grid, start, targets):
                return False
        return True

    @staticmethod
    def _bfs(grid, start, targets):
        if start in targets:
            return True
        seen = {start}
        q = deque([start])
        while q:
            r, c = q.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < ROWS and 0 <= nc < COLS) or (nr, nc) in seen:
                    continue
                if grid[nr][nc] in (STEEL, WATER):
                    continue
                if (nr, nc) in targets:
                    return True
                seen.add((nr, nc))
                q.append((nr, nc))
        return False

    # -- 基地加固 ---------------------------------------------------------
    def fortify(self, frames=SHOVEL_FRAMES):
        for r, c in self.wall_cells:
            if self.grid[r][c] in (BRICK, STEEL):
                self.grid[r][c] = STEEL
        self.shovel_timer = frames

    def update(self):
        if self.shovel_timer > 0:
            self.shovel_timer -= 1
            if self.shovel_timer == 0:
                for r, c in self.wall_cells:
                    if self.grid[r][c] == STEEL:
                        self.grid[r][c] = BRICK

    def set_base_dead(self):
        self.base_alive = False
        self.grid[self.base_row][self.base_col] = BASE_DEAD


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------
class InputState:
    __slots__ = ("dir", "fire", "pause")

    def __init__(self, direction=None, fire=False, pause=False):
        self.dir = direction
        self.fire = fire
        self.pause = pause


# ---------------------------------------------------------------------------
# 关卡配置
# ---------------------------------------------------------------------------
def build_stage_queue(stage, rng=None):
    """每关 20 辆敌方坦克，4 种类型均会出现。"""
    rng = rng or random.Random()
    counts = {
        "normal": max(4, 12 - stage),
        "fast": min(3 + stage, 9),
        "heavy": min(1 + stage, 6),
        "power": min(1 + stage // 2, 5),
    }
    queue = []
    for kind, n in counts.items():
        queue.extend([kind] * n)
    while len(queue) > 20:
        queue.pop(rng.randrange(len(queue)))
    while len(queue) < 20:
        queue.append("normal")
    rng.shuffle(queue)
    for kind in ENEMY_STATS:            # 保证每种类型都有
        if kind not in queue:
            queue[rng.randrange(len(queue))] = kind
    return queue


# ---------------------------------------------------------------------------
# 游戏主体
# ---------------------------------------------------------------------------
class Game:
    PLAYER_SPAWN = (7, ROWS - 2)               # (col, row)
    ENEMY_SPAWNS = ((0, 0), (COLS // 2, 0), (COLS - 1, 0))

    def __init__(self, stage=1, lives=3, seed=None, rng=None):
        self.rng = rng or random.Random(seed)
        self.tm = TileMap()
        self.player = None
        self.enemies = []
        self.bullets = []
        self.powerups = []
        self.explosions = []
        self.score = 0
        self.lives = lives
        self.stage = stage
        self.freeze_timer = 0
        self.spawn_queue = []
        self.spawn_timer = 0
        self.max_on_field = 4
        self.respawn_timer = 0
        self.state = "playing"
        self.state_timer = 0
        self.frame = 0
        self.stats = {"kills": 0, "powerups_taken": 0, "shots": 0,
                      "stages_cleared": 0, "deaths": 0, "powerup_drops": 0}
        self.start_stage(stage, first=True)

    # -- 关卡 -------------------------------------------------------------
    def start_stage(self, stage, first=False):
        self.stage = stage
        self.tm.generate(stage, self.rng)
        self.enemies = []
        self.bullets = []
        self.powerups = []
        self.explosions = []
        self.spawn_queue = build_stage_queue(stage, self.rng)
        self.spawn_timer = 60
        self.max_on_field = 4 + min(2, stage // 3)
        self.freeze_timer = 0
        self.respawn_timer = 0
        self.state = "playing"
        self.state_timer = 0
        self.reset_player()

    def reset_player(self):
        col, row = self.PLAYER_SPAWN
        self.player = PlayerTank(col * TILE, row * TILE)
        self.player.dir = UP
        self.player.shield = SPAWN_PROTECT_FRAMES

    def all_tanks(self):
        out = []
        if self.player is not None:
            out.append(self.player)
        out.extend(self.enemies)
        return out

    # -- 主循环 -----------------------------------------------------------
    def update(self, inp=None):
        inp = inp or InputState()
        self.frame += 1

        if self.state == "game_over":
            self.state_timer += 1
            self._update_effects()
            return
        if self.state == "stage_clear":
            self.state_timer -= 1
            self._update_effects()
            if self.state_timer <= 0:
                self.stats["stages_cleared"] += 1
                self.start_stage(self.stage + 1)
            return

        self.tm.update()
        if self.freeze_timer > 0:
            self.freeze_timer -= 1

        # 玩家
        if self.player is not None and self.player.alive:
            self.player.update(self, inp)
        elif self.player is not None and not self.player.alive:
            self.respawn_timer -= 1
            if self.respawn_timer <= 0:
                if self.lives > 0:
                    self.reset_player()
                else:
                    self.state = "game_over"
                    return

        # 敌方出场
        self._spawn_enemies()

        # 敌方更新
        for enemy in self.enemies:
            enemy.update(self)

        # 子弹
        self._update_bullets()

        # 道具拾取
        self._check_pickups()
        for pu in list(self.powerups):
            pu.update()
            if not pu.alive:
                self.powerups.remove(pu)

        self._update_effects()
        self._evaluate_state()

    def _update_effects(self):
        for ex in list(self.explosions):
            ex.update()
            if not ex.alive:
                self.explosions.remove(ex)

    def _spawn_enemies(self):
        if not self.spawn_queue:
            return
        if self.spawn_timer > 0:
            self.spawn_timer -= 1
            return
        if len(self.enemies) >= self.max_on_field:
            self.spawn_timer = 20
            return
        self.spawn_timer = max(50, 130 - self.stage * 12)
        for col, row in self.rng.sample(self.ENEMY_SPAWNS, len(self.ENEMY_SPAWNS)):
            x, y = col * TILE, row * TILE
            cell_free = self.tm.grid[row][col] not in BLOCKING_TILES
            if cell_free and self._area_free(x, y):
                kind = self.spawn_queue.pop()
                enemy = EnemyTank(x, y, kind, self.rng)
                self.enemies.append(enemy)
                self.add_explosion(x + TILE / 2, y + TILE / 2, small=True,
                                   color=(180, 240, 255))
                return

    def _area_free(self, x, y):
        rect = pygame.Rect(int(x), int(y), TILE, TILE)
        for tank in self.all_tanks():
            if tank.alive and rect.colliderect(tank.rect):
                return False
        return True

    def _update_bullets(self):
        """逐个推进子弹，每颗移动后立即结算碰撞（避免高速穿透）。"""
        for bullet in list(self.bullets):
            if not bullet.alive:
                continue
            bullet.update(self)                 # 边界 + 地形
            if not bullet.alive:
                continue
            self._bullet_vs_tanks(bullet)
            if not bullet.alive:
                continue
            self._bullet_vs_bullets(bullet)

        # 清理死亡子弹并归还弹位数
        for bullet in list(self.bullets):
            if not bullet.alive:
                if bullet.owner is not None:
                    bullet.owner.bullets_out = max(0, bullet.owner.bullets_out - 1)
                self.bullets.remove(bullet)

    def _bullet_vs_tanks(self, bullet):
        for tank in self.all_tanks():
            if tank is bullet.owner or not tank.alive or tank.spawn_timer > 0:
                continue
            if tank.faction == bullet.faction:
                continue
            if bullet.rect.colliderect(tank.rect):
                bullet.alive = False
                self._hit_tank(tank, bullet)
                return

    def _bullet_vs_bullets(self, bullet):
        for other in self.bullets:
            if other is bullet or not other.alive:
                continue
            if other.faction == bullet.faction:
                continue
            if bullet.rect.colliderect(other.rect):
                bullet.alive = False
                other.alive = False
                self.add_explosion((bullet.x + other.x) / 2, (bullet.y + other.y) / 2,
                                   small=True)
                return

    def _hit_tank(self, tank, bullet):
        destroyed = tank.hurt(self, bullet.power)
        if tank.faction == "player":
            self.add_explosion(*tank.center, small=True)
            if destroyed:
                self._kill_player()
            return
        if destroyed:
            self._kill_enemy(tank)
        else:
            self.add_explosion(*(bullet.x, bullet.y), small=True)

    def _kill_enemy(self, enemy):
        if enemy in self.enemies:
            self.enemies.remove(enemy)
        self.score += enemy.score
        self.stats["kills"] += 1
        self.add_explosion(*enemy.center, small=False)
        if self.rng.random() < 0.22 or self.stats["kills"] % 4 == 0:
            self.spawn_powerup()

    def _kill_player(self):
        self.stats["deaths"] += 1
        self.lives -= 1
        self.add_explosion(*self.player.center)
        self.respawn_timer = RESPAWN_DELAY
        if self.lives <= 0:
            self.state = "game_over"
            self.state_timer = 0

    def _evaluate_state(self):
        if self.state == "game_over":
            return
        if not self.tm.base_alive:
            self.state = "game_over"
            self.state_timer = 0
            self.add_explosion(self.tm.base_col * TILE + TILE / 2,
                               self.tm.base_row * TILE + TILE / 2, small=False)
            return
        if not self.spawn_queue and not self.enemies:
            self.state = "stage_clear"
            self.state_timer = int(1.8 * FPS)

    # -- 道具 -------------------------------------------------------------
    def spawn_powerup(self, kind=None):
        kind = kind or self.rng.choice(POWERUP_KINDS)
        free = [(c, r)
                for r in range(1, ROWS - 3)
                for c in range(1, COLS - 1)
                if self.tm.grid[r][c] == EMPTY]
        if not free:
            return None
        col, row = free[self.rng.randrange(len(free))]
        pu = PowerUp(col, row, kind)
        self.powerups.append(pu)
        self.stats["powerup_drops"] += 1
        return pu

    def apply_powerup(self, kind):
        """应用道具效果（也可被测试直接调用）。"""
        if kind not in POWERUP_KINDS:
            raise ValueError("unknown powerup: %s" % kind)
        if kind == "star":
            if self.player is not None:
                self.player.upgrade()
        elif kind == "shield":
            if self.player is not None:
                self.player.shield = SHIELD_FRAMES
        elif kind == "bomb":
            self.detonate_all_enemies()
        elif kind == "clock":
            self.freeze_timer = FREEZE_FRAMES
        elif kind == "life":
            self.lives += 1
        elif kind == "shovel":
            self.tm.fortify(SHOVEL_FRAMES)
        self.score += 500

    def detonate_all_enemies(self):
        """全屏炸弹：清除场上全部敌方坦克。"""
        n = 0
        for enemy in list(self.enemies):
            self.score += enemy.score
            self.stats["kills"] += 1
            self.add_explosion(*enemy.center, small=False)
            if enemy in self.enemies:
                self.enemies.remove(enemy)
            n += 1
        return n

    def destroy_base(self):
        if self.tm.base_alive:
            self.tm.set_base_dead()
            self.state = "game_over"
            self.state_timer = 0
            self.add_explosion(self.tm.base_col * TILE + TILE / 2,
                               self.tm.base_row * TILE + TILE / 2, small=False)

    def add_explosion(self, x, y, small=False, color=None):
        self.explosions.append(Explosion(x, y, small=small, color=color))

    # -- 玩家拾取 ---------------------------------------------------------
    def _check_pickups(self):
        if self.player is None or not self.player.alive:
            return
        prect = self.player.rect
        for pu in list(self.powerups):
            if pu.alive and prect.colliderect(pu.rect):
                pu.alive = False
                self.powerups.remove(pu)
                self.stats["powerups_taken"] += 1
                self.apply_powerup(pu.kind)

    # 供外部（如渲染）查询的敌人数
    @property
    def enemies_remaining(self):
        return len(self.enemies) + len(self.spawn_queue)


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
def draw_tile(surface, col, row, tile):
    x, y = col * TILE, row * TILE
    rect = pygame.Rect(x, y, TILE, TILE)
    if tile == BRICK:
        pygame.draw.rect(surface, COLORS["brick"], rect)
        pygame.draw.rect(surface, COLORS["brick_line"], rect, 1)
        for i in range(1, 4):
            pygame.draw.line(surface, COLORS["brick_line"],
                             (x, y + i * TILE // 4), (x + TILE, y + i * TILE // 4), 1)
        pygame.draw.line(surface, COLORS["brick_line"],
                         (x + TILE // 2, y), (x + TILE // 2, y + TILE // 4), 1)
        pygame.draw.line(surface, COLORS["brick_line"],
                         (x + TILE // 2, y + TILE // 4), (x + TILE // 2, y + TILE // 2), 1)
        pygame.draw.line(surface, COLORS["brick_line"],
                         (x + TILE // 2, y + TILE // 2), (x + TILE // 2, y + 3 * TILE // 4), 1)
        pygame.draw.line(surface, COLORS["brick_line"],
                         (x + TILE // 2, y + 3 * TILE // 4), (x + TILE // 2, y + TILE), 1)
    elif tile == STEEL:
        pygame.draw.rect(surface, COLORS["steel"], rect)
        pygame.draw.rect(surface, COLORS["steel_line"], rect, 2)
        pygame.draw.line(surface, COLORS["steel_line"],
                         (x + 3, y + 3), (x + TILE - 4, y + TILE - 4), 1)
    elif tile == WATER:
        pygame.draw.rect(surface, COLORS["water"], rect)
        pygame.draw.line(surface, COLORS["water_lite"],
                         (x + 3, y + TILE // 3), (x + TILE - 3, y + TILE // 3), 2)
        pygame.draw.line(surface, COLORS["water_lite"],
                         (x + 3, y + 2 * TILE // 3), (x + TILE - 3, y + 2 * TILE // 3), 2)
    elif tile == FOREST:
        pygame.draw.rect(surface, COLORS["forest_dark"], rect)
        pygame.draw.circle(surface, COLORS["forest"], (x + TILE // 3, y + TILE // 3), TILE // 5)
        pygame.draw.circle(surface, COLORS["forest"], (x + 2 * TILE // 3, y + TILE // 2), TILE // 5)
        pygame.draw.circle(surface, COLORS["forest"], (x + TILE // 2, y + 2 * TILE // 3), TILE // 5)
    elif tile == BASE or tile == BASE_DEAD:
        alive = tile == BASE
        color = COLORS["base"] if alive else (90, 90, 96)
        pygame.draw.rect(surface, darker(color, 0.7), rect, border_radius=3)
        cx, cy = x + TILE // 2, y + TILE // 2
        pts = [(cx, cy - 7), (cx + 8, cy + 5), (cx - 8, cy + 5)]
        pygame.draw.polygon(surface, color if alive else (120, 120, 126), pts)
        if not alive:
            pygame.draw.line(surface, COLORS["red"], (x + 3, y + 3), (x + TILE - 3, y + TILE - 3), 2)
            pygame.draw.line(surface, COLORS["red"], (x + TILE - 3, y + 3), (x + 3, y + TILE - 3), 2)


def draw_tank(surface, tank, flashing=False):
    if not tank.alive:
        return
    rect = tank.rect
    cx, cy = rect.center

    # 出生动画
    if tank.spawn_timer > 0:
        t = 1.0 - tank.spawn_timer / float(int(0.8 * FPS))
        radius = int(4 + 12 * abs(math.sin(t * math.pi * 2)))
        pygame.draw.circle(surface, (170, 235, 255), (cx, cy), radius, 2)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), 3)
        return

    body = tank.body_color()
    if flashing:
        body = lighter(body, 1.6)
    pygame.draw.rect(surface, body, rect, border_radius=3)
    pygame.draw.rect(surface, darker(body, 0.5), rect, 1, border_radius=3)

    dx, dy = DIRV[tank.dir]
    # 履带
    if tank.dir in (UP, DOWN):
        pygame.draw.rect(surface, darker(body, 0.45), pygame.Rect(rect.x, rect.y + 1, 5, rect.h - 2))
        pygame.draw.rect(surface, darker(body, 0.45), pygame.Rect(rect.right - 5, rect.y + 1, 5, rect.h - 2))
    else:
        pygame.draw.rect(surface, darker(body, 0.45), pygame.Rect(rect.x + 1, rect.y, rect.w - 2, 5))
        pygame.draw.rect(surface, darker(body, 0.45), pygame.Rect(rect.x + 1, rect.bottom - 5, rect.w - 2, 5))

    # 炮塔
    inner = rect.inflate(-8, -8)
    pygame.draw.rect(surface, darker(body, 0.72), inner, border_radius=2)
    barrel_len = tank.size * 0.62
    pygame.draw.line(surface, (36, 36, 40), (cx, cy),
                     (cx + dx * barrel_len, cy + dy * barrel_len), 5)
    pygame.draw.line(surface, darker(body, 0.8), (cx, cy), (cx, cy), 4)

    # 玩家等级标记
    if isinstance(tank, PlayerTank):
        for i in range(tank.level):
            pygame.draw.circle(surface, (255, 255, 255), (rect.x + 5 + i * 6, rect.bottom - 5), 2)

    # 重型坦克血量条
    if tank.max_hp > 1:
        w = rect.w - 6
        ratio = max(0.0, tank.hp / float(tank.max_hp))
        pygame.draw.rect(surface, (40, 40, 44), pygame.Rect(rect.x + 3, rect.y - 4, w, 3))
        pygame.draw.rect(surface, COLORS["red"] if ratio <= 0.34 else COLORS["yellow"],
                         pygame.Rect(rect.x + 3, rect.y - 4, int(w * ratio), 3))

    # 无敌护盾
    if tank.shield > 0:
        phase = (pygame.time.get_ticks() // 60) % 2 if not _TEST_MODE else (tank.shield // 4) % 2
        color = (255, 255, 255) if phase else (120, 200, 255)
        pygame.draw.circle(surface, color, (cx, cy), tank.size // 2 + 5, 2)


def draw_powerup(surface, pu):
    if pu.blinking:
        return
    rect = pu.rect
    colors = {
        "star": (250, 208, 62), "shield": (96, 190, 255), "bomb": (235, 92, 78),
        "clock": (150, 235, 140), "life": (240, 120, 190), "shovel": (200, 200, 208),
    }
    color = colors[pu.kind]
    pygame.draw.rect(surface, (16, 16, 20), rect, border_radius=4)
    pygame.draw.rect(surface, color, rect, 2, border_radius=4)
    cx, cy = rect.center
    icon = {
        "star": lambda s: draw_star(s, color, cx, cy, 7),
        "shield": lambda s: pygame.draw.polygon(
            s, color, [(cx, cy - 7), (cx + 7, cy - 3), (cx, cy + 8), (cx - 7, cy - 3)]),
        "bomb": lambda s: (pygame.draw.circle(s, color, (cx, cy + 1), 6),
                           pygame.draw.line(s, color, (cx + 3, cy - 4), (cx + 7, cy - 8), 2)),
        "clock": lambda s: (pygame.draw.circle(s, color, (cx, cy), 7, 2),
                            pygame.draw.line(s, color, (cx, cy), (cx, cy - 4), 2),
                            pygame.draw.line(s, color, (cx, cy), (cx + 4, cy), 2)),
        "life": lambda s: draw_tank_icon(s, color, cx, cy),
        "shovel": lambda s: (pygame.draw.rect(s, color, pygame.Rect(cx - 6, cy - 6, 12, 5)),
                             pygame.draw.line(s, color, (cx, cy), (cx, cy + 7), 3)),
    }[pu.kind](surface)


def draw_star(surface, color, cx, cy, r):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    pygame.draw.polygon(surface, color, pts)


def draw_tank_icon(surface, color, cx, cy):
    pygame.draw.rect(surface, color, pygame.Rect(cx - 6, cy - 4, 12, 9), border_radius=2)
    pygame.draw.line(surface, color, (cx, cy), (cx, cy - 8), 3)


def draw_frame(game, surface):
    surface.fill(COLORS["bg"])
    pygame.draw.rect(surface, COLORS["field"], pygame.Rect(0, 0, FIELD_W, FIELD_H))
    for c in range(COLS + 1):
        pygame.draw.line(surface, COLORS["grid"], (c * TILE, 0), (c * TILE, FIELD_H), 1)
    for r in range(ROWS + 1):
        pygame.draw.line(surface, COLORS["grid"], (0, r * TILE), (FIELD_W, r * TILE), 1)

    for r in range(ROWS):
        for c in range(COLS):
            tile = game.tm.grid[r][c]
            if tile not in (EMPTY, FOREST):
                draw_tile(surface, c, r, tile)

    for pu in game.powerups:
        draw_powerup(surface, pu)

    for tank in game.all_tanks():
        draw_tank(surface, tank)

    for bullet in game.bullets:
        rect = bullet.rect
        color = COLORS["white"] if bullet.faction == "player" else (255, 168, 120)
        pygame.draw.rect(surface, color, rect, border_radius=2)

    # 树林覆盖在坦克之上
    for r in range(ROWS):
        for c in range(COLS):
            if game.tm.grid[r][c] == FOREST:
                draw_tile(surface, c, r, FOREST)

    for ex in game.explosions:
        ratio = ex.t / float(ex.duration)
        radius = max(2, int((1 - ratio) * (14 if ex.small else 26)))
        color = ex.color if ratio > 0.5 else (255, 240, 200)
        pygame.draw.circle(surface, color, (int(ex.x), int(ex.y)), radius)
        if not ex.small:
            pygame.draw.circle(surface, (255, 96, 40), (int(ex.x), int(ex.y)), radius, 2)

    draw_panel(game, surface)


def draw_panel(game, surface):
    panel = pygame.Rect(FIELD_W, 0, PANEL_W, SCREEN_H)
    pygame.draw.rect(surface, COLORS["panel"], panel)
    pygame.draw.line(surface, COLORS["panel_line"], (FIELD_W, 0), (FIELD_W, SCREEN_H), 2)
    x = FIELD_W + 12
    y = 14

    def text(s, font, color=COLORS["text"]):
        nonlocal y
        surface.blit(font.render(s, True, color), (x, y))
        y += font.get_height() + 4

    text(L("坦克大战", "TANK BATTLE"), FONT_MED, COLORS["yellow"])
    y += 4
    text(L("分数", "SCORE"), FONT_TINY, COLORS["dim"])
    text(str(game.score), FONT_MED)
    text(L("关卡", "STAGE"), FONT_TINY, COLORS["dim"])
    text(str(game.stage), FONT_MED)
    text(L("剩余敌人", "ENEMIES"), FONT_TINY, COLORS["dim"])
    text(str(game.enemies_remaining), FONT_MED)

    text(L("生命", "LIVES"), FONT_TINY, COLORS["dim"])
    for i in range(min(game.lives, 6)):
        draw_tank_icon(surface, COLORS["yellow"], x + 10 + i * 18, y + 8)
    y += 22

    text(L("武器等级", "WEAPON"), FONT_TINY, COLORS["dim"])
    lvl = game.player.level if game.player else 0
    for i in range(3):
        color = COLORS["yellow"] if i < lvl else (70, 70, 78)
        draw_star(surface, color, x + 12 + i * 20, y + 8, 7)
    y += 26

    text(L("状态", "STATUS"), FONT_TINY, COLORS["dim"])
    if game.player and game.player.shield > 0:
        text(L("无敌 %.1fs", "Shield %.1fs") % (game.player.shield / FPS), FONT_SMALL, (120, 200, 255))
    if game.freeze_timer > 0:
        text(L("暂停 %.1fs", "Freeze %.1fs") % (game.freeze_timer / FPS), FONT_SMALL, (150, 235, 140))
    if game.tm.shovel_timer > 0:
        text(L("加固 %.1fs", "Fort %.1fs") % (game.tm.shovel_timer / FPS), FONT_SMALL, (200, 200, 208))
    if game.player and not game.player.alive and game.lives > 0:
        text(L("复活中...", "Respawning..."), FONT_SMALL, COLORS["red"])

    y = SCREEN_H - 118
    text(L("操作", "CONTROLS"), FONT_TINY, COLORS["dim"])
    text(L("方向键/WASD 移动", "Arrows/WASD move"), FONT_TINY, COLORS["dim"])
    text(L("空格/J 开火", "Space/J fire"), FONT_TINY, COLORS["dim"])
    text(L("P 暂停  R 重开", "P pause  R reset"), FONT_TINY, COLORS["dim"])
    text(L("ESC 退出", "ESC quit"), FONT_TINY, COLORS["dim"])


def draw_overlay(game, surface):
    if game.state == "playing":
        return
    veil = pygame.Surface((FIELD_W, FIELD_H), pygame.SRCALPHA)
    veil.fill((0, 0, 0, 150))
    surface.blit(veil, (0, 0))
    if game.state == "game_over":
        msg, color = "GAME OVER", COLORS["red"]
        sub = L("按 R 重新开始", "Press R to restart")
    elif game.state == "stage_clear":
        msg, color = L("关卡完成!", "STAGE CLEAR!"), COLORS["yellow"]
        sub = L("准备下一关...", "Next stage...")
    else:  # paused
        msg, color = L("已暂停", "PAUSED"), COLORS["text"]
        sub = L("按 P 继续", "Press P to resume")
    label = FONT_BIG.render(msg, True, color)
    surface.blit(label, (FIELD_W // 2 - label.get_width() // 2, FIELD_H // 2 - 40))
    sub_label = FONT_SMALL.render(sub, True, COLORS["text"])
    surface.blit(sub_label, (FIELD_W // 2 - sub_label.get_width() // 2, FIELD_H // 2 + 8))


# ---------------------------------------------------------------------------
# 键盘输入
# ---------------------------------------------------------------------------
KEY_DIRS = {
    pygame.K_UP: UP, pygame.K_w: UP,
    pygame.K_RIGHT: RIGHT, pygame.K_d: RIGHT,
    pygame.K_DOWN: DOWN, pygame.K_s: DOWN,
    pygame.K_LEFT: LEFT, pygame.K_a: LEFT,
}


def read_input(keys):
    direction = None
    for key in (pygame.K_UP, pygame.K_w, pygame.K_RIGHT, pygame.K_d,
                pygame.K_DOWN, pygame.K_s, pygame.K_LEFT, pygame.K_a):
        if keys[key]:
            direction = KEY_DIRS[key]
            break
    fire = bool(keys[pygame.K_SPACE] or keys[pygame.K_j])
    return InputState(direction, fire)


# ---------------------------------------------------------------------------
# 自检测试
# ---------------------------------------------------------------------------
class Tester:
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0

    def run(self, name, fn):
        try:
            fn(self)
            self.results.append((name, True, ""))
            self.passed += 1
            print("  [PASS] %s" % name)
        except AssertionError as exc:
            self.results.append((name, False, str(exc)))
            self.failed += 1
            print("  [FAIL] %s -> %s" % (name, exc))
        except Exception as exc:                     # noqa: BLE001
            import traceback
            self.results.append((name, False, "%s: %s" % (type(exc).__name__, exc)))
            self.failed += 1
            print("  [FAIL] %s -> %s: %s" % (name, type(exc).__name__, exc))
            traceback.print_exc()

    @staticmethod
    def check(cond, msg=""):
        assert cond, msg


def _new_game(stage=1, seed=1234, lives=3):
    return Game(stage=stage, lives=lives, seed=seed)


def _flat_game(seed=1234, lives=3):
    """清空地形（保留基地与外墙）的测试场地。"""
    game = Game(stage=1, lives=lives, seed=seed)
    for r in range(ROWS):
        for c in range(COLS):
            game.tm.grid[r][c] = EMPTY
    game.tm._place_base(game.tm.grid)
    return game


def _step(game, n=1, inp=None):
    for _ in range(n):
        game.update(inp or InputState())


def test_map(t):
    for stage in range(1, 6):
        game = _new_game(stage, seed=100 + stage)
        tm = game.tm
        t.check(tm.grid[tm.base_row][tm.base_col] == BASE, "基地格子缺失")
        t.check(len(tm.wall_cells) == 8, "基地外砖墙数量应为 8，实际 %d" % len(tm.wall_cells))
        br, bc = tm.base_row, tm.base_col
        for dr in (-1, -2):
            for dc in (-1, 0, 1):
                t.check(tm.grid[br + dr][bc + dc] == BRICK, "基地护墙缺失 (%d,%d)" % (br + dr, bc + dc))
        t.check(all(tm.grid[r][c] == BRICK for r, c in tm.wall_cells), "基地外墙应为砖墙")
        t.check(tm.check_connectivity(tm.grid), "第 %d 关：敌人无法到达基地" % stage)
        for col, row in Game.ENEMY_SPAWNS:
            t.check(tm.grid[row][col] == EMPTY, "出生点 %s 被阻挡" % ((col, row),))
        pcol, prow = Game.PLAYER_SPAWN
        t.check(tm.grid[prow][pcol] == EMPTY, "玩家出生点被阻挡")
        t.check(game.player.can_be_at(game, game.player.x, game.player.y), "玩家出生点碰撞异常")
        tiles = {tm.grid[r][c] for r in range(ROWS) for c in range(COLS)}
        t.check(BRICK in tiles and STEEL in tiles and WATER in tiles and FOREST in tiles,
                "地图缺少地形种类")


def test_enemy_types(t):
    t.check(set(ENEMY_STATS) == {"normal", "fast", "heavy", "power"},
            "敌方坦克类型不全")
    stats = [(ENEMY_STATS[k]["speed"], ENEMY_STATS[k]["hp"], ENEMY_STATS[k]["bullet_speed"])
             for k in ENEMY_STATS]
    t.check(len(set(stats)) == 4, "敌方坦克属性应各不相同")
    t.check(ENEMY_STATS["fast"]["speed"] > ENEMY_STATS["normal"]["speed"], "快速坦克应更快")
    t.check(ENEMY_STATS["heavy"]["hp"] >= 3, "重型坦克应有多段血量")
    t.check(ENEMY_STATS["power"]["bullet_speed"] > ENEMY_STATS["normal"]["bullet_speed"],
            "加农炮坦克弹速应更高")

    game = _new_game(1)
    for stage in range(1, 6):
        q = build_stage_queue(stage, random.Random(stage))
        t.check(len(q) == 20, "每关应有 20 辆敌方坦克")
        t.check(set(q) == set(ENEMY_STATS), "第 %d 关类型缺失: %s" % (stage, set(q)))
    t.check(game.enemies_remaining == 20, "初始剩余敌人应为 20")
    kinds = set()
    _step(game, 60 * 30)
    kinds.update(e.kind for e in game.enemies)
    t.check(len(game.enemies) > 0, "30 秒内应有敌方坦克出场")
    t.check(all(e.spawn_timer == 0 for e in game.enemies), "出场动画应已结束")


def test_powerup_catalog(t):
    t.check(set(POWERUP_KINDS) == {"star", "shield", "bomb", "clock", "life", "shovel"},
            "道具种类不完整")
    game = _new_game(1)
    pu = game.spawn_powerup("star")
    t.check(pu is not None and pu.kind == "star", "道具生成失败")
    t.check(pu.rect.width > 0 and 0 <= pu.col < COLS, "道具位置异常")
    # 拾取流程
    game.player.x = pu.rect.x
    game.player.y = pu.rect.y
    game.player.alive = True
    game.player.spawn_timer = 0
    game._check_pickups()
    t.check(not game.powerups, "道具未被拾取")
    t.check(game.stats["powerups_taken"] == 1, "拾取统计错误")
    for kind in POWERUP_KINDS:
        game = _new_game(1)
        before = game.score
        game.apply_powerup(kind)
        t.check(game.score == before + 500, "道具 %s 未加分" % kind)


def test_weapon_upgrade(t):
    game = _new_game(1)
    p = game.player
    t.check(p.level == 0 and p.max_bullets == 1 and p.bullet_power == 1, "初始武器等级错误")
    p.upgrade()
    t.check(p.level == 1 and p.bullet_speed > 6.0, "一星应提升弹速")
    p.upgrade()
    t.check(p.level == 2 and p.max_bullets == 2, "二星应支持双发")
    p.upgrade()
    t.check(p.level == 3 and p.bullet_power == 2, "三星应可摧毁钢墙")
    p.upgrade()
    t.check(p.level == 3, "武器等级上限应为 3")
    b1 = p.fire(game)
    b2 = p.fire(game)
    t.check(b1 is not None and b2 is None, "双发上限应生效")
    t.check(len(game.bullets) == 1, "子弹数量错误")


def test_shield(t):
    game = _flat_game()
    p = game.player
    game.apply_powerup("shield")
    t.check(p.shield == SHIELD_FRAMES, "护盾时长错误")
    enemy = EnemyTank(5 * TILE, 5 * TILE, "normal", game.rng)
    enemy.spawn_timer = 0
    game.enemies.append(enemy)
    lives = game.lives
    hit = Bullet(p.x + TILE / 2, p.y + TILE / 2, UP, 6.0, "enemy", 1, owner=enemy)
    game._hit_tank(p, hit)
    t.check(p.alive and p.hp == 1, "无敌状态下不应死亡")
    t.check(game.lives == lives, "无敌状态下不应扣命")
    t.check(len(game.explosions) > 0, "护盾抵挡应有火花特效")
    p.shield = 0
    game._hit_tank(p, Bullet(p.x + TILE / 2, p.y + TILE / 2, UP, 6.0, "enemy", 1, owner=enemy))
    t.check(not p.alive, "无护盾时应被击毁")
    t.check(game.lives == lives - 1, "玩家死亡应扣命")


def test_bomb(t):
    game = _new_game(1)
    for i, kind in enumerate(("normal", "fast", "heavy", "power")):
        e = EnemyTank(3 * TILE + i * TILE * 2, 3 * TILE, kind, game.rng)
        e.spawn_timer = 0
        game.enemies.append(e)
    remained = game.enemies_remaining
    score = game.score
    n = game.detonate_all_enemies()
    t.check(n == 4, "全屏炸弹应清除 4 辆坦克，实际 %d" % n)
    t.check(not game.enemies, "炸弹后场上仍有敌人")
    t.check(game.enemies_remaining == remained - 4, "剩余敌人数统计错误")
    t.check(game.score > score, "炸弹未加分")
    t.check(len(game.explosions) >= 4, "炸弹应产生爆炸特效")
    game2 = _new_game(1)
    game2.enemies.append(EnemyTank(2 * TILE, 2 * TILE, "normal", game2.rng))
    game2.apply_powerup("bomb")
    t.check(not game2.enemies, "通过道具触发炸弹失败")


def test_clock(t):
    game = _flat_game()
    enemy = EnemyTank(6 * TILE, 6 * TILE, "normal", game.rng)
    enemy.spawn_timer = 0
    game.enemies.append(enemy)
    t.check(enemy.can_be_at(game, enemy.x, enemy.y), "测试用场地应为空地")
    game.apply_powerup("clock")
    t.check(game.freeze_timer == FREEZE_FRAMES, "时间暂停时长错误")
    start = (enemy.x, enemy.y)
    for _ in range(120):
        _step(game, 1, InputState())
    t.check((enemy.x, enemy.y) == start, "时间暂停期间敌人不应移动")
    t.check(game.freeze_timer < FREEZE_FRAMES, "时间暂停计时未递减")
    game.freeze_timer = 0
    _step(game, 180)
    t.check((enemy.x, enemy.y) != start, "时间暂停结束后敌人应恢复行动")


def test_life_and_shovel(t):
    game = _new_game(1)
    lives = game.lives
    game.apply_powerup("life")
    t.check(game.lives == lives + 1, "额外生命未生效")

    game = _new_game(1)
    game.apply_powerup("shovel")
    t.check(game.tm.shovel_timer == SHOVEL_FRAMES, "基地加固计时错误")
    t.check(all(game.tm.grid[r][c] == STEEL for r, c in game.tm.wall_cells),
            "基地外墙应变为钢墙")
    t.check(game.tm.grid[game.tm.base_row][game.tm.base_col] == BASE, "基地本体不应被覆盖")
    game.tm.update()
    for _ in range(SHOVEL_FRAMES + 2):
        game.tm.update()
    t.check(game.tm.shovel_timer == 0, "加固计时应结束")
    t.check(all(game.tm.grid[r][c] == BRICK for r, c in game.tm.wall_cells),
            "加固结束后应恢复砖墙")


def test_bullet_terrain(t):
    # 砖墙：一级武器可破
    game = _flat_game()
    tm = game.tm
    tm.grid[5][5] = BRICK
    b = Bullet(5 * TILE + TILE / 2, 8 * TILE + TILE / 2, UP, 6.0, "player", 1)
    game.bullets.append(b)
    for _ in range(40):
        if not b.alive:
            break
        game._update_bullets()
    t.check(not b.alive, "子弹应撞墙消失")
    t.check(tm.grid[5][5] == EMPTY, "砖墙应被摧毁")

    # 钢墙：一级无效，二级可破
    game = _flat_game()
    tm = game.tm
    tm.grid[5][5] = STEEL
    b = Bullet(5 * TILE + TILE / 2, 8 * TILE + TILE / 2, UP, 6.0, "player", 1)
    game.bullets.append(b)
    for _ in range(40):
        if not b.alive:
            break
        game._update_bullets()
    t.check(tm.grid[5][5] == STEEL, "一级武器不应摧毁钢墙")
    b2 = Bullet(5 * TILE + TILE / 2, 8 * TILE + TILE / 2, UP, 8.2, "player", 2)
    game.bullets.append(b2)
    for _ in range(60):
        if not b2.alive:
            break
        game._update_bullets()
    t.check(tm.grid[5][5] == EMPTY, "二级武器应摧毁钢墙")

    # 河流：挡坦克不挡子弹
    game = _flat_game()
    tm = game.tm
    tm.grid[2][2] = WATER
    game.player.x, game.player.y = 2 * TILE, 10 * TILE
    t.check(not game.player.can_be_at(game, 2 * TILE, 2 * TILE), "河流应阻挡坦克")
    b3 = Bullet(2 * TILE + TILE / 2, 6 * TILE + TILE / 2, UP, 6.0, "player", 1)
    game.bullets.append(b3)
    game._update_bullets()
    t.check(b3.alive, "子弹应能飞过河流")

    # 基地被击中 -> game over
    game = _flat_game()
    tm = game.tm
    for _ in range(60):
        game.bullets.append(Bullet(tm.base_col * TILE + TILE / 2,
                                   (tm.base_row - 1) * TILE + TILE / 2,
                                   DOWN, 6.0, "enemy", 1))
        game._update_bullets()
        if not tm.base_alive:
            break
    t.check(not tm.base_alive, "基地应被摧毁")
    t.check(game.state == "game_over", "基地被毁应触发 game over")
    t.check(tm.grid[tm.base_row][tm.base_col] == BASE_DEAD, "基地应显示为毁坏状态")


def test_bullet_clash(t):
    game = _flat_game()
    pb = Bullet(100, 100, RIGHT, 6.0, "player", 1)
    eb = Bullet(108, 100, LEFT, 6.0, "enemy", 1)
    game.bullets.extend([pb, eb])
    for _ in range(3):
        game._update_bullets()
    t.check(not pb.alive and not eb.alive, "敌我子弹相撞应互相抵消")
    t.check(not game.bullets, "抵消后的子弹应被清理")

    # 同阵营子弹互不影响
    game = _flat_game()
    a = Bullet(100, 200, RIGHT, 6.0, "player", 1)
    b = Bullet(108, 200, LEFT, 6.0, "player", 1)
    game.bullets.extend([a, b])
    game._update_bullets()
    t.check(a.alive or b.alive, "友军子弹不应互相抵消")


def test_heavy_hp(t):
    game = _new_game(1)
    heavy = EnemyTank(8 * TILE, 8 * TILE, "heavy", game.rng)
    heavy.spawn_timer = 0
    game.enemies.append(heavy)
    t.check(heavy.hp == 3, "重型坦克血量应为 3")
    t.check(heavy.hurt(game, 1) is False and heavy.hp == 2, "第一击不应击毁")
    t.check(heavy.hurt(game, 1) is False and heavy.hp == 1, "第二击不应击毁")
    t.check(heavy.hurt(game, 1) is True, "第三击应击毁")
    game.enemies.remove(heavy)
    for kind in ("normal", "fast", "power"):
        e = EnemyTank(0, 0, kind, game.rng)
        e.spawn_timer = 0
        t.check(e.hurt(game, 1) is (ENEMY_STATS[kind]["hp"] == 1), "%s 血量处理异常" % kind)
    # 击杀计分与掉落
    game = _new_game(1)
    score = game.score
    e = EnemyTank(5 * TILE, 5 * TILE, "heavy", game.rng)
    e.spawn_timer = 0
    game.enemies.append(e)
    game._kill_enemy(e)
    t.check(game.score == score + 400, "重型坦克击杀分数应为 400")
    t.check(game.stats["kills"] == 1, "击杀统计错误")


def test_friendly_base_rule(t):
    """默认设置下，玩家自己的炮弹不会摧毁自家基地（敌方炮弹可以）。"""
    if PLAYER_CAN_DESTROY_BASE:
        return
    game = _flat_game()
    tm = game.tm
    for _ in range(60):
        game.bullets.append(Bullet(tm.base_col * TILE + TILE / 2,
                                   (tm.base_row - 2) * TILE + TILE / 2,
                                   DOWN, 8.0, "player", 2))
        game._update_bullets()
    t.check(tm.base_alive, "玩家炮弹不应摧毁自家基地")
    t.check(game.state == "playing", "玩家误射不应触发 game over")


def test_difficulty(t):
    """挂机（玩家不动）不应在开局几秒内就被偷家；敌方 AI 也不能完全不动。"""
    for seed in (1, 2, 3):
        game = _new_game(1, seed=seed)
        moved = 0
        last = {}
        for frame in range(60 * 60):
            game.update(InputState())
            for e in game.enemies:
                key = id(e)
                if key in last and (e.x, e.y) != last[key]:
                    moved += 1
                last[key] = (e.x, e.y)
            if game.state == "game_over":
                break
        t.check(frame >= 30 * FPS, "seed=%d 挂机 %.1f 秒即被偷家" % (seed, frame / FPS))
        t.check(moved > 0, "seed=%d 敌方坦克全程未移动" % seed)


def test_simulation(t):
    game = _new_game(1, seed=7)
    rng = random.Random(99)
    inp = InputState()
    max_bullets = 0
    for frame in range(4000):
        if frame % 12 == 0:
            d = rng.choice([None] + list(ALL_DIRS))
            inp = InputState(d, rng.random() < 0.6)
        if frame % 300 == 299:
            game.apply_powerup(rng.choice(POWERUP_KINDS))
        game.update(inp)
        max_bullets = max(max_bullets, len(game.bullets))
        if frame % 100 == 0:
            for tank in game.all_tanks():
                t.check(-0.01 <= tank.x <= FIELD_W - TILE + 0.01,
                        "坦克越界 x=%s" % tank.x)
                t.check(-0.01 <= tank.y <= FIELD_H - TILE + 0.01,
                        "坦克越界 y=%s" % tank.y)
                r0, c0 = int(tank.y // TILE), int(tank.x // TILE)
                r1 = int((tank.y + tank.size - 0.01) // TILE)
                c1 = int((tank.x + tank.size - 0.01) // TILE)
                for r in range(r0, r1 + 1):
                    for c in range(c0, c1 + 1):
                        t.check(game.tm.grid[r][c] not in BLOCKING_TILES,
                                "坦克与地形重叠 (%d,%d)" % (r, c))
            t.check(len(game.enemies) <= game.max_on_field + 1,
                    "同屏敌人超出上限")
            t.check(len(game.bullets) <= 40, "子弹数量异常")
            t.check(len(game.explosions) <= 200, "爆炸特效泄漏")
        if game.state == "game_over":
            game = _new_game(game.stage, seed=rng.randint(1, 10 ** 6))
            inp = InputState()
    t.check(max_bullets > 0, "模拟过程中玩家未开火")
    t.check(game.stats["kills"] > 0, "模拟过程中未击杀敌人")


def test_render(t, surface):
    game = _new_game(2, seed=31)
    for kind in POWERUP_KINDS:
        game.spawn_powerup(kind)
    _step(game, 400, InputState(random.choice(list(ALL_DIRS)), True))
    for _ in range(5):
        surface.fill((0, 0, 0))
        draw_frame(game, surface)
    game.state = "stage_clear"
    draw_frame(game, surface)
    draw_overlay(game, surface)
    game.state = "game_over"
    draw_frame(game, surface)
    draw_overlay(game, surface)
    game.state = "paused"
    draw_overlay(game, surface)
    t.check(surface.get_size() == (SCREEN_W, SCREEN_H), "渲染尺寸错误")
    # 渲染后画面非全黑
    colors = {surface.get_at((x, y))[:3]
              for x in range(0, FIELD_W, 40) for y in range(0, FIELD_H, 40)}
    t.check(len(colors) > 1, "画面似乎是空白")


def test_player_lifecycle(t):
    game = _new_game(1, lives=3)
    t.check(game.lives == 3 and game.player.alive, "初始玩家状态错误")
    first_lives = game.lives
    for i in range(3):
        game.player.spawn_timer = 0
        game.player.shield = 0
        game.player.hurt(game, 1)
        game._kill_player()
        _step(game, RESPAWN_DELAY + 2)
        if i < 2:
            t.check(game.lives == first_lives - (i + 1), "生命扣减错误")
            t.check(game.state == "playing", "应仍在游戏中")
            t.check(game.player is not None and game.player.alive, "玩家应已复活")
            t.check(game.player.shield > 0, "复活后应有保护罩")
    t.check(game.lives <= 0, "生命应为 0")
    t.check(game.state == "game_over", "生命耗尽应 game over")
    # game over 后继续 update 不应崩溃
    _step(game, 120)
    t.check(game.state == "game_over", "game over 状态应保持")


def test_stage_progression(t):
    game = _new_game(1, seed=5)
    stage = game.stage
    game.enemies = []
    game.spawn_queue = []
    _step(game, 1)
    t.check(game.state == "stage_clear", "清空敌人后应进入关卡完成状态")
    _step(game, int(1.8 * FPS) + 5)
    t.check(game.stage == stage + 1, "应进入下一关")
    t.check(game.enemies_remaining == 20, "新关卡敌人队列应为 20")
    t.check(game.tm.base_alive, "新关卡基地应存在")
    t.check(game.player.alive, "新关卡玩家应存活")
    t.check(game.stats["stages_cleared"] >= 1, "通过关卡统计错误")


# ---------------------------------------------------------------------------
# 自检入口
# ---------------------------------------------------------------------------
def run_tests(verbose=True):
    print("=" * 62)
    print("坦克大战 自检 (headless) | pygame %s | SDL_VIDEODRIVER=%s"
          % (pygame.version.ver, os.environ.get("SDL_VIDEODRIVER")))
    print("=" * 62)
    pygame.init()
    try:
        surface = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    except Exception:                                  # noqa: BLE001
        surface = pygame.Surface((SCREEN_W, SCREEN_H))
    load_fonts()
    print("中文字体: %s" % ("可用" if CJK_FONT else "不可用（使用英文 HUD）"))

    t = Tester()
    t.run("地图生成 / 连通性 / 出生点", test_map)
    t.run("敌方坦克类型（普通/快速/重型/加农炮）", test_enemy_types)
    t.run("道具目录与拾取", test_powerup_catalog)
    t.run("道具-武器升级", test_weapon_upgrade)
    t.run("道具-无敌护盾", test_shield)
    t.run("道具-全屏炸弹", test_bomb)
    t.run("道具-时间暂停", test_clock)
    t.run("道具-额外生命 / 基地加固", test_life_and_shovel)
    t.run("子弹与地形（砖/钢/水/基地）", test_bullet_terrain)
    t.run("子弹对撞抵消", test_bullet_clash)
    t.run("重型坦克多段血量与击杀", test_heavy_hp)
    t.run("玩家误射不毁自家基地", test_friendly_base_rule)
    t.run("难度/敌方 AI 行为", test_difficulty)
    t.run("4000 帧无界面长时间模拟", test_simulation)
    t.run("渲染管线与覆盖层", lambda tt: test_render(tt, surface))
    t.run("玩家死亡/复活/GameOver", test_player_lifecycle)
    t.run("关卡推进", test_stage_progression)

    print("-" * 62)
    total = t.passed + t.failed
    print("自检结果: %d/%d 通过, %d 失败" % (t.passed, total, t.failed))
    summary = {
        "mode": "test",
        "pygame": pygame.version.ver,
        "headless": os.environ.get("SDL_VIDEODRIVER") == "dummy",
        "total": total,
        "passed": t.passed,
        "failed": t.failed,
        "results": [{"name": n, "ok": ok, "detail": d} for n, ok, d in t.results],
    }
    print(json.dumps(summary, ensure_ascii=False))
    print("=" * 62)
    if t.failed:
        print("自检失败")
        return 1
    print("自检全部通过 ✔")
    return 0


# ---------------------------------------------------------------------------
# 图形界面入口
# ---------------------------------------------------------------------------
def run_gui(args):
    pygame.init()
    pygame.display.set_caption("坦克大战 Tank Battle")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    load_fonts()
    clock = pygame.time.Clock()

    game = Game(stage=args.stage, lives=args.lives, seed=args.seed)
    paused = False
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_p:
                    paused = not paused
                elif event.key == pygame.K_r:
                    game = Game(stage=args.stage, lives=args.lives,
                                seed=args.seed if args.seed is None else args.seed + 1)
                    paused = False
                elif event.key == pygame.K_n and args.debug:
                    game.start_stage(game.stage + 1)

        if not paused:
            inp = read_input(pygame.key.get_pressed())
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
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="坦克大战 Tank Battle（单文件实现，含 --test 无界面自检）")
    parser.add_argument("--test", action="store_true", help="无界面自检并退出")
    parser.add_argument("--stage", type=int, default=1, help="起始关卡（默认 1）")
    parser.add_argument("--lives", type=int, default=3, help="生命数（默认 3）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    parser.add_argument("--debug", action="store_true", help="调试模式（N 键跳关）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.test:
        return run_tests()
    return run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
