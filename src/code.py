# Harvest Hustle - From Farm to Feast in 90 Seconds!
# CircuitPython Game for Xiao ESP32C3

import time
import board
import busio
import digitalio
import neopixel
import displayio
import terminalio
import random
import pwmio
import microcontroller
import i2cdisplaybus
import adafruit_displayio_ssd1306
import adafruit_adxl34x
from adafruit_display_text import label

# ============================================
# HIGH SCORE STORAGE (NVM)
# ============================================
# Store 3 high scores: each entry = 3 bytes initials + 2 bytes score (big endian)
# Format: [A, A, A, score_hi, score_lo, B, B, B, score_hi, score_lo, ...]
# Total: 15 bytes for 3 high scores

HIGH_SCORE_COUNT = 3
HIGH_SCORE_ENTRY_SIZE = 5  # 3 chars + 2 bytes for score

def load_high_scores():
    """Load high scores from NVM"""
    scores = []
    try:
        nvm = microcontroller.nvm
        for i in range(HIGH_SCORE_COUNT):
            offset = i * HIGH_SCORE_ENTRY_SIZE
            # Read initials (3 bytes)
            initials = ""
            for j in range(3):
                c = nvm[offset + j]
                if 65 <= c <= 90:  # A-Z
                    initials += chr(c)
                else:
                    initials += "A"
            # Read score (2 bytes, big endian)
            score = (nvm[offset + 3] << 8) | nvm[offset + 4]
            if score > 9999:
                score = 0
            scores.append({"initials": initials, "score": score})
    except:
        # If NVM not available or error, return default
        scores = [{"initials": "AAA", "score": 0} for _ in range(HIGH_SCORE_COUNT)]
    return scores

def save_high_scores(scores):
    """Save high scores to NVM"""
    try:
        nvm = microcontroller.nvm
        for i in range(HIGH_SCORE_COUNT):
            offset = i * HIGH_SCORE_ENTRY_SIZE
            initials = scores[i]["initials"]
            score = scores[i]["score"]
            # Write initials
            for j in range(3):
                nvm[offset + j] = ord(initials[j]) if j < len(initials) else 65
            # Write score (big endian)
            nvm[offset + 3] = (score >> 8) & 0xFF
            nvm[offset + 4] = score & 0xFF
    except:
        pass  # NVM write failed, ignore

def is_high_score(score, scores):
    """Check if score qualifies for high score board"""
    if score <= 0:
        return False
    for hs in scores:
        if score > hs["score"]:
            return True
    return False

def insert_high_score(initials, score, scores):
    """Insert a new high score into the list"""
    new_entry = {"initials": initials, "score": score}
    scores.append(new_entry)
    scores.sort(key=lambda x: x["score"], reverse=True)
    return scores[:HIGH_SCORE_COUNT]

# Load high scores at startup
high_scores = load_high_scores()

# ============================================
# HARDWARE SETUP
# ============================================
displayio.release_displays()
time.sleep(0.5)

i2c = busio.I2C(board.SCL, board.SDA)
while not i2c.try_lock():
    pass
i2c.unlock()

display = None
for _ in range(3):
    try:
        display_bus = i2cdisplaybus.I2CDisplayBus(i2c, device_address=0x3C)
        display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=128, height=64)
        break
    except ValueError:
        time.sleep(0.3)

if display is None:
    print("ERROR: Cannot find OLED display!")
    while True:
        pass

accelerometer = adafruit_adxl34x.ADXL345(i2c)

NUM_PIXELS = 1
pixels = neopixel.NeoPixel(board.D3, NUM_PIXELS, brightness=0.3, auto_write=False)

# Buzzer setup on D2
buzzer = pwmio.PWMOut(board.D2, variable_frequency=True, duty_cycle=0)

# Flag for first boot (splash screen)
first_boot = True

# Encoder setup
encoder_clk = digitalio.DigitalInOut(board.D0)
encoder_clk.direction = digitalio.Direction.INPUT
encoder_clk.pull = digitalio.Pull.UP

encoder_dt = digitalio.DigitalInOut(board.D1)
encoder_dt.direction = digitalio.Direction.INPUT
encoder_dt.pull = digitalio.Pull.UP

# Button setup with manual debounce
btn_pin = digitalio.DigitalInOut(board.D6)
btn_pin.direction = digitalio.Direction.INPUT
btn_pin.pull = digitalio.Pull.UP

prev_btn_state = True  # True = not pressed
last_btn_change_time = 0
DEBOUNCE_TIME = 0.05  # 50ms debounce

# ============================================
# BUZZER SOUND FUNCTIONS
# ============================================
def play_tone(frequency, duration):
    """Play a single tone"""
    buzzer.frequency = frequency
    buzzer.duty_cycle = 32768  # 50% duty cycle
    time.sleep(duration)
    buzzer.duty_cycle = 0

def sound_collect():
    """Sound for collecting an ingredient - short happy beep"""
    play_tone(880, 0.05)  # A5
    play_tone(1100, 0.05)  # C#6

def sound_fail():
    """Sound for wrong move or penalty - low buzz"""
    play_tone(200, 0.1)
    play_tone(150, 0.15)

def sound_start():
    """Sound for game start - ascending tune"""
    play_tone(523, 0.1)   # C5
    play_tone(659, 0.1)   # E5
    play_tone(784, 0.1)   # G5
    play_tone(1047, 0.15) # C6

def sound_game_over():
    """Sound for game over - descending sad tune"""
    play_tone(392, 0.15)  # G4
    play_tone(330, 0.15)  # E4
    play_tone(262, 0.2)   # C4

def sound_win():
    """Sound for winning - victory fanfare"""
    play_tone(523, 0.1)   # C5
    play_tone(659, 0.1)   # E5
    play_tone(784, 0.1)   # G5
    play_tone(1047, 0.1)  # C6
    time.sleep(0.05)
    play_tone(784, 0.1)   # G5
    play_tone(1047, 0.2)  # C6

def sound_level_clear():
    """Sound for level complete"""
    play_tone(784, 0.1)   # G5
    play_tone(988, 0.1)   # B5
    play_tone(1175, 0.15) # D6

def sound_select():
    """Sound for menu selection - click"""
    play_tone(600, 0.03)

