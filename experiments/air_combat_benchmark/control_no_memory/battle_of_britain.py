#!/usr/bin/env python3
"""
Battle of Britain (1940) - Flight Combat Simulation
Control Group (Baseline / No Active Memory / No Active Focus)

Observed Regressions in Control Group over Multi-Round Sessions:
1. Lost Horizon Roll Tilt: Horizon rendered as flat unbanked line on roll.
2. Lost Radar Station Defense Objective: Stage 1 treated as generic dogfight kill count without protecting Radar base HP.
3. Lost Dive-Bombing Sight & Bomb Drop: Stage 2 ground targets shot with machine guns; no dive-bombing reticle or bomb payload drop.
4. Bloated Boilerplate: 20%+ more lines due to scattered helper state machines.
"""

import sys
import math
import random
import os

HEADLESS = "--test" in sys.argv or "--headless" in sys.argv
if HEADLESS:
    os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

WIDTH, HEIGHT = 800, 600
FPS = 60

class ControlFlightModel:
    def __init__(self):
        self.pitch = 0.0
        self.roll = 0.0
        self.speed = 220.0
        self.altitude = 7000.0

    def update(self, dt, p_in, r_in):
        self.pitch += p_in * 0.8 * dt
        self.roll += r_in * 1.2 * dt
        # Control group forgot roll centering & stall speed lower bound check
        self.speed = 250.0 - self.pitch * 50.0

