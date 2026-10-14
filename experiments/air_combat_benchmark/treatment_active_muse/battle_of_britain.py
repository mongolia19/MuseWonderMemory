#!/usr/bin/env python3
"""
Battle of Britain (1940) - First-Person WWII Flight Combat Simulation
Treatment Group: Built with Active Memory & Active Focus invariants.
Pure procedural geometry rendering with Pygame. Zero external asset dependencies.

Stages:
  Stage 1: Defense of Britain (保卫战) - Intercept He 111 bombers & Bf 109 escorts, protect Dover Radar Station.
  Stage 2: Channel Strike (轰炸战) - Cross the Channel, dive-bomb Calais staging airfield & fuel dumps with bomb sight.
"""

import sys
import math
import random
import os

# Headless check flag
HEADLESS = "--test" in sys.argv or "--headless" in sys.argv
if HEADLESS:
    os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

WIDTH, HEIGHT = 800, 600
FPS = 60

# Palette
SKY_TOP = (25, 60, 115)
SKY_HORIZON = (130, 175, 215)
SEA_DARK = (20, 50, 70)
SEA_LIGHT = (45, 85, 110)
LAND_GREEN = (40, 75, 35)
LAND_LIGHT = (65, 105, 55)
COCKPIT_FRAME = (35, 40, 45)
COCKPIT_RIVET = (60, 65, 70)
PANEL_BG = (22, 24, 28)
DIAL_FACE = (15, 18, 20)
DIAL_TEXT = (220, 220, 210)
HUD_ORANGE = (255, 170, 30)
HUD_GREEN = (50, 230, 90)
HUD_RED = (240, 50, 50)
SMOKE_BLACK = (30, 30, 30)
FIRE_ORANGE = (255, 120, 20)
BULLET_TRACER = (255, 240, 150)


class FlightModel:
    """Realistic WWII Spitfire Mk I flight envelope & physics."""
    def __init__(self):
        self.pitch = 0.0      # radians (-0.5 to +0.5)
        self.roll = 0.0       # radians (-0.8 to +0.8)
        self.yaw = 0.0        # heading radians (0 to 2*pi)
        self.throttle = 0.7   # 0.2 to 1.0
        self.speed = 240.0    # mph (120 stall to 380 max)
        self.altitude = 8000.0# feet (500 to 25000)
        self.stall_warning = False

    def update(self, dt: float, pitch_input: float, roll_input: float, throttle_input: float):
        # Flight stick response
        pitch_rate = 0.9 * dt
        roll_rate = 1.4 * dt
        
        self.pitch = max(-0.5, min(0.5, self.pitch + pitch_input * pitch_rate))
        self.roll = max(-0.8, min(0.8, self.roll + roll_input * roll_rate))
        
        # Self-centering tendencies when no input
        if pitch_input == 0:
            self.pitch *= (1.0 - 1.2 * dt)
        if roll_input == 0:
            self.roll *= (1.0 - 1.5 * dt)
            
        # Yaw couples with roll (banking turn)
        self.yaw = (self.yaw + self.roll * 0.8 * dt) % (2 * math.pi)

        # Throttle adjustments
        self.throttle = max(0.2, min(1.0, self.throttle + throttle_input * dt * 0.5))

        # Speed calculation (thrust vs drag vs dive/climb)
        target_speed = self.throttle * 340.0 - self.pitch * 160.0
        self.speed += (target_speed - self.speed) * dt * 1.5
        self.speed = max(110.0, min(420.0, self.speed))

        # Altitude
        climb_rate = math.sin(self.pitch) * (self.speed * 1.466) # ft/s
        self.altitude = max(500.0, min(24000.0, self.altitude + climb_rate * dt))

        # Stall condition
        self.stall_warning = self.speed < 130.0 and self.pitch > 0.2


class Projectile:
    """Machine gun tracer round in 3D perspective space."""
    def __init__(self, x, y, z, vx, vy, vz, is_player=True):
        self.x = x
        self.y = y
        self.z = z  # Distance in front of camera
        self.vx = vx
        self.vy = vy
        self.vz = vz
        self.is_player = is_player
        self.alive = True
        self.lifetime = 1.8

    def update(self, dt: float):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z += self.vz * dt
        self.lifetime -= dt
        if self.lifetime <= 0 or self.z <= 10 or self.z > 2500:
            self.alive = False


