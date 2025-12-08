"""
Created on 2025-12-08

@author: wf
"""

from dataclasses import field
from pathlib import Path
from typing import Dict, List, Optional

from basemkit.yamlable import lod_storable
from ngwidgets.llm import LLM, VisionLLM


@lod_storable
class APIConfig:
    """API configuration for LLM services"""

    base_url: str = "https://openrouter.ai/api/v1"


@lod_storable
class ModelConfig:
    """Configuration for an LLM model"""

    name: str  # ✓ Full OpenRouter model ID (e.g., google/gemini-2.0-flash-001)
    provider: str  # provider e.g. google
    description: Optional[str] = None
    context_length: Optional[int] = None
    price_per_mtoken: Optional[float] = None
    input_types: List[str] = field(
        default_factory=lambda: ["text"]
    )  # ✓ vision, text, etc.

    @classmethod
    def from_openai_model(cls, model) -> "ModelConfig":
        """
        Create ModelConfig from an OpenAI API model.

        Args:
            model: OpenAI model object from client.models.list()

        Returns:
            ModelConfig: Populated instance
        """
        # Extract provider from model ID (e.g., "google" from "google/gemini-2.0-flash-001")
        provider = model.id.split("/")[0] if "/" in model.id else "unknown"

        # Price: average of prompt + completion, in $/million tokens
        price_per_mtoken = None
        pricing = getattr(model, "pricing", None)
        if pricing:
            avg_price = (float(pricing["prompt"]) + float(pricing["completion"])) / 2
            if avg_price > 0:
                price_per_mtoken = avg_price * 1_000_000

        # Input types from architecture modalities
        input_types = ["text"]  # Text is always supported
        arch = getattr(model, "architecture", {})
        modalities = arch.get("input_modalities", [])

        # Map modalities to input types
        for modality in modalities:
            if modality in ["image", "audio", "video"] and modality not in input_types:
                input_types.append(modality)

        model_config = cls(
            name=model.id,
            provider=provider,
            context_length=getattr(model, "context_length", None),  # ✓ Fixed field name
            price_per_mtoken=price_per_mtoken,
            input_types=input_types,  # ✓ Fixed field name
        )
        return model_config


@lod_storable
class TaskConfig:
    """Configuration for an AI task"""

    prompt: str
    model: Optional[str] = None  # ✓ Key from models dict (e.g., "gemini2")
    description: Optional[str] = None
    task_type: str = "text"


@lod_storable
class AITasks:
    """Complete AI configuration"""

    api: APIConfig = field(default_factory=APIConfig)
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    tasks: Dict[str, TaskConfig] = field(default_factory=dict)
    _instance: Optional["AITasks"] = None
    _llms: Dict[str, LLM] = field(default_factory=dict)

    @classmethod
    def get_instance(cls, yaml_file_path: str = None):
        """Get singleton instance"""
        if cls._instance is None:
            if yaml_file_path is None:
                examples_path = Path(__file__).parent.parent / "scan2wiki_examples"
                yaml_file_path = examples_path / "ai_tasks.yaml"
            cls.yaml_file_path = yaml_file_path
            cls._instance = cls.load_from_yaml_file(yaml_file_path)
        return cls._instance

    def perform_task(
        self,
        task_name: str,
        model_name: Optional[str] = None,  # ✓ Now optional
        prompt_override: Optional[str] = None,
        **params,
    ) -> str:
        """
        Perform AI task with configured or override settings.

        Args:
            task_name: Name of task from configuration
            model_name: Optional model key override (e.g., "gemini2")
            prompt_override: Optional custom prompt
            **params: Task parameters (e.g., image_path)

        Returns:
            str: LLM response
        """
        # ✓ Validate task
        if task_name not in self.tasks:
            available = ", ".join(self.tasks.keys())
            raise ValueError(f"Unknown task '{task_name}'. Available: {available}")

        task = self.tasks[task_name]

        # ✓ Determine model (task default or override)
        if model_name is None:
            model_name = task.model
            if model_name is None:
                raise ValueError(f"No model specified for task '{task_name}'")

        # ✓ Validate model
        if model_name not in self.models:
            available = ", ".join(self.models.keys())
            raise ValueError(f"Unknown model '{model_name}'. Available: {available}")

        model = self.models[model_name]

        # ✓ Validate task type support
        if task.task_type not in model.task_types:
            raise ValueError(
                f"Model '{model_name}' does not support task type '{task.task_type}'. "
                f"Supported: {', '.join(model.task_types)}"
            )

        # ✓ Get or create LLM instance
        llm_cache_key = f"{model_name}-{task.task_type}"

        if llm_cache_key not in self._llms:
            # ✓ Use model.name (full OpenRouter ID), not model_name (config key)
            if task.task_type == "vision":
                self._llms[llm_cache_key] = VisionLLM(
                    model=model.name,  # ✓ FIX: Use full model ID
                    base_url=self.api.base_url,
                )
            else:
                self._llms[llm_cache_key] = LLM(
                    model=model.name,  # ✓ FIX: Use full model ID
                    base_url=self.api.base_url,
                )

        llm = self._llms[llm_cache_key]

        # ✓ Determine prompt
        prompt = prompt_override if prompt_override else task.prompt

        # ✓ Execute task
        if task.task_type == "vision":
            if "image_path" not in params:
                raise ValueError(
                    f"Vision task '{task_name}' requires 'image_path' parameter"
                )

            return llm.analyze_image(
                image_path=params["image_path"], prompt_text=prompt
            )
        else:
            return llm.ask(prompt=prompt, model=model.name)  # ✓ Use full model ID
