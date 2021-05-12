#! /usr/bin/python3

# Sound1b.py

import sys, os, re, glob, time, subprocess
import pygame
import RPi.GPIO as GPIO
from utils import stompboxpi as SB

SQUISHPLAYER_VERSION = '0.2'

pygame.init()

'''
states:
STOPPED : play process terminated
PAUSED: play process stopped (playing still underway)
PLAYING: play process executing
'''

# Play a song - allow pause, resume, & stop

def playsong(sno):
    pygame.mixer.music.load(music + '/' + files[sno])
    state = 'PLAYING'
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy() or state == 'PAUSED':
        while True:
            if SB.ROWS == 4:
                sb.lcd_write('     ' + state + ' '*(SB.COLS - (5 + len(state))), 2)
            sb.lcd_write('Pause/Play' + ' '*(SB.COLS - 14) + 'Stop', SB.ROWS - 1)
            sb.update()
            if SB.TAP in sb.buttons():
                if sb.button('left') == SB.TAP:
                    if state == 'PLAYING':
                        state = 'PAUSED'
                        pygame.mixer.music.pause()
                    elif state == 'STOPPED':
                        state = 'PLAYING'
                        pygame.mixer.music.play()
                    elif state == 'PAUSED':
                        state = 'PLAYING'
                        pygame.mixer.music.unpause()
                elif sb.button('right') == SB.TAP \
                        and (state == 'PAUSED' or state == 'PLAYING'):
                    state = 'STOPPED'
                    pygame.mixer.music.stop()
                    break

def playlist(plno):
#   open file in lists[plno] and read into array
    f = open(playlists + lists[plno], 'r')
    plist = [line.rstrip('\n') for line in f.readlines()]
    f.close()
    for mfile in plist:
        if not os.path.exists(music + mfile):
            continue
        pygame.mixer.music.load(music + mfile)
        state = 'PLAYING'
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy() or state == 'PAUSED':
            while True:
                if SB.ROWS == 4:
                    sb.lcd_write(mfile + ' '*(SB.COLS - len(mfile)), 1)
                    sb.lcd_write('     ' + state + ' '*(SB.COLS - (5 + len(state))), 2)
                sb.lcd_write('Pause/Play' + ' '*(SB.COLS - 14) + 'Stop', SB.ROWS - 1)
                sb.update()
                if SB.TAP in sb.buttons():
                    if sb.button('left') == SB.TAP:
                        if state == 'PLAYING':
                            state = 'PAUSED'
                            pygame.mixer.music.pause()
                        elif state == 'STOPPED':
                            state = 'PLAYING'
                            pygame.mixer.music.play()
                        elif state == 'PAUSED':
                            state = 'PLAYING'
                            pygame.mixer.music.unpause()
                    elif sb.button('right') == SB.TAP \
                            and (state == 'PAUSED' or state == 'PLAYING'):
                        state = 'STOPPED'
                        pygame.mixer.music.stop()
                        break

# when stopped, song selection by L & R buttons, long press L for menu, long press R for select

sb = SB.StompBox()
sb.lcd_clear()
sb.lcd_write('Squishplayer v%s' % SQUISHPLAYER_VERSION, 0)

# Load list of available music files

music = '/home/pi/Music/'
files = []

for a in ['wav', 'mp3', 'ogg']:
    files.extend(os.path.basename(x) for x in glob.glob(music + '*.' + a))
files.sort()

scnt = len(files)
sno = 0;

# Load list of available playlists

playlists = '/home/pi/Music/playlists/'
lists = []

lists.extend(os.path.basename(x) for x in glob.glob(playlists + '*.list'))
lists.sort()

plcnt = len(lists)
plno = 0;

song_mode = True;

