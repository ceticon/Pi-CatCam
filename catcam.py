
#!/usr/bin/env python3

import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from gpiozero import MotionSensor, OutputDevice
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

from web.app import init_app, update_frame, start_webserver


# ==========================================
# INSTÄLLNINGAR
# ==========================================

PIR_PIN = 17
IR_PIN = 18

PIR_FILTER_TIME = 0.5       # PIR måste vara aktiv i 500 ms
PIR_DEBUG = True

RECORD_DELAY = 10.0         # Eftergångstid i sekunder

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FRAMERATE = 25
BITRATE = 8_000_000

LIVE_WIDTH = 640
LIVE_HEIGHT = 360
LIVE_FPS = 5
JPEG_QUALITY = 70

WATCHDOG_TIMEOUT = 20.0
WATCHDOG_STARTUP_DELAY = 30.0
WATCHDOG_INTERVAL = 2.0

IR_DEFAULT_MODE = "AUTO"
IR_MOTION_IGNORE_TIME = 2.0

BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# GLOBALA VARIABLER
# ==========================================

recording = False
last_motion_time = 0.0
pir_motion_start = None
current_file = None

stop_event = threading.Event()

camera_lock = threading.Lock()
frame_lock = threading.Lock()
ir_lock = threading.Lock()

last_frame_time = time.monotonic()
conversion_threads = []

pir = None
camera = None
ir_light = None

ir_mode = IR_DEFAULT_MODE
ir_enabled = False
ir_ignore_until = 0.0


# ==========================================
# LOGGNING
# ==========================================

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


# ==========================================
# PIR-DIAGNOSTIK
# ==========================================

def pir_motion_detected():
    if PIR_DEBUG:
        log("PIR GPIO17: Rörelse upptäckt")


def pir_motion_ended():
    if PIR_DEBUG:
        log("PIR GPIO17: Ingen rörelse")


def is_recording():
    return recording


# ==========================================
# IR-BELYSNING
# ==========================================

def set_ir_output(enabled):
    global ir_enabled, ir_ignore_until

    with ir_lock:
        if ir_light is None:
            return

        enabled = bool(enabled)

        if enabled == ir_enabled:
            return

        if enabled:
            ir_light.on()
            ir_ignore_until = (
                time.monotonic() + IR_MOTION_IGNORE_TIME
            )
            log("IR-belysning PÅ (GPIO18)")
        else:
            ir_light.off()
            log("IR-belysning AV (GPIO18)")

        ir_enabled = enabled


def get_ir_status():
    with ir_lock:
        return {
            "mode": ir_mode,
            "enabled": ir_enabled
        }


def set_ir_mode(mode):
    global ir_mode

    mode = str(mode).upper()

    if mode not in ("OFF", "AUTO", "ON"):
        raise ValueError("Ogiltigt IR-läge")

    with ir_lock:
        ir_mode = mode

    log(f"IR-läge ändrat till {mode}")

    if mode == "ON":
        set_ir_output(True)
    elif mode == "OFF":
        set_ir_output(False)
    else:
        set_ir_output(is_recording())

    return get_ir_status()


def start_ir():
    global ir_light, ir_enabled

    with ir_lock:
        ir_light = OutputDevice(
            IR_PIN,
            active_high=True,
            initial_value=False
        )
        ir_enabled = False

    log(f"IR-standardläge: {ir_mode}")

    if ir_mode == "ON":
        set_ir_output(True)


def stop_ir():
    global ir_light, ir_enabled

    with ir_lock:
        if ir_light is not None:
            ir_light.off()
            ir_light.close()
            ir_light = None
            ir_enabled = False
            log("IR-belysning AV")


# ==========================================
# MP4-KONVERTERING
# ==========================================

def convert_to_mp4(h264_file):
    mp4_file = h264_file.with_suffix(".mp4")

    try:
        if not h264_file.exists():
            log(f"Filen saknas: {h264_file.name}")
            return

        if h264_file.stat().st_size == 0:
            log(f"VARNING: Tom inspelning: {h264_file.name}")
            return

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-fflags", "+genpts",
            "-r", str(FRAMERATE),
            "-i", str(h264_file),
            "-c:v", "copy",
            "-movflags", "+faststart",
            str(mp4_file)
        ]

        log(f"Konverterar: {h264_file.name}")

        subprocess.run(
            command,
            check=True,
            timeout=300
        )

        if not mp4_file.exists() or mp4_file.stat().st_size == 0:
            raise RuntimeError("MP4-filen saknas eller är tom")

        h264_file.unlink()
        log(f"MP4 sparad: {mp4_file.name}")

    except Exception as error:
        log(f"MP4-konvertering misslyckades: {error}")
        log(f"Originalfilen behålls: {h264_file.name}")


def start_conversion(h264_file):
    conversion_threads[:] = [
        thread
        for thread in conversion_threads
        if thread.is_alive()
    ]

    thread = threading.Thread(
        target=convert_to_mp4,
        args=(h264_file,),
        daemon=False
    )

    thread.start()
    conversion_threads.append(thread)


# ==========================================
# INSPELNING
# ==========================================

def start_recording():
    global recording, current_file

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S_%f"
    )

    current_file = VIDEO_DIR / f"catcam_{timestamp}.h264"

    encoder = H264Encoder(bitrate=BITRATE)

    with camera_lock:
        camera.start_encoder(
            encoder,
            FileOutput(str(current_file))
        )

    recording = True

    log(f"Rörelse! Inspelning startad: {current_file.name}")


def stop_recording():
    global recording, current_file

    if not recording:
        return

    with camera_lock:
        camera.stop_encoder()

    recording = False

    finished_file = current_file
    current_file = None

    log("Inspelning avslutad")

    start_conversion(finished_file)

    log("Väntar på rörelse...")


