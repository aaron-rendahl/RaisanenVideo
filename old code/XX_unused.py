
## src/video_utils.py
def has_audio_stream(mkv_path: Path) -> bool:
    """Returns True if the MKV container has at least one audio stream."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(mkv_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return bool(res.stdout.strip())

## src/ffmpeg_utils.py
def resolve_cmd_args(cmd_template: List[str], paths: dict) -> List[str]:
    """Resolves ${VAR} placeholders to concrete file path strings for subprocess execution."""
    resolved = []
    for token in cmd_template:
        if token.startswith("${") and token.endswith("}"):
            var_name = token[2:-1]
            resolved.append(paths[var_name])
        else:
            resolved.append(token)
    return resolved
  
## src/ffmpeg_utils.py
def format_pipeline_to_bash(pipeline: dict) -> str:
    """Formats three-stage FFmpeg pipeline into clean multiline bash script syntax with header variables."""
    paths = pipeline["paths"]

    var_header = [
        f'SRC_MKV={shlex.quote(paths["SRC_MKV"])}',
        f'TMP_MKV={shlex.quote(paths["TMP_MKV"])}',
        f'META_TXT={shlex.quote(paths["META_TXT"])}',
        f'VTT_SUB={shlex.quote(paths["VTT_SUB"])}',
        f'OUT_MP4={shlex.quote(paths["OUT_MP4"])}',
        f'MUX_MP4={shlex.quote(paths["MUX_MP4"])}',
        "\n",
    ]

    s1_str = format_cmd_tokens(pipeline["stage1"])
    s2_str = format_cmd_tokens(pipeline["stage2"])
    s3_str = format_cmd_tokens(pipeline["stage3"])

    script_body = (
        f"{s1_str}\n\n"
        f"{s2_str}\n\n"
        f'rm -f "${{TMP_MKV}}"\n\n'
        f"{s3_str}\n\n"
        f'mv -f "${{MUX_MP4}}" "${{OUT_MP4}}"\n'
    )

    return "\n".join(var_header) + script_body

## src/time_utils.py
def format_ffprobe_timestamp(seconds_str: str) -> str:
    """Converts ffprobe time in seconds to HH:MM:SS.mmm format."""
    try:
        total_seconds = float(seconds_str)
    except (ValueError, TypeError):
        return "00:00:00.000"

    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

## src/ffmpeg_utils.py
def format_cmd_tokens(cmd: list) -> str:
    """Groups FFmpeg flags with their arguments into readable multi-line shell commands, avoiding double-quoting bash variables."""
    lines = []
    i = 0
    current_line = []

    while i < len(cmd):
        token = cmd[i]
        # Avoid escaping bash variables like ${SRC_MKV}
        quoted = token if token.startswith("${") and token.endswith("}") else shlex.quote(token)

        if token.startswith("-") or i == len(cmd) - 1:
            if current_line:
                lines.append("  " + " ".join(current_line))
                current_line = []
            current_line.append(quoted)

            if i + 1 < len(cmd) and not cmd[i + 1].startswith("-"):
                nxt = cmd[i + 1]
                nxt_quoted = nxt if nxt.startswith("${") and nxt.endswith("}") else shlex.quote(nxt)
                current_line.append(nxt_quoted)
                i += 1
        else:
            current_line.append(quoted)
        i += 1

    if current_line:
        lines.append("  " + " ".join(current_line))

    if lines:
        lines[0] = lines[0].strip()

    return " \\\n".join(lines)
