from typing import Any, List, Mapping, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler


class MLX(LLM):
    """MLX wrapper for Langchain LLM compatibility"""
    model: Any
    tokenizer: Any
    sampler: Any
    model_path: str

    @classmethod
    def from_model_path(cls, model_path: str, temp: float = 0.5, top_p: float = 0.9):
        """Load the model and tokenizer from a given path."""
        model, tokenizer = load(model_path)
        sampler = make_sampler(temp=temp, top_p=top_p)
        return cls(
            model=model,
            tokenizer=tokenizer,
            sampler=sampler,
            model_path=model_path
        )

    @property
    def _llm_type(self) -> str:
        return "mlx"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:

        response = generate(
            model=self.model,
            tokenizer=self.tokenizer,
            prompt=prompt,
            sampler=self.sampler,
            max_tokens=kwargs.get("max_tokens", 512),
        )

        if stop:
            for stop_word in stop:
                if stop_word in response:
                    response = response.split(stop_word)[0]

        return response

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters."""
        return {"model_path": self.model_path}
