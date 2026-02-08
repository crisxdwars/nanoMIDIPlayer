import re
import subprocess
import os
import mido
import threading
import time
import glob

from pynput import keyboard as pynputKeyboard
from modules.functions import mainFunctions
from modules import configuration

pressedKeys = set()
heldKeys = {}
activeTransposedNotes = {}

log = mainFunctions.log

inPort = None
midiThread = None

# Detect if running Wayland or X11
def isWayland():
    """Check if running on Wayland"""
    return os.environ.get('WAYLAND_DISPLAY') is not None

def hasYdotool():
    """Check if ydotool is available"""
    try:
        subprocess.run(['which', 'ydotool'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def setupYdotoolSocket():
    """Setup ydotool socket environment variable"""
    # Check if already set
    if os.environ.get('YDOTOOL_SOCKET'):
        log(f"YDOTOOL_SOCKET already set to: {os.environ['YDOTOOL_SOCKET']}")
        return True
    
    # Try to find the socket
    socket_paths = [
        f"/run/user/{os.getuid()}/.ydotool_socket",
        "/run/user/1000/.ydotool_socket",
        "/tmp/.ydotool_socket",
    ]
    
    for socket_path in socket_paths:
        if os.path.exists(socket_path):
            os.environ['YDOTOOL_SOCKET'] = socket_path
            log(f"✓ Found and set ydotool socket: {socket_path}")
            return True
    
    log("⚠ WARNING: Could not find ydotool socket")
    return False

def isYdotooldRunning():
    """Check if ydotoold daemon is running"""
    try:
        result = subprocess.run(['pgrep', '-f', 'ydotoold'], capture_output=True, timeout=2)
        return result.returncode == 0
    except Exception as e:
        log(f"⚠ Error checking ydotoold: {e}")
        return False

def startYdotooldDaemon():
    """Start ydotoold daemon if not already running"""
    if isYdotooldRunning():
        log("✓ ydotoold daemon is already running")
        return True
    
    log("↳ Starting ydotoold daemon...")
    try:
        socket_path = os.environ.get('YDOTOOL_SOCKET', f"/run/user/{os.getuid()}/.ydotool_socket")
        
        # Start the daemon
        subprocess.Popen(['ydotoold', '--socket-path', socket_path], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL,
                        start_new_session=True)
        
        # Wait for daemon to start and socket to be created
        time.sleep(0.5)
        
        if isYdotooldRunning():
            log(f"✓ ydotoold daemon started successfully")
            return True
        else:
            log("✗ Failed to start ydotoold daemon")
            return False
    except Exception as e:
        log(f"✗ Error starting ydotoold: {e}")
        return False

USE_WAYLAND = isWayland() and hasYdotool()

if USE_WAYLAND:
    setupYdotoolSocket()
    startYdotooldDaemon()

def logKeys(action, key):
    if isinstance(key, pynputKeyboard.Key):
        keyName = key.name if key.name else str(key)
    else:
        keyName = str(key)
    if action == "press":
        pressedKeys.add(keyName)
    elif action == "release" and keyName in pressedKeys:
        pressedKeys.remove(keyName)
    if pressedKeys:
        log(f"{action}: {'+'.join(sorted(pressedKeys))}")
    else:
        log(f"{action}: {keyName}")

specialKeyMap = {
    "shift": pynputKeyboard.Key.shift,
    "ctrl": pynputKeyboard.Key.ctrl,
    "alt": pynputKeyboard.Key.alt,
    "space": pynputKeyboard.Key.space
}

# Wayland implementation using ydotool
if USE_WAYLAND:
    log("✓ Using ydotool for Wayland keyboard input")
    
    # Map keys to ydotool keycodes (USB HID usage codes)
    keyMap = {
        # Letter keys (left side)
        'a': 30, 'b': 48, 'c': 46, 'd': 32, 'e': 18, 'f': 33, 'g': 34, 'h': 35,
        'i': 23, 'j': 36, 'k': 37, 'l': 38, 'm': 50, 'n': 49, 'o': 24, 'p': 25,
        'q': 16, 'r': 19, 's': 31, 't': 20, 'u': 22, 'v': 47, 'w': 17, 'x': 45,
        'y': 21, 'z': 44,
        # Number keys
        '0': 11, '1': 2, '2': 3, '3': 4, '4': 5, '5': 6, '6': 7, '7': 8, '8': 9, '9': 10,
        # Special characters (for shift + number keys - handled by simulateKey with shift press)
        '!': 2, '@': 3, '#': 4, '$': 5, '%': 6, '^': 7, '&': 8, '*': 9, '(': 10, ')': 11,
        # Right side keys
        ';': 39, "'": 40, ',': 51, '.': 52, '/': 53,
        # Modifier keys
        'space': 57, 'shift': 42, 'ctrl': 29, 'alt': 56,
        # Uppercase letters (handled by shift in simulateKey, but map for completeness)
        'A': 30, 'B': 48, 'C': 46, 'D': 32, 'E': 18, 'F': 33, 'G': 34, 'H': 35,
        'I': 23, 'J': 36, 'K': 37, 'L': 38, 'M': 50, 'N': 49, 'O': 24, 'P': 25,
        'Q': 16, 'R': 19, 'S': 31, 'T': 20, 'U': 22, 'V': 47, 'W': 17, 'X': 45,
        'Y': 21, 'Z': 44
    }
    
    def ydotoolKeyDown(keycode):
        """Press a key using ydotool"""
        try:
            # Make sure to pass YDOTOOL_SOCKET in env
            env = os.environ.copy()
            if 'YDOTOOL_SOCKET' not in env:
                setupYdotoolSocket()
            
            # Try normal ydotool call first
            result = subprocess.run(['ydotool', 'key', f'{keycode}:1'], 
                                  capture_output=True, timeout=2, text=True, env=env)
            
            # If permission denied, try with sudo
            if "Permission denied" in result.stderr and result.returncode != 0:
                log(f"  ⚠ Permission denied, trying with sudo...")
                result = subprocess.run(['sudo', 'ydotool', 'key', f'{keycode}:1'], 
                                      capture_output=True, timeout=2, text=True, env=env)
            
            if result.returncode != 0:
                log(f"✗ ydotool press error for keycode {keycode}: {result.stderr}")
            else:
                log(f"✓ ydotool pressed key {keycode}")
        except Exception as e:
            log(f"✗ Error pressing keycode {keycode}: {e}")
    
    def ydotoolKeyUp(keycode):
        """Release a key using ydotool"""
        try:
            # Make sure to pass YDOTOOL_SOCKET in env
            env = os.environ.copy()
            if 'YDOTOOL_SOCKET' not in env:
                setupYdotoolSocket()
            
            # Try normal ydotool call first
            result = subprocess.run(['ydotool', 'key', f'{keycode}:0'], 
                                  capture_output=True, timeout=2, text=True, env=env)
            
            # If permission denied, try with sudo
            if "Permission denied" in result.stderr and result.returncode != 0:
                log(f"  ⚠ Permission denied, trying with sudo...")
                result = subprocess.run(['sudo', 'ydotool', 'key', f'{keycode}:0'], 
                                      capture_output=True, timeout=2, text=True, env=env)
            
            if result.returncode != 0:
                log(f"✗ ydotool release error for keycode {keycode}: {result.stderr}")
            else:
                log(f"✓ ydotool released key {keycode}")
        except Exception as e:
            log(f"✗ Error releasing keycode {keycode}: {e}")
    
    def press(key):
        try:
            if isinstance(key, str):
                keyStr = key.lower()
            else:
                keyStr = str(key).lower()
            
            log(f"→ press('{keyStr}')")
            if keyStr in keyMap:
                log(f"  → keycode {keyMap[keyStr]}")
                ydotoolKeyDown(keyMap[keyStr])
                heldKeys[keyStr] = (keyMap[keyStr], time.time())
            else:
                log(f"  ⚠ '{keyStr}' not in keyMap")
            logKeys("press", key)
        except Exception as e:
            log(f"✗ Error pressing key {key}: {e}")
    
    def release(key):
        try:
            if isinstance(key, str):
                keyStr = key.lower()
            else:
                keyStr = str(key).lower()
            
            log(f"→ release('{keyStr}')")
            if keyStr in keyMap:
                log(f"  → keycode {keyMap[keyStr]}")
                ydotoolKeyUp(keyMap[keyStr])
                if keyStr in heldKeys:
                    del heldKeys[keyStr]
            else:
                log(f"  ⚠ '{keyStr}' not in keyMap")
            logKeys("release", key)
        except Exception as e:
            log(f"✗ Error releasing key {key}: {e}")

# X11 implementation using pynput
else:
    log("Using pynput for X11 keyboard input")
    
    if configuration.configData["midiToQwerty"]["inputModule"] == "keyboard":
        import keyboard
        def press(key):
            keyboard.press(key)
            logKeys("press", key)
        def release(key):
            keyboard.release(key)
            logKeys("release", key)

    elif configuration.configData["midiToQwerty"]["inputModule"] == "pynput":
        pynputController = pynputKeyboard.Controller()
        blockedKeys = {f"f{i}" for i in range(1, 13)} | {"tab", "backspace", "esc"}
        
        # Special characters that require shift
        shiftChars = set("!@#$%^&*()_+{}:\"<>?|~")

        def translateKey(key):
            keyLower = key.lower() if isinstance(key, str) else key
            if isinstance(keyLower, str) and keyLower in specialKeyMap:
                return specialKeyMap[keyLower]
            elif isinstance(keyLower, str) and len(keyLower) == 1:
                return keyLower
            elif isinstance(key, pynputKeyboard.Key):
                return key
            else:
                raise ValueError(f"Unsupported key for pynput: {key}")

        def isBlockedKey(keyObj):
            if isinstance(keyObj, str):
                return keyObj.lower() in blockedKeys
            if isinstance(keyObj, pynputKeyboard.Key):
                name = getattr(keyObj, "name", None)
                if isinstance(name, str) and name.lower() in blockedKeys:
                    return True
                s = str(keyObj).lower()
                if s.startswith("key.f") and any(s.startswith(f"key.f{i}") for i in range(1, 13)):
                    return True
                return False
            return False

        def press(key):
            keyObj = translateKey(key)
            if isBlockedKey(keyObj):
                return
            # Handle special characters that require shift
            if isinstance(keyObj, str) and keyObj in shiftChars:
                pynputController.press(pynputKeyboard.Key.shift)
                pynputController.press(keyObj)
                heldKeys[f"shift+{keyObj}"] = (pynputKeyboard.Key.shift, keyObj)
            else:
                pynputController.press(keyObj)
                logKeys("press", keyObj)
                heldKeys[str(keyObj)] = keyObj

        def release(key):
            keyObj = translateKey(key)
            if isBlockedKey(keyObj):
                return
            # Handle special characters that require shift
            if isinstance(keyObj, str) and keyObj in shiftChars:
                pynputController.release(keyObj)
                pynputController.release(pynputKeyboard.Key.shift)
                key_str = f"shift+{keyObj}"
                if key_str in heldKeys:
                    del heldKeys[key_str]
            else:
                pynputController.release(keyObj)
                logKeys("release", keyObj)
                key_str = str(keyObj)
                if key_str in heldKeys:
                    del heldKeys[key_str]

stopEvent = threading.Event()
keyboardHandlers = []
timerList = []
closeThread = False
sustainActive = False

def findVelocityKey(velocity):
    velocityMap = configuration.configData["midiToQwerty"]["pianoMap"]["velocityMap"]
    thresholds = sorted(int(k) for k in velocityMap.keys())
    minimum = 0
    maximum = len(thresholds) - 1
    index = 0
    while minimum <= maximum:
        index = (minimum + maximum) // 2
        if index == 0 or index == len(thresholds) - 1:
            break
        if thresholds[index] < velocity:
            minimum = index + 1
        else:
            maximum = index - 1
    return velocityMap[str(thresholds[index])]

def pressAndMaybeRelease(key):
    log(f"  ↳ pressAndMaybeRelease('{key}')")
    press(key)
    if configuration.configData["midiToQwerty"]["customHoldLength"]["enabled"]:
        t = threading.Timer(configuration.configData["midiToQwerty"]["customHoldLength"]["noteLength"], lambda: release(key))
        timerList.append(t)
        t.start()

def simulateKey(msgType, note, velocity):
    log(f"→ simulateKey(msgType={msgType}, note={note}, velocity={velocity})")
    
    if not -15 <= note - 36 <= 88:
        log(f"  ✗ out of range: {note}")
        return

    key = None
    letterNoteMap = configuration.configData["midiToQwerty"]["pianoMap"]["61keyMap"]
    lowNotes = configuration.configData["midiToQwerty"]["pianoMap"]["88keyMap"]["lowNotes"]
    highNotes = configuration.configData["midiToQwerty"]["pianoMap"]["88keyMap"]["highNotes"]

    if str(note) in letterNoteMap:
        key = letterNoteMap[str(note)]
    elif str(note) in lowNotes:
        key = lowNotes[str(note)]
    elif str(note) in highNotes:
        key = highNotes[str(note)]

    if not key:
        log(f"  ✗ no mapping for note {note}")
        return
    
    log(f"  → mapped to key '{key}'")
    
    pianoWidget = mainFunctions.getApp().frames["miditoqwerty"].piano

    if msgType == "note_on":
        pianoWidget.down(note, velocity)
        log(f"  → note_on: pressing '{key}'")

        if configuration.configData["midiToQwerty"]["velocity"]:
            velocityKey = findVelocityKey(velocity)
            log(f"    ↳ velocity key: {velocityKey}")
            press("alt")
            press(velocityKey)
            release(velocityKey)
            release("alt")

        if 36 <= note <= 96:
            if configuration.configData["midiToQwerty"]["noDoubles"]:
                if re.search("[!@$%^*(]", key):
                    release(letterNoteMap[str(note - 1)])
                else:
                    release(key.lower())
            if re.search("[!@$%^*(]", key):
                log(f"    ↳ special char: pressing shift + {letterNoteMap[str(note - 1)]}")
                press("shift")
                pressAndMaybeRelease(letterNoteMap[str(note - 1)])
                release("shift")
            elif key.isupper():
                log(f"    ↳ uppercase: pressing shift + {key.lower()}")
                press("shift")
                pressAndMaybeRelease(key.lower())
                release("shift")
            else:
                log(f"    ↳ normal char: {key}")
                pressAndMaybeRelease(key)
        else:
            log(f"    ↳ outside 36-96 range: ctrl + {key.lower()}")
            release(key.lower())
            press("ctrl")
            pressAndMaybeRelease(key.lower())
            release("ctrl")

    elif msgType == "note_off":
        pianoWidget.up(note)
        log(f"  → note_off: releasing '{key}'")

        if 36 <= note <= 96:
            if re.search("[!@$%^*(]", key):
                release(letterNoteMap[str(note - 1)])
            else:
                release(key.lower())
        else:
            release(key.lower())

def parseMidi(message):
    global sustainActive
    log(f"→ parseMidi: {message}")
    
    if message.type == "control_change" and configuration.configData["midiToQwerty"]["sustain"]:
        if not sustainActive and message.value > configuration.configData["midiToQwerty"]["sustainCutoff"]:
            sustainActive = True
            press("space")
        elif sustainActive and message.value < configuration.configData["midiToQwerty"]["sustainCutoff"]:
            sustainActive = False
            release("space")
    elif message.type in ("note_on", "note_off"):
        try:
            if message.velocity == 0:
                simulateKey("note_off", message.note, message.velocity)
            else:
                simulateKey(message.type, message.note, message.velocity)
        except IndexError:
            log(f"  ✗ IndexError processing MIDI message")
            pass

def startMidiInput(portName=None):
    global inPort, midiThread, stopEvent, closeThread
    stopEvent.clear()
    closeThread = False
    if USE_WAYLAND:
        log("nanoMIDI Mid2VK Translator v1.0 (Live Input) [Wayland/ydotool]")
        # Ensure ydotoold is running before starting MIDI input
        if not isYdotooldRunning():
            log("↳ ydotoold not running, starting daemon...")
            if not startYdotooldDaemon():
                log("✗ Failed to start ydotoold - keys may not work outside app")
    else:
        log("nanoMIDI Mid2VK Translator v1.0 (Live Input) [X11/pynput]")
    try:
        if portName:
            inPort = mido.open_input(portName)
        else:
            inPort = mido.open_input()
    except Exception as e:
        log(f"Could not open MIDI input: {e}")
        return

    def midiLoop():
        for msg in inPort:
            if stopEvent.is_set() or closeThread:
                break
            parseMidi(msg)

    midiThread = threading.Thread(target=midiLoop, daemon=True)
    midiThread.start()
    return midiThread


def stopMidiInput():
    global closeThread, stopEvent, keyboardHandlers, timerList, inPort, midiThread
    stopEvent.set()
    closeThread = True

    if inPort:
        try:
            inPort.close()
        except Exception:
            pass
        inPort = None

    if midiThread and midiThread.is_alive():
        try:
            midiThread.join(timeout=1.0)
        except Exception:
            pass
        midiThread = None

    for key in list(heldKeys.keys()):
        try:
            # Handle special shift+char format
            if isinstance(key, str) and key.startswith("shift+"):
                char = key[6:]
                pynputController.release(char)
                pynputController.release(pynputKeyboard.Key.shift)
            else:
                release(key)
        except Exception:
            pass
    heldKeys.clear()
    
    for t in list(timerList):
        try:
            t.cancel()
        except Exception:
            pass
    timerList.clear()
    try:
        for h in list(keyboardHandlers):
            try:
                import keyboard
                keyboard.unhook(h)
            except Exception:
                pass
        keyboardHandlers.clear()
    except Exception:
        pass

    try:
        pianoWidget = mainFunctions.getApp().frames["miditoqwerty"].piano
        for note in pianoWidget.currentNotes():
            pianoWidget.up(note)
    except Exception:
        pass
