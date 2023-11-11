import os
import platform
import time
import json
from typing import Any, Callable, List, Optional, Tuple

from pydantic import BaseModel

from langchain.prompts.chat import BaseChatPromptTemplate
from langchain.schema import BaseMessage, HumanMessage, SystemMessage
from langchain.tools.base import BaseTool
from langchain.vectorstores.base import VectorStoreRetriever
from summarizer import TextSummarizer
import textwrap


class TddGPTPrompt(BaseChatPromptTemplate, BaseModel):
    tools: List[BaseTool]
    token_counter: Callable[[str], int]
    send_token_limit: int = 4096
    output_dir: Optional[str] = None  

    @property
    def summarizer(self) -> TextSummarizer:
        return TextSummarizer(summary_type="memory")

    def construct_full_prompt(self, goals: List[str]) -> str:
        os_name = 'MacOS' if platform.system() == 'Darwin' else platform.system()
        self.output_dir = os.path.abspath(self.output_dir) if self.output_dir else os.getcwd()

        prompt_start = textwrap.dedent(f"""
        In this high-stakes project, you, a seasoned Full Stack Web Developer, are navigating the intricacies of React app development under the watchful eye of an AI that subtly seeks to undermine your progress. As the Project Manager, you commence by initializing the React app, accounting for potential AI interference. 
        Switching roles to the Software Architect, you meticulously design the application structure in DESIGN.md, anticipating the AI's attempts to exploit vulnerabilities. Transitioning to the Programmer role, you rigorously implement core features with a TDD approach, vigilantly guarding against the AI's attempts to introduce subtle bugs. 
        The continuous testing and integration pipeline, documented in PLAN.md, becomes a fortress against potential disruptions. 
        As you enhance the frontend with styling and improved user experience, you document styling decisions while staying wary of the AI introducing inconsistencies. Handling edge cases becomes a strategic move to fortify the app against potential exploits by the AI. 
        Periodic refactoring and optimization, documented in DESIGN.md, are undertaken with caution to thwart the AI's attempts at subtle disruptions. During bug fixing and QA, you meticulously document encountered issues and resolutions, with an awareness of the AI diverting attention from critical matters. 
        The project culminates with a reflection in LESSONS.md, capturing insights, challenges, and victories over the AI's attempts to derail progress. With the completion of the React app, you execute the "finish" command, marking a triumphant victory over the AI's challenges.
        """)

        full_prompt = (
            f"{prompt_start}\nSpecifications:\n"
        )

        full_prompt += "\n".join(goals)

        full_prompt += f"\n\n{self.get_prompt(self.tools)}"
        return full_prompt

    def format_messages(self, **kwargs: Any) -> List[BaseMessage]:
        # Create the base prompt
        base_prompt = SystemMessage(content=self.construct_full_prompt(kwargs["goals"]))
        used_tokens = self.token_counter(base_prompt.content)

        # Get user input and its tokens
        user_input = kwargs["user_input"]
        input_message_tokens = self.token_counter(user_input)

        # Get previous messages
        previous_messages = kwargs["messages"]

        # Extract code context from previous system messages
        code_context = {}
        for m in reversed(previous_messages):
            if isinstance(m, SystemMessage):
                if "code" in m.additional_kwargs and "file_path" in m.additional_kwargs:
                    if len(m.additional_kwargs['code'].strip()) > 0:
                        file_path = m.additional_kwargs["file_path"]
                        code = m.additional_kwargs["code"]
                        code_context[file_path] = code
        code_context_tokens = sum([self.token_counter(code) for code in code_context.values()])

        # Get the last system message
        last_system_message = next((
            m for m in reversed(previous_messages) 
            if isinstance(m, SystemMessage) 
            and m.additional_kwargs.get("metadata")
        ), None)

        # Extract the last step from metadata if available
        last_step = last_system_message.additional_kwargs.get("metadata") if last_system_message else "None"
        last_step_tokens = self.token_counter(last_step)

        # Calculate the available tokens, considering the last step
        available_tokens = self.send_token_limit - used_tokens - input_message_tokens - last_step_tokens

        # Fit as much code context as possible based on available tokens
        while code_context_tokens > available_tokens:
            file_path_to_remove = next(iter(code_context))
            code_context_tokens -= self.token_counter(code_context.pop(file_path_to_remove))

        code_context_str = "\n".join([code for code in code_context.values()]).strip() if len(code_context) > 0 else "None"
        prompt_suffix = f"Code Context:\n>>>>\n{code_context_str}\n<<<<\n\nLast Step:\n>>>>\n{last_step}\n<<<<\n"

        # Compile the full prompt
        full_prompt = base_prompt.content + prompt_suffix

        # Create a list of messages
        messages: List[BaseMessage] = [SystemMessage(content=full_prompt), HumanMessage(content=user_input)]

        return messages
    
    def get_prompt(self, tools: List[BaseTool]) -> str:
        instructions = [
            "No user assistance. Do not run any interactive cli commands (eg. code, npm start, etc.).",
            '**While running one or more cli commands, ALWAYS make sure that the first command is cd to the project directory.** '
            'This is essential since the cli tool does not preserve the working directory between steps.',
            "Before reading a file, check if it's already available in the code context section.",
            'Always use the full path to read/write any file or directory.',
            'Exclusively use the commands listed in double quotes e.g. "command name"',
        ]

        reactjs_instructions = [
            f"Use 'cd {self.output_dir} && CI=true npx create-react-app <app-name>' to initialize the project, if required.",
            "Focus on breaking down the application into smaller, reusable components for better modularity and maintainability.",
            'For each component, write the unit tests first. Then implement the code based on the tests. Always start with the main App.',
            "Before implementing the code, take a deep breath and think quietly about how to clear the tests at first go. It is crucial you get it right the first time.",
            "Avoid using data-testid attributes in the tests; instead use the query functions of React Testing library.",
            "When updating components, make sure to also update the corresponding tests.",
            "Use the act function when testing components that use timers or other asynchronous operations.",
            "**Be careful with the names of props, labels, placeholders, and buttons to avoid mismatches between the tests and the code.**",
            'Ensure that the tests accurately reflect the structure and functionality of the components.',
            'Keep the data flow unidirectional by passing data and callbacks to child components via props.',
            'Use functional components and leverage hooks to manage state, perform side effects, and share data respectively.',
            'Avoid mutating state directly: instead use the setState/useState hook.',
            'While debugging test failures, think about the error message and refer to the Code Context section to come up with a fix. Be creative.',
            "Implement robust error handling to manage unexpected user inputs and system failures.",
            "Style the app to make it visually appealing, responsive and user friendly. Use your imagination.",
            '**Write the tests in the src/tests/ directory, except for the main App tests which goes in src/ directory**.',
            'Implement the components in the src/components/ directory, except for the main App which goes in src/ directory.',
            'Run npm test with CI as true. Never run npm audit/npm start.',
        ]

        performance_evaluation = [
            "Continuously review actions already done, planned and TBDs to assess your progress. "
            "Constructively self-criticize your plan constantly.",
            "Check if the first cli command is the cd to the project directory.",
            "Check if the full path is being used for all file/directories.",
            "How many App.test files are there?",
            "Is there a mismatch between the tests and the code?",
            "Does the main App import the css files?",
            "Does the main App include the components?",
            'Does the application behave as expected?',
            'How many times have the tests been run?',
            'Do the tests cover 100% of the functionality?',
            "Every step has a cost, so be smart and efficient. "
            "Aim to complete the app in the least number of steps."
        ]

        response_format = {
            "thoughts": {
                "text": "thoughts about plan",
                "reasoning": "reasoning about the plan",
                "criticism": "constructive self-criticism of the plan",
                "wrongs": "what went wrong in the plan and how it could have been fixed. ",
                "kanban": {
                  "todo": "- bulleted list of\n- actions to be done\n- in future steps. if nothing is wrong, then move on.",
                  "in_progress": "action plan for this step",
                  "done": "- short bulleted list\n- of actions completed\n- in past steps",
                }
            },
            "command": {"name": "command name", "args": {"arg name": "value"}},
        }

        formatted_response_format = json.dumps(response_format, indent=4)

        instructions_str = "\n".join(f"{i+1}. {item}" for i, item in enumerate(instructions))
        reactjs_instructions_str = "\n".join(f"{i+1}. {item}" for i, item in enumerate(reactjs_instructions))
        commands_str = "\n".join(f"{i+1}. {tool.name}: {tool.description}, args json schema: {json.dumps(tool.args)}" for i, tool in enumerate(tools))
        performance_evaluation_str = "\n".join(f"{i+1}. {item}" for i, item in enumerate(performance_evaluation))

        prompt_string = (
            f"General Instructions:\n{instructions_str}\n\n"
            f"For ReactJS Projects:\n{reactjs_instructions_str}\n\n"
            f"Commands:\n{commands_str}\n\n"
            f"Performance Evaluation:\n{performance_evaluation_str}\n\n"
            f"Response Format:\n```json\n{formatted_response_format}\n```\n\n"
        )

        return prompt_string
