CLIP_DIR="./02_clips"

magick -size 1920x1080 canvas:'#1e1e1e' \
  -font Helvetica-Bold -fill white -gravity center -pointsize 64 \
  -annotate +0-50 "RAISANEN FAMILY FILM ARCHIVE" \
  -font Helvetica -fill '#cccccc' -pointsize 36 \
  -annotate +0+60 "Check the video description below for all playlist links" \
  png:- | ffmpeg -y -loop 1 -i - -c:v libx264 -t 10 -pix_fmt yuv420p -vf "fps=59.94" -movflags +faststart \
  $CLIP_DIR/Raisanen_index_video.mp4
