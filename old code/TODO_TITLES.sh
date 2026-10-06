## ADD METADATA TITLE WHEN CREATING FILE

    # 2. Process Video
    ffmpeg -nostdin -hide_banner -loglevel error -y \
      -fflags +genpts+discardcorrupt \
      -ss "$SEEK_START_SEC" -to "$SEEK_END_SEC" -i "$INPUT_FILE" \
      -vf "${VF_STAGE1}" \
      ${=AUDIO_STAGE1} \
      -c:v rawvideo -pix_fmt yuv420p \
      -f nut pipe:1 | \
    ffmpeg -nostdin -hide_banner -loglevel error -y \
      -f nut -i pipe:0 \
      -vf "${VF_STAGE2}" \
      -c:v libx264 -crf 22 -preset fast -pix_fmt yuv420p \
      -tag:v avc1 -g 60 \
      -color_primaries smpte170m -color_trc smpte170m -colorspace smpte170m \
      ${=AUDIO_STAGE2} \
      -metadata title="$YT_TITLE" \
      -movflags +faststart -shortest \
      "$OUTPUT_NAME"

### READ IT WHEN UPLOADING TO YOUTUBE

import subprocess
import json
import os
import re

def get_mp4_title(file_path):
    """Extract embedded metadata title from MP4 file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        # Pull title from format tags, checking case-insensitivity just in case
        tags = data.get("format", {}).get("tags", {})
        for key, value in tags.items():
            if key.lower() == "title":
                return value.strip()
    except Exception:
        pass
    return None

### INSIDE THE LOOP, QUERY DIRECTLY

for file_path in mp4_files:
    # 1. Try reading title embedded directly inside the MP4 container
    title = get_mp4_title(file_path)

    # 2. Fall back to filename parsing if no embedded title exists
    if not title:
        full_filename = os.path.basename(file_path)
        filename = re.sub(r"_YouTube(?=\.[^.]+$)", "", full_filename, flags=re.IGNORECASE)
        raw_title = os.path.splitext(filename)[0]
        t = raw_title.replace("_", " ").replace("-", " ")
        t = re.sub(r"^Raisanen\s*", "", t, flags=re.IGNORECASE)
        title = re.sub(r"\s*\b\d{2}\b\s*", ": ", t).strip()

    # Upload using the exact title string
    video_id = upload_video(youtube, file_path, title, os.path.basename(file_path))
    add_to_playlist(youtube, video_id, PLAYLIST_ID)


#### FOR THE MASTER FILE TITLE

ffmpeg -i "Raisanen-1972-Lake-Trip.mkv" \
  -c copy \
  -metadata title="1972 Lake Trip: Duluth, MN & BWCA" \
  "Raisanen-1972-Lake-Trip_tagged.mkv"

# or update directly
mkvpropedit "Raisanen-1987a.mkv" --edit info --set "title=Raisanen 1987a"

# and read it as needed
ffprobe -v quiet -print_format json -show_format "Raisanen-1987a.mkv"

