#!/usr/bin/env python3
"""
Description: an implementation of patcher.py for a Raspberry Pi in a stompbox
plus a music file and playlist player
"""
import sys, os, re, glob, subprocess
import patcher
import pygame
from utils import netlink, stompboxpi as SB


SQUISHMASTER_VERSION = '0.2'

################################## Softsynth ##################################

def scan_midiports():
    midiports = {}
    x = subprocess.check_output(['aconnect', '-o']).decode()
    for port, client in re.findall(" (\d+): '([^\n]*)'", x):
        if client == 'System':
            continue
        if client == 'Midi Through':
            continue
        if 'FLUID Synth' in client:
            midiports['FLUID Synth'] = port
        else:
            midiports[client] = port
    return midiports

def list_banks():
    bpaths = sorted(glob.glob(os.path.join(pxr.bankdir, '**', '*.yaml'), recursive=True), key=str.lower)
    return [os.path.relpath(x, start=pxr.bankdir) for x in bpaths]

def list_soundfonts():
    sfpaths = sorted(glob.glob(os.path.join(pxr.sfdir, '**', '*.sf2'), recursive=True), key=str.lower)
    return [os.path.relpath(x, start=pxr.sfdir) for x in sfpaths]

def load_bank_menu():
    banks = list_banks()
    if not banks:
        sb.lcd_write('no banks found!', 1)
        sb.waitforrelease(2)
        return False
    sb.lcd_write('Load Bank:', row=0)
    i = sb.choose_opt(banks, row=1, timeout=0)
    if i < 0:
        return False
    sb.lcd_write('loading patches', 1)
    try:
        pxr.load_bank(banks[i])
    except patcher.PatcherError:
        sb.lcd_write('bank load error!', 1)
        sb.waitforrelease(2)
        return False
    pxr.write_config()
    sb.waitforrelease(1)
    return True

def squishpatch():

    global pxr

# initialise the patcher
    if len(sys.argv) > 1:
        cfgfile = sys.argv[1]
    else:
        cfgfile = '/home/pi/SquishBox/squishboxconf.yaml'
    try:
        pxr = patcher.Patcher(cfgfile)
    except patcher.PatcherError:
        sb.lcd_write('bad config file!', 1)
        sys.exit('bad config file')

# hack to connect MIDI devices to old versions of fluidsynth
    midiports = scan_midiports()
    for client in midiports:
        if client == 'FLUID Synth':
            continue
        subprocess.run(['aconnect', midiports[client], midiports['FLUID Synth']])

# load bank
    sb.lcd_write('loading patches', 1)
    try:
        pxr.load_bank(pxr.currentbank)
    except patcher.PatcherError:
        while True:
            sb.lcd_write('bank load error!', 1)
            sb.waitfortap(10)
            if load_bank_menu():
                break

