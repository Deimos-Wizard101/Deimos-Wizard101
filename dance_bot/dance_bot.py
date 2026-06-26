"""
Standalone Wizard101 Dance Game Bot

Uses screenshot-based template matching to detect arrows and play the dance game.
No memory hooks required - works regardless of game updates.

Usage:
  1. First run: python dance_bot.py --setup
     - Positions your game window, then follow prompts to capture arrow templates
  2. Play:      python dance_bot.py
     - Stand on the dance game sigil, then press F9 to start/stop the bot

Controls:
  F9  = Start / Pause the bot
  F10 = Stop and exit
"""

import argparse
import ctypes
import os
import sys
import time
import threading
from pathlib import Path

import cv2
import keyboard
import mss
import numpy as np
import pyautogui
from PIL import Image

SCRIPT_DIR = Path(__file__).parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"

ARROW_NAMES = ["up", "down", "left", "right"]
ARROW_KEYS = {"up": "up", "down": "down", "left": "left", "right": "right"}

CONFIDENCE_THRESHOLD = 0.85
SCAN_INTERVAL = 0.05

# How long to wait after "Go!" before reading arrows
POST_GO_DELAY = 0.3
# Delay between key presses
KEY_PRESS_DELAY = 0.15
# How long each key is held
KEY_HOLD_DURATION = 0.05

# Game has 5 rounds
TOTAL_ROUNDS = 5