# ==========================================
# LIVEVIDEO
# ==========================================

def live_video_worker():
    global last_frame_time

    log("Livevideo startad")

    interval = 1.0 / LIVE_FPS

    while not stop_event.is_set():
        start_time = time.monotonic()

        try:
            yuv = camera.capture_array("lores")

            with frame_lock:
                last_frame_time = time.monotonic()

            bgr = cv2.cvtColor(
                yuv,
                cv2.COLOR_YUV2BGR_I420
            )

            success, jpeg = cv2.imencode(
                ".jpg",
                bgr,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )

            if success:
                update_frame(jpeg.tobytes())

        except Exception as error:
            if not stop_event.is_set():
                log(f"Livevideo-fel: {error}")
                stop_event.wait(0.5)

        elapsed = time.monotonic() - start_time

        stop_event.wait(
            max(0, interval - elapsed)
        )

    log("Livevideo stoppad")


# ==========================================
# CAMERA WATCHDOG
# ==========================================

def camera_watchdog():
    log("Camera Watchdog startad")

    if stop_event.wait(WATCHDOG_STARTUP_DELAY):
        return

    while not stop_event.is_set():

        with frame_lock:
            elapsed = time.monotonic() - last_frame_time

        if elapsed > WATCHDOG_TIMEOUT:
            log(
                f"WATCHDOG: Inga nya bildrutor på "
                f"{elapsed:.1f} sekunder!"
            )
            log(
                "WATCHDOG: Startar om Pi-CatCam via systemd..."
            )
            os._exit(1)

        stop_event.wait(WATCHDOG_INTERVAL)


# ==========================================
# HUVUDPROGRAM
# ==========================================

def main():
    global pir, camera
    global last_frame_time, last_motion_time
    global pir_motion_start

    log("================================")
    log(" Pi-CatCam v1.8 - PIR Filter")
    log("================================")

    log(f"PIR: GPIO{PIR_PIN}")
    log(f"PIR-filter: {PIR_FILTER_TIME} sekunder")
    log(f"PIR-diagnostik: {'PÅ' if PIR_DEBUG else 'AV'}")
    log(f"IR-belysning: GPIO{IR_PIN}")
    log(f"Inspelning: {VIDEO_WIDTH}x{VIDEO_HEIGHT}")
    log(f"Livevideo: {LIVE_WIDTH}x{LIVE_HEIGHT}")
    log(f"Eftergångstid: {RECORD_DELAY} sekunder")

    try:
        # Starta PIR
        pir = MotionSensor(PIR_PIN)

        if PIR_DEBUG:
            pir.when_motion = pir_motion_detected
            pir.when_no_motion = pir_motion_ended

        # Starta IR
        start_ir()

        # Starta kamera
        camera = Picamera2()

        config = camera.create_video_configuration(
            main={
                "size": (VIDEO_WIDTH, VIDEO_HEIGHT),
                "format": "YUV420"
            },
            lores={
                "size": (LIVE_WIDTH, LIVE_HEIGHT),
                "format": "YUV420"
            },
            controls={
                "FrameRate": FRAMERATE
            },
            buffer_count=4
        )

        camera.configure(config)
        camera.start()

        with frame_lock:
            last_frame_time = time.monotonic()

        log("Kamera startad")

        # Starta webbserver
        init_app(
            camera,
            pir,
            is_recording,
            get_ir_status,
            set_ir_mode
        )

        web_thread = threading.Thread(
            target=start_webserver,
            daemon=True
        )

        live_thread = threading.Thread(
            target=live_video_worker,
            daemon=True
        )

        watchdog_thread = threading.Thread(
            target=camera_watchdog,
            daemon=True
        )

        web_thread.start()
        live_thread.start()
        watchdog_thread.start()

        log("Webbserver: http://0.0.0.0:5000")
        log("Väntar på rörelse...")

        # ==================================
        # HUVUDLOOP MED DIGITALT PIR-FILTER
        # ==================================

        while not stop_event.is_set():

            now = time.monotonic()
            motion = pir.motion_detected

            # Digitalt filter:
            # PIR måste vara aktiv kontinuerligt
            # under PIR_FILTER_TIME sekunder.

            if motion:
                if pir_motion_start is None:
                    pir_motion_start = now

                filtered_motion = (
                    now - pir_motion_start >= PIR_FILTER_TIME
                )
            else:
                pir_motion_start = None
                filtered_motion = False

            # Starta inspelning
            if filtered_motion and not recording:

                last_motion_time = now

                with ir_lock:
                    mode = ir_mode

                if mode == "AUTO":
                    set_ir_output(True)

                start_recording()

            # Förläng inspelning
            elif filtered_motion and recording:

                with ir_lock:
                    ignore_until = ir_ignore_until

                if now >= ignore_until:
                    last_motion_time = now

            # Stoppa inspelning efter eftergångstid
            elif recording:

                if now - last_motion_time >= RECORD_DELAY:

                    stop_recording()

                    with ir_lock:
                        mode = ir_mode

                    if mode == "AUTO":
                        set_ir_output(False)

            stop_event.wait(0.1)

    except KeyboardInterrupt:
        log("Avslutar Pi-CatCam...")

    finally:
        stop_event.set()

        try:
            if recording:
                stop_recording()
        except Exception as error:
            log(f"Fel vid inspelningsstopp: {error}")

        stop_ir()

        if camera is not None:
            try:
                camera.stop()
                camera.close()
            except Exception as error:
                log(f"Fel vid kamerastopp: {error}")

        if pir is not None:
            pir.close()

        for thread in conversion_threads:
            thread.join()

        log("Pi-CatCam stoppad")


if __name__ == "__main__":
    main()
