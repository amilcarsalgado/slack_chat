import librosa
import numpy as np

AUDIO_FILE = "The Phantoms - Take The World (Let's Go).mp3"
OUTPUT_EDL = "beats_markers.edl"
FPS = 24  # Change to your DaVinci Resolve timeline frame rate (e.g. 24, 30, 60)
MARKER_COLOR = "Cyan"  # Resolves standard colors: Cyan, Blue, Green, Yellow, Red, Pink, etc.


def seconds_to_tc(seconds: float, fps: int) -> str:
    total_frames = int(round(seconds * fps))
    h = 1 + total_frames // (3600 * fps)
    m = (total_frames % (3600 * fps)) // (60 * fps)
    s = (total_frames % (60 * fps)) // fps
    f = total_frames % fps
    return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


print(f"Analyzing {AUDIO_FILE}...")
y, sr = librosa.load(AUDIO_FILE)

# Detect tempo and beat timestamps
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
beat_times = librosa.frames_to_time(beat_frames, sr=sr)

# Handle tempo float return across different librosa versions
bpm = tempo[0] if isinstance(tempo, (np.ndarray, list)) else tempo
print(f"Estimated BPM: {bpm:.2f} | Detected {len(beat_times)} beats")

# Generate standard DaVinci Resolve Marker EDL
with open(OUTPUT_EDL, "w") as f:
    f.write("TITLE: BEAT MARKERS\nFCM: NON-DROP FRAME\n\n")
    for i, t in enumerate(beat_times, start=1):
        tc_in = seconds_to_tc(t, FPS)
        tc_out = seconds_to_tc(t + (1.0 / FPS), FPS)
        f.write(f"{i:03d}  001      V     C        {tc_in} {tc_out} {tc_in} {tc_out}\n")
        f.write(f" |C:ResolveColor{MARKER_COLOR} |M:Beat {i} |D:1\n\n")

print(f"Saved {OUTPUT_EDL}. Ready to import into DaVinci Resolve!")