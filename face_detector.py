import os
import cv2
import logging
from collections import Counter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_FACE_CASCADE = None

def get_face_cascade():
    """Safely initializes the OpenCV Haar Face Cascade classifier."""
    global _FACE_CASCADE
    if _FACE_CASCADE is not None:
        return _FACE_CASCADE

    try:
        cascade_dir = getattr(cv2, "data", None)
        if cascade_dir and hasattr(cascade_dir, "haarcascades"):
            path = os.path.join(cascade_dir.haarcascades, 'haarcascade_frontalface_default.xml')
            if os.path.exists(path):
                _FACE_CASCADE = cv2.CascadeClassifier(path)
                return _FACE_CASCADE
        
        # Fallback constructor
        _FACE_CASCADE = cv2.CascadeClassifier()
        return _FACE_CASCADE
    except Exception as e:
        logging.warning(f"[!] Warning initializing face cascade: {e}")
        return None

def detect_facecam(video_path, sample_rate_sec=1):
    """
    Analyzes video frames sampled every `sample_rate_sec` seconds to detect streamer facecams.
    
    Returns dict:
    {
        "should_skip": bool,
        "skip_reason": str or None,
        "corner": str or None ("top-left", "top-right", "bottom-left", "bottom-right"),
        "max_face_percentage": float,
        "detected_corner": str or None
    }
    """
    if not os.path.exists(video_path):
        logging.error(f"[!] Video file not found for face detection: {video_path}")
        return {"should_skip": True, "skip_reason": "Video file not found", "corner": None}

    cascade = get_face_cascade()
    if not cascade or cascade.empty():
        logging.warning("[!] Face detector cascade unavailable. Skipping face detection.")
        return {"should_skip": False, "skip_reason": None, "corner": None, "max_face_percentage": 0.0}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logging.error(f"[!] Cannot open video file: {video_path}")
        return {"should_skip": True, "skip_reason": "Failed to open video file", "corner": None}

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    frame_interval = max(int(fps * sample_rate_sec), 1)
    
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frame_area = frame_width * frame_height

    frame_count = 0
    sampled_frames = 0
    corner_detections = []
    max_face_percentage = 0.0
    multi_face_count = 0
    centered_face_count = 0
    large_face_count = 0

    logging.info(f"[*] Analyzing video for facecam detection: {os.path.basename(video_path)} ({frame_width}x{frame_height})")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            sampled_frames += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray, 
                scaleFactor=1.1, 
                minNeighbors=5, 
                minSize=(40, 40)
            )

            if len(faces) > 1:
                multi_face_count += 1
                logging.info(f"[-] Sampled frame {sampled_frames}: Multiple faces detected ({len(faces)} faces)")

            for (x, y, w, h) in faces:
                face_area = w * h
                face_pct = (face_area / total_frame_area) * 100.0
                if face_pct > max_face_percentage:
                    max_face_percentage = face_pct

                if face_pct > 20.0:
                    large_face_count += 1
                    logging.info(f"[-] Sampled frame {sampled_frames}: Face covers {face_pct:.1f}% (> 20% limit)")

                # Face center coordinates
                fc_x = x + (w / 2.0)
                fc_y = y + (h / 2.0)

                # Check if face is centered (35% to 65% width, 30% to 70% height)
                if (0.35 * frame_width <= fc_x <= 0.65 * frame_width) and (0.30 * frame_height <= fc_y <= 0.70 * frame_height):
                    centered_face_count += 1
                    logging.info(f"[-] Sampled frame {sampled_frames}: Face is centered at ({fc_x:.0f}, {fc_y:.0f})")
                else:
                    # Determine corner
                    horiz = "left" if fc_x < 0.5 * frame_width else "right"
                    vert = "top" if fc_y < 0.5 * frame_height else "bottom"
                    corner = f"{vert}-{horiz}"
                    corner_detections.append(corner)
                    logging.info(f"[+] Sampled frame {sampled_frames}: Facecam detected in {corner} (Area: {face_pct:.1f}%)")

        frame_count += 1

    cap.release()

    if sampled_frames == 0:
        return {"should_skip": False, "skip_reason": None, "corner": None, "max_face_percentage": 0.0}

    # Evaluation Criteria
    if multi_face_count >= 2:
        skip_msg = f"Multiple faces detected in {multi_face_count} sampled frames"
        logging.warning(f"[!] Rejection Triggered: {skip_msg}")
        return {"should_skip": True, "skip_reason": skip_msg, "corner": None, "max_face_percentage": max_face_percentage}

    if large_face_count >= 2:
        skip_msg = f"Face covers > 20% of frame (max: {max_face_percentage:.1f}%)"
        logging.warning(f"[!] Rejection Triggered: {skip_msg}")
        return {"should_skip": True, "skip_reason": skip_msg, "corner": None, "max_face_percentage": max_face_percentage}

    if centered_face_count >= 2:
        skip_msg = "Streamer face is centered in gameplay area"
        logging.warning(f"[!] Rejection Triggered: {skip_msg}")
        return {"should_skip": True, "skip_reason": skip_msg, "corner": None, "max_face_percentage": max_face_percentage}

    # Evaluate dominant facecam corner
    if corner_detections:
        counter = Counter(corner_detections)
        most_common_corner, count = counter.most_common(1)[0]
        if count / len(corner_detections) >= 0.5:
            logging.info(f"[+] Dominant Facecam Corner Confirmed: {most_common_corner} ({count}/{len(corner_detections)} frames)")
            return {
                "should_skip": False,
                "skip_reason": None,
                "corner": most_common_corner,
                "max_face_percentage": max_face_percentage
            }

    logging.info("[+] No streamer facecam detected in corners. Proceeding with clean video.")
    return {
        "should_skip": False,
        "skip_reason": None,
        "corner": None,
        "max_face_percentage": max_face_percentage
    }

if __name__ == "__main__":
    import sys
    test_file = sys.argv[1] if len(sys.argv) > 1 else "data/raw_videos/test.mp4"
    res = detect_facecam(test_file)
    print("FACE DETECTION RESULT:", res)
