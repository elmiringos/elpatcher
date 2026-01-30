"""Code Agent for processing issues and generating code using LangGraph."""

import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, TypedDict

from operator import add

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from patcher.agents.base import BaseAgent, AgentContext
from patcher.agents.tools import create_code_analysis_tools, create_github_tools
from patcher.github.models import IssueData, FileChange as GHFileChange, CIResult, CIStatus
from patcher.llm.schemas import CodeGeneration, FileChange
from patcher.state.models import AgentState as PatcherAgentState, IterationStatus
from patcher.state.manager import StateManager


@dataclass
class CodeAgentResult:
    """Result of code agent execution."""

    success: bool
    pr_url: str | None = None
    pr_number: int | None = None
    changes: list[GHFileChange] | None = None
    iteration_count: int = 0
    error: str | None = None


class AgentState(TypedDict):
    """State for the LangGraph code agent."""

    messages: Annotated[list[BaseMessage], add]
    issue_number: int
    issue: IssueData | None
    repo_context: str | None
    implementation_plan: str | None
    code_changes: list[dict] | None
    iteration: int
    status: str
    error: str | None


SYSTEM_PROMPT = """You are a skilled software engineer. Your task is to analyze GitHub issues and implement the required changes.

You have access to tools to explore and understand the codebase:
- read_file: Read source code files
- search_code: Search for patterns using ripgrep
- find_definition: Find where functions/classes are defined
- find_references: Find all usages of a symbol
- get_repository_map: Get an overview of the codebase structure with symbols
- list_files: List files in directories
- detect_languages: Detect programming languages used

Workflow:
1. FIRST use detect_languages to identify the PRIMARY programming language
2. Use get_repository_map to understand the codebase structure
3. Read relevant files to understand existing patterns and code style
4. Search for related code using search_code and find_definition
5. Based on your analysis, generate the implementation IN THE SAME LANGUAGE

Guidelines:
- CRITICAL: Write code in the SAME programming language as the existing codebase
- Follow the existing code style, naming conventions, and patterns exactly
- Write clean, maintainable code following best practices for that language
- Include appropriate error handling
- Create or update tests when appropriate
- Keep changes focused and minimal - only change what's necessary

IMPORTANT RESTRICTIONS:
- NEVER create or modify GitHub Actions workflow files (.github/workflows/*.yml or *.yaml)
- NEVER create or modify CI/CD configuration files
- Focus only on source code, tests, and documentation
- If the issue asks for workflow changes, explain that this is not supported"""