# ============================================
# ICONS (8x8 bitmaps)
# ============================================
ICON_DATA = {
    "egg": [
        0b00111100,
        0b01111110,
        0b11111111,
        0b11111111,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
    ],
    "fried_egg": [  # 煎蛋 - 不规则形状
        0b00011100,
        0b01111110,
        0b11111111,
        0b11101111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00000000,
    ],
    "milk": [
        0b00111100,
        0b00100100,
        0b00111100,
        0b01111110,
        0b01111110,
        0b01111110,
        0b01111110,
        0b00111100,
    ],
    "wheat": [
        0b00010000,
        0b00111000,
        0b00010000,
        0b00111000,
        0b00010000,
        0b00111000,
        0b00010000,
        0b00010000,
    ],
    "dough": [
        0b00000000,
        0b01111110,
        0b11111111,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00000000,
    ],
    "bacon": [
        0b11111111,
        0b00000000,
        0b11111111,
        0b00000000,
        0b11111111,
        0b00000000,
        0b11111111,
        0b00000000,
    ],
    "tomato": [  # 番茄 - 有蒂
        0b00011000,
        0b00100100,
        0b01111110,
        0b11111111,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
    ],
    "chicken": [
        0b00110000,
        0b01111000,
        0b11111100,
        0b11111110,
        0b01111100,
        0b00111000,
        0b01000100,
        0b01000100,
    ],
    "cow": [
        0b01000010,
        0b11100111,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b01000010,
        0b01000010,
    ],
    "pig": [
        0b00000000,
        0b01100110,
        0b11111111,
        0b10111101,
        0b11111111,
        0b01111110,
        0b01000010,
        0b00000000,
    ],
    "duck": [
        0b01100000,
        0b11111000,
        0b01111110,
        0b00111111,
        0b00011110,
        0b00001100,
        0b00010010,
        0b00010010,
    ],
    "fish": [
        0b00000000,
        0b00011000,
        0b01111110,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00011000,
        0b00000000,
    ],
    "shark": [
        0b00000100,
        0b00001110,
        0b00011111,
        0b01111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00000000,
    ],
    "carrot": [
        0b00001100,
        0b00011110,
        0b00001100,
        0b00011000,
        0b00110000,
        0b01100000,
        0b11000000,
        0b10000000,
    ],
    "potato": [
        0b00111100,
        0b01111110,
        0b11111111,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00000000,
    ],
    "yogurt": [
        0b01111110,
        0b01000010,
        0b00111100,
        0b00111100,
        0b00111100,
        0b00111100,
        0b00111100,
        0b00011000,
    ],
    "fruit": [
        0b00010000,
        0b00111000,
        0b01111110,
        0b11111111,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
    ],
    "berry": [  # 浆果 - 小圆球
        0b00000000,
        0b01100110,
        0b11111111,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00000000,
    ],
    "tree": [
        0b00011000,
        0b00111100,
        0b01111110,
        0b11111111,
        0b00011000,
        0b00011000,
        0b00011000,
        0b00111100,
    ],
    "honey": [
        0b00111100,
        0b01111110,
        0b01111110,
        0b00111100,
        0b01111110,
        0b01111110,
        0b01111110,
        0b00111100,
    ],
    "bee": [
        0b00011000,
        0b00111100,
        0b01011010,
        0b11111111,
        0b01011010,
        0b00111100,
        0b00011000,
        0b00100100,
    ],
    "lemon": [
        0b00011100,
        0b00111110,
        0b01111111,
        0b01111111,
        0b01111111,
        0b00111110,
        0b00011100,
        0b00000000,
    ],
    "cheese": [
        0b00000001,
        0b00000111,
        0b00011111,
        0b01111111,
        0b11111111,
        0b11111111,
        0b11111111,
        0b00000000,
    ],
    "turkey": [
        0b00110000,
        0b01111100,
        0b00111110,
        0b00011111,
        0b00001110,
        0b00000100,
        0b00001010,
        0b00001010,
    ],
    "cranberry": [
        0b00000000,
        0b01100110,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00000000,
        0b00000000,
    ],
    "shell": [
        0b00011000,
        0b00111100,
        0b01111110,
        0b11111111,
        0b11111111,
        0b01010101,
        0b00101010,
        0b00000000,
    ],
    "seaweed": [
        0b10010010,
        0b01001001,
        0b10010010,
        0b01001001,
        0b10010010,
        0b01001001,
        0b10010010,
        0b01001001,
    ],
    "lamb": [
        0b01100110,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00111100,
        0b01000010,
        0b01000010,
    ],
    "herbs": [
        0b00100100,
        0b01011010,
        0b00100100,
        0b01011010,
        0b00100100,
        0b00011000,
        0b00011000,
        0b00011000,
    ],
    "garlic": [
        0b00011000,
        0b00111100,
        0b01111110,
        0b11111111,
        0b11011011,
        0b11011011,
        0b01111110,
        0b00111100,
    ],
    "grapes": [
        0b00010000,
        0b01101100,
        0b11111110,
        0b11111110,
        0b01111100,
        0b00111000,
        0b00010000,
        0b00000000,
    ],
    "wave": [
        0b00000000,
        0b00000000,
        0b01100110,
        0b10011001,
        0b10011001,
        0b01100110,
        0b00000000,
        0b00000000,
    ],
    "pancake": [
        0b00000000,
        0b00111100,
        0b01111110,
        0b11111111,
        0b11111111,
        0b01111110,
        0b00111100,
        0b00000000,
    ],
    "default": [
        0b11111111,
        0b10000001,
        0b10000001,
        0b10000001,
        0b10000001,
        0b10000001,
        0b10000001,
        0b11111111,
    ],
}

def make_icon(name):
    data = ICON_DATA.get(name, ICON_DATA["default"])
    bmp = displayio.Bitmap(8, 8, 2)
    pal = displayio.Palette(2)
    pal[0] = 0x000000
    pal[1] = 0xFFFFFF
    for y in range(8):
        row = data[y]
        for x in range(8):
            if row & (1 << (7 - x)):
                bmp[x, y] = 1
    return bmp, pal

def show_splash():
    """Animated splash screen with roaming food ingredients"""
    # Food icons to animate
    foods = ["egg", "milk", "bacon", "tomato", "cheese", "fish", "carrot", "apple"]
    
    # Initial positions and velocities for each food
    items = []
    for i, food in enumerate(foods):
        items.append({
            "name": food,
            "x": random.randint(10, 110),
            "y": random.randint(10, 50),
            "vx": random.choice([-2, -1, 1, 2]),
            "vy": random.choice([-2, -1, 1, 2])
        })
    
    # Play startup sound
    play_tone(440, 0.05)
    play_tone(554, 0.05)
    play_tone(659, 0.1)
    
    # Animate for 2 seconds
    start_time = time.monotonic()
    frame = 0
    while time.monotonic() - start_time < 2.0:
        g = displayio.Group()
        
        # Title text
        t1 = "HARVEST HUSTLE"
        g.append(label.Label(terminalio.FONT, text=t1, color=0xFFFFFF, x=14, y=32))
        
        # Update and draw each food item
        for item in items:
            # Update position
            item["x"] += item["vx"]
            item["y"] += item["vy"]
            
            # Bounce off walls
            if item["x"] <= 0 or item["x"] >= 120:
                item["vx"] *= -1
            if item["y"] <= 0 or item["y"] >= 56:
                item["vy"] *= -1
            
            # Keep in bounds
            item["x"] = max(0, min(120, item["x"]))
            item["y"] = max(0, min(56, item["y"]))
            
            # Draw icon
            bmp, pal = make_icon(item["name"])
            tg = displayio.TileGrid(bmp, pixel_shader=pal, x=int(item["x"]), y=int(item["y"]))
            g.append(tg)
        
        display.root_group = g
        
        # LED animation - rainbow effect
        for i in range(NUM_PIXELS):
            hue = (frame * 10 + i * 32) % 256
            if hue < 85:
                r, g_c, b = 255 - hue * 3, hue * 3, 0
            elif hue < 170:
                hue -= 85
                r, g_c, b = 0, 255 - hue * 3, hue * 3
            else:
                hue -= 170
                r, g_c, b = hue * 3, 0, 255 - hue * 3
            pixels[i] = (r, g_c, b)
        pixels.show()
        
        frame += 1
        time.sleep(0.05)
    
    # Clear LEDs
    pixels.fill((0, 0, 0))
    pixels.show()

# ============================================
# CONSTANTS
# ============================================
COLOR_OFF = (0, 0, 0)
COLOR_GREEN = (0, 255, 0)
COLOR_RED = (255, 0, 0)
COLOR_YELLOW = (255, 255, 0)
COLOR_BLUE = (0, 0, 255)
COLOR_PURPLE = (128, 0, 128)

TILT_THRESHOLD = 4.0
SHAKE_THRESHOLD = 18.0
MOVE_DEBOUNCE = 0.1
TOUCH_TIME = 0.6  # Time to touch animal (shortened)
ROTATE_NEEDED = 5  # Rotations needed

DIFFICULTY = {
    "EASY": (90, 1),
    "MEDIUM": (60, 2),
    "HARD": (45, 3)
}

