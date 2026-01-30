"""Graph-based agent using LangGraph for complex workflows."""

from typing import Annotated, TypedDict
from operator import add

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from patcher.llm.factory import get_model
from patcher.agents.tools import create_all_tools


class AgentState(TypedDict):
    """State for the graph agent."""

    messages: Annotated[list[BaseMessage], add]
    issue_number: int | None
    pr_number: int | None
    iteration: int
    max_iterations: int
    status: str
    error: str | None


class GraphAgent:
    """Graph-based agent for complex multi-step workflows using LangGraph."""

    def __init__(
        self,
        github_client=None,
        provider_name: str | None = None,
        max_iterations: int = 5,
    ):
        """Initialize the graph agent.

        Args:
            github_client: GitHubClient instance
            provider_name: LLM provider name
            max_iterations: Maximum iterations for the workflow
        """
        self.github_client = github_client
        self.max_iterations = max_iterations

        # Create LLM with tools
        self.llm = get_model(provider_name=provider_name)
        self.tools = create_all_tools(github_client)
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        # Build the graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow.

        Returns:
            Compiled StateGraph
        """
        # Create tool node
        tool_node = ToolNode(self.tools)

        # Define the graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("check_iteration", self._check_iteration_node)

        # Set entry point
        workflow.set_entry_point("agent")

        # Add edges
        workflow.add_conditional_edges(
            "agent",
            self._should_use_tools,
            {
                "tools": "tools",
                "check": "check_iteration",
                "end": END,
            },
        )
        workflow.add_edge("tools", "agent")
        workflow.add_conditional_edges(
            "check_iteration",
            self._should_continue,
            {
                "continue": "agent",
                "end": END,
            },
        )

        return workflow.compile()

    async def _agent_node(self, state: AgentState) -> dict:
        """Agent node that decides next action.

        Args:
            state: Current state

        Returns:
            Updated state
        """
        messages = state["messages"]
        response = await self.llm_with_tools.ainvoke(messages)

        return {"messages": [response]}

    def _check_iteration_node(self, state: AgentState) -> dict:
        """Check iteration count and update status.

        Args:
            state: Current state

        Returns:
            Updated state
        """
        iteration = state.get("iteration", 0) + 1
        return {"iteration": iteration}

    def _should_use_tools(self, state: AgentState) -> str:
        """Determine if tools should be used.

        Args:
            state: Current state

        Returns:
            Next node name
        """
        messages = state["messages"]
        last_message = messages[-1]

        # Check if the model wants to use tools
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # Check if we're done or should continue
        if state.get("status") == "completed":
            return "end"

        return "check"

    def _should_continue(self, state: AgentState) -> str:
        """Determine if workflow should continue.

        Args:
            state: Current state

        Returns:
            'continue' or 'end'
        """
        iteration = state.get("iteration", 0)
        max_iterations = state.get("max_iterations", self.max_iterations)

        if iteration >= max_iterations:
            return "end"

        status = state.get("status", "")
        if status in ["completed", "failed"]:
            return "end"

        return "continue"

    async def run(
        self,
        initial_message: str,
        issue_number: int | None = None,
        pr_number: int | None = None,
    ) -> AgentState:
        """Run the graph agent workflow.

        Args:
            initial_message: Initial message/task for the agent
            issue_number: Optional issue number
            pr_number: Optional PR number

        Returns:
            Final state
        """
        initial_state: AgentState = {
            "messages": [HumanMessage(content=initial_message)],
            "issue_number": issue_number,
            "pr_number": pr_number,
            "iteration": 0,
            "max_iterations": self.max_iterations,
            "status": "running",
            "error": None,
        }

        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)
        return final_state

    async def process_issue(self, issue_number: int) -> AgentState:
        """Process a GitHub issue using the graph workflow.

        Args:
            issue_number: Issue number to process

        Returns:
            Final state
        """
        message = f"""Process GitHub issue #{issue_number}.

1. First, get the issue details using the get_issue_details tool
2. Analyze the requirements
3. List relevant files in the repository
4. Read the files that need to be modified
5. Generate a plan for implementing the changes

Provide a detailed implementation plan based on your analysis."""

        return await self.run(message, issue_number=issue_number)

    async def review_pr(self, pr_number: int) -> AgentState:
        """Review a pull request using the graph workflow.

        Args:
            pr_number: PR number to review

        Returns:
            Final state
        """
        message = f"""Review pull request #{pr_number}.

1. Get the PR details using the get_pr_details tool
2. Get the PR diff using the get_pr_diff tool
3. Check the CI status using the get_ci_status tool
4. Analyze the code changes for issues
5. Provide a comprehensive review

Include:
- Overall assessment
- Any issues found (bugs, security, style)
- Whether the changes meet the requirements
- Recommendation (approve or request changes)"""

        return await self.run(message, pr_number=pr_number)


def create_issue_processing_graph(github_client, llm) -> StateGraph:
    """Create a specialized graph for issue processing.

    Args:
        github_client: GitHubClient instance
        llm: LLM instance

    Returns:
        Compiled StateGraph for issue processing
    """

    class IssueState(TypedDict):
        """State for issue processing."""

        messages: Annotated[list[BaseMessage], add]
        issue_number: int
        requirements: dict | None
        files_to_change: list[str]
        implementation_plan: str | None
        code_changes: list[dict]
        status: str

    def analyze_issue(state: IssueState) -> dict:
        """Analyze the issue and extract requirements."""
        # This would use the LLM to analyze
        return {"status": "requirements_extracted"}

    def plan_implementation(state: IssueState) -> dict:
        """Create implementation plan."""
        return {"status": "planned"}

    def generate_code(state: IssueState) -> dict:
        """Generate code changes."""
        return {"status": "code_generated"}

    def validate_code(state: IssueState) -> dict:
        """Validate generated code."""
        return {"status": "validated"}

    def create_pr(state: IssueState) -> dict:
        """Create pull request."""
        return {"status": "pr_created"}

    # Build the graph
    workflow = StateGraph(IssueState)

    workflow.add_node("analyze", analyze_issue)
    workflow.add_node("plan", plan_implementation)
    workflow.add_node("generate", generate_code)
    workflow.add_node("validate", validate_code)
    workflow.add_node("create_pr", create_pr)

    workflow.set_entry_point("analyze")
    workflow.add_edge("analyze", "plan")
    workflow.add_edge("plan", "generate")
    workflow.add_edge("generate", "validate")

    # Conditional edge for validation
    def check_validation(state: IssueState) -> str:
        if state.get("status") == "validated":
            return "create_pr"
        return "generate"  # Retry generation

    workflow.add_conditional_edges(
        "validate",
        check_validation,
        {"create_pr": "create_pr", "generate": "generate"},
    )
    workflow.add_edge("create_pr", END)

    return workflow.compile()