class DanceBot:
    def __init__(self):
        self.running = False
        self.paused = True
        self.templates = {}
        self.game_region = None
        self.arrow_region = None
        self.sct = mss.mss()
        self._load_templates()

    def _load_templates(self):
        """Load arrow template images from the templates directory."""
        for name in ARROW_NAMES:
            path = TEMPLATES_DIR / f"{name}.png"
            if path.exists():
                img = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if img is not None:
                    self.templates[name] = img
                    print(f"  Loaded template: {name} ({img.shape[1]}x{img.shape[0]})")

        if not self.templates:
            print("\n  No arrow templates found!")
            print("  Run with --setup first to capture arrow templates.")
            print(f"  Templates directory: {TEMPLATES_DIR}")

    def _screenshot(self, region=None):
        """Take a screenshot, optionally of a specific region."""
        if region:
            monitor = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3],
            }
        else:
            monitor = self.sct.monitors[0]

        img = np.array(self.sct.grab(monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _find_template(self, screenshot, template, threshold=CONFIDENCE_THRESHOLD):
        """Find all occurrences of a template in a screenshot."""
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)
        matches = []
        h, w = template.shape[:2]
        for pt in zip(*locations[::-1]):
            matches.append((pt[0], pt[1], w, h, result[pt[1], pt[0]]))
        return matches

    def _deduplicate_matches(self, matches, min_distance=30):
        """Remove duplicate detections that are too close together."""
        if not matches:
            return []

        matches.sort(key=lambda m: m[0])
        filtered = [matches[0]]
        for m in matches[1:]:
            if all(abs(m[0] - f[0]) > min_distance or abs(m[1] - f[1]) > min_distance for f in filtered):
                filtered.append(m)
        return filtered

    def detect_arrows(self, screenshot=None):
        """Detect arrow sequence in the current screen."""
        if not self.templates:
            return []

        if screenshot is None:
            if self.arrow_region:
                screenshot = self._screenshot(self.arrow_region)
            else:
                screenshot = self._screenshot()

        all_matches = []
        for name, template in self.templates.items():
            matches = self._find_template(screenshot, template)
            for m in matches:
                all_matches.append((name, m[0], m[1], m[4]))

        all_matches = self._deduplicate_matches_by_name(all_matches)
        all_matches.sort(key=lambda m: m[1])

        return [m[0] for m in all_matches]

    def _deduplicate_matches_by_name(self, matches, min_distance=30):
        """Remove duplicate detections, keeping highest confidence."""
        if not matches:
            return []

        filtered = []
        for m in matches:
            is_dup = False
            for i, f in enumerate(filtered):
                if abs(m[1] - f[1]) < min_distance and abs(m[2] - f[2]) < min_distance:
                    if m[3] > f[3]:
                        filtered[i] = m
                    is_dup = True
                    break
            if not is_dup:
                filtered.append(m)
        return filtered

    def press_arrow(self, direction):
        """Press an arrow key."""
        key = ARROW_KEYS.get(direction)
        if key:
            pyautogui.press(key)

    def play_round(self, arrows):
        """Press the detected arrow sequence."""
        print(f"    Playing: {' '.join(a.upper() for a in arrows)}")
        for arrow in arrows:
            self.press_arrow(arrow)
            time.sleep(KEY_PRESS_DELAY)

    def wait_for_go(self):
        """
        Wait for the 'Go!' signal by watching for a change in the arrow display area.
        During the display phase, arrows are shown. When 'Go!' appears, arrows disappear
        and the player needs to input the sequence.
        """
        print("    Waiting for 'Go!' signal...")
        time.sleep(POST_GO_DELAY)

    def detect_game_active(self):
        """Check if the dance game is currently active by looking for arrow templates."""
        screenshot = self._screenshot()
        arrows = self.detect_arrows(screenshot)
        return len(arrows) > 0

    def play_dance_game(self):
        """Play a full dance game (5 rounds)."""
        print("\n  Starting dance game...")

        for round_num in range(1, TOTAL_ROUNDS + 1):
            if not self.running or self.paused:
                print("  Bot paused/stopped.")
                return False

            print(f"\n  Round {round_num}/{TOTAL_ROUNDS}:")

            # Wait for arrows to appear (display phase)
            print("    Waiting for arrows to appear...")
            arrows = []
            attempts = 0
            max_attempts = 200  # 10 seconds max wait
            while len(arrows) < round_num and attempts < max_attempts:
                if not self.running or self.paused:
                    return False
                arrows = self.detect_arrows()
                if len(arrows) < round_num:
                    time.sleep(SCAN_INTERVAL)
                    attempts += 1

            if len(arrows) < round_num:
                print(f"    Warning: Expected {round_num} arrows, detected {len(arrows)}")
                if not arrows:
                    print("    No arrows detected, skipping round")
                    continue

            print(f"    Detected {len(arrows)} arrows: {' '.join(a.upper() for a in arrows)}")

            # Wait for arrows to disappear (Go! signal)
            print("    Waiting for input phase...")
            disappear_attempts = 0
            while disappear_attempts < 200:
                if not self.running or self.paused:
                    return False
                current = self.detect_arrows()
                if len(current) == 0:
                    break
                time.sleep(SCAN_INTERVAL)
                disappear_attempts += 1

            # Small delay after Go! appears
            time.sleep(POST_GO_DELAY)

            # Play the sequence
            self.play_round(arrows)

            # Wait before next round
            time.sleep(0.5)

        print("\n  Dance game complete!")
        return True

    def click_at(self, x, y, delay=0.3):
        """Click at screen coordinates."""
        pyautogui.click(x, y)
        time.sleep(delay)

    def run(self):
        """Main bot loop."""
        self.running = True
        self.paused = True

        print("\n" + "=" * 50)
        print("  Wizard101 Dance Game Bot")
        print("=" * 50)
        print("\n  Controls:")
        print("    F9  = Start / Pause")
        print("    F10 = Stop and Exit")

        if not self.templates:
            print("\n  ERROR: No templates loaded. Run with --setup first.")
            return

        print(f"\n  Templates loaded: {', '.join(self.templates.keys())}")
        print("\n  Instructions:")
        print("    1. Make sure Wizard101 is visible on screen")
        print("    2. Stand on the Dance Game sigil")
        print("    3. Open the pet game selection window")
        print("    4. Select the Dance Game and click Play")
        print("    5. Press F9 to start the bot")
        print("\n  Waiting for F9 to start...")

        keyboard.add_hotkey("F9", self._toggle_pause)
        keyboard.add_hotkey("F10", self._stop)

        try:
            while self.running:
                if self.paused:
                    time.sleep(0.1)
                    continue

                success = self.play_dance_game()

                if success and self.running and not self.paused:
                    print("\n  Waiting for reward screen (3s)...")
                    time.sleep(3.0)
                    print("  Ready for next game. Press F9 to pause, or the bot")
                    print("  will attempt to detect the next round automatically.")
                    print("  (If you need to manually click 'Play Again', pause first)")
                    time.sleep(2.0)

        except KeyboardInterrupt:
            pass
        finally:
            keyboard.unhook_all()
            print("\n  Bot stopped.")

    def _toggle_pause(self):
        self.paused = not self.paused
        state = "PAUSED" if self.paused else "RUNNING"
        print(f"\n  >> Bot {state} <<")

    def _stop(self):
        self.running = False
        self.paused = False
        print("\n  >> Stopping bot... <<")


def setup_mode():
    """Interactive setup to capture arrow templates."""
    print("\n" + "=" * 50)
    print("  Dance Bot Setup - Arrow Template Capture")
    print("=" * 50)
    print("\n  This will help you capture arrow template images")
    print("  for the bot to recognize during the dance game.")
    print()
    print("  Instructions:")
    print("    1. Start a dance game in Wizard101")
    print("    2. When arrows appear on screen, this tool will")
    print("       let you select each arrow type")
    print()

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    sct = mss.mss()

    for arrow in ARROW_NAMES:
        existing = TEMPLATES_DIR / f"{arrow}.png"
        if existing.exists():
            resp = input(f"\n  Template for '{arrow}' already exists. Recapture? (y/N): ").strip().lower()
            if resp != "y":
                print(f"  Keeping existing '{arrow}' template.")
                continue

        print(f"\n  --- Capturing '{arrow.upper()}' arrow ---")
        print(f"  Make sure the {arrow.upper()} arrow is visible on screen.")
        print("  Press F8 when ready to take a screenshot...")
        keyboard.wait("F8")
        time.sleep(0.1)

        screenshot = np.array(sct.grab(sct.monitors[0]))
        screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

        temp_path = TEMPLATES_DIR / "_temp_screenshot.png"
        cv2.imwrite(str(temp_path), screenshot)

        print(f"\n  Screenshot saved. Now you need to crop the {arrow.upper()} arrow.")
        print("  A window will open - select the arrow region and press ENTER.")
        print("  Press 'c' to cancel this arrow.")

        roi = cv2.selectROI(f"Select {arrow.upper()} arrow", screenshot, fromCenter=False)
        cv2.destroyAllWindows()

        if roi[2] > 0 and roi[3] > 0:
            cropped = screenshot[int(roi[1]):int(roi[1] + roi[3]),
                                 int(roi[0]):int(roi[0] + roi[2])]
            save_path = TEMPLATES_DIR / f"{arrow}.png"
            cv2.imwrite(str(save_path), cropped)
            print(f"  Saved '{arrow}' template ({cropped.shape[1]}x{cropped.shape[0]} px)")
        else:
            print(f"  Skipped '{arrow}' arrow.")

        if temp_path.exists():
            temp_path.unlink()

    print("\n  Setup complete!")
    print(f"  Templates saved to: {TEMPLATES_DIR}")

    existing = [f.stem for f in TEMPLATES_DIR.glob("*.png")]
    missing = [a for a in ARROW_NAMES if a not in existing]
    if missing:
        print(f"\n  Warning: Missing templates for: {', '.join(missing)}")
        print("  Run --setup again to capture missing arrows.")
    else:
        print("\n  All 4 arrow templates captured!")
        print("  You can now run: python dance_bot.py")


def setup_region_mode():
    """Let the user define a scan region to speed up detection."""
    print("\n" + "=" * 50)
    print("  Dance Bot Setup - Define Scan Region")
    print("=" * 50)
    print("\n  This narrows the screenshot area for faster detection.")
    print("  Select the region where arrows appear during the dance game.")
    print("\n  Press F8 when the dance game arrows are visible...")

    keyboard.wait("F8")
    time.sleep(0.1)

    sct = mss.mss()
    screenshot = np.array(sct.grab(sct.monitors[0]))
    screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

    roi = cv2.selectROI("Select arrow region", screenshot, fromCenter=False)
    cv2.destroyAllWindows()

    if roi[2] > 0 and roi[3] > 0:
        config_path = TEMPLATES_DIR / "region.txt"
        with open(config_path, "w") as f:
            f.write(f"{roi[0]},{roi[1]},{roi[2]},{roi[3]}")
        print(f"\n  Scan region saved: x={roi[0]}, y={roi[1]}, w={roi[2]}, h={roi[3]}")
        print(f"  Config saved to: {config_path}")
    else:
        print("\n  No region selected.")


def main():
    parser = argparse.ArgumentParser(description="Wizard101 Dance Game Bot")
    parser.add_argument("--setup", action="store_true",
                        help="Run interactive setup to capture arrow templates")
    parser.add_argument("--region", action="store_true",
                        help="Define a scan region for faster arrow detection")
    parser.add_argument("--confidence", type=float, default=CONFIDENCE_THRESHOLD,
                        help=f"Template matching confidence (default: {CONFIDENCE_THRESHOLD})")
    parser.add_argument("--test", action="store_true",
                        help="Test arrow detection on current screen")
    args = parser.parse_args()

    if args.setup:
        setup_mode()
        return

    if args.region:
        setup_region_mode()
        return

    if args.test:
        print("\n  Testing arrow detection...")
        bot = DanceBot()

        region_config = TEMPLATES_DIR / "region.txt"
        if region_config.exists():
            parts = region_config.read_text().strip().split(",")
            bot.arrow_region = tuple(int(p) for p in parts)
            print(f"  Using scan region: {bot.arrow_region}")

        print("  Press F8 to take a screenshot and detect arrows...")
        keyboard.wait("F8")
        time.sleep(0.1)

        arrows = bot.detect_arrows()
        if arrows:
            print(f"\n  Detected {len(arrows)} arrows: {' '.join(a.upper() for a in arrows)}")
        else:
            print("\n  No arrows detected.")
            print("  Tips:")
            print("    - Make sure arrows are visible on screen")
            print("    - Try lowering --confidence (e.g., --confidence 0.75)")
            print("    - Re-run --setup to recapture templates")
        return

    # Normal run mode
    global CONFIDENCE_THRESHOLD
    CONFIDENCE_THRESHOLD = args.confidence

    bot = DanceBot()

    region_config = TEMPLATES_DIR / "region.txt"
    if region_config.exists():
        parts = region_config.read_text().strip().split(",")
        bot.arrow_region = tuple(int(p) for p in parts)
        print(f"  Using scan region: {bot.arrow_region}")

    bot.run()


if __name__ == "__main__":
    main()