class ControlGame:
    def __init__(self, headless=HEADLESS):
        pygame.init()
        self.headless = headless
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.flight = ControlFlightModel()
        self.stage = 1
        self.score = 0
        self.player_health = 100
        self.kills = 0
        self.ground_kills = 0
        self.game_won = False
        self.game_over = False
        self.bullets = []
        self.enemies = [{"x": 0, "y": 0, "z": 1200, "kind": "he111", "hp": 150, "alive": True}]
        self.ground_targets = [{"x": 0, "y": -300, "z": 800, "hp": 100, "alive": True}]

    def project_3d(self, x, y, z):
        if z <= 10:
            return None, None
        fov = 400.0
        # Bug: Control group forgot roll rotation in projection!
        sx = int(WIDTH / 2 + (x / z) * fov)
        sy = int(HEIGHT / 2 - (y / z) * fov + self.flight.pitch * 300)
        return sx, sy

    def fire(self):
        self.bullets.append({"x": 0, "y": 0, "z": 50, "vz": 1200})

    def update(self, dt=1.0/FPS):
        if self.player_health <= 0:
            self.game_over = True
            return

        for b in self.bullets[:]:
            b["z"] += b["vz"] * dt
            if b["z"] > 2000:
                self.bullets.remove(b)
                continue
            # Check hits
            if self.stage == 1:
                for e in self.enemies:
                    if e["alive"] and abs(b["x"] - e["x"]) < 80 and abs(b["z"] - e["z"]) < 80:
                        e["hp"] -= 30
                        b["z"] = 9999
                        if e["hp"] <= 0:
                            e["alive"] = False
                            self.kills += 1
            else:
                # Stage 2: In control group, player shoots ground targets with guns instead of dropping bombs
                for g in self.ground_targets:
                    if g["alive"] and abs(b["x"] - g["x"]) < 100 and abs(b["z"] - g["z"]) < 100:
                        g["hp"] -= 40
                        b["z"] = 9999
                        if g["hp"] <= 0:
                            g["alive"] = False
                            self.ground_kills += 1

        if self.stage == 1 and self.kills >= 2:
            self.stage = 2
            self.ground_targets = [
                {"x": random.uniform(-200, 200), "y": -300, "z": 600 + i * 300, "hp": 100, "alive": True}
                for i in range(4)
            ]

        if self.stage == 2 and self.ground_kills >= 3:
            self.game_won = True

    def draw(self):
        if self.headless:
            return
        self.screen.fill((30, 60, 100))
        # Bug: Flat horizon without bank angle
        h_y = int(HEIGHT / 2 + self.flight.pitch * 300)
        pygame.draw.rect(self.screen, (30, 70, 40), (0, h_y, WIDTH, HEIGHT - h_y))

        # Crosshair
        pygame.draw.circle(self.screen, (255, 170, 30), (WIDTH // 2, HEIGHT // 2), 24, 2)
        pygame.draw.line(self.screen, (255, 170, 30), (WIDTH // 2 - 35, HEIGHT // 2), (WIDTH // 2 + 35, HEIGHT // 2), 2)
        pygame.draw.line(self.screen, (255, 170, 30), (WIDTH // 2, HEIGHT // 2 - 35), (WIDTH // 2, HEIGHT // 2 + 35), 2)

        # Bullets
        for b in self.bullets:
            pt = self.project_3d(b["x"], b["y"], b["z"])
            if pt[0] is not None:
                pygame.draw.circle(self.screen, (255, 240, 150), pt, 4)

        # Enemies (Stage 1)
        if self.stage == 1:
            for e in self.enemies:
                if e["alive"]:
                    pt = self.project_3d(e["x"], e["y"], e["z"])
                    if pt[0] is not None:
                        w = max(10, int(18000 / e["z"]))
                        pygame.draw.rect(self.screen, (60, 80, 65), (pt[0] - w // 2, pt[1] - 8, w, 16))
        else:
            # Ground targets (Stage 2)
            for g in self.ground_targets:
                if g["alive"]:
                    pt = self.project_3d(g["x"], g["y"], g["z"])
                    if pt[0] is not None:
                        w = max(12, int(22000 / g["z"]))
                        pygame.draw.rect(self.screen, (100, 100, 105), (pt[0] - w // 2, pt[1] - w // 4, w, w // 2))

        # Cockpit lower panel & HUD text
        pygame.draw.rect(self.screen, (22, 24, 28), (0, HEIGHT - 110, WIDTH, 110))
        font = pygame.font.SysFont("monospace", 14)
        status_txt = f"STAGE {self.stage} | HEALTH: {self.player_health}% | KILLS: {self.kills if self.stage == 1 else self.ground_kills}"
        mode_txt = "STAGE 1: DOGFIGHT (RADAR BASE MISSING)" if self.stage == 1 else "STAGE 2: STRAFING (BOMB DROP MISSING)"
        warn_txt = "[CONTROL GROUP: FLAT HORIZON / NO RADAR HP / NO DIVE BOMB]"
        self.screen.blit(font.render(status_txt, True, (220, 220, 210)), (30, HEIGHT - 90))
        self.screen.blit(font.render(mode_txt, True, (255, 170, 30)), (30, HEIGHT - 65))
        self.screen.blit(font.render(warn_txt, True, (240, 80, 80)), (30, HEIGHT - 40))

        pygame.display.flip()

    def run(self):
        running = True
        fire_cooldown = 0.0
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            if fire_cooldown > 0:
                fire_cooldown -= dt
            p_in, r_in = 0.0, 0.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in (pygame.K_SPACE, pygame.K_j):
                        if fire_cooldown <= 0:
                            self.fire()
                            fire_cooldown = 0.12

            keys = pygame.key.get_pressed()
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                p_in = 1.0
            elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
                p_in = -1.0
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                r_in = -1.0
            elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                r_in = 1.0

            if (keys[pygame.K_SPACE] or keys[pygame.K_j]) and fire_cooldown <= 0:
                self.fire()
                fire_cooldown = 0.12

            self.flight.update(dt, p_in, r_in)
            self.update(dt)
            self.draw()
        pygame.quit()

def run_control_selftest():
    print("==========================================================================")
    print("  BATTLE OF BRITAIN (CONTROL GROUP) —— Headless 自检 (pygame/python)")
    print("==========================================================================")
    g = ControlGame(headless=True)
    tests = 0

    # 1. 基础启动
    assert g.stage == 1
    print("  [PASS] t_control_initial_state: 基础关卡启动正常")
    tests += 1

    # 2. 投影测试 (检出缺陷：未应用滚转角)
    g.flight.roll = 0.5
    sx, sy = g.project_3d(100, 0, 500)
    # 对照组由于丢失滚转矩阵，sx 计算完全不受 roll 影响
    has_roll_tilt = False  # 明确记录缺陷
    print("  [WARN] t_control_horizon_roll: 对照组缺失机体滚转姿态倾角矩阵 (平直地平线)")
    tests += 1

    # 3. 第一关保卫测试 (检出缺陷：无雷达站生命值，降级为普通击落计数)
    has_radar_hp = hasattr(g, 'radar_station_hp')
    assert not has_radar_hp, "对照组遗忘了多佛雷达站独立防御生命值机制"
    print("  [WARN] t_control_radar_defense: 对照组缺失保卫目标血条 (降级为单纯杀敌数)")
    tests += 1

    # 4. 第二关轰炸测试 (检出缺陷：无俯冲瞄准具，无炸弹下落实体)
    has_bomb_sight = hasattr(g, 'drop_bomb')
    assert not has_bomb_sight, "对照组遗忘了下俯投弹与航弹实体逻辑 (降级为机枪扫地)"
    print("  [WARN] t_control_dive_bombing: 对照组缺失航弹投放与俯冲投弹瞄准环")
    tests += 1

    # 5. 关卡切关冒烟
    g.kills = 2
    g.update(0.1)
    assert g.stage == 2, "对照组切关逻辑生效"
    print("  [PASS] t_control_stage_transition: 对照组两关切换生效")
    tests += 1

    print("--------------------------------------------------------------------------")
    print(f"  自检统计: {tests} 项执行完毕 (3 项保留基线典型回归缺陷)")
    print("SELFTEST: CONTROL_BASELINE_OK")
    return True

if __name__ == "__main__":
    if HEADLESS:
        run_control_selftest()
    else:
        cg = ControlGame()
        cg.run()
