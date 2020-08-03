#!/usr/bin/python3
"""
Copyright (c) 2020 Bill Peterson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

"""
Description: an implementation of patcher.py for a Raspberry Pi in a stompbox
"""
import sys, os, re, glob, subprocess
import patcher
from utils import netlink, stompboxpi as SB


def list_midiports():
    midiports = {}
    x = subprocess.check_output(['aconnect', '-o']).decode()
    for port, client in re.findall(" (\d+): '([^\n]*)'", x):
        if client == 'System': continue
        if client == 'Midi Through': continue
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
        sb.lcd_write("no banks found! ", 1)
        sb.waitforrelease(2)
        return False
    sb.lcd_write("Load Bank:      ", row=0)
    i = sb.choose_opt(banks, row=1, timeout=0)
    if i < 0: return False
    sb.lcd_write("loading patches ", 1)
    try:
        pxr.load_bank(banks[i])
    except patcher.PatcherError:
        sb.lcd_write("bank load error!", 1)
        sb.waitforrelease(2)
        return False
    pxr.write_config()
    sb.waitforrelease(1)
    return True



sb = SB.StompBox()
sb.lcd_clear()
sb.lcd_write("Squishbox v3.2", 0)

# start the patcher
if len(sys.argv) > 1:
    cfgfile = sys.argv[1]
else:
    cfgfile = '/home/pi/SquishBox/squishboxconf.yaml'
try:
    pxr = patcher.Patcher(cfgfile)
except patcher.PatcherError:
    sb.lcd_write("bad config file!", 1)
    sys.exit("bad config file")

# hack to connect MIDI devices to old versions of fluidsynth
midiports = list_midiports()
for client in midiports:
    if client == 'FLUID Synth': continue
    subprocess.run(['aconnect', midiports[client], midiports['FLUID Synth']])
        
# initialize network link
port = pxr.cfg.get('remotelink_port', netlink.DEFAULT_PORT)
passkey = pxr.cfg.get('remotelink_passkey', netlink.DEFAULT_PASSKEY)
remote_link = netlink.Server(port, passkey)

# load bank
sb.lcd_write("loading patches ", 1)
try:
    pxr.load_bank(pxr.cfg['currentbank'])
except patcher.PatcherError:
    while True:
        sb.lcd_write("bank load error!", 1)
        sb.waitfortap(10)
        if load_bank_menu():
            break
pno = 0
pxr.select_patch(pno)
networks = []


# update LCD
while True:
    sb.lcd_clear()
    if pxr.sfpresets:
        ptot = len(pxr.sfpresets)
        p = pxr.sfpresets[pno]
        sb.lcd_write(p.name, 0)
        sb.lcd_write("%16s" % ("preset %03d:%03d" % (p.bank, p.prog)), 1)
    else:
        ptot = pxr.patches_count()
        patchname = pxr.patch_name(pno)
        sb.lcd_write(patchname, 0)
        sb.lcd_write("%16s" % ("patch: %d/%d" % (pno + 1, ptot)), 1)

    # input loop
    while True:
        sb.update()
        pxr.poll_cc()

        # patch/preset switching
        if SB.STATE_TAP in sb.state.values():
            if sb.state[SB.BTN_R] == SB.STATE_TAP:
                pno = (pno + 1) % ptot
            elif sb.state[SB.BTN_L] == SB.STATE_TAP:
                pno = (pno - 1) % ptot
            if pxr.sfpresets:
                pxr.select_sfpreset(pno)
            else:
                pxr.select_patch(pno)
            break

        # right button menu
        if sb.state[SB.BTN_R] == SB.STATE_HOLD:
            k = sb.choose_opt(['Save Patch', 'Delete Patch', 'Load Bank', 'Save Bank', 'Load Soundfont', 'Effects..'], row=1, passlong=True)
            
            if k == 0: # save the current patch or save preset to a patch
                sb.lcd_write("Save patch:     ", 0)
                if pxr.sfpresets:
                    newname = sb.char_input(pxr.sfpresets[pno].name)
                    if newname == '': break
                    pxr.add_patch(newname)
                    pxr.update_patch(newname)
                else:
                    newname = sb.char_input(patchname)
                    if newname == '': break
                    if newname != patchname:
                        pxr.add_patch(newname, addlike=patchname)
                    pxr.update_patch(newname)
                pno = pxr.patch_index(newname)
                pxr.select_patch(pno)
                
            elif k == 1: # delete patch if it's not last one or a preset; ask confirm
                if pxr.sfpresets or ptot < 2:
                    sb.lcd_write("cannot delete   ", 1)
                    sb.waitforrelease(1)
                    break
                j = sb.choose_opt(['confirm delete?', 'cancel'], row=1)
                if j == 0:
                    pxr.delete_patch(patchname)
                    pno = min(pno, (ptot - 2))
                    pxr.select_patch(pno)
                    
            elif k == 2: # load bank
                if not load_bank_menu(): break
                pno = 0
                pxr.select_patch(pno)
                pxr.write_config()
                
            elif k == 3: # save bank, prompt for name
                if pxr.sfpresets:
                    sb.lcd_write("cannot save     ", 1)
                    sb.waitforrelease(1)
                    break
                sb.lcd_write("Save bank:      ", 0)
                bankfile = sb.char_input(pxr.cfg['currentbank'])
                if bankfile == '': break
                try:
                    pxr.save_bank(bankfile)
                except patcher.PatcherError:
                    sb.lcd_write("bank save error!", 1)
                    sb.waitforrelease(2)
                    break
                pxr.write_config()
                sb.lcd_write("bank saved.     ", 1)
                sb.waitforrelease(1)
                
            elif k == 4: # load soundfont
                sf = list_soundfonts()
                if not sf:
                    sb.lcd_write("no soundfonts!  ", 1)
                    sb.waitforrelease(2)
                    break
                sb.lcd_write("Load Soundfont: ", row=0)
                s = sb.choose_opt(sf, row=1, timeout=0)
                if s < 0: break
                sb.lcd_write("loading...      ", row=1)
                pxr.load_soundfont(sf[s])
                sb.waitforrelease(1)
                pno = 0
                pxr.select_sfpreset(pno)
                
            elif k == 5: # effects menu
                sb.lcd_write("Effects:        ", row=0)
                j = sb.choose_opt(['Reverb', 'Chorus', 'Gain'], 1)
                if j == 0:
                    while True:
                        sb.lcd_write("Reverb:         ", row=0)
                        i = sb.choose_opt(['Reverb Size', 'Reverb Damping','Reverb Width','Reverb Level'], 1)
                        if i < 0: break
                        if i == 0:
                            sb.lcd_write("Size (0-1):     ", row=0)
                            curval = pxr.fluid_get('synth.reverb.room-size')
                            newval = sb.choose_val(curval, 0.1, 0.0, 1.0, '%16.1f')
                            pxr.fluid_set('synth.reverb.room-size', newval, True)
                        if i == 1:
                            sb.lcd_write("Damping (0-1):  ", row=0)
                            curval = pxr.fluid_get('synth.reverb.damp')
                            newval = sb.choose_val(curval, 0.1, 0.0, 1.0, '%16.1f')
                            pxr.fluid_set('synth.reverb.damp', newval, True)
                        if i == 2:
                            sb.lcd_write("Width (0-100):  ", row=0)
                            curval = pxr.fluid_get('synth.reverb.width')
                            newval = sb.choose_val(curval, 1.0, 0.0, 100.0, '%16.1f')
                            pxr.fluid_set('synth.reverb.width', newval, True)
                        if i == 3:
                            sb.lcd_write("Level (0-1):    ", row=0)
                            curval = pxr.fluid_get('synth.reverb.level')
                            newval = sb.choose_val(curval, 0.01, 0.00, 1.00, '%16.2f')
                            pxr.fluid_set('synth.reverb.level', newval, True)
                elif j == 1:
                    while True:
                        sb.lcd_write("Chorus:         ", row=0)
                        i = sb.choose_opt(['Chorus Voices', 'Chorus Level', 'Chorus Speed', 'Chorus Depth'], 1)
                        if i < 0: break
                        
                        if i == 0:
                            sb.lcd_write("Voices (0-99):  ", row=0)
                            curval = pxr.fluid_get('synth.chorus.nr')
                            newval = sb.choose_val(curval, 1, 0, 99,'%16d')
                            pxr.fluid_set('synth.chorus.nr', newval, True)
                        if i == 1:
                            sb.lcd_write("Level (0-10):   ", row=0)
                            curval = pxr.fluid_get('synth.chorus.level')
                            newval = sb.choose_val(curval, 0.1, 0.0, 10.0, '%16.1f')
                            pxr.fluid_set('synth.chorus.level', newval, True)
                        if i == 2:
                            sb.lcd_write("Speed (0.1-21): ", row=0)
                            curval = pxr.fluid_get('synth.chorus.level')
                            newval = sb.choose_val(curval, 0.1, 0.1, 21.0, '%16.1f')
                            pxr.fluid_set('synth.chorus.level', newval, True)
                        if i == 3:
                            sb.lcd_write("Depth (0.3-5):  ", row=0)
                            curval = pxr.fluid_get('synth.chorus.depth')
                            newval = sb.choose_val(curval, 0.1, 0.3, 5.0, '%16.1f')
                            pxr.fluid_set('synth.chorus.depth', newval, True)
                elif j == 2:
                    sb.lcd_write("Gain (0-1):     ", row=0)
                    curval = pxr.fluid_get('synth.gain')
                    newval = sb.choose_val(curval, 0.1, 0.0, 5.0, "%16.2f")
                    pxr.fluid_set('synth.gain', newval, True)
            break

            
        # left button menu - system-related tasks
        if sb.state[SB.BTN_L] == SB.STATE_HOLD:
            sb.lcd_write("Options:        ", 0)
            k = sb.choose_opt(['Power Down', 'MIDI Devices', 'Wifi Settings', 'Add From USB'], row=1, passlong=True)
            
            if k == 0: # power down
                sb.lcd_write("Shutting down...", 0)
                sb.lcd_write("Wait 30s, unplug", 1)
                subprocess.run('sudo shutdown -h now'.split())
                
            elif k == 1: # reconnect midi devices
                ports = list_midiports()
                clients = list(ports.keys())
                clients.remove('FLUID Synth')
                sb.lcd_write("MIDI Devices:   ", 0)
                if clients == []:
                    sb.lcd_write("no devices found", 1)
                    sb.waitforrelease(2)
                m = sb.choose_opt(clients, row=1, timeout=0)
                subprocess.run(['aconnect', ports[clients[m]], ports['FLUID Synth']])
                sb.waitforrelease(0)
                
            elif k == 2: # wifi settings
                ssid = subprocess.check_output(['iwgetid', 'wlan0', '--raw']).strip().decode('ascii')
                ip = re.sub(b'\s.*', b'', subprocess.check_output(['hostname', '-I'])).decode('ascii')
                sb.lcd_clear()
                if ssid == "":
                    sb.lcd_write("Not connected", 0)
                else:
                    sb.lcd_write(ssid, 0)
                    sb.lcd_write("%-16s" % ip, 1)
                if not sb.waitfortap(10): break
                sb.lcd_write("Add Network:    ", 0)
                while True:
                    j = sb.choose_opt(networks + ['Rescan..'], 1, timeout=0)
                    if j < 0: break
                    if j == len(networks):
                        sb.lcd_write("scanning..      ", 1)
                        x = subprocess.check_output('sudo iwlist wlan0 scan'.split(), timeout=20).decode()
                        networks = re.findall('ESSID:"([^\n]*)"', x)
                    else:
                        sb.lcd_write("Password:", 0)
                        newpsk = sb.char_input()
                        if newpsk == '': break
                        sb.lcd_clear()
                        sb.lcd_write(networks[j], 0)
                        sb.lcd_write("adding network..", 1)
                        f = open('/etc/wpa_supplicant/wpa_supplicant.conf', 'a')
                        f.write('network={\n  ssid="%s"\n  psk="%s"\n}\n' % (networks[j], newpsk))
                        f.close()
                        subprocess.run('sudo service networking restart'.split())
                        break
                break
                
            elif k == 3: # add soundfonts from a flash drive
                sb.lcd_clear()
                sb.lcd_write("looking for USB ", row=0)
                b = subprocess.check_output('sudo blkid'.split())
                x = re.findall('/dev/sd[a-z]\d*', b.decode('ascii'))
                if not x:
                    sb.lcd_write("USB not found!  ", row=1)
                    sb.waitforrelease(1)
                    break
                sb.lcd_write("copying files.. ", row=1)
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
                    sb.lcd_write("halted - errors:", 0)
                    sb.lcd_write(str(e).replace('\n', ' '), 1)
                    while not sb.waitfortap(10):
                        pass
                sb.lcd_write("copying files.. done!           ")
                sb.waitforrelease(1)
            break

        # long-hold right button = refresh bank
        if sb.state[SB.BTN_R] == SB.STATE_LONG:
            sb.lcd_clear()
            sb.lcd_blink("Refreshing Bank ", row=0)
            lastpatch = pxr.patch_name(pno)
            pxr.load_bank(pxr.cfg['currentbank'])
            try:
                pno = pxr.patch_index(lastpatch)
            except patcher.PatcherError:
                if pno >= pxr.patches_count():
                    pno = 0
            pxr.select_patch(pno)
            sb.waitforrelease(1)
            break

        # long-hold left button = panic
        if sb.state[SB.BTN_L] == SB.STATE_LONG:
            sb.lcd_clear()
            sb.lcd_blink("Panic Restart   ", row=0)
            sb.waitforrelease(1)
            sys.exit(1)

        # check remote link for requests
        if remote_link.pending():
            req = remote_link.requests.pop(0)
            
            if req.type == netlink.SEND_STATE:
                state = patcher.write_yaml(pxr.bank, pxr.patch_name(), pxr.cfg['currentbank'])
                remote_link.reply(req, state)

            elif req.type == netlink.RECV_BANK:
                try:
                    pxr.load_bank(req.body)
                except patcher.PatcherError as e:
                    remote_link.reply(req, str(e), netlink.REQ_ERROR)
                else:
                    remote_link.reply(req, ','.join(pxr.patch_name()))
                    pno = 0
                    pxr.select_patch(pno)
                    break
                    
            elif req.type == netlink.LIST_BANKS:
                banks = list_banks()
                if not banks:
                    remote_link.reply(req, "no banks found!", netlink.REQ_ERROR)
                else:
                    remote_link.reply(req, ','.join(banks))
                
            elif req.type == netlink.LOAD_BANK:
                try:
                    sb.lcd_write(req.body, 0)
                    sb.lcd_write("loading patches ", 1)
                    pxr.load_bank(req.body)
                except patcher.PatcherError as e:
                    remote_link.reply(req, str(e), netlink.REQ_ERROR)
                    sb.lcd_write("bank load error!", 1)
                    sb.waitforrelease(2)
                else:
                    state = patcher.write_yaml(pxr.bank, pxr.patch_name())
                    remote_link.reply(req, state)
                    pno = 0
                    pxr.select_patch(pno)
                    break
                    
            elif req.type == netlink.SAVE_BANK:
                bfile, rawbank = patcher.read_yaml(req.body)
                try:
                    pxr.save_bank(bfile, rawbank)
                except patcher.PatcherError as e:
                    remote_link.reply(req, str(e), netlink.REQ_ERROR)
                else:
                    remote_link.reply(req)
                            
            elif req.type == netlink.SELECT_PATCH:
                try:
                    warn = pxr.select_patch(int(req.body))
                except patcher.PatcherError as e:
                    warn = str(e)
                if warn:
                    remote_link.reply(req, warn, netlink.REQ_ERROR)
                else:
                    remote_link.reply(req)
                    pno = int(req.body)
                    break
                    
            elif req.type == netlink.LIST_SOUNDFONTS:
                sf = list_soundfonts()
                if not sf:
                    remote_link.reply(req, "no soundfonts!", netlink.REQ_ERROR)
                else:
                    remote_link.reply(req, ','.join(sf))
            
            elif req.type == netlink.LOAD_SOUNDFONT:
                sb.lcd_write(req.body, 0)
                sb.lcd_write("loading...      ", 1)
                pxr.load_soundfont(req.body)
                remote_link.reply(req, patcher.write_yaml(pxr.sfpresets))
                pno = 0
                pxr.select_sfpreset(pno)
                break
            
            elif req.type == netlink.SELECT_SFPRESET:
                remote_link.reply(req)
                pno = int(req.body)
                pxr.select_sfpreset(pno)
                break

            elif req.type == netlink.LIST_PLUGINS:
                info = subprocess.check_output(['listplugins']).decode()
                remote_link.reply(req, info)

            elif req.type == netlink.LIST_PORTS:
                info = '\n'.join(list_midiports().keys())
                remote_link.reply(req, info)
