"""LLM provider abstraction using LangChain."""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel


@dataclass
class Message:
    """A message in the conversation."""

    role: str  # "system", "user", "assistant"
    content: str

    def to_langchain(self) -> BaseMessage:
        """Convert to LangChain message format."""
        if self.role == "system":
            return SystemMessage(content=self.content)
        elif self.role == "assistant":
            return AIMessage(content=self.content)
        else:
            return HumanMessage(content=self.content)


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw_response: Any = None


class LLMProvider:
    """LLM provider wrapper using LangChain."""

    def __init__(
        self,
        model: BaseChatModel,
        model_name: str = "unknown",
    ):
        """Initialize the provider.

        Args:
            model: LangChain chat model instance
            model_name: Name of the model for logging
        """
        self.model = model
        self.model_name = model_name
        self._str_parser = StrOutputParser()

    async def complete(
        self,
        messages: list[Message],
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion from the LLM.

        Args:
            messages: List of messages in the conversation
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in the response
            stop: Stop sequences

        Returns:
            LLMResponse with the generated content
        """
        langchain_messages = [msg.to_langchain() for msg in messages]

        # Build kwargs for invoke
        kwargs: dict[str, Any] = {}
        if stop:
            kwargs["stop"] = stop

        response = await self.model.ainvoke(langchain_messages, **kwargs)

        # Extract usage if available
        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.get("input_tokens", 0),
                "completion_tokens": response.usage_metadata.get("output_tokens", 0),
                "total_tokens": response.usage_metadata.get("total_tokens", 0),
            }

        return LLMResponse(
            content=response.content if isinstance(response.content, str) else str(response.content),
            model=self.model_name,
            usage=usage,
            raw_response=response,
        )

    async def complete_structured(
        self,
        messages: list[Message],
        output_schema: type[BaseModel],
        temperature: float | None = None,
    ) -> BaseModel:
        """Generate a structured output from the LLM.

        Args:
            messages: List of messages in the conversation
            output_schema: Pydantic model for structured output
            temperature: Sampling temperature

        Returns:
            Parsed Pydantic model instance
        """
        langchain_messages = [msg.to_langchain() for msg in messages]

        # Use with_structured_output for reliable parsing
        structured_model = self.model.with_structured_output(output_schema)
        result = await structured_model.ainvoke(langchain_messages)

        return result

    def create_chain(
        self,
        system_prompt: str,
        output_parser: Any | None = None,
    ):
        """Create a reusable chain with system prompt.

        Args:
            system_prompt: System message for the chain
            output_parser: Optional output parser

        Returns:
            LangChain chain
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        if output_parser:
            return prompt | self.model | output_parser
        return prompt | self.model | self._str_parser

    def create_structured_chain(
        self,
        system_prompt: str,
        output_schema: type[BaseModel],
    ):
        """Create a chain with structured output.

        Args:
            system_prompt: System message for the chain
            output_schema: Pydantic model for output

        Returns:
            LangChain chain with structured output
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        structured_model = self.model.with_structured_output(output_schema)
        return prompt | structured_model
