"""
Description: python interface for a raspberry pi with two gpio buttons
and an LCD display, either I2C or GPIO
"""


# adjust timings below as needed/desired
POLL_TIME = 0.01
HOLD_TIME = 1.0
LONG_TIME = 3.0
MENU_TIMEOUT = 5.0
BLINK_TIME = 0.1
SCROLL_TIME = 0.4


import time
import RPLCD, RPi.GPIO as GPIO
from .hw_overlay import *
if I2C:
    from RPLCD.i2c import CharLCD
else:
    from RPLCD.gpio import CharLCD

if ACTIVE_HIGH:
    ACTIVE = GPIO.HIGH
else:
    ACTIVE = GPIO.LOW
UP = 0
DOWN = 1
TAP = 2
HOLD = 3
HELD = 4
LONG = 5
LONGER = 6

CHR_BSP = 0
CHR_ENT = 1
INPCHARS = " abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.\/" + chr(CHR_BSP) + chr(CHR_ENT)
PRNCHARS = ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~' + chr(CHR_BSP) + chr(CHR_ENT)
BUTTONS = {'left': BTN_L, 'right': BTN_R}

LINESTR = "%-" + str(COLS) + "s"

class StompBox():

    def __init__(self):

        # initialize LCD
        if I2C:
            self.LCD = CharLCD(i2c_expander=I2CEXPANDER, address=I2CADDR,
                               port=1, cols=COLS, rows=ROWS, dotsize=8,
                               charmap='A02',
                               auto_linebreaks=True,
                               backlight_enabled=True)
        else:
            self.LCD = RPLCD.CharLCD(pin_rs=LCD_RS,
                                     pin_e=LCD_EN,
                                     pin_rw=None,
                                     pins_data=[LCD_D4, LCD_D5, LCD_D6, LCD_D7],
                                     numbering_mode=GPIO.BCM,
                                     cols=COLS, rows=ROWS,
                                     compat_mode=True)
        self.LCD.create_char(CHR_BSP,[0,3,5,9,5,3,0,0])
        self.LCD.create_char(CHR_ENT,[0,1,5,9,31,8,4,0])
        self.lcd_clear()

        # set up buttons
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        for button in BUTTONS:
            if ACTIVE_HIGH:
                GPIO.setup(BUTTONS[button], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            else:
                GPIO.setup(BUTTONS[button], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.state = {button: UP for button in BUTTONS}
        self.timer = {button: 0 for button in BUTTONS}

    def button(self, button):
        return self.state[button]

    def buttons(self):
        return self.state.values()

    def update(self):
        time.sleep(POLL_TIME)

        t = time.time()
        for button in BUTTONS:
            if GPIO.input(BUTTONS[button]) != ACTIVE:
                self.timer[button] = t
                if self.state[button] == DOWN:
                    self.state[button] = TAP
                else:
                    self.state[button] = UP
            else:
                if self.state[button] == UP:
                    self.state[button] = DOWN
                    self.timer[button] = t
                elif self.state[button] == DOWN:
                    if (t - self.timer[button]) >= HOLD_TIME:
                        self.state[button] = HOLD
                elif self.state[button] == HOLD:
                    self.state[button] = HELD
                elif self.state[button] == HELD:
                    if (t - self.timer[button]) >= LONG_TIME:
                        self.state[button] = LONG
                elif self.state[button] == LONG:
                    self.state[button] = LONGER

        if self.scrollmsg:
            if (t - self.lastscroll) >= SCROLL_TIME:
                self.lastscroll = t
                self.scrollpos += 1
                self.lcd_write(self.scrollmsg, self.scrollrow)

    def waitforrelease(self, tmin=0):
        # wait for all buttons to be released and at least :tmin seconds
        tmin = time.time() + tmin
        while True:
            self.update()
            if time.time() >= tmin:
                if all(s == UP for s in self.state.values()):
                    break

    def waitfortap(self, t):
        # wait :t seconds or until a button is tapped
        # return True if tapped, False if not
        tstop = time.time() + t
        while time.time() < tstop:
            self.update()
            if TAP in self.state.values():
                return True
        return False

    def lcd_clear(self):
        self.LCD.clear()
        self.scrollmsg = ''

    def lcd_write(self, text, row=0, col=0):
        if len(text) > COLS:
            if self.scrollmsg:
                self.LCD.cursor_pos = (row, 0)
                if self.scrollpos < 0:
                    self.LCD.write_string(LINESTR % self.scrollmsg[:COLS])
                elif self.scrollpos < (len(self.scrollmsg) - COLS):
                    self.LCD.write_string(LINESTR % self.scrollmsg[self.scrollpos:self.scrollpos+COLS])
                elif self.scrollpos < (len(self.scrollmsg) - (COLS - 2)):
                    self.LCD.write_string(LINESTR % self.scrollmsg[-COLS:])
                else:
                    self.scrollpos = -4
            else:
                self.scrollmsg = text
                self.scrollrow = row
                self.scrollpos = -4
                self.lastscroll = time.time()
                self.LCD.cursor_pos = (row, 0)
                self.LCD.write_string(LINESTR % text[:COLS])
        else:
            if self.scrollmsg and row == self.scrollrow:
                self.scrollmsg = ''
            self.LCD.cursor_pos = (row, col)
            self.LCD.write_string(text + ' '*(COLS - len(text)))


    def lcd_blink(self, text, row=0, n=3):
        while n != 0:
            self.lcd_write(' '*COLS, row)
            time.sleep(BLINK_TIME)
            self.lcd_write(LINESTR % text, row)
            time.sleep(BLINK_TIME)
            n -= 1

    def choose_opt(self, opts, row=0, timeout=MENU_TIMEOUT, passlong=False):
        """
        has the user choose from a list of choices in :opts
        returns the index of the choice
        or -1 if the user backed out or time expired
        passlong: pass LONG through to calling loop
        """
        i=0
        while True:
            self.lcd_write(' '*COLS, row)
            self.lcd_write(opts[i], row)
            if ROWS == 4:
                if COLS == 20:
                    self.lcd_write('Prev            Next', 2)
                    self.lcd_write('Back---Long---Select', 3)
                else:
                    self.lcd_write('Prev        Next', 2)
                    self.lcd_write('Back-Long-Select', 3)
            tstop = time.time() + timeout
            while True:
                if timeout and time.time() > tstop:
                    self.lcd_write(' '*COLS, row)
                    return -1
                self.update()
                if sum(self.state.values()) == UP:
                    continue
                elif self.state['right'] == TAP:
                    i=(i+1)%len(opts)
                    break
                elif self.state['left'] == TAP:
                    i=(i-1)%len(opts)
                    break
                elif self.state['right'] == HOLD:
                    self.lcd_blink(opts[i], row)
                    return i
                elif self.state['left'] == HOLD:
                    self.lcd_write(' '*COLS, row)
                    return -1
                elif LONG in self.state.values() and passlong:
                    for b in self.state:
                        if self.state[b] == LONG:
                            self.state[b] = HELD
                    return -1

    def choose_val(self, val, inc, minval, maxval, format=LINESTR):
        """
        lets the user change a numeric parameter
        returns the user's choice on timeout
        """
        while True:
            self.lcd_write(LINESTR % (format % val), 1)
            tstop = time.time() + MENU_TIMEOUT
            while time.time() < tstop:
                self.update()
                if sum(self.state.values()) == UP:
                    continue
                if self.state['right'] > DOWN:
                    val = min(val + inc, maxval)
                elif self.state['left'] > DOWN:
                    val = max(val - inc, minval)
                break
            else:
                return val

    def char_input(self, text='', row=1, timeout=MENU_TIMEOUT, charset=INPCHARS):
        """
        a way of letting the user enter a text string with two buttons
        text: the initial value of the text
        user taps buttons to choose character, holds buttons to move
         cursor right or left
        when cursor is at end of input, user can tap to
         delete or newline character
        newline returns text
        timeout returns empty string
        """
        i = len(text)
        char = len(charset) - 1
        self.LCD.cursor_mode = 'blink'
        while True:
            if i < len(text):
                char = charset.find(text[i])
            lpos = max(i - (COLS - 1), 0)
            self.lcd_write(LINESTR % text[lpos:lpos + COLS], row)
            if char > -1:
                self.lcd_write(charset[char], row, min(i, COLS - 1))
            self.LCD.cursor_pos = (row, min(i, COLS - 1))
            tstop = time.time() + timeout
            while time.time() < tstop:
                self.update()
                if sum(self.state.values()) == UP:
                    continue
                elif TAP in self.state.values():
                    if i==len(text):
                        if self.state['right'] == TAP:
                            char = (char + 1) % len(charset)
                        else:
                            char = (char - 1) % len(charset)
                    else:
                        if self.state['right'] == TAP:
                            char = (char + 1) % (len(charset) - 2)
                        else:
                            char = (char - 1) % (len(charset) - 2)
                    if char < (len(charset) - 2):
                        text = text[0:i] + charset[char] + text[i+1:]
                    break
                elif self.state['right'] >= HOLD:
                    if self.state['right'] == HELD:
                        continue
                    if char == (len(charset) - 1):
                        if self.state['right'] != HOLD:
                            continue
                        self.LCD.cursor_mode = 'hide'
                        self.lcd_blink(text.strip()[0:COLS], row)
                        return text.strip()
                    if self.state['right'] > HELD:
                        time.sleep(BLINK_TIME)
                    i = min(i + 1, len(text))
                    if i == len(text):
                        char = len(charset) - 1
                    break
                elif self.state['left'] >= HOLD:
                    if self.state['left'] == HELD:
                        continue
                    if char == (len(charset) - 2):
                        text = text[0:max(0, i - 1)] + text[i:]
                    if self.state['left'] > HELD: time.sleep(BLINK_TIME)
                    i = max(i - 1, 0)
                    break
            else:
                self.LCD.cursor_mode = 'hide'
                return ''

