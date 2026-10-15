#!/usr/bin/env python3
"""
Generate and save high-resolution gameplay screenshots for all benchmark games.
Captures key action moments:
1. Battle of Britain Stage 1: Spitfire Cockpit Intercept & Radar Defense
2. Battle of Britain Stage 2: Calais Dive-Bombing Run & Flak Bursts
3. Raiden Arcade Stage 1: Vulcan 5-way Bullet Hell & Starfield
4. Raiden Boss Battle: Boss Warship with multi-phase health bar & laser beams
5. Tank Battle: Classic 2D Tank Combat & Power-Ups
"""

import os
import sys
import math

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.abspath("."))
import pygame

OUTPUT_DIR = "experiments/screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# 1. Battle of Britain - Stage 1 (Dover Defense)
# ----------------------------------------------------------------------
def capture_air_combat_stage1():
    from experiments.air_combat_benchmark.treatment_active_muse.battle_of_britain import BattleOfBritainGame
    game = BattleOfBritainGame(headless=False)
    # Simulate a dynamic dogfight frame with roll and banking
    game.flight.pitch = 0.08
    game.flight.roll = 0.28
    game.flight.speed = 280.0
    game.flight.altitude = 7500.0
    game.gun_heat = 42.0

    # Advance enemies into clear view
    for e in game.enemies:
        if e.kind == 'he111':
            e.z = 450.0
            e.y = 30.0
        else:
            e.z = 320.0
            e.x = 80.0
            e.y = -20.0

    # Fire converging tracers
    game.fire_machine_guns()
    for p in game.projectiles:
        p.z += 120.0

    game.draw()
    path = os.path.join(OUTPUT_DIR, "air_combat_stage1_defense.png")
    pygame.image.save(game.screen, path)
    print(f"Saved: {path}")

# ----------------------------------------------------------------------
# 2. Battle of Britain - Stage 2 (Calais Dive Bombing)
# ----------------------------------------------------------------------
def capture_air_combat_stage2():
    from experiments.air_combat_benchmark.treatment_active_muse.battle_of_britain import BattleOfBritainGame
    game = BattleOfBritainGame(headless=False)
    game._init_stage2_bombing()
    # Steep dive angle to activate red dive bombing reticle
    game.flight.pitch = -0.16
    game.flight.roll = -0.15
    game.flight.speed = 340.0
    game.flight.altitude = 3200.0

    # Ground targets in field of view
    game.ground_targets[0].z = 380.0
    game.ground_targets[0].x = 40.0
    game.ground_targets[1].z = 620.0
    game.ground_targets[1].x = -80.0

    # Released 500lb bomb in flight
    game.drop_bomb()
    if game.bombs:
        game.bombs[0].z = 240.0
        game.bombs[0].y = -90.0

    # Atmospheric 88mm flak black smoke bursts
    game.flak_bursts.append({"x": -60, "y": 80, "z": 450, "timer": 0.9})
    game.flak_bursts.append({"x": 140, "y": -40, "z": 380, "timer": 0.7})

    game.draw()
    path = os.path.join(OUTPUT_DIR, "air_combat_stage2_bombing.png")
    pygame.image.save(game.screen, path)
    print(f"Saved: {path}")