# update LCD
while True:
    sb.lcd_clear()
    i = 0
    if song_mode:
        if scnt == 0:
            sb.lcd_write('    NO SONGS', i)
        else:
            while i < (SB.ROWS - 1) and (sno + i) < scnt:
                fname = files[sno + i]
                sb.lcd_write(fname[0:SB.COLS], i)
                i = i + 1
    else:
        if plcnt == 0:
            sb.lcd_write('  NO PLAYLISTS', i)
        else:
            while i < (SB.ROWS - 1) and (plno + i) < plcnt:
                lname = lists[plno + i]
                sb.lcd_write(lname[0:SB.COLS], i)
                i = i + 1
    if SB.COLS == 20:
        sb.lcd_write('<-/ Menu (L) Sel /->', SB.ROWS - 1)
    else:
        sb.lcd_write('<-/Menu(L)Sel/->', SB.ROWS - 1)

    # input loop
    while True:
        sb.update()

        # patch/preset switching
        if SB.TAP in sb.buttons():
            if sb.button('right') == SB.TAP:
                if song_mode and scnt > 0:
                    sno = (sno + 1) % scnt
                elif plcnt > 0:
                    plno = (plno + 1) % plcnt
            elif sb.button('left') == SB.TAP:
                if song_mode and scnt > 0:
                    sno = (sno - 1) % scnt
                elif plcnt > 0:
                    plno = (plno - 1) % plcnt
            break

        # right button menu
        if sb.button('right') == SB.HOLD and (scnt > 0 or plcnt > 0):
            if song_mode:
                if plcnt > 0:
                    opts = ['Play Song', 'List Mode']
                else:
                    opts = ['Play Song']
                k = sb.choose_opt(opts, row=1, passlong=True)
                if k == 0:      # play the current song
                    playsong(sno)
                elif k == 1:    # select playlist mode
                    song_mode = False;
            else:
                k = sb.choose_opt(['Play List', 'Song Mode'], row=1, passlong=True)
                if k == 0:    # play the current playlist
                    playlist(plno)
                elif k == 1:    # select song mode
                    song_mode = True;
            break

        # left button menu - system-related tasks
        if sb.button('left') == SB.HOLD:
            sb.lcd_write('Options:        ', 0)
            k = sb.choose_opt(['Power Down', 'Add From USB'], row=1, passlong=True)

            if k == 0: # power down
                sb.lcd_clear()
                sb.lcd_write('Shutting down...', 0)
                sb.lcd_write('Wait 30s, unplug', 1)
                subprocess.run('sudo shutdown -h now'.split())

            elif k == 1: # add music files from a flash drive
                sb.lcd_clear()
                sb.lcd_write('looking for USB ', row=0)
                b = subprocess.check_output('sudo blkid'.split())
                x = re.findall('/dev/sd[a-z]\d*', b.decode('ascii'))
                if not x:
                    sb.lcd_write('USB not found!  ', row=1)
                    sb.waitforrelease(1)
                    break
                sb.lcd_write('copying files.. ', row=1)
                try:
                    if not os.path.exists('/mnt/usbdrv/'):
                        subprocess.run(['sudo', 'mkdir', '/mnt/usbdrv/'])
                    for usb in x:
                        subprocess.run(['sudo', 'mount', usb, '/mnt/usbdrv/'], timeout=30)
                        for a in ['wav', 'mp3', 'ogg']:
                            for mf in glob.glob(os.path.join('/mnt/usbdrv', '**', '*.' + a), recursive=True):
                                mfbase = os.path.basename(mf)
                                m1 = mfbase.replace(' ', '_')
                                mfbase = m1.replace("'", '_')
                                dest = os.path.join(music, mfbase)
                                if not os.path.exists(os.path.dirname(dest)):
                                    os.makedirs(os.path.dirname(dest))
                                subprocess.run(['sudo', 'cp', '-f', mf, dest], timeout=30)
                        for plf in glob.glob(os.path.join('/mnt/usbdrv', '**', '*.list'), recursive=True):
                            plfbase = os.path.basename(plf)
                            pl1 = plfbase.replace(' ', '_')
                            plfbase = pl1.replace("'", '_')
                            dest = os.path.join(playlists, plfbase)
                            if not os.path.exists(os.path.dirname(dest)):
                                os.makedirs(os.path.dirname(dest))
                            subprocess.run(['sudo', 'cp', '-f', plf, dest], timeout=30)
                        subprocess.run(['sudo', 'umount', usb], timeout=30)
                except Exception as e:
                    sb.lcd_write('halted - errors:', 0)
                    sb.lcd_write(str(e).replace('\n', ' '), 1)
                    while not sb.waitfortap(10):
                        pass
                sb.lcd_write('copying files..' + ' '*(SB.COLS - 1) + 'done!' + ' '*(SB.COLS - 5))
                sb.waitforrelease(1)
                files = []
                for a in ['wav', 'mp3', 'ogg']:
                    files.extend(os.path.basename(x) for x in glob.glob(music + '*.' + a))
                files.sort()
                scnt = len(files)
                sno = 0;

            break