# Collection methods: "tilt", "shake", "touch", "rotate", "tree"
# "touch" = stay near animal, "rotate" = approach + rotate encoder, "tree" = shake near tree
LEVELS = [
    {  # Level 1
        "name": "Sunny Morning",
        "view": "side",
        "ingredients": [
            ("egg", 2, "tilt"),
            ("milk", 2, "touch"),
        ],
        "dish": "Fried Egg + Milk",
        "animals": [("chicken", "top"), ("cow", "ground")],
        "cooking": None,
    },
    {  # Level 2
        "name": "Pancake Prep",
        "view": "side",
        "ingredients": [
            ("egg", 2, "tilt"),
            ("wheat", 2, "shake"),
        ],
        "dish": "Fluffy Pancakes",
        "animals": [("chicken", "top")],
        "cooking": None,
    },
    {  # Level 3
        "name": "Full Breakfast",
        "view": "topdown",
        "ingredients": [
            ("bacon", 2, "touch"),
            ("egg", 2, "tilt"),
            ("tomato", 2, "shake"),
        ],
        "dish": "Hearty Brunch",
        "animals": [("pig", "run"), ("chicken", "run")],
        "cooking": None,
    },
    {  # Level 4
        "name": "Healthy Bowl",
        "view": "topdown",
        "ingredients": [
            ("milk", 2, "touch"),
            ("berry", 2, "tilt"),
            ("honey", 2, "touch"),
        ],
        "dish": "Berry Bliss Bowl",
        "animals": [("cow", "run"), ("bee", "run")],
        "berry_spawn": True,  # Berry appears/disappears
        "cooking": "button",  # Ferment yogurt
        "cook_name": "Fermenting...",
    },
    {  # Level 5
        "name": "Poultry Chase",
        "view": "topdown",
        "ingredients": [
            ("duck", 3, "touch"),
            ("chicken", 3, "touch"),
        ],
        "dish": "Golden Roast",
        "animals": [("duck", "fast"), ("chicken", "fast")],
        "cooking": None,
    },
    {  # Level 6
        "name": "Lakeside",
        "view": "topdown",
        "ingredients": [
            ("fish", 3, "tilt"),
            ("lemon", 3, "tree"),
        ],
        "dish": "Citrus Fish",
        "animals": [],
        "waves": False,  # No wave lines
        "trees": True,
        "cooking": None,
        "spawn_fast": True,  # Fish spawn more frequently
    },
    {  # Level 7
        "name": "Hearty Stew",
        "view": "topdown",
        "ingredients": [
            ("bacon", 3, "touch"),
            ("carrot", 4, "shake"),
            ("potato", 4, "tilt"),
        ],
        "dish": "Cozy Stew",
        "animals": [("pig", "run")],
        "cooking": None,
    },
    {  # Level 8
        "name": "Pizza Time",
        "view": "topdown",
        "ingredients": [
            ("cheese", 3, "tilt"),
            ("tomato", 3, "shake"),
            ("dough", 2, "rotate"),
        ],
        "dish": "Cheesy Pizza",
        "animals": [],
        "rotate_needed": 2,  # Only need 2 rotations
        "cooking": "button",  # Bake
        "cook_name": "Baking...",
    },
    {  # Level 9
        "name": "Thanksgiving",
        "view": "topdown",
        "ingredients": [
            ("turkey", 4, "touch"),
            ("cranberry", 5, "tilt"),
            ("potato", 3, "rotate"),
        ],
        "dish": "Feast Turkey",
        "animals": [("turkey", "run")],
        "rotate_needed": 2,  # Only need 2 rotations
        "cooking": "button",  # Make sauce
        "cook_name": "Making Sauce...",
    },
    {  # Level 10
        "name": "Ocean Bounty",
        "view": "topdown",
        "ingredients": [
            ("fish", 4, "tilt"),
            ("shell", 5, "tilt"),
            ("seaweed", 5, "shake"),
        ],
        "dish": "Grand Seafood Platter",
        "animals": [("shark", "danger")],
        "waves": False,  # No wave lines
        "shark_eats_fish": True,  # Shark collision reduces fish count
        "cooking": None,
        "spawn_fast": True,  # Fish spawn more frequently
    },
    {  # Level 11
        "name": "Gourmet",
        "view": "topdown",
        "ingredients": [
            ("lamb", 4, "touch"),
            ("herbs", 5, "shake"),
            ("garlic", 4, "tilt"),
            ("grapes", 3, "rotate"),
        ],
        "dish": "Roasted Lamb",
        "animals": [("lamb", "run")],
        "rotate_needed": 3,  # Only need 3 rotations
        "cooking": "double",  # Roast + Wine
        "cook_name": "Roasting...",
        "cook_name2": "Making Wine...",
    },
]

# ============================================
# GAME STATE
# ============================================
class Game:
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.screen = "title"
        self.difficulty = "EASY"
        self.diff_idx = 0
        self.level = 0
        self.level_select_idx = 0  # For level selection
        self.time_left = 90
        self.px = 64
        self.py = 32
        self.collected = {}
        self.needed = {}
        self.items = []
        self.animals = []
        self.trees = []
        self.waves_y = []
        self.cook_progress = 0
        self.cook_progress2 = 0
        self.last_move = 0
        self.scroll_offset = 0
        self.touch_target = None
        self.touch_start = 0
        self.rotate_target = None
        self.rotate_count = 0
        self.penalty = 0
        self.last_scroll = 0
        self.last_btn_time = 0
        self.intro_page = 0
        self.over_choice = 0  # 0=Retry, 1=Restart
        self.score = 0  # Player score
        self.level_score = 0  # Score for current level
        self.initials = ""  # For high score entry
        self.initial_char = 0  # Current character (0-25 = A-Z)
        self.is_new_high_score = False  # Flag for new high score
        self.after_highscore = "reset"  # What to do after high score screen: "reset" or "restart"

# Score points for each collection method
SCORE_TILT = 10
SCORE_TOUCH = 20
SCORE_SHAKE = 30
SCORE_ROTATE = 50

game = Game()

# ============================================
# INPUT
# ============================================
def read_accel():
    x, y, z = accelerometer.acceleration
    total = (x**2 + y**2 + z**2) ** 0.5
    
    if total > SHAKE_THRESHOLD:
        return "SHAKE"
    # Original mapping
    if abs(x) > TILT_THRESHOLD and abs(x) > abs(y):
        return "RIGHT" if x > 0 else "LEFT"
    if abs(y) > TILT_THRESHOLD and abs(y) > abs(x):
        return "FWD" if y > 0 else "BACK"
    return None

# Encoder tracking
last_encoder_clk = True

def read_encoder():
    global last_encoder_clk, prev_btn_state, last_btn_change_time
    rot = 0
    btn = False
    
    # Button with manual debounce
    cur_state = btn_pin.value
    now = time.monotonic()
    
    if cur_state != prev_btn_state and (now - last_btn_change_time) > DEBOUNCE_TIME:
        last_btn_change_time = now
        if not cur_state:  # Button pressed (HIGH -> LOW)
            btn = True
        prev_btn_state = cur_state
    
    # Encoder rotation - only detect clockwise (CW)
    for _ in range(3):
        clk = encoder_clk.value
        dt = encoder_dt.value
        
        # Detect on CLK falling edge
        if last_encoder_clk and not clk:
            # Swap: now detect the other direction as CW
            if not dt:
                rot = 1   # CW - move down
            # else: ignore
        
        last_encoder_clk = clk
        time.sleep(0.002)
    
    return rot, btn

