"""
Description: model-dependent wiring and behavior
"""

# copy and paste definitions for your model at the bottom of this file

# model 0000 (my prototype)
BTN_R = 6
BTN_L = 5
ACTIVE_HIGH = 0
LCD_RS = 24
LCD_EN = 25
LCD_D4 = 8
LCD_D5 = 7
LCD_D6 = 12
LCD_D7 = 16

# models 0001-0009 (v2 wiring)
# LCD pins on exterior edge of board - easier for homebrew/perfboard builds
BTN_R = 22
BTN_L = 27
ACTIVE_HIGH = 1
LCD_RS = 15
LCD_EN = 23
LCD_D4 = 24
LCD_D5 = 25
LCD_D6 = 8
LCD_D7 = 7
COLS = 16
ROWS = 2

# models 0010-
# custom PCB v1
BTN_R = 3
BTN_L = 2
ACTIVE_HIGH = 0
LCD_RS = 4
LCD_EN = 27
LCD_D4 = 9
LCD_D5 = 11
LCD_D6 = 5
LCD_D7 = 6
COLS = 16
ROWS = 2

# I2C model
# Use i2cdetect -a 1 to find address
BTN_R = 22
BTN_L = 27
ACTIVE_HIGH = 1
I2C = True
COLS = 20
ROWS = 4
I2CADDR = 0x27
I2CEXPANDER = 'PCF8574'
