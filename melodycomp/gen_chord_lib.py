import json
import os

NOTE_MAP = {
    "C": 60, "C#": 61, "Db": 61, "D": 62, "D#": 63, "Eb": 63,
    "E": 64, "F": 65, "F#": 66, "Gb": 66, "G": 67, "G#": 68,
    "Ab": 68, "A": 69, "A#": 70, "Bb": 70, "B": 71
}

CHORD_FORMULAS = {
    "":         [0, 4, 7],      # Major
    "m":        [0, 3, 7],      # Minor
    "sus2":     [0, 2, 7],
    "sus4":     [0, 5, 7],
    "dim":      [0, 3, 6],
    "aug":      [0, 4, 8],

    "7":        [0, 4, 7, 10],  # Dominant 7th
    "maj7":     [0, 4, 7, 11],  # Major 7th
    "m7":       [0, 3, 7, 10],  # Minor 7th
    "m(maj7)":  [0, 3, 7, 11],
    "m7b5":     [0, 3, 6, 10],  # Half-diminished
    "dim7":     [0, 3, 6, 9],
    "7b5":      [0, 4, 6, 10],
    "7#5":      [0, 4, 8, 10],
    "6":        [0, 4, 7, 9],   # Major 6th
    "m6":       [0, 3, 7, 9],   # Minor 6th

    "9":        [0, 4, 7, 10, 14], # Dominant 9th
    "maj9":     [0, 4, 7, 11, 14], # Major 9th
    "m9":       [0, 3, 7, 10, 14], # Minor 9th
    "add9":     [0, 4, 7, 14],     # Add 9
    "m(add9)":  [0, 3, 7, 14],     # Minor add 9
    "6/9":      [0, 4, 7, 9, 14],  # 6/9 Chord
    "7b9":      [0, 4, 7, 10, 13],
    "7#9":      [0, 4, 7, 10, 15],

    "11":       [0, 4, 7, 10, 14, 17], # Dominant 11th
    "m11":      [0, 3, 7, 10, 14, 17], # Minor 11th
    "maj7#11":  [0, 4, 7, 11, 18],     # Lydian chord
    "13":       [0, 4, 7, 10, 14, 21], # Dominant 13th
    "maj13":    [0, 4, 7, 11, 14, 21], # Major 13th
    "m13":      [0, 3, 7, 10, 14, 21]  # Minor 13th
}

# --- Function to generate the full map ---
def generate_full_chord_map(note_map, formula_map):
    """
    Generates a comprehensive chord map for all root notes.
    """
    full_map = {}
    for root_name, root_midi in note_map.items():
        # Generate for all 12 root notes, not just non-sharps
        for chord_suffix, intervals in formula_map.items():
            chord_name = f"{root_name}{chord_suffix}"
            full_map[chord_name] = [root_midi + i for i in intervals]
    return full_map

if __name__ == "__main__":
    expanded_chord_map = generate_full_chord_map(NOTE_MAP, CHORD_FORMULAS)
    # Ensure the directory exists
    os.makedirs("knowledge_base", exist_ok=True)
    filename = "knowledge_base/chords.json"

    with open(filename, 'w') as f:
        json.dump(expanded_chord_map, f, indent=2)

    print(f"✅ Chord map with {len(expanded_chord_map)} chords successfully saved to {filename}")  # noqa: E501
