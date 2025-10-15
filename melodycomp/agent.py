import ast
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import chromadb
import yaml

# from google import generativeai as genai
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

from .local_llm import MLX


class MelodyCompAgent:
    def __init__(
        self,
        local: bool = False,
        **kwargs
    ) -> None:
        print("..Building agent with knowledge base..")

        if not os.path.exists("knowledge_base/chords.json"):
            os.system("python gen_chord_lib.py")
        with open("knowledge_base/chords.json", "r") as f:
            self.chord_library = json.load(f)
        self._load_scales_config()
        print("✅ Chord library loaded.")

        try:
            with open("knowledge_base/finetuning_data.json", "r") as f:
                self.finetuning_examples = json.load(f)
            print(f"✅ Loaded {len(self.finetuning_examples)} few-shot examples.")
        except FileNotFoundError:
            print("⚠️ finetuning_data.json not found. The agent will run without dynamic examples.")  # noqa: E501
            self.finetuning_examples = []

        self.local = local
        if self.local:
            self.model = MLX.from_model_path("mlx-community/Qwen3-8B-4bit", temp=0.7)
        else:
            with open("./configs/config.yaml", "r") as f:
                config = yaml.safe_load(f)
                api_key = config.get("gemini_api_key")
            if not api_key:
                raise ValueError("Gemini API key not found in ./configs/config.yaml")
            # genai.configure(api_key=api_key)
            # self.model = genai.GenerativeModel("gemini-2.5-flash")
            self.model = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=api_key,
                temperature=0.7
            )

        # Setup ChromaDB client and collections
        self.client = chromadb.Client()
        self.genre_collection = self._setup_genre_collection()
        self.examples_collection = self._setup_examples_collection()

        self.memory = ConversationBufferMemory(
            return_messages=True,
            memory_key="memory",
            input_key="input"
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are an expert music theorist and composer.
            You will receive context about genre and a specific chord palette.
            Your task is to generate a Python list of chord names that fulfills the user's request.
            The last chord in the sequence should not be the same as the last, unless the user specifically has asked for it.
            Your final output must be ONLY the Python list of chord names.

            ## AVAILABLE CHORDS (PALETTE)
            {chord_palette}

            ## CONTEXT ON GENRE
            {genre_context}
            """ # noqa E501
            ),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ])
        self.conversation_chain = (
            {
                "input": lambda x: x["input"],
                "genre_context": lambda x: x["genre_context"],
                "chord_palette": lambda x: x["chord_palette"],
                "history": RunnableLambda(self.memory.load_memory_variables) | (lambda x: x.get("history", [])) # noqa E501,
            }
            | self.prompt
            | self.model
        )

        print("✅ Agent ready!")

    def _load_scales_config(
        self,
        config_path: str = "knowledge_base/scales.yaml"
    ) -> None:
        """
        Loads music theory configuration from YAML file.
        Falls back to hardcoded values if file doesn't exist.
        """
        if not os.path.exists(config_path):
            print(f"⚠️ {config_path} not found. Using fallback scale configuration.")
            self._load_fallback_scales()
            return

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.NOTES: List[str] = config.get('notes', [])
        self.SCALE_INTERVALS: Dict[str, List[int]] = config.get("scale_intervals", {})
        self.CHORD_TYPES_PER_DEGREE: Dict[str, List[List[str]]] = config.get(
            "chord_types_per_degree", {}
        )

        # Validate configuration
        if not self.NOTES or not self.SCALE_INTERVALS or not self.CHORD_TYPES_PER_DEGREE:  # noqa: E501
            print("⚠️ Incomplete scales configuration. Using fallback.")
            self._load_fallback_scales()
            return

        available_modes = list(self.SCALE_INTERVALS.keys())
        print(f"✅ Scales config loaded: {len(available_modes)} modes available")
        print(f"   Available modes: {', '.join(available_modes)}")

    def _setup_genre_collection(
        self,
        name: str = "genre-knowledge",
        knowledge_base_path: str = "knowledge_base/genres",
    ) -> chromadb.Collection:
        """
        Reads all .md files from the knowledge base, embeds them, and stores them
        in a ChromaDB collection. Creates the collection if it doesn't exist.
        """
        collection = self.client.get_or_create_collection(name=name)

        all_chunks = []
        all_ids = []
        all_metadatas = []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            length_function=len
        )
        if os.path.exists(knowledge_base_path):
            for filename in os.listdir(knowledge_base_path):
                if filename.endswith(".md"):
                    genre_id = filename.split(".")[0]
                    with open(os.path.join(knowledge_base_path, filename), "r") as f:
                        for i, chunk in enumerate(text_splitter.split_text(f.read())):
                            chunk_id = f"{genre_id}-{i}"
                            all_chunks.append(chunk)
                            all_ids.append(chunk_id)
                            all_metadatas.append({"genre": genre_id})

            if all_ids:
                collection.add(
                    ids=all_ids,
                    documents=all_chunks,
                    metadatas=all_metadatas
                )

        print(f"✅ Collection '{collection.name}' is set up with {collection.count()} documents.")  # noqa: E501
        return collection

    def _setup_examples_collection(
        self,
        name: str = "few-shot-examples"
    ) -> chromadb.Collection:
        """
        Creates a ChromaDB collection for few-shot examples and indexes them.
        Uses semantic embeddings instead of keyword matching.
        """
        collection = self.client.get_or_create_collection(name=name)

        # Only add examples if collection is empty and we have examples to add
        if collection.count() == 0 and self.finetuning_examples:
            documents = []
            ids = []
            metadatas = []

            for i, example in enumerate(self.finetuning_examples):
                documents.append(example["instruction"])
                ids.append(f"example_{i}")
                metadatas.append({
                    "output": example["output"],
                    "instruction": example["instruction"]
                })

            collection.add(
                documents=documents,
                ids=ids,
                metadatas=metadatas
            )
            print(f"✅ Indexed {len(documents)} few-shot examples in vector DB.")
        else:
            print(f"✅ Few-shot examples collection has {collection.count()} examples.")

        return collection

    def _get_few_shot_examples(
        self,
        query: str,
        n_examples: int = 2
    ) -> str:
        """
        Finds the most relevant examples using semantic similarity via ChromaDB.
        Replaces the old keyword-based matching method.
        """
        if self.examples_collection.count() == 0:
            return ""

        results = self.examples_collection.query(
            query_texts=[query],
            n_results=min(n_examples, self.examples_collection.count())
        )

        if not results["documents"][0]:
            return ""

        formatted_examples = "### HIGH-QUALITY EXAMPLES\n"
        for i, (instruction, metadata, distance) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        )):
            # Convert distance to similarity score (lower distance = higher similarity)
            similarity_score = 1 - distance
            formatted_examples += f"Example {i+1} (Similarity: {similarity_score:.3f}):\n"  # noqa: E501
            formatted_examples += f"- Request: \"{instruction}\"\n"
            formatted_examples += f"- Response: {metadata['output']}\n\n"

        return formatted_examples

    def _query_knowledge_base(
        self,
        collection: chromadb.Collection,
        query: str,
        n_results: int = 5
    ) -> str:
        """
        Queries the collection and formats the results into a single context string.
        """
        if collection.count() == 0:
            return "No genre context available."

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count())
        )
        retrieved_docs = results["documents"][0]
        context = "\n\n---\n\n".join(retrieved_docs)
        return context

    def _parse_key_from_query(
        self,
        query: str
    ) -> Optional[Tuple[str, str]]:
        """
        Parses a query like "...in A# minor..." and returns the root and mode.
        Now supports all modes defined in scales.yaml.
        """
        available_modes = list(self.SCALE_INTERVALS.keys())
        mode_aliases = {
            "ionian": "major",
            "aeolian": "minor"
        }

        all_modes = available_modes + list(mode_aliases.keys())
        modes_pattern = "|".join(all_modes)

        pattern = rf"in\s+([A-G][#b]?)\s+({modes_pattern})"
        match = re.search(pattern, query, re.IGNORECASE)

        if match:
            root = match.group(1)
            mode = match.group(2).lower()

            # Convert aliases
            if mode in mode_aliases:
                mode = mode_aliases[mode]

            # Validate mode exists in configuration
            if mode not in self.SCALE_INTERVALS:
                print(f"⚠️ Mode '{mode}' not found in configuration. Available: {', '.join(available_modes)}")
                return None

            return root, mode

        return None

    def _get_diatonic_palette(
        self,
        root: str,
        mode: str
    ) -> List[str]:
        """
        Generates diatonic triads, 7ths, and their valid extensions for a given key.
        loads from scales.yaml config.

        Args:
            root: Root note (e.g., "C", "F#", "Bb")
            mode: Scale/mode name (e.g., "major", "harmonic_minor", "dorian")

        Returns:
            List of chord names that exist in the chord library and are diatonic to the key.
        """  # noqa: E501
        # Validate mode
        if mode not in self.SCALE_INTERVALS:
            available_modes = ', '.join(self.SCALE_INTERVALS.keys())
            print(f"⚠️ Invalid mode '{mode}'. Available: {available_modes}")
            return []

        # Validate root note
        if root not in self.NOTES:
            print(f"⚠️ Invalid root note '{root}'. Must be one of: {self.NOTES}")
            return []

        root_index = self.NOTES.index(root)
        intervals = self.SCALE_INTERVALS[mode]
        chord_qualities_for_mode = self.CHORD_TYPES_PER_DEGREE[mode]

        # Verify chord qualities list matches scale length
        if len(chord_qualities_for_mode) != len(intervals):
            print(f"⚠️ Configuration error: Chord qualities length ({len(chord_qualities_for_mode)}) "  # noqa: E501
                  f"doesn't match scale intervals ({len(intervals)}) for mode '{mode}'")
            return []

        full_palette = []

        for degree_index in range(len(intervals)):
            note_index = (root_index + intervals[degree_index]) % 12
            note_name = self.NOTES[note_index]

            for quality in chord_qualities_for_mode[degree_index]:
                chord_name = f"{note_name}{quality}"

                if chord_name in self.chord_library:
                    full_palette.append(chord_name)

        return list(dict.fromkeys(full_palette))

    def _chords_to_notes_json(
        self,
        chords: list,
        duration_per_chord: float = 2.0
    ) -> List:
        notes = []
        current_time = 0.0
        note_map = {"C": 60, "C#": 61, "Db": 61, "D": 62, "D#": 63, "Eb": 63, "E": 64,
                    "F": 65, "F#": 66, "Gb": 66, "G": 67, "G#": 68, "Ab": 68, "A": 69,
                    "A#": 70, "Bb": 70, "B": 71}
        for chord_name in chords:
            chord_name = chord_name.strip()
            root_match = re.match(r"([A-G][#b]?)", chord_name)
            if not root_match:
                continue
            root_note = root_match.group(1)
            quality = chord_name[len(root_note):]
            base_chord_name = "C" + quality
            base_chord_notes = self.chord_library.get(base_chord_name)
            if not base_chord_notes:
                continue
            transposition = note_map.get(root_note, 60) - 60
            for base_pitch in base_chord_notes:
                transposed_pitch = base_pitch + transposition
                notes.append({
                    "pitch": transposed_pitch,
                    "velocity": 100,
                    "start_time": current_time,
                    "end_time": current_time + duration_per_chord
                })
            current_time += duration_per_chord
        return notes

    def run_conversation(
        self,
        user_input: str
    ) -> Dict | None:
        genre_context = self._query_knowledge_base(
            collection=self.genre_collection,
            query=user_input,
        )
        key_info = self._parse_key_from_query(user_input)
        if key_info:
            root, mode = key_info #
            palette = self._get_diatonic_palette(root, mode) #
            chord_palette_str = f"You MUST primarily use chords from this list: \n- {', '.join(palette)}\n" # noqa: E501
        else:
            chord_palette_str = "No specific key was requested. You are free to choose."

        inputs = {
            "input": user_input,
            "genre_context": genre_context,
            "chord_palette": chord_palette_str,
        }

        response = self.conversation_chain.invoke(inputs)
        if hasattr(response, "content"):
            model_output_str = response.content
        else:
            model_output_str = response

        self.memory.save_context(inputs, {"output": model_output_str})

        try:
            match = re.search(r"\[.*\]", model_output_str, re.DOTALL) #
            if match:
                chords_list = ast.literal_eval(match.group(0)) #
            else:
                raise ValueError("No valid list found in model output.") #

            final_notes_json = self._chords_to_notes_json(chords=chords_list)
            tips_and_tricks = self._generate_music_theory_tips(user_input, chords_list)

            return {
                "chords": chords_list,
                "notes": final_notes_json,
                "tips": tips_and_tricks
            }

        except (ValueError, SyntaxError):
            print(f"--- ERROR: Could not parse chord list from model ---\nRaw output: {model_output_str}") # noqa: E501
            return None

    def _generate_music_theory_tips(
        self,
        original_prompt: str,
        chords: list
    ) -> str:
        """Generates musical tips based on the user's request and the generated chords.
        TODO: Add functionality here, probably some RAG for getting better tips and tricks?""" # noqa: E501
        chords_str = " -> ".join(chords)
        tips_prompt = f"""
            A user requested the following: "{original_prompt}".
            The chord progression generated was: {chords_str}.

            Based on this, provide 2-3 brief, helpful music theory or production tips.
            Also, suggest one or two alternative musical scales that would be excellent for improvising a melody over these chords.
            Format your response as markdown.
        """ # noqa: E501
        response = self.model.invoke(tips_prompt)
        return response.content


def main():
    """Main function to run the agent for testing."""
    try:
        agent = MelodyCompAgent(local=False)
        query = "I want a 16-bar atmospheric trip-hop progression in A minor that builds tension towards the end" # noqa: E501

        result1 = agent.run_conversation(query=query, n_results=5, temp=0.2)
        if result1:
            print("\n--- Progression 1 ---")
            print(result1["chords"])

            result2 = agent.run(query=query, previous_progression=result1["chords"], n_results=5, temp=0.5) # noqa: E501
            if result2:
                print("\n--- Progression 2 (Variation) ---")
                print(result2["chords"])
    except (FileNotFoundError, ValueError) as e:
        print(f"Could not run agent: {e}")


if __name__ == "__main__":
    main()