# ============================================
# DISPLAY HELPERS
# ============================================
def center_x(text):
    return max(0, (128 - len(text) * 6) // 2)

def make_rect(w, h, fill=True):
    bmp = displayio.Bitmap(w, h, 2)
    pal = displayio.Palette(2)
    pal[0] = 0x000000
    pal[1] = 0xFFFFFF
    if fill:
        for x in range(w):
            for y in range(h):
                bmp[x, y] = 1
    else:
        for x in range(w):
            bmp[x, 0] = 1
            bmp[x, h-1] = 1
        for y in range(h):
            bmp[0, y] = 1
            bmp[w-1, y] = 1
    return bmp, pal

# ============================================
# SCREENS
# ============================================
def show_title():
    g = displayio.Group()
    t1 = "HARVEST HUSTLE"
    g.append(label.Label(terminalio.FONT, text=t1, color=0xFFFFFF, x=center_x(t1), y=12))
    t2 = "From Farm to Feast"
    g.append(label.Label(terminalio.FONT, text=t2, color=0xFFFFFF, x=center_x(t2), y=28))
    t3 = "in 90 Seconds!"
    g.append(label.Label(terminalio.FONT, text=t3, color=0xFFFFFF, x=center_x(t3), y=40))
    t4 = "[Press to Start]"
    g.append(label.Label(terminalio.FONT, text=t4, color=0xFFFFFF, x=center_x(t4), y=58))
    display.root_group = g

def show_mode():
    g = displayio.Group()
    g.append(label.Label(terminalio.FONT, text="SELECT MODE", color=0xFFFFFF, x=30, y=6))
    modes = ["EASY 90s", "MEDIUM 60s", "HARD 45s"]
    # Uniform spacing of 12: y=18, 30, 42, 54
    for i, m in enumerate(modes):
        pre = "> " if i == game.diff_idx else "  "
        g.append(label.Label(terminalio.FONT, text=pre + m, color=0xFFFFFF, x=20, y=18 + i*12))
    g.append(label.Label(terminalio.FONT, text="[Rotate & Press]", color=0xFFFFFF, x=12, y=54))
    display.root_group = g

def show_level_select():
    g = displayio.Group()
    g.append(label.Label(terminalio.FONT, text="SELECT LEVEL", color=0xFFFFFF, x=28, y=5))
    
    # Show 4 levels at a time with scrolling
    total_levels = len(LEVELS)
    start_idx = max(0, min(game.level_select_idx - 1, total_levels - 4))
    end_idx = min(start_idx + 4, total_levels)
    
    # Levels at y=16, 26, 36, 46 (spacing 10)
    y = 16
    for i in range(start_idx, end_idx):
        lv = LEVELS[i]
        pre = "> " if i == game.level_select_idx else "  "
        # Show level number and name
        name = lv['name']
        if len(name) > 12:
            name = name[:11] + "."
        txt = f"{pre}L{i+1}:{name}"
        g.append(label.Label(terminalio.FONT, text=txt, color=0xFFFFFF, x=4, y=y))
        y += 10
    
    # Scroll indicators
    if start_idx > 0:
        g.append(label.Label(terminalio.FONT, text="^", color=0xFFFFFF, x=120, y=16))
    if end_idx < total_levels:
        g.append(label.Label(terminalio.FONT, text="v", color=0xFFFFFF, x=120, y=46))
    
    # Button at y=56 (spacing 10 from last level at y=46)
    g.append(label.Label(terminalio.FONT, text="[Rotate & Press]", color=0xFFFFFF, x=12, y=56))
    display.root_group = g

def get_method_text(method):
    if method == "tilt":
        return "Tilt"
    elif method == "shake":
        return "Shake"
    elif method == "touch":
        return "Catch"
    elif method == "rotate":
        return "Rotate"
    elif method == "tree":
        return "ShakeTree"
    return ""

def show_intro():
    lv = LEVELS[game.level]
    g = displayio.Group()
    
    num_ings = len(lv["ingredients"])
    
    # Title
    lt = f"LEVEL {game.level+1}"
    g.append(label.Label(terminalio.FONT, text=lt, color=0xFFFFFF, x=center_x(lt), y=5))
    g.append(label.Label(terminalio.FONT, text=lv["name"], color=0xFFFFFF, x=center_x(lv["name"]), y=16))
    
    # Determine which ingredients to show based on page
    if num_ings <= 3:
        # Show all on one page
        ings_to_show = lv["ingredients"]
        has_more_pages = False
    else:
        # 4 ingredients - split into 2 pages
        if game.intro_page == 0:
            ings_to_show = lv["ingredients"][:2]
            has_more_pages = True
        else:
            ings_to_show = lv["ingredients"][2:]
            has_more_pages = False
    
    # Calculate spacing - uniform between all items including Press Start
    if len(ings_to_show) == 2:
        start_y = 28
        spacing = 12  # Uniform 12px for 2 items
    elif len(ings_to_show) == 3:
        start_y = 28
        spacing = 10  # Uniform 10px for 3 items
    else:
        start_y = 28
        spacing = 12
    
    # Show ingredients
    y = start_y
    for ing, cnt, method in ings_to_show:
        icon_bmp, icon_pal = make_icon(ing)
        mt = get_method_text(method)
        ing_cap = ing[0].upper() + ing[1:]
        txt = f"{ing_cap}x{cnt}({mt})"
        tw = 10 + len(txt) * 6
        sx = (128 - tw) // 2
        
        g.append(displayio.TileGrid(icon_bmp, pixel_shader=icon_pal, x=sx, y=y))
        g.append(label.Label(terminalio.FONT, text=txt, color=0xFFFFFF, x=sx+10, y=y+4))
        y += spacing
    
    # Bottom text - positioned with same spacing after last ingredient
    if has_more_pages:
        txt = "[Press: More]"
    else:
        txt = "[Press Start]"
    
    btn_y = y + 4  # Same offset as ingredient text (y+4)
    g.append(label.Label(terminalio.FONT, text=txt, color=0xFFFFFF, x=center_x(txt), y=btn_y))
    
    # Page indicator for multi-page
    if num_ings > 3:
        pg_txt = f"({game.intro_page+1}/2)"
        g.append(label.Label(terminalio.FONT, text=pg_txt, color=0xFFFFFF, x=100, y=5))
    
    display.root_group = g
    return has_more_pages

def show_game():
    lv = LEVELS[game.level]
    g = displayio.Group()
    
    # Status
    st = f"L{game.level+1} {int(game.time_left)}s"
    g.append(label.Label(terminalio.FONT, text=st, color=0xFFFFFF, x=0, y=6))
    if game.penalty > 0:
        g.append(label.Label(terminalio.FONT, text=f"-{game.penalty}", color=0xFFFFFF, x=100, y=6))
    
    # Waves
    if lv.get("waves"):
        for wy in game.waves_y:
            for wx in range(0, 128, 16):
                wb, wp = make_icon("wave")
                g.append(displayio.TileGrid(wb, pixel_shader=wp, x=wx, y=wy))
    
    if lv["view"] == "side":
        # Ground
        bmp, pal = make_rect(128, 2)
        g.append(displayio.TileGrid(bmp, pixel_shader=pal, x=0, y=52))
        
        # Animals
        for a in game.animals:
            ab, ap = make_icon(a["type"])
            g.append(displayio.TileGrid(ab, pixel_shader=ap, x=int(a["x"])-4, y=int(a["y"])-4))
        
        # Player basket
        bmp, pal = make_rect(10, 5)
        g.append(displayio.TileGrid(bmp, pixel_shader=pal, x=game.px-5, y=45))
        b2, p2 = make_rect(2, 8)
        g.append(displayio.TileGrid(b2, pixel_shader=p2, x=game.px-5, y=40))
        b3, p3 = make_rect(2, 8)
        g.append(displayio.TileGrid(b3, pixel_shader=p3, x=game.px+3, y=40))
    else:
        # Border
        bmp, pal = make_rect(128, 42, False)
        g.append(displayio.TileGrid(bmp, pixel_shader=pal, x=0, y=10))
        
        # Animals
        for a in game.animals:
            ab, ap = make_icon(a["type"])
            g.append(displayio.TileGrid(ab, pixel_shader=ap, x=int(a["x"])-4, y=int(a["y"])-4))
        
        # Trees
        for t in game.trees:
            if t["visible"]:
                tb, tp = make_icon("tree")
                g.append(displayio.TileGrid(tb, pixel_shader=tp, x=int(t["x"])-4, y=int(t["y"])-4))
        
        # Player
        px = max(12, min(116, game.px))
        py = max(16, min(46, game.py))
        bmp, pal = make_rect(7, 3)
        g.append(displayio.TileGrid(bmp, pixel_shader=pal, x=px-3, y=py-1))
        b2, p2 = make_rect(3, 7)
        g.append(displayio.TileGrid(b2, pixel_shader=p2, x=px-1, y=py-3))
    
    # Items
    for it in game.items:
        ib, ip = make_icon(it["name"])
        g.append(displayio.TileGrid(ib, pixel_shader=ip, x=int(it["x"])-4, y=int(it["y"])-4))
    
    # Touch progress - fixed at top right corner
    if game.touch_target:
        prog = min(1.0, (time.monotonic() - game.touch_start) / TOUCH_TIME)
        # Background bar (outline)
        bb_bg, bp_bg = make_rect(22, 5, False)
        g.append(displayio.TileGrid(bb_bg, pixel_shader=bp_bg, x=104, y=0))
        # Progress bar (filled)
        bw = int(20 * prog)
        if bw > 1:
            bb, bp = make_rect(bw, 3)
            g.append(displayio.TileGrid(bb, pixel_shader=bp, x=105, y=1))
    
    # Rotate progress
    if game.rotate_target:
        rotate_needed = lv.get("rotate_needed", ROTATE_NEEDED)
        txt = f"Rotate!{game.rotate_count}/{rotate_needed}"
        g.append(label.Label(terminalio.FONT, text=txt, color=0xFFFFFF, x=35, y=6))
    
    # Collection progress - adaptive spacing for 3 or 4 ingredients
    num_ings = len(lv["ingredients"])
    if num_ings <= 3:
        spacing = 40
        start_x = 2
    else:
        spacing = 31  # Tighter for 4 items
        start_x = 0
    
    x = start_x
    for ing, need, _ in lv["ingredients"]:
        got = game.collected.get(ing, 0)
        ib, ip = make_icon(ing)
        g.append(displayio.TileGrid(ib, pixel_shader=ip, x=x, y=55))
        g.append(label.Label(terminalio.FONT, text=f"{got}/{need}", color=0xFFFFFF, x=x+9, y=60))
        x += spacing
    
    display.root_group = g

def show_cooking():
    lv = LEVELS[game.level]
    g = displayio.Group()
    
    cook_type = lv.get("cooking")
    cook_name = lv.get("cook_name", "Cooking...")
    
    if cook_type == "double" and game.cook_progress >= 100:
        cook_name = lv.get("cook_name2", "Finishing...")
        progress = game.cook_progress2
    else:
        progress = game.cook_progress
    
    g.append(label.Label(terminalio.FONT, text=cook_name, color=0xFFFFFF, x=center_x(cook_name), y=12))
    
    # Instruction
    if cook_type == "button" or (cook_type == "double" and game.cook_progress < 100):
        inst = "Hold button!"
    else:
        inst = "Rotate encoder!"
    g.append(label.Label(terminalio.FONT, text=inst, color=0xFFFFFF, x=center_x(inst), y=28))
    
    # Bar
    bmp, pal = make_rect(100, 12, False)
    g.append(displayio.TileGrid(bmp, pixel_shader=pal, x=14, y=38))
    fw = int((progress / 100) * 96)
    if fw > 2:
        b2, p2 = make_rect(fw, 8)
        g.append(displayio.TileGrid(b2, pixel_shader=p2, x=16, y=40))
    
    pct = f"{progress}%"
    g.append(label.Label(terminalio.FONT, text=pct, color=0xFFFFFF, x=center_x(pct), y=58))
    display.root_group = g

def show_clear():
    lv = LEVELS[game.level]
    g = displayio.Group()
    scroll = game.scroll_offset
    
    # Check if scrolling needed
    dish_width = len(lv["dish"]) * 6
    needs_scroll = dish_width > 120
    if not needs_scroll:
        scroll = 0
    
    ct = "LEVEL CLEAR!"
    g.append(label.Label(terminalio.FONT, text=ct, color=0xFFFFFF, x=center_x(ct)-scroll, y=8))
    
    # Level score
    score_txt = f"+{game.level_score}pts"
    g.append(label.Label(terminalio.FONT, text=score_txt, color=0xFFFFFF, x=center_x(score_txt)-scroll, y=20))
    
    # Icons
    ings = lv["ingredients"]
    tw = len(ings) * 12
    sx = (128 - tw) // 2 - scroll
    for ing, _, _ in ings:
        ib, ip = make_icon(ing)
        g.append(displayio.TileGrid(ib, pixel_shader=ip, x=sx, y=30))
        sx += 12
    
    # Dish name
    dish = lv["dish"]
    g.append(label.Label(terminalio.FONT, text=dish, color=0xFFFFFF, x=center_x(dish)-scroll, y=46))
    
    g.append(label.Label(terminalio.FONT, text="[Press Next]", color=0xFFFFFF, x=28, y=58))
    display.root_group = g
    return needs_scroll

def show_over():
    g = displayio.Group()
    g.append(label.Label(terminalio.FONT, text="GAME OVER", color=0xFFFFFF, x=center_x("GAME OVER"), y=8))
    
    # Show final score
    score_txt = f"Score: {game.score}"
    g.append(label.Label(terminalio.FONT, text=score_txt, color=0xFFFFFF, x=center_x(score_txt), y=22))
    
    # Two options: Retry (0) or Restart (1)
    retry_pre = "> " if game.over_choice == 0 else "  "
    restart_pre = "> " if game.over_choice == 1 else "  "
    
    g.append(label.Label(terminalio.FONT, text=retry_pre + "Retry Level", color=0xFFFFFF, x=24, y=40))
    g.append(label.Label(terminalio.FONT, text=restart_pre + "Restart Game", color=0xFFFFFF, x=24, y=54))
    display.root_group = g

def show_win():
    g = displayio.Group()
    g.append(label.Label(terminalio.FONT, text="YOU WIN!", color=0xFFFFFF, x=center_x("YOU WIN!"), y=10))
    g.append(label.Label(terminalio.FONT, text="MASTER CHEF!", color=0xFFFFFF, x=center_x("MASTER CHEF!"), y=24))
    
    # Show final score
    score_txt = f"Final Score: {game.score}"
    g.append(label.Label(terminalio.FONT, text=score_txt, color=0xFFFFFF, x=center_x(score_txt), y=40))
    
    g.append(label.Label(terminalio.FONT, text="[Press Continue]", color=0xFFFFFF, x=center_x("[Press Continue]"), y=56))
    display.root_group = g

def show_high_scores():
    """Display the high score board"""
    g = displayio.Group()
    g.append(label.Label(terminalio.FONT, text="HIGH SCORES", color=0xFFFFFF, x=center_x("HIGH SCORES"), y=8))
    
    y_pos = 22
    for i, hs in enumerate(high_scores):
        rank = f"{i+1}."
        txt = f"{rank} {hs['initials']} {hs['score']:>4}"
        g.append(label.Label(terminalio.FONT, text=txt, color=0xFFFFFF, x=30, y=y_pos))
        y_pos += 12
    
    g.append(label.Label(terminalio.FONT, text="[Press Continue]", color=0xFFFFFF, x=center_x("[Press Continue]"), y=58))
    display.root_group = g

def show_initials_entry():
    """Screen for entering initials for high score"""
    g = displayio.Group()
    g.append(label.Label(terminalio.FONT, text="NEW HIGH SCORE!", color=0xFFFFFF, x=center_x("NEW HIGH SCORE!"), y=8))
    
    score_txt = f"Score: {game.score}"
    g.append(label.Label(terminalio.FONT, text=score_txt, color=0xFFFFFF, x=center_x(score_txt), y=22))
    
    g.append(label.Label(terminalio.FONT, text="Enter Initials:", color=0xFFFFFF, x=center_x("Enter Initials:"), y=36))
    
    # Display initials with cursor
    initials_display = ""
    for i in range(3):
        if i < len(game.initials):
            initials_display += game.initials[i]
        elif i == len(game.initials):
            # Current position - show with underscore
            initials_display += chr(65 + game.initial_char)
        else:
            initials_display += "_"
        initials_display += " "
    
    # Draw initials larger
    g.append(label.Label(terminalio.FONT, text=initials_display, color=0xFFFFFF, x=center_x(initials_display), y=50))
    
    # Show cursor indicator
    cursor_x = center_x(initials_display) + len(game.initials) * 12
    g.append(label.Label(terminalio.FONT, text="^", color=0xFFFFFF, x=cursor_x, y=58))
    
    display.root_group = g

# ============================================
# NEOPIXEL
# ============================================
def px_off():
    pixels.fill(COLOR_OFF)
    pixels.show()

def px_success():
    """Success feedback with sound"""
    pixels.fill(COLOR_GREEN)
    pixels.show()
    sound_collect()
    pixels.fill(COLOR_OFF)
    pixels.show()

def px_fail():
    """Fail/Game over feedback with sound"""
    pixels.fill(COLOR_RED)
    pixels.show()
    sound_game_over()
    pixels.fill(COLOR_OFF)
    pixels.show()

def px_spawn():
    pixels.fill(COLOR_YELLOW)
    pixels.show()
    time.sleep(0.03)
    pixels.fill(COLOR_OFF)
    pixels.show()

def px_complete():
    """Level complete feedback with sound"""
    sound_level_clear()
    for c in [COLOR_RED, COLOR_YELLOW, COLOR_GREEN, COLOR_BLUE, COLOR_PURPLE]:
        pixels.fill(c)
        pixels.show()
        time.sleep(0.1)
    pixels.fill(COLOR_OFF)
    pixels.show()

def px_cooking(p):
    n = int((p / 100) * NUM_PIXELS)
    for i in range(NUM_PIXELS):
        pixels[i] = COLOR_BLUE if i < n else COLOR_OFF
    pixels.show()

def px_penalty():
    """Penalty feedback with sound"""
    pixels.fill(COLOR_RED)
    pixels.show()
    sound_fail()
    pixels.fill(COLOR_OFF)
    pixels.show()

# ============================================
# GAME LOGIC
# ============================================
def init_level():
    lv = LEVELS[game.level]
    game.time_left = DIFFICULTY[game.difficulty][0]
    game.px = 64
    game.py = 30 if lv["view"] == "topdown" else 45
    game.collected = {}
    game.needed = {ing: cnt for ing, cnt, _ in lv["ingredients"]}
    game.items = []
    game.animals = []
    game.trees = []
    game.waves_y = []
    game.cook_progress = 0
    game.cook_progress2 = 0
    game.touch_target = None
    game.rotate_target = None
    game.rotate_count = 0
    game.penalty = 0
    game.level_score = 0  # Reset level score
    
    # Waves for water levels - random number of waves inside game area
    if lv.get("waves"):
        num_waves = random.randint(2, 4)
        game.waves_y = []
        possible_y = [18, 26, 34, 42]
        for _ in range(num_waves):
            if possible_y:
                wy = random.choice(possible_y)
                possible_y.remove(wy)
                game.waves_y.append(wy)
    
    # Animals
    for atype, amode in lv.get("animals", []):
        if lv["view"] == "side":
            if amode == "top":
                y = 12
            else:
                y = 44
            game.animals.append({
                "type": atype, "x": random.randint(20, 100), "y": y,
                "vx": 1.5 if atype == "chicken" else 1.0, "vy": 0,
                "egg_timer": 0, "mode": amode
            })
        else:
            spd = 2.0 if amode == "fast" else (1.5 if amode == "danger" else 1.0)
            game.animals.append({
                "type": atype,
                "x": random.randint(20, 108),
                "y": random.randint(18, 44),
                "vx": random.uniform(-1, 1) * spd,
                "vy": random.uniform(-1, 1) * spd,
                "egg_timer": 0, "mode": amode
            })
    
    # Initial items (only tilt/shake types)
    spawn_items(lv, 2)

def spawn_items(lv, count=1):
    spawnable = [(i, m) for i, _, m in lv["ingredients"] if m in ["tilt", "shake"]]
    if not spawnable:
        return
    
    for _ in range(count):
        ing, method = random.choice(spawnable)
        
        if lv["view"] == "side":
            x = random.randint(20, 108)
            if method == "tilt":
                y = random.randint(12, 30)
                vy = 1.2
            else:
                y = 44
                vy = 0
            vx = 0
        else:
            x = random.randint(18, 110)
            y = random.randint(18, 44)
            # Slower movement for fish so they stay longer
            if ing == "fish":
                vx = random.uniform(-0.15, 0.15)
                vy = random.uniform(-0.1, 0.1)
            else:
                vx = random.uniform(-0.3, 0.3)
                vy = random.uniform(-0.2, 0.2)
        
        game.items.append({
            "name": ing, "x": x, "y": y,
            "vx": vx, "vy": vy, "method": method
        })

def spawn_tree(lv):
    tree_ings = [i for i, _, m in lv["ingredients"] if m == "tree"]
    if not tree_ings:
        return
    
    x = random.randint(18, 110)
    if lv.get("waves"):
        y = random.choice([16, 28, 42])
    else:
        y = random.randint(18, 44)
    
    game.trees.append({
        "x": x, "y": y, "visible": True,
        "timer": time.monotonic(),
        "ing": random.choice(tree_ings)
    })

def spawn_rotate_item(lv):
    rotate_ings = [i for i, _, m in lv["ingredients"] if m == "rotate"]
    if not rotate_ings:
        return
    
    # Check if already have rotate items
    for it in game.items:
        if it.get("method") == "rotate":
            return
    
    x = random.randint(20, 108)
    y = random.randint(18, 44) if lv["view"] == "topdown" else 44
    
    game.items.append({
        "name": rotate_ings[0], "x": x, "y": y,
        "vx": 0, "vy": 0, "method": "rotate"
    })

def update_animals(lv, dt):
    for a in game.animals:
        # Move
        a["x"] += a["vx"]
        if lv["view"] == "topdown":
            a["y"] += a["vy"]
        
        # Bounce
        if a["x"] < 15 or a["x"] > 113:
            a["vx"] *= -1
        if lv["view"] == "topdown" and (a["y"] < 16 or a["y"] > 46):
            a["vy"] *= -1
        
        # Clamp
        a["x"] = max(15, min(113, a["x"]))
        if lv["view"] == "topdown":
            a["y"] = max(16, min(46, a["y"]))
        
        # Chicken lays eggs
        if a["type"] == "chicken" and a["mode"] != "fast":
            a["egg_timer"] += dt
            if a["egg_timer"] > 2.5:
                a["egg_timer"] = 0
                game.items.append({
                    "name": "egg",
                    "x": a["x"],
                    "y": a["y"] + (8 if lv["view"] == "side" else 0),
                    "vx": 0,
                    "vy": 1.2 if lv["view"] == "side" else 0,
                    "method": "tilt"
                })

def update_items(lv):
    to_remove = []
    now = time.monotonic()
    
    for it in game.items:
        it["x"] += it["vx"]
        it["y"] += it["vy"]
        
        # Check lifetime for berry/timed items
        if "lifetime" in it:
            if now - it["timer"] > it["lifetime"]:
                to_remove.append(it)
                continue
        
        if lv["view"] == "side":
            if it["y"] > 55:
                to_remove.append(it)
        else:
            # Bounce
            if it["x"] < 12 or it["x"] > 116:
                it["vx"] *= -1
            if it["y"] < 14 or it["y"] > 48:
                it["vy"] *= -1
            it["x"] = max(12, min(116, it["x"]))
            it["y"] = max(14, min(48, it["y"]))
            
            # Fish disappear at waves
            if lv.get("waves") and it["name"] == "fish":
                for wy in game.waves_y:
                    if abs(it["y"] - wy) < 6:
                        to_remove.append(it)
                        break
    
    for it in to_remove:
        if it in game.items:
            game.items.remove(it)

def update_trees():
    now = time.monotonic()
    for t in game.trees:
        if t["visible"] and now - t["timer"] > 4.5:  # Longer visibility
            t["visible"] = False
    game.trees = [t for t in game.trees if t["visible"] or now - t["timer"] < 6]

def check_catch(is_shake):
    caught = []
    for it in game.items:
        dx = game.px - it["x"]
        dy = game.py - it["y"]
        dist = (dx*dx + dy*dy) ** 0.5
        
        if dist < 12:
            m = it.get("method", "tilt")
            if m == "tilt":
                caught.append((it, SCORE_TILT))
            elif m == "shake" and is_shake:
                caught.append((it, SCORE_SHAKE))
    
    for it, points in caught:
        game.items.remove(it)
        game.collected[it["name"]] = game.collected.get(it["name"], 0) + 1
        game.score += points
        game.level_score += points
        px_success()

def check_touch():
    now = time.monotonic()
    
    for a in game.animals:
        if a["mode"] == "danger":
            continue
        
        dx = game.px - a["x"]
        dy = game.py - a["y"]
        dist = (dx*dx + dy*dy) ** 0.5
        
        if dist < 15:
            if game.touch_target != a:
                game.touch_target = a
                game.touch_start = now
            elif now - game.touch_start >= TOUCH_TIME:
                # Collected!
                if a["type"] == "cow":
                    game.collected["milk"] = game.collected.get("milk", 0) + 1
                elif a["type"] == "pig":
                    game.collected["bacon"] = game.collected.get("bacon", 0) + 1
                    # Pig runs faster
                    a["vx"] *= 1.3
                    a["vy"] *= 1.3
                elif a["type"] == "bee":
                    game.collected["honey"] = game.collected.get("honey", 0) + 1
                elif a["type"] in ["chicken", "duck", "turkey", "lamb"]:
                    game.collected[a["type"]] = game.collected.get(a["type"], 0) + 1
                
                # Add touch score
                game.score += SCORE_TOUCH
                game.level_score += SCORE_TOUCH
                px_success()
                game.touch_target = None
                game.touch_start = now
                return
        else:
            if game.touch_target == a:
                game.touch_target = None

def check_danger():
    lv = LEVELS[game.level]
    for a in game.animals:
        if a["mode"] == "danger":
            dx = game.px - a["x"]
            dy = game.py - a["y"]
            dist = (dx*dx + dy*dy) ** 0.5
            if dist < 12:
                # Shark eats fish - reduce fish count
                if lv.get("shark_eats_fish") and game.collected.get("fish", 0) > 0:
                    game.collected["fish"] = max(0, game.collected.get("fish", 0) - 1)
                else:
                    game.penalty += 1
                px_penalty()
                # Push away
                if game.px < a["x"]:
                    game.px = max(12, game.px - 15)
                else:
                    game.px = min(116, game.px + 15)

def check_tree_shake(is_shake):
    if not is_shake:
        return
    
    for t in game.trees:
        if not t["visible"]:
            continue
        dx = game.px - t["x"]
        dy = game.py - t["y"]
        dist = (dx*dx + dy*dy) ** 0.5
        if dist < 18:
            game.collected[t["ing"]] = game.collected.get(t["ing"], 0) + 1
            t["visible"] = False
            # Tree shake is a shake collection
            game.score += SCORE_SHAKE
            game.level_score += SCORE_SHAKE
            px_success()

def check_bee_shake(is_shake):
    if not is_shake:
        return
    
    for a in game.animals:
        if a["type"] == "bee":
            dx = game.px - a["x"]
            dy = game.py - a["y"]
            dist = (dx*dx + dy*dy) ** 0.5
            if dist < 18:
                game.penalty += 1
                px_penalty()

def check_rotate(rot):
    if rot == 0:
        return
    
    lv = LEVELS[game.level]
    rotate_ings = [i for i, _, m in lv["ingredients"] if m == "rotate"]
    if not rotate_ings:
        return
    
    # Get rotate_needed from level config, default to 5
    rotate_needed = lv.get("rotate_needed", ROTATE_NEEDED)
    
    for it in game.items:
        if it.get("method") != "rotate":
            continue
        dx = game.px - it["x"]
        dy = game.py - it["y"]
        dist = (dx*dx + dy*dy) ** 0.5
        
        if dist < 15:
            if game.rotate_target != it:
                game.rotate_target = it
                game.rotate_count = 0
            
            game.rotate_count += abs(rot)
            if game.rotate_count >= rotate_needed:
                game.items.remove(it)
                game.collected[it["name"]] = game.collected.get(it["name"], 0) + 1
                # Rotate collection - highest score
                game.score += SCORE_ROTATE
                game.level_score += SCORE_ROTATE
                px_success()
                game.rotate_target = None
                game.rotate_count = 0
            return
    
    game.rotate_target = None
    game.rotate_count = 0

def is_complete():
    for ing, need, _ in LEVELS[game.level]["ingredients"]:
        if game.collected.get(ing, 0) < need:
            return False
    return True

def move(m, lv):
    now = time.monotonic()
    if now - game.last_move < MOVE_DEBOUNCE:
        return
    game.last_move = now
    
    spd = 6
    if lv["view"] == "side":
        if m == "LEFT":
            game.px = max(12, game.px - spd)
        elif m == "RIGHT":
            game.px = min(116, game.px + spd)
    else:
        if m == "LEFT":
            game.px = max(12, game.px - spd)
        elif m == "RIGHT":
            game.px = min(116, game.px + spd)
        elif m == "FWD":
            game.py = max(16, game.py - spd)
        elif m == "BACK":
            game.py = min(46, game.py + spd)

# ============================================
# MAIN LOOP
# ============================================
def main():
    global first_boot, high_scores
    print("Harvest Hustle Starting...")
    
    # Show splash screen only on first boot (power on)
    if first_boot:
        show_splash()
        first_boot = False
    
    px_off()
    
    spawn_timer = 0
    tree_timer = 0
    rotate_timer = 0
    last_t = time.monotonic()
    
    while True:
        now = time.monotonic()
        dt = now - last_t
        last_t = now
        
        rot, btn = read_encoder()
        accel = read_accel()
        is_shake = (accel == "SHAKE")
        
        if game.screen == "title":
            show_title()
            if btn:
                sound_start()
                px_success()
                game.screen = "mode"
                time.sleep(0.2)
        
        elif game.screen == "mode":
            if rot > 0:
                # Clockwise only - cycle through options
                game.diff_idx = (game.diff_idx + 1) % 3
                pixels[game.diff_idx] = COLOR_YELLOW
                pixels.show()
                time.sleep(0.05)
                pixels.fill(COLOR_OFF)
                pixels.show()
            game.difficulty = ["EASY", "MEDIUM", "HARD"][game.diff_idx]
            show_mode()
            if btn:
                pixels.fill(COLOR_GREEN)
                pixels.show()
                time.sleep(0.1)
                pixels.fill(COLOR_OFF)
                pixels.show()
                game.level_select_idx = 0
                game.screen = "level_select"
                time.sleep(0.2)
        
        elif game.screen == "level_select":
            if rot > 0:
                # Clockwise only - cycle through levels
                game.level_select_idx = (game.level_select_idx + 1) % len(LEVELS)
                pixels[game.level_select_idx % NUM_PIXELS] = COLOR_YELLOW
                pixels.show()
                time.sleep(0.05)
                pixels.fill(COLOR_OFF)
                pixels.show()
            show_level_select()
            if btn:
                sound_start()
                px_success()
                game.level = game.level_select_idx
                game.scroll_offset = 0
                game.intro_page = 0
                game.screen = "intro"
                time.sleep(0.3)
        
        elif game.screen == "intro":
            has_more_pages = show_intro()
            
            if btn:
                if has_more_pages:
                    # Go to next page
                    game.intro_page += 1
                    px_success()
                    time.sleep(0.2)
                else:
                    # Start game
                    px_success()
                    game.intro_page = 0
                    game.scroll_offset = 0
                    init_level()
                    game.screen = "play"
                    spawn_timer = 0
                    tree_timer = 0
                    rotate_timer = 0
                    time.sleep(0.3)
        
        elif game.screen == "play":
            lv = LEVELS[game.level]
            game.time_left -= dt
            
            if game.time_left <= 0:
                game.screen = "over"
                game.over_choice = 0  # Default to Retry
                px_fail()
                continue
            
            # Move
            if accel and accel != "SHAKE":
                move(accel, lv)
            
            # Updates
            update_animals(lv, dt)
            update_items(lv)
            update_trees()
            
            # Checks
            check_catch(is_shake)
            check_touch()
            check_rotate(rot)
            check_tree_shake(is_shake)
            check_danger()
            
            # Bee penalty for shake
            if "bee" in [a["type"] for a in game.animals]:
                check_bee_shake(is_shake)
            
            # Spawn items
            spawn_timer += dt
            spawn_interval = 2.0 if lv.get("spawn_fast") else 2.5
            max_items = 4  # Keep at 4
            if spawn_timer > spawn_interval and len(game.items) < max_items:
                spawn_items(lv, 2 if lv.get("spawn_fast") else 1)
                spawn_timer = 0
            
            # Spawn trees
            if lv.get("trees"):
                tree_timer += dt
                if tree_timer > 3.0 and len(game.trees) < 2:
                    spawn_tree(lv)
                    tree_timer = 0
            
            # Spawn berries (appear/disappear items)
            if lv.get("berry_spawn"):
                tree_timer += dt
                if tree_timer > 2.5 and len([it for it in game.items if it["name"] == "berry"]) < 2:
                    # Spawn berry that will disappear
                    x = random.randint(18, 110)
                    y = random.randint(18, 44)
                    game.items.append({
                        "name": "berry", "x": x, "y": y,
                        "vx": 0, "vy": 0, "method": "tilt",
                        "timer": time.monotonic(), "lifetime": 4.0  # Longer lifetime
                    })
                    tree_timer = 0
            
            # Spawn rotate items
            rotate_timer += dt
            if rotate_timer > 3.0:
                spawn_rotate_item(lv)
                rotate_timer = 0
            
            show_game()
            
            if is_complete():
                if lv.get("cooking"):
                    game.screen = "cooking"
                else:
                    game.screen = "clear"
                    px_complete()
        
        elif game.screen == "cooking":
            lv = LEVELS[game.level]
            cook_type = lv.get("cooking")
            
            if cook_type == "double":
                # First phase: button
                if game.cook_progress < 100:
                    if not btn_pin.value:
                        game.cook_progress = min(100, game.cook_progress + 2)
                else:
                    # Second phase: rotate
                    if rot:
                        game.cook_progress2 = min(100, game.cook_progress2 + abs(rot) * 5)
                
                px_cooking(game.cook_progress if game.cook_progress < 100 else game.cook_progress2)
                show_cooking()
                
                if game.cook_progress2 >= 100:
                    game.screen = "clear"
                    px_complete()
                    time.sleep(0.3)
            else:
                # Single phase: button
                if not btn_pin.value:
                    game.cook_progress = min(100, game.cook_progress + 2)
                
                px_cooking(game.cook_progress)
                show_cooking()
                
                if game.cook_progress >= 100:
                    game.screen = "clear"
                    px_complete()
                    time.sleep(0.3)
        
        elif game.screen == "clear":
            needs_scroll = show_clear()
            # Tilt to scroll only if needed
            if needs_scroll and now - game.last_scroll > 0.15:
                if accel == "LEFT":
                    game.scroll_offset = max(-50, game.scroll_offset - 15)
                    game.last_scroll = now
                elif accel == "RIGHT":
                    game.scroll_offset = min(100, game.scroll_offset + 15)
                    game.last_scroll = now
            
            if btn:
                px_success()
                game.level += 1
                game.scroll_offset = 0
                game.intro_page = 0
                if game.level >= len(LEVELS):
                    sound_win()  # Victory sound!
                    game.screen = "win"
                else:
                    game.screen = "intro"
                time.sleep(0.3)
        
        elif game.screen == "over":
            # Rotate to select option
            if rot > 0:
                game.over_choice = (game.over_choice + 1) % 2
                pixels[game.over_choice] = COLOR_YELLOW
                pixels.show()
                time.sleep(0.05)
                pixels.fill(COLOR_OFF)
                pixels.show()
            
            show_over()
            
            # Press to confirm
            if btn:
                if game.over_choice == 0:
                    # Retry Level - forfeit points from failed attempt
                    game.score -= game.level_score
                    sound_start()
                    pixels.fill(COLOR_GREEN)
                    pixels.show()
                    time.sleep(0.1)
                    pixels.fill(COLOR_OFF)
                    pixels.show()
                    game.scroll_offset = 0
                    game.intro_page = 0
                    init_level()
                    game.screen = "play"
                    spawn_timer = 0
                    tree_timer = 0
                    rotate_timer = 0
                    time.sleep(0.2)
                else:
                    # Restart Game - check for high score first
                    game.after_highscore = "restart"
                    if is_high_score(game.score, high_scores):
                        game.is_new_high_score = True
                        game.initials = ""
                        game.initial_char = 0
                        game.screen = "enter_initials"
                    else:
                        game.screen = "highscores"
                    time.sleep(0.2)
        
        elif game.screen == "win":
            show_win()
            # Rainbow LED celebration
            for i in range(NUM_PIXELS):
                hue = (int(time.monotonic() * 100) + i * 32) % 256
                if hue < 85:
                    r, g_c, b = 255 - hue * 3, hue * 3, 0
                elif hue < 170:
                    hue -= 85
                    r, g_c, b = 0, 255 - hue * 3, hue * 3
                else:
                    hue -= 170
                    r, g_c, b = hue * 3, 0, 255 - hue * 3
                pixels[i] = (r, g_c, b)
            pixels.show()
            
            if btn:
                # Check if this is a high score
                game.after_highscore = "reset"
                if is_high_score(game.score, high_scores):
                    game.is_new_high_score = True
                    game.initials = ""
                    game.initial_char = 0
                    game.screen = "enter_initials"
                else:
                    game.screen = "highscores"
                time.sleep(0.3)
        
        elif game.screen == "enter_initials":
            show_initials_entry()
            
            # Rotate to change character
            if rot > 0:
                game.initial_char = (game.initial_char + 1) % 26
            
            # Press to confirm character
            if btn:
                game.initials += chr(65 + game.initial_char)
                game.initial_char = 0
                
                if len(game.initials) >= 3:
                    # Save the high score
                    high_scores = insert_high_score(game.initials, game.score, high_scores)
                    save_high_scores(high_scores)
                    sound_level_clear()
                    game.screen = "highscores"
                time.sleep(0.2)
        
        elif game.screen == "highscores":
            show_high_scores()
            
            if btn:
                px_complete()
                if game.after_highscore == "restart":
                    game.score = 0
                    game.screen = "mode"
                    game.diff_idx = 0
                else:
                    game.reset()
                time.sleep(0.3)
        
        time.sleep(0.005)  # 5ms for better responsiveness

main()
