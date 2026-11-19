
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

from web.app import (
    init_app,
    update_frame,
    start_webserver
)

# ==========================================
# Pi-CatCam v1.6
# ==========================================

# GPIO
PIR_PIN = 17
IR_PIN = 18

# Inspelning
RECORD_DELAY = 10.0
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FRAMERATE = 25
BITRATE = 8_000_000

# Livevideo
LIVE_WIDTH = 640
LIVE_HEIGHT = 360
LIVE_FPS = 5
JPEG_QUALITY = 70

# Kamerawatchdog
WATCHDOG_TIMEOUT = 20.0
WATCHDOG_STARTUP_DELAY = 30.0
WATCHDOG_INTERVAL = 2.0

# IR-belysning
IR_ENABLED = True

BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# Globala variabler
# ==========================================

recording = False
last_motion_time = 0.0
current_file = None

stop_event = threading.Event()
camera_lock = threading.Lock()
frame_lock = threading.Lock()

last_frame_time = time.monotonic()

conversion_threads = []

pir = None
camera = None
ir_light = None


# ==========================================
# Loggning
# ==========================================

def log(message):
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    print(f"[{timestamp}] {message}", flush=True)


# ==========================================
# Inspelningsstatus
# ==========================================

def is_recording():
    return recording


# ==========================================
# IR-belysning
# ==========================================

def start_ir():
    global ir_light

    # initial_value=False gör att utgången
    # börjar i avstängt läge.
    ir_light = OutputDevice(
        IR_PIN,
        active_high=True,
        initial_value=False
    )

    if IR_ENABLED:
        ir_light.on()
        log("IR-belysning PÅ (GPIO18)")
    else:
        log("IR-belysning AV")


def stop_ir():
    global ir_light

    if ir_light is not None:
        ir_light.off()
        ir_light.close()
        ir_light = None
        log("IR-belysning AV")


# ==========================================
# MP4-konvertering
# ==========================================

def convert_to_mp4(h264_file):

    mp4_file = h264_file.with_suffix(".mp4")

    try:
        if not h264_file.exists():
            log(f"Filen saknas: {h264_file.name}")
            return

        if h264_file.stat().st_size == 0:
            log(
                f"VARNING: Tom inspelning: "
                f"{h264_file.name}"
            )
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

        if (
            not mp4_file.exists()
            or mp4_file.stat().st_size == 0
        ):
            raise RuntimeError(
                "MP4-filen saknas eller är tom"
            )

        h264_file.unlink()

        log(f"MP4 sparad: {mp4_file.name}")

    except Exception as error:
        log(f"MP4-konvertering misslyckades: {error}")
        log(f"Originalfilen behålls: {h264_file.name}")


def start_conversion(h264_file):

    # Ta bort avslutade trådar från listan.
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
# Starta inspelning
# ==========================================

def start_recording():

    global recording, current_file

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S_%f"
    )

    current_file = (
        VIDEO_DIR / f"catcam_{timestamp}.h264"
    )

    encoder = H264Encoder(bitrate=BITRATE)

    with camera_lock:
        camera.start_encoder(
            encoder,
            FileOutput(str(current_file))
        )

    recording = True

    log(
        f"Rörelse! Inspelning startad: "
        f"{current_file.name}"
    )


# ==========================================
# Stoppa inspelning
# ==========================================

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
# Livevideo
# ==========================================

def live_video_worker():

    global last_frame_time

    log("Livevideo startad")

    interval = 1.0 / LIVE_FPS

    while not stop_event.is_set():

        start_time = time.monotonic()

        try:
            yuv = camera.capture_array("lores")

            # En riktig bildruta har mottagits.
            with frame_lock:
                last_frame_time = time.monotonic()

            bgr = cv2.cvtColor(
                yuv,
                cv2.COLOR_YUV2BGR_I420
            )

            success, jpeg = cv2.imencode(
                ".jpg",
                bgr,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    JPEG_QUALITY
                ]
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
# Kamerawatchdog
# ==========================================

def camera_watchdog():

    log("Camera Watchdog startad")

    if stop_event.wait(WATCHDOG_STARTUP_DELAY):
        return

    while not stop_event.is_set():

        with frame_lock:
            elapsed = (
                time.monotonic()
                - last_frame_time
            )

        if elapsed > WATCHDOG_TIMEOUT:

            log(
                "WATCHDOG: Inga nya bildrutor "
                f"på {elapsed:.1f} sekunder!"
            )

            log(
                "WATCHDOG: Startar om "
                "Pi-CatCam via systemd..."
            )

            # Restart=on-failure i systemd.
            # OBS: Tvingad avslutning innebär att
            # pågående inspelning inte hinner stängas.
            os._exit(1)

        stop_event.wait(WATCHDOG_INTERVAL)


# ==========================================
# Huvudprogram
# ==========================================

def main():

    global pir, camera
    global last_frame_time, last_motion_time

    log("================================")
    log("        Pi-CatCam v1.6")
    log("================================")

    log(f"PIR: GPIO{PIR_PIN}")
    log(f"IR-belysning: GPIO{IR_PIN}")

    log(
        f"Inspelning: "
        f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}"
    )

    log(
        f"Livevideo: "
        f"{LIVE_WIDTH}x{LIVE_HEIGHT}"
    )

    log(
        f"Eftergångstid: "
        f"{RECORD_DELAY} sekunder"
    )

    try:
        pir = MotionSensor(PIR_PIN)

        # Starta IR-belysningen.
        start_ir()

        camera = Picamera2()

        config = camera.create_video_configuration(
            main={
                "size": (
                    VIDEO_WIDTH,
                    VIDEO_HEIGHT
                ),
                "format": "YUV420"
            },
            lores={
                "size": (
                    LIVE_WIDTH,
                    LIVE_HEIGHT
                ),
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

        init_app(
            camera,
            pir,
            is_recording
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

        while not stop_event.is_set():

            now = time.monotonic()

            if pir.motion_detected:

                last_motion_time = now

                if not recording:
                    start_recording()

            elif recording:

                if (
                    now - last_motion_time
                    >= RECORD_DELAY
                ):
                    stop_recording()

            stop_event.wait(0.1)

    except KeyboardInterrupt:
        log("Avslutar Pi-CatCam...")

    finally:

        stop_event.set()

        # Stoppa inspelningen först.
        try:
            if recording:
                stop_recording()
        except Exception as error:
            log(f"Fel vid inspelningsstopp: {error}")

        # Stäng av IR även om kameran får fel.
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
