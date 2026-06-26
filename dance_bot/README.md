# Wizard101 Dance Game Bot (Standalone)

A standalone bot for the Wizard101 Dance Game pet mini-game that uses screenshot-based template matching. No memory hooks required - works regardless of game updates.

## Requirements

- Python 3.8+
- Windows (Wizard101 is Windows-only)

## Install

```bash
cd dance_bot
pip install -r requirements.txt
```

## Setup

### 1. Capture Arrow Templates

Start a dance game in Wizard101, then run:

```bash
python dance_bot.py --setup
```

For each arrow direction (up, down, left, right):
- Press **F8** when that arrow is visible on screen
- A window opens - draw a box around the arrow and press **ENTER**

Templates are saved to `dance_bot/templates/`.

### 2. (Optional) Define Scan Region

Speed up detection by limiting the scan area:

```bash
python dance_bot.py --region
```

Press **F8** when arrows are visible, then select the region where arrows appear.

### 3. Test Detection

Verify templates work:

```bash
python dance_bot.py --test
```

Press **F8** with arrows on screen. Should report detected arrows.

## Usage

1. Open Wizard101 and stand on the Dance Game sigil
2. Open pet game selection, select Dance Game, click Play
3. Run the bot:

```bash
python dance_bot.py
```

4. Press **F9** to start the bot once arrows appear

## Controls

| Key | Action |
|-----|--------|
| F9  | Start / Pause |
| F10 | Stop and Exit |

## Options

```
--setup        Capture arrow templates
--region       Define scan region
--test         Test arrow detection
--confidence   Template matching threshold (default: 0.85, lower = more lenient)
```

## How It Works

1. Takes screenshots and uses OpenCV template matching to find arrows
2. During display phase: detects which arrows appear (left to right order)
3. Waits for arrows to disappear (the "Go!" signal)
4. Presses the arrow keys in the detected sequence
5. Repeats for all 5 rounds

## Troubleshooting

- **No arrows detected**: Lower confidence with `--confidence 0.75`, or recapture templates with `--setup`
- **Wrong arrows detected**: Recapture templates, making sure to tightly crop each arrow
- **Bot too slow/fast**: Adjust `POST_GO_DELAY` and `KEY_PRESS_DELAY` in `dance_bot.py`
