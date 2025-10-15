import io

import pretty_midi
import streamlit as st

from melodycomp.agent import MelodyCompAgent
from melodycomp.melody_generator import generate_melody_for_chords

st.set_page_config(layout="wide")
st.title("🎵 Melodycomp")
st.write("Your AI creative partner for music composition. Start by describing an idea!")

@st.cache_resource
def load_agent():
    """Load the MelodyCompAgent once and cache it."""
    try:
        return MelodyCompAgent()
    except Exception as e:
        st.error(f"Failed to load agent: {e}")
        return None

agent = load_agent()

# --- State Management ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "notes_json" not in st.session_state:
    st.session_state.notes_json = None
if "chords" not in st.session_state:
    st.session_state.chords = None
if "tips" not in st.session_state:
    st.session_state.tips = None
if "melody_instrument" not in st.session_state:
    st.session_state.melody_instrument = None

if not agent:
    st.warning("Agent could not be loaded. Please check the console for errors.")
else:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # --- Chat Input ---
    if prompt := st.chat_input("What's your musical idea?"):
        st.session_state.chords = None
        st.session_state.notes_json = None
        st.session_state.tips = None
        st.session_state.melody_instrument = None

        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response_data = agent.run_conversation(prompt)

                if response_data and response_data.get("chords"):
                    st.session_state.chords = response_data["chords"]
                    st.session_state.notes_json = response_data["notes"]
                    st.session_state.tips = response_data.get(
                        "tips",
                        "No tips were generated."
                    )

                    chords_str = " -> ".join(st.session_state.chords)
                    response_content = f"Here is a progression for you:\n```\n{chords_str}\n```" # noqa: E501
                    st.markdown(response_content)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": response_content}
                    )
                else:
                    response_content = "Sorry, I couldn't generate a valid progression. Please try again." # noqa: E501
                    st.error(response_content)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": response_content}
                    )
        st.rerun()

    # --- Tips and Melody Generation Section ---
    if st.session_state.chords:
        st.markdown("---")

        if st.session_state.tips:
            with st.expander("💡 Tips & Theory", expanded=True):
                st.markdown(st.session_state.tips)

        if st.button("✨ Generate a Melody", use_container_width=True):
            with st.spinner("Composing a melody..."):
                melody = generate_melody_for_chords(st.session_state.chords)
                st.session_state.melody_instrument = melody if melody else False
                st.rerun()

        if st.session_state.melody_instrument is False:
            st.warning(
                "Could not generate a melody for this progression. Please try again."
            )


    # --- MIDI Download Section ---
    if st.session_state.notes_json:
        st.markdown("---")
        st.markdown("#### Downloads")

        chord_instrument = pretty_midi.Instrument(
            program=pretty_midi.instrument_name_to_program("Acoustic Grand Piano")
        )
        for note_data in st.session_state.notes_json:
            note = pretty_midi.Note(
                velocity=note_data["velocity"],
                pitch=note_data["pitch"],
                start=note_data["start_time"],
                end=note_data["end_time"]
            )
            chord_instrument.notes.append(note)


        num_cols = 3 if st.session_state.melody_instrument else 1
        cols = st.columns(num_cols)

        with cols[0]:
            chord_midi_io = io.BytesIO()
            chord_midi = pretty_midi.PrettyMIDI()
            chord_midi.instruments.append(chord_instrument)
            chord_midi.write(chord_midi_io)
            chord_midi_io.seek(0)
            st.download_button(
                label="📥 Download Chords",
                data=chord_midi_io,
                file_name="chords.mid",
                mime="audio/midi",
                use_container_width=True
            )

        melody_instrument = st.session_state.melody_instrument
        if melody_instrument:
            with cols[1]:
                melody_midi_io = io.BytesIO()
                melody_midi = pretty_midi.PrettyMIDI()
                melody_midi.instruments.append(melody_instrument)
                melody_midi.write(melody_midi_io)
                melody_midi_io.seek(0)
                st.download_button(
                    label="📥 Download Melody",
                    data=melody_midi_io,
                    file_name="melody.mid",
                    mime="audio/midi",
                    use_container_width=True
                )

            with cols[2]:
                combined_midi_io = io.BytesIO()
                combined_midi = pretty_midi.PrettyMIDI()
                combined_midi.instruments.append(chord_instrument)
                combined_midi.instruments.append(melody_instrument)
                combined_midi.write(combined_midi_io)
                combined_midi_io.seek(0)
                st.download_button(
                    label="📥 Download Combined",
                    data=combined_midi_io,
                    file_name="combined.mid",
                    mime="audio/midi",
                    use_container_width=True
                )