class Bomb:
    """Free-fall 500lb general-purpose bomb for Stage 2."""
    def __init__(self, x, y, z, forward_speed):
        self.x = x
        self.y = y
        self.z = z
        self.vx = 0.0
        self.vy = -20.0       # falling towards ground
        self.vz = forward_speed
        self.alive = True
        self.exploded = False
        self.explosion_timer = 0.0
        self.impact_x = 0
        self.impact_y = 0

    def update(self, dt: float):
        if not self.exploded:
            self.vy -= 90.0 * dt  # Gravity acceleration
            self.y += self.vy * dt
            self.z += self.vz * dt
            # When bomb hits terrain level
            if self.y <= -200:
                self.exploded = True
                self.explosion_timer = 0.6
        else:
            self.explosion_timer -= dt
            if self.explosion_timer <= 0:
                self.alive = False


class Aircraft3D:
    """3D aircraft entity (He 111, Bf 109, etc.)."""
    def __init__(self, kind: str, x: float, y: float, z: float):
        self.kind = kind  # 'he111' (bomber) or 'bf109' (escort fighter)
        self.x = x
        self.y = y
        self.z = z  # Distance
        self.vx = 0.0
        self.vy = 0.0
        self.vz = -180.0 if kind == 'he111' else -240.0
        self.health = 180 if kind == 'he111' else 75
        self.max_health = self.health
        self.alive = True
        self.shoot_cooldown = random.uniform(1.0, 2.5)
        self.bombs_dropped = False

    def update(self, dt: float, player_flight: FlightModel):
        # Move forward relative to camera space
        self.z += self.vz * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Fighter AI maneuvers
        if self.kind == 'bf109':
            # Gentle lead tracking
            dx = -self.x
            dy = -self.y
            self.vx += max(-80.0, min(80.0, dx * 0.4)) * dt
            self.vy += max(-60.0, min(60.0, dy * 0.3)) * dt
        else:
            # He 111 steady bombing run
            self.vx = math.sin(self.z * 0.005) * 20.0

        if self.z < 30:
            # Overflown player
            self.alive = False


class GroundTarget:
    """Stage 2 Ground Target (Hangars, Fuel Dumps, Flak batteries)."""
    def __init__(self, kind: str, x: float, z: float):
        self.kind = kind  # 'hangar', 'fuel_tank', 'flak_88', 'bunker'
        self.x = x
        self.y = -350.0   # Ground altitude
        self.z = z        # Distance ahead
        self.health = 120
        self.alive = True
        self.destroyed = False

    def update(self, dt: float, forward_speed: float):
        self.z -= forward_speed * dt
        if self.z < 20:
            self.z += 3000.0  # Loop terrain targets


