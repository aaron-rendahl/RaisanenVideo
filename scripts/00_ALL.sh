VID="Raisanen-1987a"
VID="Raisanen-8mm"
VID="Raisanen-1987-Willy-40th"
VID="You-Cant-Take-It-With-You"
IS8MM=false

SCRIPT_DIR="./scripts"
ORIGINAL_DIR="./00_originals"
ARCHIVE_DIR="./01_archive"

$PYTHON=python3

## ---------------------------------------------
## 0) Unit tests on the code
if false; then
  pytest
fi


## ---------------------------------------------
## 1) MAKE THE ARCHIVAL VERSION

[[ "$IS8MM" = true ]] && FLAG8="-8" ||  FLAG8=""
$SCRIPT_DIR/01_clean_tape.sh $FLAG8 $ORIGINAL_DIR/$VID.mpg

## ---------------------------------------------
## 2) EMBED METADATA AND TIMESTAMPS

## 2a) Using LosslessCut, determine timestamps and create spec file in 03_specs
## 2b) Embed metadata and timestamps:
$PYTHON $SCRIPT_DIR/02_embed_metadata.py $VID

## 2c) Check that they were written properly
if false; then
  VID01="$ARCHIVE_DIR/$VID.mkv"
  ## check chapters
  mkvextract chapters "$VID01" | xmllint --format - | less
  ## check global title
  ffprobe -v error -show_entries format_tags=title -of default=noprint_wrappers=1 $VID01
  ## check global tags
  ffprobe -v error -show_entries format_tags -of json $VID01
  ## check cropping metadata
  mkvinfo $VID01 | grep -i crop
fi

## ---------------------------------------------
## 3) CREATE CLIPS

if false; then
  $SCRIPT_DIR/03_make_clips.py --uncropped-frames $VID
  $SCRIPT_DIR/03_make_clips.py --frames-only $VID
fi



## -----------------------------------------------
## 4) CREATE INDEX SLIDE (if not already created)

if false; then
  $SCRIPT_DIR/04_create_index.sh
fi