# initialize network link
    if pxr.cfg.get('remotelink_active', 0):
        port = pxr.cfg.get('remotelink_port', netlink.DEFAULT_PORT)
        passkey = pxr.cfg.get('remotelink_passkey', netlink.DEFAULT_PASSKEY)
        remote_link = netlink.Server(port, passkey)
    else:
        remote_link = None

    pno = 0
    warn = pxr.select_patch(pno)
    networks = []

    fxmenu_info = (
    ('Reverb Size', 'synth.reverb.room-size', '%4.1f', 0.1, 0.0, 1.0),
    ('Reverb Damp', 'synth.reverb.damp', '%4.1f', 0.1, 0.0, 1.0),
    ('Rev. Width', 'synth.reverb.width', '%5.1f', 1.0, 0.0, 100.0),
    ('Rev. Level', 'synth.reverb.level', '%5.2f', 0.01, 0.00, 1.00),
    ('Chorus Voices', 'synth.chorus.nr', '%2d', 1, 0, 99),
    ('Chor. Level', 'synth.chorus.level', '%4.1f', 0.1, 0.0, 10.0),
    ('Chor. Speed', 'synth.chorus.speed', '%4.1f', 0.1, 0.1, 21.0),
    ('Chorus Depth', 'synth.chorus.depth', '%3.1f', 0.1, 0.3, 5.0),
    ('Gain', 'synth.gain', '%11.1f', 0.1, 0.0, 5.0)
    )

    # update LCD
    while True:
        sb.lcd_clear()
        if pxr.sfpresets:
            ptot = len(pxr.sfpresets)
            p = pxr.sfpresets[pno]
            sb.lcd_write(p.name, 0)
            sb.lcd_write(SB.LINESTR % ('preset %03d:%03d' % (p.bank, p.prog)), 1)
        else:
            ptot = pxr.patches_count()
            patchname = pxr.patch_name(pno)
            sb.lcd_write(patchname, 0)
            sb.lcd_write(SB.LINESTR % ('patch: %d/%d' % (pno + 1, ptot)), 1)
        if warn:
            sb.lcd_write(';'.join(warn), 1)

        # input loop
        while True:
            if SB.ROWS == 4:
                if SB.COLS == 20:
                    sb.lcd_write('Prev            Next', 2)
                    sb.lcd_write('Sys----Long-----Menu', 3)
                else:
                    sb.lcd_write('Prev        Next', 2)
                    sb.lcd_write('Sys--Long---Menu', 3)

            sb.update()
            pxr.poll_cc()

            # patch/preset switching
            if SB.TAP in sb.buttons():
                if warn:
                    warn = []
                    break
                if sb.button('right') == SB.TAP:
                    pno = (pno + 1) % ptot
                elif sb.button('left') == SB.TAP:
                    pno = (pno - 1) % ptot
                if pxr.sfpresets:
                    warn = pxr.select_sfpreset(pno)
                else:
                    warn = pxr.select_patch(pno)
                break

            # right button menu
            if sb.button('right') == SB.HOLD:
                k = sb.choose_opt(['Save Patch', 'Delete Patch', 'Load Bank', 'Save Bank', 'Load Soundfont', 'Effects..'], row=1, passlong=True)

                if k == 0: # save the current patch or save preset to a patch
                    sb.lcd_write('Save patch:', 0)
                    if pxr.sfpresets:
                        newname = sb.char_input(pxr.sfpresets[pno].name)
                        if newname == '':
                            break
                        pxr.add_patch(newname)
                        pxr.update_patch(newname)
                    else:
                        newname = sb.char_input(patchname)
                        if newname == '':
                            break
                        if newname != patchname:
                            pxr.add_patch(newname, addlike=patchname)
                        pxr.update_patch(newname)
                    pno = pxr.patch_index(newname)
                    warn = pxr.select_patch(pno)

                elif k == 1: # delete patch if it's not last one or a preset; ask confirm
                    if pxr.sfpresets or ptot < 2:
                        sb.lcd_write('cannot delete', 1)
                        sb.waitforrelease(1)
                        break
                    j = sb.choose_opt(['confirm delete?', 'cancel'], row=1)
                    if j == 0:
                        pxr.delete_patch(patchname)
                        pno = min(pno, (ptot - 2))
                        warn = pxr.select_patch(pno)

                elif k == 2: # load bank
                    if not load_bank_menu():
                        break
                    pno = 0
                    warn = pxr.select_patch(pno)
                    pxr.write_config()

                elif k == 3: # save bank, prompt for name
                    if pxr.sfpresets:
                        sb.lcd_write('cannot save', 1)
                        sb.waitforrelease(1)
                        break
                    sb.lcd_write('Save bank:', 0)
                    bankfile = sb.char_input(pxr.currentbank)
                    if bankfile == '':
                        break
                    try:
                        pxr.save_bank(bankfile)
                    except patcher.PatcherError:
                        sb.lcd_write('bank save error!', 1)
                        sb.waitforrelease(2)
                        break
                    pxr.write_config()
                    sb.lcd_write('bank saved.', 1)
                    sb.waitforrelease(1)

                elif k == 4: # load soundfont
                    sf = list_soundfonts()
                    if not sf:
                        sb.lcd_write('no soundfonts!', 1)
                        sb.waitforrelease(2)
                        break
                    sb.lcd_write('Load Soundfont:', row=0)
                    s = sb.choose_opt(sf, row=1, timeout=0)
                    if s < 0:
                        break
                    sb.lcd_write('loading...', row=1)
                    if not pxr.load_soundfont(sf[s]):
                        sb.lcd_write('unable to load! ', 1)
                    sb.waitforrelease(2)
                    pno = 0
                    warn = pxr.select_sfpreset(pno)

                elif k == 5: # effects menu
                    i=0
                    while True:
                        fxopts = []
                        args = []
                        for name, opt, fmt, inc, min, max in fxmenu_info[i:] + fxmenu_info[0:i]:
                            curval = pxr.fluid_get(opt)
                            fxopts.append('%s:%s' % (name, fmt % curval))
                            args.append((curval, inc, min, max, fmt, opt))
                        sb.lcd_write('Effects:', row=0)
                        j = sb.choose_opt(fxopts, row=1)
                        if j < 0:
                            break
                        sb.lcd_write(fxopts[j], row=0)
                        newval = sb.choose_val(*args[j][0:5])
                        if sb.choose_opt(['set?%12s' % (args[j][4] % newval)], row=1) > -1:
                            pxr.fluid_set(args[j][5], newval, updatebank=True, patch=pno)
                        i = (i + j) % len(fxmenu_info)
                break


            # left button menu - system-related tasks
            if sb.button('left') == SB.HOLD:
                sb.lcd_write('Options:', 0)
                k = sb.choose_opt(['MIDI Devices', 'Wifi Settings', 'Add From USB', 'Exit', 'Power Down'], row=1, passlong=True)

                if k == 0: # reconnect midi devices
                    ports = scan_midiports()
                    clients = list(ports.keys())
                    clients.remove('FLUID Synth')
                    sb.lcd_write('MIDI Devices:', 0)
                    if clients == []:
                        sb.lcd_write('no devices found', 1)
                        sb.waitforrelease(2)
                    m = sb.choose_opt(clients, row=1, timeout=0)
                    subprocess.run(['aconnect', ports[clients[m]], ports['FLUID Synth']])
                    sb.waitforrelease(0)

                elif k == 1: # wifi settings
                    ssid = subprocess.check_output(['iwgetid', 'wlan0', '--raw']).strip().decode('ascii')
                    ip = re.sub(b'\s.*', b'', subprocess.check_output(['hostname', '-I'])).decode('ascii')
                    sb.lcd_clear()
                    if ssid == '':
                        sb.lcd_write('Not connected', 0)
                    else:
                        sb.lcd_write(ssid, 0)
                        sb.lcd_write(SB.LINESTR % ip, 1)
                    if not sb.waitfortap(10):
                        break
                    sb.lcd_write('Connections:', 0)
                    while True:
                        if remote_link:
                            opts = networks + ['Rescan...', 'Block RemoteLink']
                        else:
                            opts = networks + ['Rescan...', 'Allow RemoteLink']
                        j = sb.choose_opt(opts, 1, timeout=0)
                        if j < 0:
                            break
                        if j == len(opts) - 1:
                            if remote_link:
                                remote_link = None
                                pxr.cfg['remotelink_active'] = 0
                            else:
                                port = pxr.cfg.get('remotelink_port', netlink.DEFAULT_PORT)
                                passkey = pxr.cfg.get('remotelink_passkey', netlink.DEFAULT_PASSKEY)
                                remote_link = netlink.Server(port, passkey)
                                pxr.cfg['remotelink_active'] = 1
                            pxr.write_config()
                            break
                        if j == len(opts) - 2:
                            sb.lcd_write('scanning..', 1)
                            x = subprocess.check_output('sudo iwlist wlan0 scan'.split(), timeout=20).decode()
                            networks = re.findall('ESSID:"([^\n]*)"', x)
                        else:
                            sb.lcd_write('Password:', 0)
                            newpsk = sb.char_input(charset = SB.PRNCHARS)
                            if newpsk == '':
                                break
                            sb.lcd_clear()
                            sb.lcd_write(networks[j], 0)
                            sb.lcd_write('adding network..', 1)
                            f = open('/etc/wpa_supplicant/wpa_supplicant.conf', 'a')
                            f.write('network={\n  ssid="%s"\n  psk="%s"\n}\n' % (networks[j], newpsk))
                            f.close()
                            subprocess.run('sudo service networking restart'.split())
                            break

                elif k == 2: # add soundfonts from a flash drive
                    sb.lcd_clear()
                    sb.lcd_write('looking for USB', row=0)
                    b = subprocess.check_output('sudo blkid'.split())
                    x = re.findall('/dev/sd[a-z]\d*', b.decode('ascii'))
                    if not x:
                        sb.lcd_write('USB not found!', row=1)
                        sb.waitforrelease(1)
                        break
                    sb.lcd_write('copying files..', row=1)
                    try:
                        if not os.path.exists('/mnt/usbdrv/'):
                            os.mkdir('/mnt/usbdrv')
                        for usb in x:
                            subprocess.run(['sudo', 'mount', usb, '/mnt/usbdrv/'], timeout=30)
                            for sf in glob.glob(os.path.join('/mnt/usbdrv', '**', '*.sf2'), recursive=True):
                                sfrel = os.path.relpath(sf, start='/mnt/usbdrv')
                                dest = os.path.join(pxr.sfdir, sfrel)
                                if not os.path.exists(os.path.dirname(dest)):
                                    os.makedirs(os.path.dirname(dest))
                                subprocess.run(['sudo', 'cp', '-f', sf, dest], timeout=30)
                            subprocess.run(['sudo', 'umount', usb], timeout=30)
                    except Exception as e:
                        sb.lcd_write('halted - errors:', 0)
                        sb.lcd_write(str(e).replace('\n', ' '), 1)
                        while not sb.waitfortap(10):
                            pass
                    sb.lcd_write('copying files.. done!')
                    sb.waitforrelease(1)

                elif k == 3: # exit player
                    sb.lcd_clear()
                    sb.lcd_write('Exiting', 0)
                    return

                elif k == 4: # power down
                    sb.lcd_write('Shutting down...', 0)
                    sb.lcd_write('Wait 30s, unplug', 1)
                    subprocess.run('sudo shutdown -h now'.split())

                break

            # long-hold right button = reload bank
            if sb.button('right') == SB.LONG:
                sb.lcd_clear()
                sb.lcd_blink('Reloading Bank  ', row=0)
                lastpatch = pxr.patch_name(pno)
                pxr.load_bank(pxr.currentbank)
                try:
                    pno = pxr.patch_index(lastpatch)
                except patcher.PatcherError:
                    if pno >= pxr.patches_count():
                        pno = 0
                warn = pxr.select_patch(pno)
                sb.waitforrelease(1)
                break

            # long-hold left button = panic
            if sb.button('left') == SB.LONG:
                sb.lcd_clear()
                sb.lcd_blink('Panic Restart   ', row=0)
                sb.waitforrelease(1)
                sys.exit(1)

            # check remote link for requests
            if remote_link and remote_link.pending():
                req = remote_link.requests.pop(0)

                if req.type == netlink.SEND_VERSION:
                    remote_link.reply(req, patcher.VERSION)

                elif req.type == netlink.RECV_BANK:
                    try:
                        pxr.load_bank(req.body)
                    except patcher.PatcherError as e:
                        remote_link.reply(req, str(e), netlink.REQ_ERROR)
                    else:
                        remote_link.reply(req, patcher.write_yaml(pxr.patch_names()))

                elif req.type == netlink.LIST_BANKS:
                    banks = list_banks()
                    if not banks:
                        remote_link.reply(req, 'no banks found!', netlink.REQ_ERROR)
                    else:
                        remote_link.reply(req, patcher.write_yaml(banks))

                elif req.type == netlink.LOAD_BANK:
                    sb.lcd_write(req.body, 0)
                    sb.lcd_write('loading patches', 1)
                    try:
                        if req.body == '':
                            rawbank = pxr.load_bank()
                        else:
                            rawbank = pxr.load_bank(req.body)
                    except patcher.PatcherError as e:
                        remote_link.reply(req, str(e), netlink.REQ_ERROR)
                        sb.lcd_write('bank load error!', 1)
                        sb.waitforrelease(2)
                    else:
                        info = patcher.write_yaml(pxr.currentbank, rawbank, pxr.patch_names())
                        remote_link.reply(req, info)
                        pxr.write_config()

                elif req.type == netlink.SAVE_BANK:
                    bfile, rawbank = patcher.read_yaml(req.body)
                    try:
                        pxr.save_bank(bfile, rawbank)
                    except patcher.PatcherError as e:
                        remote_link.reply(req, str(e), netlink.REQ_ERROR)
                    else:
                        remote_link.reply(req)
                        pxr.write_config()

                elif req.type == netlink.SELECT_PATCH:
                    try:
                        if req.body.isdecimal():
                            pno = int(req.body)
                        else:
                            pno = pxr.patch_index(req.body)
                        warn = pxr.select_patch(pno)
                    except patcher.PatcherError as e:
                        remote_link.reply(req, str(e), netlink.REQ_ERROR)
                    else:
                        remote_link.reply(req, warn)
                        break

                elif req.type == netlink.LIST_SOUNDFONTS:
                    sf = list_soundfonts()
                    if not sf:
                        remote_link.reply(req, 'no soundfonts!', netlink.REQ_ERROR)
                    else:
                        remote_link.reply(req, patcher.write_yaml(sf))

                elif req.type == netlink.LOAD_SOUNDFONT:
                    sb.lcd_write(req.body, 0)
                    sb.lcd_write('loading...', 1)
                    if not pxr.load_soundfont(req.body):
                        sb.lcd_write('unable to load!', 1)
                        remote_link.reply(req, 'Unable to load %s' % req.body, netlink.REQ_ERROR)
                    else:
                        remote_link.reply(req, patcher.write_yaml(pxr.sfpresets))

                elif req.type == netlink.SELECT_SFPRESET:
                    pno = int(req.body)
                    warn = pxr.select_sfpreset(pno)
                    remote_link.reply(req, warn)
                    break

                elif req.type == netlink.LIST_PLUGINS:
                    try:
                        info = subprocess.check_output(['listplugins']).decode()
                    except:
                        remote_link.reply(req, 'No plugins installed')
                    else:
                        remote_link.reply(req, patcher.write_yaml(info))

                elif req.type == netlink.LIST_PORTS:
                    ports = list(scan_midiports().keys())
                    remote_link.reply(req, patcher.write_yaml(ports))

                elif req.type == netlink.READ_CFG:
                    info = patcher.write_yaml(pxr.cfgfile, pxr.read_config())
                    remote_link.reply(req, info)

                elif req.type == netlink.SAVE_CFG:
                    try:
                        pxr.write_config(req.body)
                    except patcher.PatcherError as e:
                        remote_link.reply(req, str(e), netlink.REQ_ERROR)
                    else:
                        remote_link.reply(req)