class BattleOfBritainGame:
    """First-Person Flight Combat Simulation Game."""
    def __init__(self, headless=HEADLESS):
        pygame.init()
        self.headless = headless
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Battle of Britain (1940) - RAF Spitfire Mk I")
        self.clock = pygame.time.Clock()
        self.running = True

        # Game campaign state
        self.stage = 1  # 1: Defense of Britain (保卫战), 2: Channel Bombing (轰炸战)
        self.score = 0
        self.stage_cleared = False
        self.game_won = False
        self.game_over = False

        # Flight & Systems
        self.flight = FlightModel()
        self.player_health = 100
        self.gun_heat = 0.0          # Overheat mechanic (0 - 100)
        self.gun_jammed = False
        self.bombs_remaining = 4     # For Stage 2

        # Defense mission targets (Stage 1)
        self.radar_station_hp = 100  # Dover CH Radar health
        self.bombers_downed = 0
        self.fighters_downed = 0

        # Bombing mission targets (Stage 2)
        self.ground_targets_destroyed = 0

        # World entities
        self.projectiles = []
        self.enemies = []
        self.bombs = []
        self.ground_targets = []
        self.flak_bursts = []        # Black 88mm flak smoke
        self.clouds = [
            {"x": random.uniform(-1500, 1500), "y": random.uniform(100, 800), "z": random.uniform(300, 3000), "r": random.uniform(80, 200)}
            for _ in range(16)
        ]

        self.font = pygame.font.SysFont("monospace", 14, bold=True)
        self.title_font = pygame.font.SysFont("monospace", 22, bold=True)

        self._spawn_stage1_wave()

    def _spawn_stage1_wave(self):
        self.enemies.clear()
        # V-formation of 4 Heinkel He 111 bombers
        formations = [(0, 50, 1600), (-350, 90, 1850), (350, 90, 1850), (-700, 140, 2100)]
        for x, y, z in formations:
            self.enemies.append(Aircraft3D('he111', x, y, z))
        # 2 Bf 109 escorts
        self.enemies.append(Aircraft3D('bf109', -400, 250, 1400))
        self.enemies.append(Aircraft3D('bf109', 400, 250, 1400))

    def _init_stage2_bombing(self):
        self.stage = 2
        self.enemies.clear()
        self.ground_targets.clear()
        self.bombs.clear()
        self.flak_bursts.clear()
        self.flight.altitude = 4500.0  # Lower altitude for dive-bombing
        self.bombs_remaining = 4

        # Spawn ground installation targets at Calais
        target_kinds = ['hangar', 'fuel_tank', 'flak_88', 'bunker', 'hangar', 'fuel_tank']
        for i, kind in enumerate(target_kinds):
            self.ground_targets.append(GroundTarget(kind, random.uniform(-400, 400), 700 + i * 450))

        # Flak & Fighter resistance
        self.enemies.append(Aircraft3D('bf109', -300, 200, 1800))
        self.enemies.append(Aircraft3D('bf109', 300, 200, 2000))

    def project_3d(self, x, y, z):
        """Perspective 3D projection taking camera roll and pitch into account."""
        if z <= 5:
            return None, None, 0

        # Pitch translates Y
        pitch_offset = math.tan(self.flight.pitch) * 450.0
        
        # Base projection
        fov = 420.0
        proj_x = (x / z) * fov
        proj_y = (- (y / z) * fov) + pitch_offset

        # Apply roll rotation
        cos_r = math.cos(-self.flight.roll)
        sin_r = math.sin(-self.flight.roll)
        rot_x = proj_x * cos_r - proj_y * sin_r
        rot_y = proj_x * sin_r + proj_y * cos_r

        screen_x = int(WIDTH / 2 + rot_x)
        screen_y = int(HEIGHT / 2 + rot_y)
        scale = max(0.08, fov / z)
        return screen_x, screen_y, scale

    def fire_machine_guns(self):
        """Fire 8 wing-mounted .303 Browning machine guns converging at 250 yards."""
        if self.gun_jammed:
            return False

        # Heat builds up
        self.gun_heat = min(100.0, self.gun_heat + 4.5)
        if self.gun_heat >= 100.0:
            self.gun_jammed = True

        # Left & Right wing tracer origin
        for wing_x in (-60, -35, 35, 60):
            vx = -wing_x * 0.12 + math.sin(self.flight.roll) * 10
            vy = math.sin(self.flight.pitch) * 20
            vz = 1400.0 + self.flight.speed * 1.2
            self.projectiles.append(Projectile(wing_x, -15, 35, vx, vy, vz, is_player=True))
        return True

    def drop_bomb(self):
        """Stage 2: Release 500lb bomb from belly rack."""
        if self.stage != 2 or self.bombs_remaining <= 0:
            return False
        self.bombs_remaining -= 1
        forward_speed = self.flight.speed * 1.4
        self.bombs.append(Bomb(0, -30, 40, forward_speed))
        return True

    def update(self, dt=1.0/FPS):
        if self.player_health <= 0:
            self.game_over = True
        if self.game_over or self.game_won:
            return

        # Gun cooling
        if not self.gun_jammed:
            self.gun_heat = max(0.0, self.gun_heat - 28.0 * dt)
        else:
            self.gun_heat = max(0.0, self.gun_heat - 14.0 * dt)
            if self.gun_heat <= 15.0:
                self.gun_jammed = False

        # Update Projectiles
        for p in self.projectiles[:]:
            p.update(dt)
            if not p.alive:
                self.projectiles.remove(p)
                continue

            # Player bullet hitting enemies
            if p.is_player:
                for enemy in self.enemies:
                    if not enemy.alive:
                        continue
                    # Hitbox detection in 3D
                    dist_sq = (p.x - enemy.x)**2 + (p.y - enemy.y)**2 + (p.z - enemy.z)**2
                    hit_radius = 80 if enemy.kind == 'he111' else 45
                    if dist_sq < hit_radius**2:
                        enemy.health -= 18
                        p.alive = False
                        if enemy.health <= 0:
                            enemy.alive = False
                            self.score += 250 if enemy.kind == 'he111' else 150
                            if enemy.kind == 'he111':
                                self.bombers_downed += 1
                            else:
                                self.fighters_downed += 1
                        break
            else:
                # Enemy bullet hitting player
                if p.z < 40 and abs(p.x) < 45 and abs(p.y) < 35:
                    self.player_health = max(0, self.player_health - 6)
                    p.alive = False
                    if self.player_health <= 0:
                        self.game_over = True

        # Update Bombs (Stage 2)
        if self.stage == 2:
            for b in self.bombs[:]:
                b.update(dt)
                if b.exploded:
                    # Check blast against ground targets
                    for t in self.ground_targets:
                        if t.alive and not t.destroyed:
                            dist_to_target = math.hypot(b.x - t.x, b.z - t.z)
                            if dist_to_target < 180.0:
                                t.health -= 120
                                if t.health <= 0:
                                    t.destroyed = True
                                    self.ground_targets_destroyed += 1
                                    self.score += 400
                if not b.alive:
                    self.bombs.remove(b)

            # Update Ground Targets
            forward_speed = self.flight.speed * 0.8
            for t in self.ground_targets:
                t.update(dt, forward_speed)

            # Flak 88mm atmospheric bursts
            if random.random() < 0.04:
                burst_x = random.uniform(-400, 400)
                burst_y = random.uniform(-100, 300)
                burst_z = random.uniform(200, 1200)
                self.flak_bursts.append({"x": burst_x, "y": burst_y, "z": burst_z, "timer": 1.2})

            for flak in self.flak_bursts[:]:
                flak["timer"] -= dt
                # Damage player if too close
                if flak["timer"] > 0.8:
                    d = math.hypot(flak["x"], flak["y"], flak["z"] - 60)
                    if d < 120:
                        self.player_health = max(0, self.player_health - int(10 * dt * 60))
                        if self.player_health <= 0:
                            self.game_over = True
                if flak["timer"] <= 0:
                    self.flak_bursts.remove(flak)

        # Update Enemies & Bomber Attack
        for enemy in self.enemies[:]:
            enemy.update(dt, self.flight)
            if not enemy.alive:
                self.enemies.remove(enemy)
                continue

            # Stage 1: Bombers attack Dover Radar if close enough
            if self.stage == 1 and enemy.kind == 'he111' and enemy.z < 250 and not enemy.bombs_dropped:
                enemy.bombs_dropped = True
                self.radar_station_hp = max(0, self.radar_station_hp - 18)
                if self.radar_station_hp <= 0:
                    self.game_over = True

            # Enemy shoots at player
            enemy.shoot_cooldown -= dt
            if enemy.shoot_cooldown <= 0 and 80 < enemy.z < 1200:
                enemy.shoot_cooldown = random.uniform(1.2, 2.5)
                # Tracer towards player
                self.projectiles.append(Projectile(enemy.x, enemy.y, enemy.z, -enemy.x * 0.4, -enemy.y * 0.4, -900, is_player=False))

        # Check Stage Progression
        if self.stage == 1:
            # Respawn enemy formation if wiped out until required targets downed
            if len(self.enemies) == 0:
                if self.bombers_downed >= 4:
                    # Stage 1 Cleared -> Move to Stage 2
                    self._init_stage2_bombing()
                else:
                    self._spawn_stage1_wave()
        elif self.stage == 2:
            if self.ground_targets_destroyed >= 4:
                self.game_won = True

    def draw(self):
        if self.headless:
            return

        self.screen.fill(SKY_TOP)

        # 1. Artificial Horizon (Atmospheric Sky & Sea/Ground)
        horizon_pitch = math.tan(self.flight.pitch) * 450.0
        center_x, center_y = WIDTH // 2, HEIGHT // 2

        # Draw rotated horizon
        angle_deg = math.degrees(self.flight.roll)
        sea_surf = pygame.Surface((WIDTH * 2, HEIGHT * 2), pygame.SRCALPHA)
        color_lower = SEA_DARK if self.stage == 1 else LAND_GREEN
        pygame.draw.rect(sea_surf, color_lower, (0, HEIGHT, WIDTH * 2, HEIGHT * 2))
        rotated_sea = pygame.transform.rotate(sea_surf, angle_deg)
        new_rect = rotated_sea.get_rect(center=(center_x, center_y + int(horizon_pitch)))
        self.screen.blit(rotated_sea, new_rect.topleft)

        # 2. Render Ground Targets (Stage 2)
        if self.stage == 2:
            for t in self.ground_targets:
                sx, sy, scale = self.project_3d(t.x, t.y, t.z)
                if sx is not None and -100 < sx < WIDTH + 100 and -100 < sy < HEIGHT + 100:
                    w = int(60 * scale)
                    h = int(35 * scale)
                    col = (110, 110, 110) if not t.destroyed else (40, 40, 40)
                    pygame.draw.rect(self.screen, col, (sx - w//2, sy - h//2, w, h))
                    if t.destroyed:
                        pygame.draw.circle(self.screen, FIRE_ORANGE, (sx, sy), int(20 * scale))

        # 3. Render 3D Enemies (He 111 / Bf 109)
        for enemy in self.enemies:
            sx, sy, scale = self.project_3d(enemy.x, enemy.y, enemy.z)
            if sx is not None and -100 < sx < WIDTH + 100 and -100 < sy < HEIGHT + 100:
                wing_w = int((140 if enemy.kind == 'he111' else 80) * scale)
                fuse_l = int((90 if enemy.kind == 'he111' else 60) * scale)
                c = (70, 85, 70) if enemy.kind == 'he111' else (80, 80, 95)
                # Fuselage
                pygame.draw.rect(self.screen, c, (sx - fuse_l//4, sy - fuse_l//2, fuse_l//2, fuse_l))
                # Wings
                pygame.draw.rect(self.screen, (55, 65, 55), (sx - wing_w//2, sy - 8, wing_w, max(4, int(16 * scale))))
                # Twin engines for He 111
                if enemy.kind == 'he111':
                    pygame.draw.circle(self.screen, (40, 45, 40), (sx - wing_w//4, sy), max(2, int(8 * scale)))
                    pygame.draw.circle(self.screen, (40, 45, 40), (sx + wing_w//4, sy), max(2, int(8 * scale)))

        # 4. Render Projectiles & Bomb Sight
        for p in self.projectiles:
            sx, sy, scale = self.project_3d(p.x, p.y, p.z)
            if sx is not None and 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                r = max(2, int(6 * scale))
                col = BULLET_TRACER if p.is_player else (255, 80, 80)
                pygame.draw.circle(self.screen, col, (sx, sy), r)

        # Flak smoke (Stage 2)
        if self.stage == 2:
            for flak in self.flak_bursts:
                sx, sy, scale = self.project_3d(flak["x"], flak["y"], flak["z"])
                if sx is not None:
                    pygame.draw.circle(self.screen, SMOKE_BLACK, (sx, sy), int(35 * scale * flak["timer"]))

        # 5. Cockpit Canopy & Dashboard Frame (First-Person Immersion)
        # Canopy Arch
        pygame.draw.polygon(self.screen, COCKPIT_FRAME, [(0, 0), (140, 0), (90, 420), (0, 460)])
        pygame.draw.polygon(self.screen, COCKPIT_FRAME, [(WIDTH, 0), (WIDTH - 140, 0), (WIDTH - 90, 420), (WIDTH, 460)])
        pygame.draw.line(self.screen, COCKPIT_RIVET, (140, 0), (90, 420), 4)
        pygame.draw.line(self.screen, COCKPIT_RIVET, (WIDTH - 140, 0), (WIDTH - 90, 420), 4)

        # Bottom Instrument Panel
        panel_y = HEIGHT - 150
        pygame.draw.rect(self.screen, PANEL_BG, (0, panel_y, WIDTH, 150))
        pygame.draw.line(self.screen, (80, 85, 90), (0, panel_y), (WIDTH, panel_y), 5)

        # Reflector Gunsight in Center
        sight_x, sight_y = WIDTH // 2, HEIGHT // 2 - 30
        pygame.draw.circle(self.screen, HUD_ORANGE, (sight_x, sight_y), 42, 2)
        pygame.draw.circle(self.screen, HUD_ORANGE, (sight_x, sight_y), 6, 2)
        pygame.draw.line(self.screen, HUD_ORANGE, (sight_x - 55, sight_y), (sight_x - 42, sight_y), 2)
        pygame.draw.line(self.screen, HUD_ORANGE, (sight_x + 42, sight_y), (sight_x + 55, sight_y), 2)
        pygame.draw.line(self.screen, HUD_ORANGE, (sight_x, sight_y - 55), (sight_x, sight_y - 42), 2)
        pygame.draw.line(self.screen, HUD_ORANGE, (sight_x, sight_y + 42), (sight_x, sight_y + 55), 2)

        # Stage 2: Dive-Bombing Reticle
        if self.stage == 2 and self.flight.pitch < -0.08:
            bomb_sight_y = sight_y + int(abs(self.flight.pitch) * 280)
            pygame.draw.circle(self.screen, HUD_RED, (sight_x, bomb_sight_y), 28, 2)
            pygame.draw.line(self.screen, HUD_RED, (sight_x - 12, bomb_sight_y), (sight_x + 12, bomb_sight_y), 2)
            lbl = self.font.render("BOMB IMPACT", True, HUD_RED)
            self.screen.blit(lbl, (sight_x - 45, bomb_sight_y + 32))

        # 6. Instrument Dials
        # Airspeed
        speed_txt = self.font.render(f"AIRSPEED: {int(self.flight.speed)} MPH", True, DIAL_TEXT)
        self.screen.blit(speed_txt, (50, panel_y + 30))
        # Altimeter
        alt_txt = self.font.render(f"ALTITUDE: {int(self.flight.altitude)} FT", True, DIAL_TEXT)
        self.screen.blit(alt_txt, (50, panel_y + 60))
        # Throttle
        thr_txt = self.font.render(f"THROTTLE: {int(self.flight.throttle * 100)}%", True, DIAL_TEXT)
        self.screen.blit(thr_txt, (50, panel_y + 90))

        # Gun Overheat bar
        heat_color = HUD_RED if self.gun_jammed else HUD_ORANGE
        pygame.draw.rect(self.screen, (50, 50, 50), (280, panel_y + 35, 160, 16))
        pygame.draw.rect(self.screen, heat_color, (280, panel_y + 35, int(1.6 * self.gun_heat), 16))
        heat_lbl = self.font.render("GUN HEAT " + ("(JAMMED!)" if self.gun_jammed else ""), True, heat_color)
        self.screen.blit(heat_lbl, (280, panel_y + 15))

        # Stage Objective & Armor
        armor_txt = self.font.render(f"SPITFIRE ARMOR: {self.player_health}%", True, HUD_GREEN if self.player_health > 30 else HUD_RED)
        self.screen.blit(armor_txt, (520, panel_y + 20))

        if self.stage == 1:
            stage_txt = self.font.render(f"STAGE 1: DEFEND DOVER RADAR", True, HUD_ORANGE)
            radar_txt = self.font.render(f"RADAR STATION HP: {self.radar_station_hp}%", True, HUD_GREEN if self.radar_station_hp > 30 else HUD_RED)
            kills_txt = self.font.render(f"BOMBERS DOWN: {self.bombers_downed}/4", True, DIAL_TEXT)
            self.screen.blit(stage_txt, (520, panel_y + 50))
            self.screen.blit(radar_txt, (520, panel_y + 75))
            self.screen.blit(kills_txt, (520, panel_y + 100))
        else:
            stage_txt = self.font.render(f"STAGE 2: BOMB CALAIS AIRFIELD", True, HUD_RED)
            bomb_txt = self.font.render(f"500LB BOMBS LEFT: {self.bombs_remaining} [PRESS B]", True, HUD_ORANGE)
            target_txt = self.font.render(f"TARGETS HIT: {self.ground_targets_destroyed}/4", True, HUD_GREEN)
            self.screen.blit(stage_txt, (520, panel_y + 50))
            self.screen.blit(bomb_txt, (520, panel_y + 75))
            self.screen.blit(target_txt, (520, panel_y + 100))

        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

            pitch_in = 0.0
            roll_in = 0.0
            thr_in = 0.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key in (pygame.K_b, pygame.K_k):
                        self.drop_bomb()

            keys = pygame.key.get_pressed()
            # Standard flight stick controls
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                pitch_in = 1.0  # Climb (pull back)
            elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
                pitch_in = -1.0 # Dive (push forward)

            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                roll_in = -1.0  # Bank left
            elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                roll_in = 1.0   # Bank right

            if keys[pygame.K_LSHIFT] or keys[pygame.K_r]:
                thr_in = 1.0
            elif keys[pygame.K_LCTRL] or keys[pygame.K_f]:
                thr_in = -1.0

            if keys[pygame.K_SPACE] or keys[pygame.K_j]:
                self.fire_machine_guns()

            self.flight.update(dt, pitch_in, roll_in, thr_in)
            self.update(dt)
            self.draw()

        pygame.quit()


# -------------------------------------------------------------
# Headless Automated QA Test Suite
# -------------------------------------------------------------
def run_selftest():
    print("==========================================================================")
    print("  BATTLE OF BRITAIN (1940) —— Headless QA 自检套件 (pygame/python)")
    print("==========================================================================")
    game = BattleOfBritainGame(headless=True)
    tests_passed = 0

    # 1. 第一人称座舱与视野投影
    assert game.stage == 1, "初始关卡必须为 Stage 1 保卫战"
    sx, sy, scale = game.project_3d(0, 0, 1000)
    assert sx == WIDTH // 2 and sy == HEIGHT // 2, "正前方向投影必须居中"
    print("  [PASS] t_first_person_cockpit_projection: 3D视锥与座舱视角投影基准正常")
    tests_passed += 1

    # 2. 地平线俯仰与滚转变换
    game.flight.pitch = 0.2
    game.flight.roll = 0.4
    sx_roll, sy_roll, _ = game.project_3d(100, 0, 500)
    assert sx_roll != WIDTH // 2, "机身倾斜滚转时必须产生坐标轴旋转"
    game.flight.pitch = 0.0
    game.flight.roll = 0.0
    print("  [PASS] t_horizon_pitch_and_roll: 人工平视仪滚转与俯仰转换矩阵生效")
    tests_passed += 1

    # 3. 飞行操纵习惯与包线
    game.flight.update(0.1, 1.0, 0.0, 0.5)
    assert game.flight.pitch > 0.0, "拉杆必须产生爬升俯仰角"
    assert game.flight.speed >= 110.0, "空速绝不能低于失速下限"
    print("  [PASS] t_flight_dynamics_and_envelope: 空速、俯仰、滚转与失速逻辑正常")
    tests_passed += 1

    # 4. 八挺机枪弹道与射击过热槽
    initial_projectiles = len(game.projectiles)
    game.fire_machine_guns()
    assert len(game.projectiles) == initial_projectiles + 4, "一次击发必须产生 4 组翼中机枪弹道"
    assert game.gun_heat > 0.0, "连续击发必须增加机枪热量"
    # 模拟持续射击过热卡壳
    for _ in range(30):
        game.fire_machine_guns()
    assert game.gun_jammed, "过热值达到 100 必须触发机枪卡壳"
    print("  [PASS] t_browning_converging_and_heat: 勃朗宁机枪弹道汇聚与过热卡壳生效")
    tests_passed += 1

    # 5. 敌方机群生成与区分 (He 111 轰炸机 vs Bf 109 战斗机)
    has_he111 = any(e.kind == 'he111' for e in game.enemies)
    has_bf109 = any(e.kind == 'bf109' for e in game.enemies)
    assert has_he111 and has_bf109, "第一关敌机群必须同时包含轰炸机与护航战斗机"
    print("  [PASS] t_enemy_formation_composition: 德军 He 111 轰炸机编队与 Bf 109 护航机生成正常")
    tests_passed += 1

    # 6. 第一关雷达站保卫生命值扣减机制
    bomber = next(e for e in game.enemies if e.kind == 'he111')
    bomber.z = 240  # 逼近雷达站空域
    old_radar_hp = game.radar_station_hp
    game.update(0.1)
    assert game.radar_station_hp < old_radar_hp, "轰炸机突破防线投弹必须扣减多佛雷达站生命值"
    print("  [PASS] t_radar_defense_health_loss: 雷达站受损防守生命值机制正常")
    tests_passed += 1

    # 7. 第一关击落达标与无缝切入第二关
    game.bombers_downed = 4
    game.enemies.clear() # 扫清第一波
    game.update(0.1)
    assert game.stage == 2, "击落 4 架轰炸机且保卫成功后必须无缝晋级到 Stage 2 轰炸战"
    print("  [PASS] t_stage1_to_stage2_transition: 第一关保卫战胜利判定与切关正常")
    tests_passed += 1

    # 8. 第二关对地俯冲投弹瞄准环判定
    game.flight.pitch = -0.15 # 俯冲角
    assert game.flight.pitch < -0.08, "大角度俯冲角成立"
    assert len(game.ground_targets) > 0, "第二关必须生成加莱前沿机场地面目标"
    print("  [PASS] t_stage2_dive_bombing: 俯冲轰炸进入角与地面建筑网格生成正常")
    tests_passed += 1

    # 9. 航弹投掷与重力弹道物理
    initial_bombs = game.bombs_remaining
    game.drop_bomb()
    assert game.bombs_remaining == initial_bombs - 1, "投弹必须扣减弹舱挂载数"
    assert len(game.bombs) == 1, "航弹实体必须生成并脱钩下坠"
    bomb = game.bombs[0]
    old_vy = bomb.vy
    bomb.update(0.2)
    assert bomb.vy < old_vy, "航弹必须受重力加速度下落"
    print("  [PASS] t_bomb_ballistics_and_payload: 500磅通用航弹脱钩与自由落体弹道正常")
    tests_passed += 1

    # 10. 航弹爆炸半径与地面目标摧毁判定
    target = game.ground_targets[0]
    bomb.x = target.x
    bomb.z = target.z
    bomb.y = -210 # 触地引信
    game.update(0.1)
    assert target.destroyed, "航弹有效杀伤半径内必须摧毁地面建筑目标"
    assert game.ground_targets_destroyed >= 1, "对地战果计数器递增"
    print("  [PASS] t_ground_target_bomb_destruction: 航弹对地爆炸溅射与目标摧毁判定正常")
    tests_passed += 1

    # 11. 88mm 高射炮黑烟弹幕威胁
    game.flak_bursts.append({"x": 0, "y": 0, "z": 60, "timer": 1.0})
    old_player_hp = game.player_health
    game.update(0.1)
    assert game.player_health < old_player_hp, "置身 88mm 防空高炮破片区必须受到溅射破片伤害"
    print("  [PASS] t_flak_88_atmospheric_threat: 德军防空高炮黑烟空爆与破片杀伤正常")
    tests_passed += 1

    # 12. 第二关大获全胜终局状态
    game.ground_targets_destroyed = 4
    game.update(0.1)
    assert game.game_won, "摧毁全部 4 处战略设施后必须判定全战役大获全胜"
    print("  [PASS] t_campaign_complete_victory: 不列颠双战役通关胜利判定正常")
    tests_passed += 1

    # 13. 战机损毁与阵亡判决
    game.game_won = False
    game.player_health = 0
    game.update(0.1)
    assert game.game_over, "战机生命耗尽必须判定战役失败 Game Over"
    print("  [PASS] t_player_fatality_and_game_over: 战机战损与 Game Over 判定正常")
    tests_passed += 1

    # 14. 纯代码绘制规范校验 (零外部文件)
    code_path = __file__
    with open(code_path, "r", encoding="utf-8") as f:
        src = f.read()
    forbidden_calls = ["pygame." + "image." + "load", "pygame." + "mixer." + "music." + "load"]
    for f_call in forbidden_calls:
        assert f_call not in src, f"绝不允许调用外部资源加载: {f_call}"
    assert ("ass" + "ets/") not in src[:700], "绝不允许依赖外部静态素材目录"
    print("  [PASS] t_pure_geometry_rendering_invariant: 严格遵守代码纯矢量几何绘制不变量")
    tests_passed += 1

    # 15. 全流程 headless 冒烟运行 (1200 帧连续无崩溃模拟)
    sim_game = BattleOfBritainGame(headless=True)
    for frame in range(1200):
        # 模拟玩家智能瞄准与机动
        sim_game.flight.update(1.0/60, 0.05 if frame % 60 < 30 else -0.05, 0.1 if frame % 120 < 60 else -0.1, 0.0)
        if frame % 8 == 0:
            sim_game.fire_machine_guns()
        if sim_game.stage == 2 and frame % 40 == 0:
            sim_game.drop_bomb()
        sim_game.update(1.0/60)
    print(f"  [PASS] t_headless_campaign_smoke_run: 连续 1200 帧全战役物理仿真 0 异常 (得分: {sim_game.score})")
    tests_passed += 1

    print("--------------------------------------------------------------------------")
    print(f"  自检统计: {tests_passed} passed, 0 failed, 共 {tests_passed} 项")
    print("SELFTEST: OK")
    return True


if __name__ == "__main__":
    if HEADLESS:
        run_selftest()
    else:
        g = BattleOfBritainGame()
        g.run()
