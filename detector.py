import cv2
import supervision as sv
import yaml
import logging
from ultralytics import YOLO
from db import record_direction

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


class PeopleDetector:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

        self._setup_model()
        self._setup_camera()
        self._setup_tracking()
        self._setup_line_zone()

    def _setup_model(self):
        self.model = YOLO(self.cfg["model"]["path"])

    def _setup_camera(self):
        cam = self.cfg["camera"]
        self.cap = cv2.VideoCapture(cam["id"])
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam["width"])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam["height"])
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logging.info(f"Camera resolution: {self.frame_width}x{self.frame_height}")

    def _setup_tracking(self):
        self.tracker = sv.ByteTrack()
        self.box_annotator = sv.BoxAnnotator()
        self.recorded_in_ids = set()
        self.prev_bboxes = {}
        self.last_trigger_frame = {}  # tracker_id -> last frame number, debounce

    def _setup_line_zone(self):
        det = self.cfg["detection"]
        self.orientation = det["line_orientation"]
        self.in_direction = det["in_direction"]
        ratio = det["line_ratio"]

        if self.orientation == "vertical":
            line_pos = int(self.frame_width * ratio)
            self.line_start = sv.Point(line_pos, 0)
            self.line_end = sv.Point(line_pos, self.frame_height)
            logging.info(f"Vertical line at x={line_pos}")
        else:
            line_pos = int(self.frame_height * ratio)
            self.line_start = sv.Point(0, line_pos)
            self.line_end = sv.Point(self.frame_width, line_pos)
            logging.info(f"Horizontal line at y={line_pos}")

        self.line_pos = line_pos
        self.line_zone = sv.LineZone(start=self.line_start, end=self.line_end)
        self.line_annotator = sv.LineZoneAnnotator()

    def _get_center_coord(self, bbox):
        """Return the coordinate perpendicular to the detection line."""
        if self.orientation == "vertical":
            return (bbox[0] + bbox[2]) / 2
        return (bbox[1] + bbox[3]) / 2

    def _get_direction(self, prev_pos, curr_pos):
        """Return 'IN' or 'OUT' based on crossing direction."""
        if self.orientation == "vertical":
            if self.in_direction == "right_to_left":
                return "IN" if curr_pos < self.line_pos and prev_pos >= self.line_pos else "OUT"
            else:  # left_to_right
                return "IN" if curr_pos > self.line_pos and prev_pos <= self.line_pos else "OUT"
        else:
            if self.in_direction == "top_to_bottom":
                return "IN" if curr_pos > self.line_pos and prev_pos <= self.line_pos else "OUT"
            else:  # bottom_to_top
                return "IN" if curr_pos < self.line_pos and prev_pos >= self.line_pos else "OUT"

    def _process_detections(self, detections, frame_count):
        cooldown = 15  # min frames between same-direction triggers
        for i, tracker_id in enumerate(detections.tracker_id):
            bbox = detections.xyxy[i]
            curr_pos = self._get_center_coord(bbox)

            if tracker_id in self.prev_bboxes:
                prev_pos = self._get_center_coord(self.prev_bboxes[tracker_id])
                crossed = (prev_pos - self.line_pos) * (curr_pos - self.line_pos) < 0
                if crossed:
                    direction = self._get_direction(prev_pos, curr_pos)
                    last_frame = self.last_trigger_frame.get(tracker_id, 0)
                    if frame_count - last_frame > cooldown:
                        if direction == "IN" and tracker_id not in self.recorded_in_ids:
                            record_direction("IN")
                            self.recorded_in_ids.add(tracker_id)
                            self.last_trigger_frame[tracker_id] = frame_count
                        elif direction == "OUT":
                            record_direction("OUT")
                            self.last_trigger_frame[tracker_id] = frame_count

            self.prev_bboxes[tracker_id] = bbox

    def _annotate_frame(self, frame, detections):
        frame = self.box_annotator.annotate(scene=frame, detections=detections)
        frame = self.line_annotator.annotate(frame=frame, line_counter=self.line_zone)
        return frame

    def run(self):
        self._verbose = logging.getLogger().isEnabledFor(logging.DEBUG)
        frame_count = 0

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            frame_count += 1

            results = self.model(frame, verbose=not self._verbose)[0]
            detections = sv.Detections.from_ultralytics(results)
            target_class = self.cfg["detection"]["target_class"]
            detections = detections[detections.class_id == target_class]
            detections = self.tracker.update_with_detections(detections)

            self._process_detections(detections, frame_count)
            self.line_zone.trigger(detections)

            frame = self._annotate_frame(frame, detections)
            cv2.imshow("People Counting", frame)
            if self._verbose:
                logging.info(f"IN: {len(self.recorded_in_ids)}  |  OUT: {self.line_zone.out_count}")

            if cv2.waitKey(1) == ord("q"):
                break

        self.cleanup()

    def cleanup(self):
        self.cap.release()
        cv2.destroyAllWindows()