############################## Sound File Player ##############################

# Play a song - allow pause, resume, & stop

def playsong(mfile):
    pygame.mixer.music.load(mfile)
    state = 'PLAYING'
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy() or state == 'PAUSED':
        while True:
            if SB.ROWS == 4:
                sb.lcd_write('     ' + state, 2)
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

def playlist(plfile, files, fnames):
    # open file and read into array, stripping newlines
    f = open(plfile, 'r')
    plist = [line.rstrip('\n') for line in f.readlines()]
    f.close()
    for mfile in plist:
        mfname = fnames[files.index(mfile)]
        if not os.path.exists(mfname):
            continue
        pygame.mixer.music.load(mfname)
        state = 'PLAYING'
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy() or state == 'PAUSED':
            while True:
                if SB.ROWS == 4:
                    sb.lcd_write(mfile, 1)
                    sb.lcd_write('     ' + state, 2)
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

                # long right button - exit from playlist
                if sb.button('right') == SB.HOLD:
                    pygame.mixer.music.stop()
                    return


def squishplayer():
    # when stopped, song selection by L & R buttons, long press L for menu, long press R for select
    # Load list of available music files

    music = '/home/pi/Music'
    files = []
    fnames = []

    for a in ['wav', 'mp3', 'ogg']:
        files.extend(os.path.basename(x) for x in glob.glob(music + '/*.' + a))
    files.sort()

    for a in files:
        fnames.append(music + '/' + a)

    scnt = len(files)
    sno = 0;

    # Load list of available playlists

    playlists = '/home/pi/Music/playlists'
    lists = []
    lnames = []

    lists.extend(os.path.basename(x) for x in glob.glob(playlists + '/*.list'))
    lists.sort()

    for a in lists:
        lnames.append(playlists + '/' + a)

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
                        playsong(fnames[sno])
                    elif k == 1:    # select playlist mode
                        song_mode = False;
                else:
                    k = sb.choose_opt(['Play List', 'Song Mode'], row=1, passlong=True)
                    if k == 0:      # play the current playlist
                        playlist(lnames[plno], files, fnames)
                    elif k == 1:    # select song mode
                        song_mode = True;
                break

            # left button menu - system-related tasks
            if sb.button('left') == SB.HOLD:
                sb.lcd_write('Options:', 0)
                k = sb.choose_opt(['Exit', 'Use USB', 'Add from USB', 'Power Down'], row=1, passlong=True)

                if k == 0: # exit and run Squishbox
                    sb.lcd_clear()
                    sb.lcd_write('Exiting', 0)
                    return

                elif k == 1: # use music files and playlists direct from a flash drive
                    sb.lcd_clear()
                    sb.lcd_write('looking for USB', row=0)
                    b = subprocess.check_output('sudo blkid'.split())
                    x = re.findall('/dev/sd[a-z]\d*', b.decode('ascii'))
                    if not x:
                        sb.lcd_write('USB not found!', row=1)
                        sb.waitforrelease(1)
                        break
                    sb.lcd_write('using files..', row=1)
                    try:
                        if not os.path.exists('/mnt/usbdrv/'):
                            subprocess.run(['sudo', 'mkdir', '/mnt/usbdrv/'])
                        for usb in x:
                            subprocess.run(['sudo', 'mount', usb, '/mnt/usbdrv/'], timeout=30)
                            for a in ['wav', 'mp3', 'ogg']:
                                for mf in glob.glob(os.path.join('/mnt/usbdrv', '**', '*.' + a), recursive=True):
                                    fnames.append(mf)
                                    mfbase = os.path.basename(mf)
                                    files.append(mfbase)
                            for plf in glob.glob(os.path.join('/mnt/usbdrv', '**', '*.list'), recursive=True):
                                lnames.append(plf)
                                plfbase = os.path.basename(plf)
                                lists.append(plfbase)
                    except Exception as e:
                        sb.lcd_write('halted - errors:', 0)
                        sb.lcd_write(str(e).replace('\n', ' '), 1)
                        while not sb.waitfortap(10):
                            pass
                    scnt = len(files)
                    sno = 0;
                    plcnt = len(lists)
                    plno = 0;

                elif k == 2: # add music files and playlists from a flash drive
                    sb.lcd_clear()
                    sb.lcd_write('looking for USB', row=0)
                    b = subprocess.check_output('sudo blkid'.split())
                    x = re.findall('/dev/sd[a-z]\d*', b.decode('ascii'))
                    if not x:
                        sb.lcd_write('USB not found!', row=1)
                        sb.waitforrelease(1)
                        break
                    sb.lcd_write('copying files..', row=1)
                    try:
                        if not os.path.exists('/mnt/usbdrv/'):
                            subprocess.run(['sudo', 'mkdir', '/mnt/usbdrv/'])
                        for usb in x:
                            subprocess.run(['sudo', 'mount', usb, '/mnt/usbdrv/'], timeout=30)
                            for a in ['wav', 'mp3', 'ogg']:
                                for mf in glob.glob(os.path.join('/mnt/usbdrv', '**', '*.' + a), recursive=True):
                                    mfbase = os.path.basename(mf)
                                    dest = os.path.join(music, mfbase)
                                    if not os.path.exists(os.path.dirname(dest)):
                                        os.makedirs(os.path.dirname(dest))
                                    subprocess.run(['sudo', 'cp', '-f', mf, dest], timeout=30)
                            for plf in glob.glob(os.path.join('/mnt/usbdrv', '**', '*.list'), recursive=True):
                                plfbase = os.path.basename(plf)
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
                    # refresh lists of music files & playlists
                    files = []
                    fnames = []
                    for a in ['wav', 'mp3', 'ogg']:
                        files.extend(os.path.basename(x) for x in glob.glob(music + '/*.' + a))
                    files.sort()
                    for a in files:
                        fnames.append(music + '/' + a)
                    scnt = len(files)
                    sno = 0;
                    lists = []
                    lnames = []
                    lists.extend(os.path.basename(x) for x in glob.glob(playlists + '/*.list'))
                    lists.sort()
                    for a in lists:
                        lnames.append(playlists + '/' + a)
                    plcnt = len(lists)
                    plno = 0;

                elif k == 3: # power down
                    sb.lcd_clear()
                    sb.lcd_write('Shutting down...', 0)
                    sb.lcd_write('Wait 30s, unplug', 1)
                    subprocess.run('sudo shutdown -h now'.split())

                break

################################### Control ###################################

sb = SB.StompBox()
sb.lcd_clear()
sb.lcd_write('SquishMaster v%s' % SQUISHMASTER_VERSION, 0)
pygame.init()

os.umask(0o002)

while True:
    sb.lcd_write('Options:', 0)
    k = sb.choose_opt(['Squishbox', 'Squishplayer', 'Power Down'], row=1, passlong=True)
    if k == 0: # run Squishbox
        sb.lcd_clear()
        squishpatch()

    elif k == 1: # run player
        sb.lcd_clear()
        squishplayer()

    elif k == 2: # power down
        sb.lcd_clear()
        sb.lcd_write('Shutting down...', 0)
        sb.lcd_write('Wait 30s, unplug', 1)
        subprocess.run('sudo shutdown -h now'.split())
