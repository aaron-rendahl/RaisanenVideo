#!/usr/bin/env bash
#
# 01_clean_tape.sh
#
# Remuxes raw analog capture files into standardized, clean Matroska (.mkv) archival versions.
# Rebuilds presentation timestamps (PTS) while preserving all video frames
# to guarantee rock-solid timestamp accuracy and perfect A/V sync.
#
# Usage:
#   ./scripts/01_clean_tape.sh [-8] <INPUT_FILE> [OUTPUT_FILE]
#
# Options:
#   -8    8mm tape mode: Applies 1.5x slowdown to video PTS and strips audio.
#

set -euo pipefail

IS_8MM=false

while getopts "8" opt; do
  case ${opt} in
    8 )
      IS_8MM=true
      ;;
    \? )
      echo "Usage: $0 [-8] <INPUT_FILE> [OUTPUT_FILE]"
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 [-8] <INPUT_FILE> [OUTPUT_FILE]"
    exit 1
fi

INPUT_FILE="$1"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file '$INPUT_FILE' does not exist."
    exit 1
fi

# Determine default output path in 01_archive/ if not explicitly provided
if [ "$#" -ge 2 ]; then
    OUTPUT_FILE="$2"
else
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    ARCHIVE_DIR="$PROJECT_ROOT/01_archive"

    mkdir -p "$ARCHIVE_DIR"

    TAPE_NAME="$(basename "$INPUT_FILE")"
    TAPE_STEM="${TAPE_NAME%.*}"
    OUTPUT_FILE="$ARCHIVE_DIR/${TAPE_STEM}.mkv"
fi

echo "=== Cleaning & Remuxing Master Tape ==="
echo "Input : $INPUT_FILE"
echo "Output: $OUTPUT_FILE"

if [ "$IS_8MM" = true ]; then
    echo "Mode  : 8mm Tape Transfer (1.5x slowdown, stripping audio)"
    ## ## NOPE! Don't do this, there are still video alignment issues that need to be fixed
    ## ## Use mkvmerge to get fps correct, don't need +genpts to align audio mismatch
    ## ## # mkvmerge -o $OUTPUT_FILE --default-duration 0:19.98fps $INPUT_FILE
    ## To use ffmpeg properly, need both -itsscale and -r, as the fps is stored two ways
    ffmpeg -hide_banner -loglevel error -y \
      -fflags +genpts \
      -itsscale 1.5 \
      -r 20000/1001 \
      -i "$INPUT_FILE" \
      -c:v copy \
      -an \
      -max_muxing_queue_size 1024 \
      "$OUTPUT_FILE"
else
    echo "Mode  : Standard Tape (Original speed and audio)"
    # Use ffmpeg with +genpts to fix audio misalignment
    ffmpeg -hide_banner -loglevel error -y \
      -fflags +genpts \
      -i "$INPUT_FILE" \
      -c copy \
      -max_muxing_queue_size 1024 \
      "$OUTPUT_FILE"
fi

echo "Done! Archival version created successfully at: $OUTPUT_FILE"