# ----------------------------------------------------------------------
# 3. Raiden Arcade - Vulcan 5-way & Homing Missiles
# ----------------------------------------------------------------------
def capture_raiden_combat():
    pygame.init()
    pygame.font.init()
    sys.path.insert(0, "experiments/tank_battle_benchmark/treatment_active_memory")
    import raiden_game
    from raiden_game import Game, W, H, Enemy, PowerUp, render

    game = Game(seed=42)
    game.weapon.kind = "vulcan"
    game.weapon.level = 3
    game.player.x = W / 2
    game.player.y = H - 90
    game.player.invuln = 0.0

    # Populate active enemy waves
    game.enemies.append(Enemy("scout", W / 2 - 120, 140, game.rng))
    game.enemies.append(Enemy("diver", W / 2 + 100, 160, game.rng))
    game.enemies.append(Enemy("turret", W / 2 - 20, 90, game.rng))
    game.enemies.append(Enemy("spinner", W / 2 + 140, 110, game.rng))
    game.powerups.append(PowerUp("vulcan", W / 2 + 60, 260))

    # Fire multiple frames so bullets travel upward across screen
    for _ in range(16):
        game._fire_weapon(1.0 / 60, inp={"fire": True})
        for b in game.bullets:
            b.y += b.vy * (1.0 / 60)
            b.x += b.vx * (1.0 / 60)

    # Add some homing missiles as well
    from raiden_game import HOMING_SPECS
    for dx, off in HOMING_SPECS[2]:
        b = game.player_bullet(game.player.x + dx, game.player.y - 8, -math.pi / 2 + off, 330, radius=5,
                               color=(120, 240, 150), damage=2, kind="missile", homing=True)
        b.y -= 110.0

    # Add some enemy counter-fire
    game.enemy_bullet(W / 2 - 20, 95, math.pi / 2, 140, radius=5, color=(255, 160, 160))
    game.enemy_bullet(W / 2 - 20, 95, math.pi / 2 - 0.3, 140, radius=5, color=(255, 160, 160))
    game.enemy_bullet(W / 2 - 20, 95, math.pi / 2 + 0.3, 140, radius=5, color=(255, 160, 160))

    surface = pygame.Surface((W, H))
    font = pygame.font.Font(None, 14)
    render(surface, game, font)
    path = os.path.join(OUTPUT_DIR, "raiden_combat_vulcan_missiles.png")
    pygame.image.save(surface, path)
    print(f"Saved: {path}")

# ----------------------------------------------------------------------
# 4. Raiden Arcade - Boss Battle with Multi-Phase Health Bar & Lasers
# ----------------------------------------------------------------------
def capture_raiden_boss():
    pygame.init()
    pygame.font.init()
    sys.path.insert(0, "experiments/tank_battle_benchmark/treatment_active_memory")
    import raiden_game
    from raiden_game import Game, W, H, Boss, render

    game = Game(seed=101)
    game.boss = Boss(W / 2, 130)
    game.boss.state = "fight"
    game.boss.phase = 2
    game.boss.hp = int(game.boss.max_hp * 0.55)
    game.weapon.kind = "laser"
    game.weapon.level = 2
    game.player.x = W / 2
    game.player.y = H - 85
    game.player.invuln = 0.0

    # Trigger boss circular bullet spray with visible spread radius
    for i in range(24):
        ang = (i / 24.0) * math.tau
        b = game.enemy_bullet(game.boss.x, game.boss.y, ang, 160, radius=5, color=(255, 120, 220))
        b.x += b.vx * 0.72
        b.y += b.vy * 0.72

    # Player firing piercing laser beam
    game._fire_weapon(1.0 / 60, inp={"fire": True})

    surface = pygame.Surface((W, H))
    font = pygame.font.Font(None, 14)
    render(surface, game, font)
    path = os.path.join(OUTPUT_DIR, "raiden_boss_battle_lasers.png")
    pygame.image.save(surface, path)
    print(f"Saved: {path}")

# ----------------------------------------------------------------------
# 5. Tank Battle - Classic 2D Combat
# ----------------------------------------------------------------------
def capture_tank_battle():
    pygame.init()
    pygame.font.init()
    sys.path.insert(0, "experiments/tank_battle_benchmark/treatment_active_memory")
    import tank_game
    from tank_game import Game, WIN_W, WIN_H, PowerUp, Explosion, render

    game = Game(seed=7)
    # Simulate a few movements and enemy spawns
    for _ in range(60):
        game.update(1.0 / 60)

    if game.player:
        game.player.level = 3
        game.player.shield_timer = 4.0
        game.player.fire(game)

    # Spawn powerups & explosions for action capture
    game.powerups.append(PowerUp("star", 200, 240))
    game.powerups.append(PowerUp("shield", 320, 300))
    game.explosions.append(Explosion(260, 200, 0.4, big=True))

    surface = pygame.Surface((WIN_W, WIN_H))
    font = pygame.font.Font(None, 14)
    render(surface, game, font)
    path = os.path.join(OUTPUT_DIR, "tank_battle_action.png")
    pygame.image.save(surface, path)
    print(f"Saved: {path}")

if __name__ == "__main__":
    capture_air_combat_stage1()
    capture_air_combat_stage2()
    capture_raiden_combat()
    capture_raiden_boss()
    capture_tank_battle()
    print("All screenshots captured successfully!")
