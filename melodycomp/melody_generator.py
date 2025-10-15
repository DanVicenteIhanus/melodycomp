import json
import re
from typing import Dict, List

import google.generativeai as genai
import pretty_midi
import streamlit as st
import yaml
from llama_cpp import Llama


@st.cache_resource
def load_melody_model():
    """Load the Llama model once and cache it."""
    print("--- LOADING MELODY MODEL (llama-cpp-python) ---")
    return Llama(
        model_path="./models/chatmusician.Q4_K_M.gguf",
        n_gpu_layers=-1,
        n_ctx=2048,
        verbose=False
    )

llm = load_melody_model()


def convert_abc_to_notes_json(raw_abc: str) -> List[Dict]:
    """
    Uses Gemini to convert a raw (potentially malformed) ABC string
    into a structured JSON list of notes.
    """
    with open("./configs/config.yaml", "r")  as f:
        cfg = yaml.safe_load(f)
        api_key = cfg.get("gemini_api_key")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""
    You are an expert music notation converter. Your task is to interpret the following raw ABC notation and convert it into a clean JSON array of note objects.

    RULES:
    1. The time signature is 4/4.
    2. The default note length (L:) is 1/8. This means a duration of "1" is an eighth note. A quarter note has a duration of "2". A half note has a duration of "4".
    3. Calculate the start time for each note sequentially. The first note starts at time 0.
    4. The output MUST be only a valid JSON array and nothing else.
    5. Durations in the final JSON should be in quarter notes (e.g., an eighth note has a duration of 0.5, a quarter note is 1.0).

    EXAMPLE:
    Input ABC: | "C" C2 G2 "G" G z |
    Output JSON:
    [
      {{"pitch": "C4", "start_time": 0.0, "duration": 1.0}},
      {{"pitch": "G4", "start_time": 1.0, "duration": 1.0}},
      {{"pitch": "G4", "start_time": 2.0, "duration": 0.5}},
      {{"pitch": "rest", "start_time": 2.5, "duration": 0.5}}
    ]

    Now, convert this raw ABC input:
    ---
    {raw_abc}
    ---
    """ # noqa: E501

    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1}
        )

        json_text = response.text.strip()
        if json_text.startswith("```json"):
            json_text = json_text[7:]
        if json_text.startswith("```"):
            json_text = json_text[3:]
        if json_text.endswith("```"):
            json_text = json_text[:-3]

        print("\n--- GEMINI CONVERTED JSON ---")
        print(json_text)
        print("-----------------------------\n")

        return json.loads(json_text)
    except Exception as e:
        print(f"🔴 Gemini JSON conversion failed: {e}")
        return []


def generate_melody_for_chords(chords: List[str]) -> pretty_midi.Instrument:
    chord_str = ", ".join([f"'{c}'" for c in chords])

    instruction = f"Develop a simple, single-line musical piece using the given chord progression. {chord_str} in the key of {chord_str[0].split()[0]}" # noqa: E501
    prompt = f"Human: {instruction} </s> Assistant: M:4/4\nL:1/8\nK:C\n"

    output = llm(prompt, max_tokens=1024, temperature=0.8, stop=["Human:", "</s>"])
    raw_response_text = output["choices"][0]["text"].strip()

    notes_list = convert_abc_to_notes_json(raw_response_text)

    if not notes_list:
        print("⚠️ Melody generation failed after JSON conversion.")
        return None

    melody_instrument = pretty_midi.Instrument(
        program=pretty_midi.instrument_name_to_program("Violin")
    )
    note_map = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

    for note_info in notes_list:
        if note_info["pitch"].lower() == "rest":
            continue

        try:
            pitch_name = note_info["pitch"]
            duration = float(note_info["duration"])
            start_time = float(note_info["start_time"])

            base_pitch_name = pitch_name[0].upper()
            octave = 4
            accidental = 0

            octave_match = re.search(r"(\d+)$", pitch_name)
            if octave_match:
                octave = int(octave_match.group(1))

            if "#" in pitch_name:
                accidental = 1
            elif "b" in pitch_name:
                accidental = -1

            midi_note_number = 12 * (octave + 1) + note_map[base_pitch_name] + accidental # noqa: E501

            note = pretty_midi.Note(
                velocity=100,
                pitch=midi_note_number,
                start=start_time,
                end=start_time + duration
            )
            melody_instrument.notes.append(note)

        except (KeyError, ValueError, TypeError) as e:
            print(f"⚠️ Skipping malformed note object from JSON: {note_info}. Error: {e}") # noqa: E501
            continue

    return melody_instrument
