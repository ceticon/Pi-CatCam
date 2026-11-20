
from pathlib import Path
from datetime import datetime
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    send_from_directory,
    abort,
    request
)
import threading

# ==========================================
# Pi-CatCam v1.7 - Flask Web Interface
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
VIDEO_DIR = PROJECT_DIR / "videos"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static")
)

camera = None
pir = None
get_recording_status = None

# IR-funktioner från catcam.py
get_ir_status_callback = None
set_ir_mode_callback = None

frame_lock = threading.Condition()
latest_frame = None
frame_number = 0


# ==========================================
# Initiering
# ==========================================

def init_app(
    cam,
    pir_sensor,
    recording_status,
    ir_status=None,
    ir_set_mode=None
):
    global camera, pir, get_recording_status
    global get_ir_status_callback
    global set_ir_mode_callback

    camera = cam
    pir = pir_sensor
    get_recording_status = recording_status

    get_ir_status_callback = ir_status
    set_ir_mode_callback = ir_set_mode


# ==========================================
# Livevideo
# ==========================================

def update_frame(jpeg):
    global latest_frame, frame_number

    with frame_lock:
        latest_frame = jpeg
        frame_number += 1
        frame_lock.notify_all()


def generate_frames():
    last_frame_number = -1

    while True:
        with frame_lock:
            frame_lock.wait_for(
                lambda: frame_number != last_frame_number,
                timeout=2.0
            )

            if latest_frame is None:
                continue

            frame = latest_frame
            last_frame_number = frame_number

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + frame +
            b"\r\n"
        )


# ==========================================
# Huvudsida
# ==========================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ==========================================
# Status
# ==========================================

@app.route("/api/status")
def status():

    ir_status = {
        "mode": "OFF",
        "enabled": False
    }

    if get_ir_status_callback:
        ir_status = get_ir_status_callback()

    return jsonify({
        "camera": (
            "online" if camera else "offline"
        ),
        "motion": (
            bool(pir.motion_detected)
            if pir else False
        ),
        "recording": (
            bool(get_recording_status())
            if get_recording_status else False
        ),
        "ir": ir_status
    })


# ==========================================
# IR-belysning - Läs status
# ==========================================

@app.route("/api/ir", methods=["GET"])
def get_ir():

    if get_ir_status_callback is None:
        return jsonify({
            "success": False,
            "error": "IR-styrningen är inte tillgänglig"
        }), 503

    return jsonify({
        "success": True,
        **get_ir_status_callback()
    })


# ==========================================
# IR-belysning - Ändra driftläge
# ==========================================

@app.route("/api/ir", methods=["POST"])
def set_ir():

    if set_ir_mode_callback is None:
        return jsonify({
            "success": False,
            "error": "IR-styrningen är inte tillgänglig"
        }), 503

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "Ogiltiga JSON-data"
        }), 400

    mode = data.get("mode")

    if not isinstance(mode, str):
        return jsonify({
            "success": False,
            "error": "IR-läge saknas"
        }), 400

    mode = mode.upper()

    if mode not in ("OFF", "AUTO", "ON"):
        return jsonify({
            "success": False,
            "error": "Ogiltigt IR-läge"
        }), 400

    try:
        result = set_ir_mode_callback(mode)

        return jsonify({
            "success": True,
            **result
        })

    except Exception:
        app.logger.exception(
            "Kunde inte ändra IR-läge"
        )

        return jsonify({
            "success": False,
            "error": "Kunde inte ändra IR-läge"
        }), 500


# ==========================================
# Videogalleri
# ==========================================

@app.route("/gallery")
def gallery():
    videos = []

    for file in VIDEO_DIR.glob("*.mp4"):

        try:
            stat = file.stat()
        except FileNotFoundError:
            continue

        # Försök läsa datum från filnamnet
        try:
            date_string = file.stem.replace(
                "catcam_", ""
            )

            dt = datetime.strptime(
                date_string,
                "%Y-%m-%d_%H-%M-%S_%f"
            )

        except ValueError:
            dt = datetime.fromtimestamp(
                stat.st_mtime
            )

        videos.append({
            "filename": file.name,
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S"),
            "size": round(
                stat.st_size / (1024 * 1024), 1
            ),
            "timestamp": dt.timestamp()
        })

    videos.sort(
        key=lambda video: video["timestamp"],
        reverse=True
    )

    return render_template(
        "gallery.html",
        videos=videos
    )


# ==========================================
# Spela upp videofiler
# ==========================================

@app.route("/videos/<path:filename>")
def serve_video(filename):

    if not filename.lower().endswith(".mp4"):
        abort(404)

    return send_from_directory(
        VIDEO_DIR,
        filename,
        conditional=True
    )


# ==========================================
# Ta bort videofil
# ==========================================

@app.route(
    "/api/videos/<filename>",
    methods=["DELETE"]
)
def delete_video(filename):

    if (
        Path(filename).name != filename
        or not filename.startswith("catcam_")
        or not filename.endswith(".mp4")
    ):
        return jsonify({
            "success": False,
            "error": "Ogiltigt filnamn"
        }), 400

    video_file = VIDEO_DIR / filename

    if (
        not video_file.is_file()
        or video_file.is_symlink()
    ):
        return jsonify({
            "success": False,
            "error": "Videofilen finns inte"
        }), 404

    try:
        video_file.unlink()

        print(
            f"Videofil raderad: {filename}",
            flush=True
        )

        return jsonify({
            "success": True,
            "filename": filename
        })

    except OSError as error:
        print(
            f"Fel vid radering av "
            f"{filename}: {error}",
            flush=True
        )

        return jsonify({
            "success": False,
            "error": "Kunde inte radera videofilen"
        }), 500


# ==========================================
# Flask-server
# ==========================================

def start_webserver():
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )
