
from pathlib import Path
from datetime import datetime
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    send_from_directory,
    abort
)
import threading

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

frame_lock = threading.Condition()
latest_frame = None
frame_number = 0


# ==========================================
# Initiering
# ==========================================

def init_app(cam, pir_sensor, recording_status):
    global camera, pir, get_recording_status

    camera = cam
    pir = pir_sensor
    get_recording_status = recording_status


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
    return jsonify({
        "camera": "online" if camera else "offline",
        "motion": (
            bool(pir.motion_detected)
            if pir else False
        ),
        "recording": (
            bool(get_recording_status())
            if get_recording_status else False
        )
    })


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
            date_string = file.stem.replace("catcam_", "")
            dt = datetime.strptime(
                date_string,
                "%Y-%m-%d_%H-%M-%S_%f"
            )
        except ValueError:
            dt = datetime.fromtimestamp(stat.st_mtime)

        videos.append({
            "filename": file.name,
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S"),
            "size": round(stat.st_size / (1024 * 1024), 1),
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

@app.route("/api/videos/<filename>", methods=["DELETE"])
def delete_video(filename):

    # Tillåt endast CatCam MP4-filer.
    if (
        Path(filename).name != filename
        or not filename.startswith("catcam_")
        or not filename.endswith(".mp4")
    ):
        return jsonify({
            "success": False,
            "error": "Ogiltigt filnamn"
        }), 400

    # Kontrollera att filen ligger i videos-katalogen.
    video_file = VIDEO_DIR / filename

    if not video_file.is_file() or video_file.is_symlink():
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
            f"Fel vid radering av {filename}: {error}",
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