class CodeAgent(BaseAgent):
    """Agent that processes issues and generates code using LangGraph with tools."""

    def __init__(self, context: AgentContext):
        """Initialize the code agent."""
        super().__init__(context)
        self.state_manager = StateManager(self.github)
        self._local_repo_path: Path | None = None

        # Create structured output chain for code generation
        self._code_chain = self.llm.create_structured_chain(
            system_prompt=SYSTEM_PROMPT,
            output_schema=CodeGeneration,
        )

    def _ensure_local_repo(self) -> Path:
        """Ensure repository is cloned locally.

        Returns:
            Path to local repository
        """
        if self._local_repo_path is None:
            self._log_info("Cloning repository for analysis...")
            self._local_repo_path = self.github.clone_repo()
            self._log_info(f"Repository cloned to {self._local_repo_path}")
        return self._local_repo_path

    def _create_tools(self, repo_path: Path) -> list:
        """Create tools for the agent.

        Args:
            repo_path: Path to local repository

        Returns:
            List of LangChain tools
        """
        github_tools = create_github_tools(self.github)
        code_tools = create_code_analysis_tools(repo_path)
        return github_tools + code_tools

    def _build_graph(self, tools: list) -> StateGraph:
        """Build the LangGraph workflow.

        Args:
            tools: List of tools for the agent

        Returns:
            Compiled StateGraph
        """
        # Create LLM with tools
        llm_with_tools = self.llm.model.bind_tools(tools)

        # Tool node
        tool_node = ToolNode(tools)

        async def agent_node(state: AgentState) -> dict:
            """Main agent node that decides actions."""
            messages = state["messages"]
            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        def should_continue(state: AgentState) -> str:
            """Determine next step based on last message."""
            messages = state["messages"]
            last_message = messages[-1]

            # If LLM wants to use tools
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"

            # Check iteration limit
            if state.get("iteration", 0) >= 10:  # Max tool iterations
                return "generate"

            # If we have enough context, move to code generation
            return "generate"

        async def generate_code_node(state: AgentState) -> dict:
            """Generate the final code changes."""
            # Collect context from conversation
            messages = state["messages"]
            context_parts = []

            for msg in messages:
                if isinstance(msg, AIMessage) and msg.content:
                    context_parts.append(msg.content)

            context = "\n\n".join(context_parts[-5:])  # Last 5 messages

            return {
                "repo_context": context,
                "status": "ready_for_generation",
            }

        def increment_iteration(state: AgentState) -> dict:
            """Increment iteration counter."""
            return {"iteration": state.get("iteration", 0) + 1}

        # Build graph
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("increment", increment_iteration)
        workflow.add_node("generate", generate_code_node)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                "generate": "generate",
            },
        )
        workflow.add_edge("tools", "increment")
        workflow.add_edge("increment", "agent")
        workflow.add_edge("generate", END)

        return workflow.compile()

    async def run(
        self,
        issue_number: int,
        dry_run: bool = False,
    ) -> CodeAgentResult:
        """Process an issue and create a PR.

        Args:
            issue_number: GitHub issue number
            dry_run: If True, don't create PR

        Returns:
            CodeAgentResult with outcome
        """
        try:
            # Fetch issue
            self._log_info(f"Fetching issue #{issue_number}")
            issue = self.github.get_issue(issue_number)

            # Clone repo for local analysis
            repo_path = self._ensure_local_repo()

            # Create tools and build graph
            tools = self._create_tools(repo_path)
            graph = self._build_graph(tools)

            # Create initial message with task
            initial_message = f"""Analyze this GitHub issue and prepare to implement the required changes.

Issue #{issue.number}: {issue.title}

{issue.body}

Steps:
1. Use get_repository_map to understand the codebase structure
2. Identify which files need to be modified or created
3. Read the relevant existing files to understand the code patterns
4. Search for related code and dependencies
5. Summarize your findings and the implementation approach

After exploration, I will generate the actual code changes."""

            initial_state: AgentState = {
                "messages": [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=initial_message),
                ],
                "issue_number": issue_number,
                "issue": issue,
                "repo_context": None,
                "implementation_plan": None,
                "code_changes": None,
                "iteration": 0,
                "status": "exploring",
                "error": None,
            }

            # Run the exploration graph
            self._log_info("Exploring codebase with agent...")
            final_state = await graph.ainvoke(initial_state)

            # Now generate actual code using structured output
            self._log_info("Generating code changes...")
            code_gen = await self._generate_code(issue, final_state.get("repo_context", ""))

            # Check if code generation failed (empty files from fallback)
            if not code_gen.files:
                error_msg = code_gen.explanation if hasattr(code_gen, 'explanation') else "No files generated"
                self._log_error(f"Code generation produced no files: {error_msg}")
                return CodeAgentResult(
                    success=False,
                    error=f"Code generation failed: {error_msg}",
                )

            # Convert to GitHub FileChange format
            changes = [
                GHFileChange(
                    path=f.path,
                    content=f.content,
                    status="added" if f.action == "create" else "modified",
                )
                for f in code_gen.files
            ]

            if dry_run:
                self._log_info("Dry run - skipping PR creation")
                return CodeAgentResult(
                    success=True,
                    changes=changes,
                    iteration_count=1,
                )

            # Get default branch from repository
            default_branch = self.github.default_branch
            self._log_info(f"Repository default branch: {default_branch}")

            # Create branch and PR
            branch_name = self._generate_branch_name(issue)
            self._log_info(f"Creating branch: {branch_name}")
            self.github.create_branch(branch_name, default_branch)

            # Commit changes
            self._log_info("Committing changes")
            files_dict = {change.path: change.content for change in changes}
            commit_sha = self.github.commit_changes(
                files=files_dict,
                message=f"feat: {issue.title}\n\nResolves #{issue_number}",
                branch=branch_name,
            )

            # Create state
            state = PatcherAgentState(
                issue_number=issue_number,
                branch_name=branch_name,
                requirements_hash=self._hash_requirements(issue.body),
            )
            state.add_iteration(
                status=IterationStatus.AWAITING_REVIEW,
                changes=[c.path for c in changes],
            )
            if state.current_iteration:
                state.current_iteration.commit_sha = commit_sha

            # Create PR
            self._log_info("Creating pull request")
            pr_body = self._generate_pr_body(issue, code_gen, changes, state)
            pr = self.github.create_pull_request(
                title=f"feat: {issue.title}",
                body=pr_body,
                head=branch_name,
                base=default_branch,
                labels=["ai-review", "elpatcher"],
            )

            # Update state with PR number
            state.pr_number = pr.number
            self.state_manager.save_to_pr(pr.number, state)

            return CodeAgentResult(
                success=True,
                pr_url=pr.url,
                pr_number=pr.number,
                changes=changes,
                iteration_count=1,
            )

        except Exception as e:
            self._log_error(f"Code agent failed: {e}")
            return CodeAgentResult(
                success=False,
                error=str(e),
            )

    async def iterate(
        self,
        pr_number: int,
        state: PatcherAgentState,
    ) -> CodeAgentResult:
        """Continue iterating on a PR based on CI failures or review feedback.

        Priority:
        1. First check for CI failures and fix them
        2. If no CI failures, check for review feedback

        Args:
            pr_number: PR number
            state: Current agent state

        Returns:
            CodeAgentResult with outcome
        """
        try:
            self._log_info(f"Processing iteration for PR #{pr_number}")

            # Clone repo for local analysis
            repo_path = self._ensure_local_repo()

            # Update local repo to latest
            self._log_info("Updating local repository...")
            self.github.pull_latest(state.branch_name)

            # Get original issue
            issue = self.github.get_issue(state.issue_number)

            # Create tools and build graph for analysis
            tools = self._create_tools(repo_path)
            graph = self._build_graph(tools)

            # PRIORITY 1: Check for CI failures first
            self._log_info("Checking CI status...")
            ci_result = await self._get_ci_failures(pr_number)

            if ci_result:
                self._log_info("CI failures detected, generating fixes...")

                # Analyze CI failures
                ci_failures = [
                    f"{check.name}: {check.output or 'Failed'}"
                    for check in ci_result.checks
                    if check.status == CIStatus.FAILURE
                ]

                initial_message = f"""CI failures detected for PR #{pr_number}. Analyze and fix them.

Original Issue #{issue.number}: {issue.title}
{issue.body}

CI Failures:
{chr(10).join(ci_failures)}

Steps:
1. Understand what each CI check is failing on
2. Read the files that have errors
3. Fix the issues to make CI pass

After analysis, I will generate the fixed code."""

                initial_state: AgentState = {
                    "messages": [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=initial_message),
                    ],
                    "issue_number": state.issue_number,
                    "issue": issue,
                    "repo_context": None,
                    "implementation_plan": None,
                    "code_changes": None,
                    "iteration": 0,
                    "status": "analyzing_ci_failures",
                    "error": None,
                }

                self._log_info("Analyzing CI failures with agent...")
                final_state = await graph.ainvoke(initial_state)

                # Generate CI fixes
                code_gen = await self._generate_ci_fixes(
                    issue, ci_result, final_state.get("repo_context", "")
                )
                commit_message = f"fix: resolve CI failures\n\nIteration {state.iteration_count + 1}"

            else:
                # PRIORITY 2: Check for review feedback
                self._log_info("No CI failures, checking review feedback...")
                feedback = await self._get_review_feedback(pr_number)

                if not feedback:
                    self._log_info("No CI failures or review feedback found")
                    return CodeAgentResult(
                        success=True,
                        pr_url=self.github.get_pr(pr_number).url,
                        iteration_count=state.iteration_count,
                    )

                self._log_info("Processing review feedback...")

                initial_message = f"""Review feedback received for PR #{pr_number}. Analyze and prepare fixes.

Original Issue #{issue.number}: {issue.title}
{issue.body}

Review Feedback:
{feedback}

Steps:
1. Understand the feedback and what needs to be fixed
2. Read the files that were mentioned or need changes
3. Search for related code if needed
4. Prepare the fixes

After analysis, I will generate the fixed code."""

                initial_state: AgentState = {
                    "messages": [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=initial_message),
                    ],
                    "issue_number": state.issue_number,
                    "issue": issue,
                    "repo_context": None,
                    "implementation_plan": None,
                    "code_changes": None,
                    "iteration": 0,
                    "status": "analyzing_feedback",
                    "error": None,
                }

                self._log_info("Analyzing feedback with agent...")
                final_state = await graph.ainvoke(initial_state)

                # Generate fixes based on feedback
                code_gen = await self._generate_fixes(
                    issue, feedback, final_state.get("repo_context", "")
                )
                commit_message = f"fix: address review feedback\n\nIteration {state.iteration_count + 1}"

            # Check if fix generation failed (empty files from fallback)
            if not code_gen.files:
                error_msg = code_gen.explanation if hasattr(code_gen, 'explanation') else "No fixes generated"
                self._log_error(f"Fix generation produced no files: {error_msg}")
                return CodeAgentResult(
                    success=False,
                    error=f"Fix generation failed: {error_msg}",
                    iteration_count=state.iteration_count,
                )

            changes = [
                GHFileChange(
                    path=f.path,
                    content=f.content,
                    status="modified",
                )
                for f in code_gen.files
            ]

            # Commit changes
            self._log_info("Committing fixes")
            files_dict = {change.path: change.content for change in changes}
            commit_sha = self.github.commit_changes(
                files=files_dict,
                message=commit_message,
                branch=state.branch_name,
            )

            # Update state
            iteration = state.add_iteration(
                status=IterationStatus.AWAITING_REVIEW,
                changes=[c.path for c in changes],
            )
            iteration.commit_sha = commit_sha

            # Store feedback (CI failures or review feedback)
            if ci_result:
                ci_failures_text = "\n".join(
                    f"{check.name}: {check.output or 'Failed'}"
                    for check in ci_result.checks
                    if check.status == CIStatus.FAILURE
                )
                iteration.review_feedback = f"[CI Fixes]\n{ci_failures_text}"
                iteration.ci_status = "failed"
            else:
                iteration.review_feedback = feedback
                iteration.ci_status = "passed"

            self.state_manager.save_to_pr(pr_number, state)

            return CodeAgentResult(
                success=True,
                pr_url=self.github.get_pr(pr_number).url,
                changes=changes,
                iteration_count=state.iteration_count,
            )

        except Exception as e:
            self._log_error(f"Iteration failed: {e}")
            return CodeAgentResult(
                success=False,
                error=str(e),
                iteration_count=state.iteration_count,
            )

    def _detect_primary_language(self) -> tuple[str, dict[str, int]]:
        """Detect the primary programming language in the repository.

        Returns:
            Tuple of (primary_language, all_languages_dict)
        """
        from patcher.code.analyzer import CodeAnalyzer

        try:
            analyzer = CodeAnalyzer(self._local_repo_path)
            languages = analyzer.detect_languages()

            if languages:
                primary = list(languages.keys())[0]  # Most common language
                return primary, languages
            return "unknown", {}
        except Exception:
            return "unknown", {}

    async def _generate_code(
        self,
        issue: IssueData,
        repo_context: str,
    ) -> CodeGeneration:
        """Generate code changes using structured output.

        Args:
            issue: GitHub issue
            repo_context: Context from codebase exploration

        Returns:
            Structured code generation with file changes
        """
        from langchain_core.messages import HumanMessage

        # Detect primary language
        primary_lang, all_langs = self._detect_primary_language()
        lang_summary = ", ".join(f"{k}: {v} files" for k, v in list(all_langs.items())[:5])

        self._log_info(f"Primary language detected: {primary_lang}")

        prompt = f"""Based on the codebase analysis, implement the changes for this issue.

IMPORTANT: This repository uses **{primary_lang.upper()}** as the primary language.
Languages in repo: {lang_summary}

You MUST write all code in **{primary_lang.upper()}** following the existing patterns.

Issue #{issue.number}: {issue.title}
{issue.body}

Codebase Analysis:
{repo_context[:8000]}

Generate the complete content for each file that needs to be created or modified.
For each file, specify:
- path: the file path relative to repository root
- content: complete file content (in {primary_lang.upper()})
- action: 'create' for new files, 'modify' for existing files

CRITICAL: Follow the existing code patterns, naming conventions, and style found in the repository.
Write code ONLY in {primary_lang.upper()}."""

        try:
            result = await self._code_chain.ainvoke({
                "messages": [HumanMessage(content=prompt)],
            })
            return result
        except Exception as e:
            # Fallback if structured output parsing fails (e.g., invalid unicode escapes)
            self._log_warning(f"Structured output failed: {e}, using fallback")
            return CodeGeneration(
                files=[],
                explanation=f"Code generation failed due to parsing error: {e}",
            )

    async def _generate_fixes(
        self,
        issue: IssueData,
        feedback: str,
        repo_context: str,
    ) -> CodeGeneration:
        """Generate fixes based on review feedback.

        Args:
            issue: Original issue
            feedback: Review feedback
            repo_context: Context from analysis

        Returns:
            Structured code generation with fixes
        """
        from langchain_core.messages import HumanMessage

        # Detect primary language
        primary_lang, _ = self._detect_primary_language()

        prompt = f"""Fix the code based on this review feedback.

IMPORTANT: This repository uses **{primary_lang.upper()}** as the primary language.

Original Issue #{issue.number}: {issue.title}
{issue.body}

Review Feedback:
{feedback}

Analysis:
{repo_context[:5000]}

Generate the fixed content for each file that needs changes.
Address all the feedback points in your fixes.
Write all code in **{primary_lang.upper()}**.

For each file, specify:
- path: the file path
- content: complete fixed file content (in {primary_lang.upper()})
- action: 'modify' for existing files"""

        try:
            result = await self._code_chain.ainvoke({
                "messages": [HumanMessage(content=prompt)],
            })
            return result
        except Exception as e:
            # Fallback if structured output parsing fails (e.g., invalid unicode escapes)
            self._log_warning(f"Structured output failed: {e}, using fallback")
            return CodeGeneration(
                files=[],
                explanation=f"Fix generation failed due to parsing error: {e}",
            )

    async def _generate_ci_fixes(
        self,
        issue: IssueData,
        ci_result: CIResult,
        repo_context: str,
    ) -> CodeGeneration:
        """Generate fixes based on CI failures.

        Args:
            issue: Original issue
            ci_result: CI result with failures
            repo_context: Context from analysis

        Returns:
            Structured code generation with CI fixes
        """
        from langchain_core.messages import HumanMessage

        # Collect failure details
        failures = []
        for check in ci_result.checks:
            if check.status == CIStatus.FAILURE:
                failure_info = f"**{check.name}**"
                if check.output:
                    failure_info += f":\n```\n{check.output[:2000]}\n```"
                failures.append(failure_info)

        if not failures:
            return CodeGeneration(
                files=[],
                explanation="No CI failures to fix",
            )

        failures_text = "\n\n".join(failures)

        # Detect primary language
        primary_lang, _ = self._detect_primary_language()

        prompt = f"""Analyze and fix the CI failures for this PR.

IMPORTANT: This repository uses **{primary_lang.upper()}** as the primary language.

Original Issue #{issue.number}: {issue.title}
{issue.body}

CI Failures:
{failures_text}

Repository Context:
{repo_context[:5000]}

Analyze each CI failure and generate fixes (in {primary_lang.upper()}):

1. For linting errors (ruff, flake8, eslint):
   - Identify the exact line and error
   - Fix formatting, imports, or style issues

2. For type errors (mypy, pyright):
   - Fix type annotations
   - Add missing types
   - Correct type mismatches

3. For test failures (pytest, jest):
   - Analyze the assertion error
   - Fix the implementation (not the test unless test is wrong)
   - Ensure the fix aligns with requirements

4. For build/syntax errors:
   - Fix syntax errors
   - Resolve import issues

Generate the fixed content for each file that needs changes.
Write all code in **{primary_lang.upper()}**.

For each file, specify:
- path: the file path
- content: complete fixed file content (in {primary_lang.upper()})
- action: 'modify' for existing files

IMPORTANT: Only fix what's needed to pass CI. Don't refactor or add new features."""

        try:
            result = await self._code_chain.ainvoke({
                "messages": [HumanMessage(content=prompt)],
            })
            return result
        except Exception as e:
            self._log_warning(f"Structured output failed: {e}, using fallback")
            return CodeGeneration(
                files=[],
                explanation=f"CI fix generation failed due to parsing error: {e}",
            )

    async def _get_ci_failures(self, pr_number: int) -> CIResult | None:
        """Get CI failures for a PR.

        Args:
            pr_number: PR number

        Returns:
            CIResult if there are failures, None otherwise
        """
        try:
            ci_result = self.github.get_ci_status(pr_number)

            # Check if there are any failures
            has_failures = any(
                check.status == CIStatus.FAILURE
                for check in ci_result.checks
            )

            if has_failures:
                return ci_result
            return None
        except Exception as e:
            self._log_warning(f"Failed to get CI status: {e}")
            return None

    async def _get_review_feedback(self, pr_number: int) -> str | None:
        """Get the latest review feedback from PR.

        Args:
            pr_number: PR number

        Returns:
            Review feedback or None
        """
        try:
            pr = self.github.repo.get_pull(pr_number)
            reviews = list(pr.get_reviews())

            # Get the latest review with feedback
            for review in reversed(reviews):
                if review.state == "CHANGES_REQUESTED" and review.body:
                    return review.body

            # Check for review comments
            comments = list(pr.get_review_comments())
            if comments:
                feedback_parts = []
                for comment in comments[-5:]:  # Last 5 comments
                    feedback_parts.append(f"- {comment.path}: {comment.body}")
                return "\n".join(feedback_parts)

            # Check for issue comments with @patcher mention
            issue_comments = list(pr.get_issue_comments())
            for comment in reversed(issue_comments[-10:]):
                if "@patcher" in comment.body.lower() or "/patcher" in comment.body.lower():
                    return comment.body

            return None
        except Exception:
            return None

    def _generate_branch_name(self, issue: IssueData) -> str:
        """Generate a branch name from issue.

        Args:
            issue: GitHub issue

        Returns:
            Branch name
        """
        # Sanitize title for branch name
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", issue.title.lower())
        slug = slug.strip("-")[:40]
        return f"patcher/issue-{issue.number}-{slug}"

    def _generate_pr_body(
        self,
        issue: IssueData,
        code_gen: CodeGeneration,
        changes: list[GHFileChange],
        state: PatcherAgentState,
    ) -> str:
        """Generate PR body/description.

        Args:
            issue: GitHub issue
            code_gen: Generated code
            changes: File changes
            state: Agent state

        Returns:
            PR body markdown
        """
        files_list = "\n".join(f"- `{c.path}` ({c.status})" for c in changes)

        body = f"""## Summary

Resolves #{issue.number}

## Changes

{files_list}

## Implementation Notes

{code_gen.explanation if hasattr(code_gen, 'explanation') and code_gen.explanation else 'See code changes above.'}

---
*This PR was automatically generated by Patcher AI Agent*

{self.state_manager.format_state_for_pr(state)}"""

        return body

    @staticmethod
    def _hash_requirements(body: str) -> str:
        """Create a hash of requirements for change detection.

        Args:
            body: Issue body

        Returns:
            Hash string
        """
        return hashlib.sha256(body.encode()).hexdigest()[:16]
