import os
import json
import shutil
import asyncio
from pathlib import Path
import jinja2
from glob import glob
from pydantic import BaseModel, ValidationError, create_model
from typing import Any, Dict, List, Optional, Union
from code_blocks import CodeBlocks  # Import the CodeBlocks class
import re  # For extracting code blocks


class Code2Prompt:
    def __init__(self, options: Dict[str, Any]):
        self.options = options
        self.extensions = options.get('extensions', [])
        self.ignore_patterns = options.get('ignore', [])
        self.schema = options.get('schema')
        self.code_blocks = []
        self.QA_recordings = {}
        self.last_QA_session = None
        self.full_source_tree = False
        self.binary = False
        self.custom_viewers = options.get('custom_viewers', {})
        self.OPENAI_KEY = options.get('OPENAI_KEY')
        self.GROQ_KEY = options.get('GROQ_KEY')
        self.ANTHROPIC_KEY = options.get('ANTHROPIC_KEY')
        self.max_bytes_per_file = options.get('max_bytes_per_file', 8192)
        self.debugger = options.get('debugger', False)
        self.model_preferences = ["OPENAI", "ANTHROPIC", "GROQ"]
        self.template = None

    async def initialize(self):
        await self.load_and_register_template(self.options.get('template'))

    def debug(self, message: str):
        if self.debugger:
            print(f'[code2prompt]: {message}')

    def set_model_preferences(self, preferences: List[str]):
        self.model_preferences = preferences
        self.debug(f'Model preferences updated: {json.dumps(preferences)}')

    def set_llm_api(self, provider: str, value: str) -> bool:
        if provider == 'ANTHROPIC':
            self.ANTHROPIC_KEY = value
            return True
        elif provider == 'GROQ':
            self.GROQ_KEY = value
            return True
        elif provider == 'OPENAI':
            self.OPENAI_KEY = value
            return True
        return False

    def register_file_viewer(self, ext: str, method: callable):
        self.custom_viewers[ext] = method
        self.debug(f'Viewer registered for {ext}')

    def record_QA(self, session: str = ''):
        self.last_QA_session = session
        if session not in self.QA_recordings:
            self.QA_recordings[session] = []

    def get_QA_recordings(self, session: str):
        return self.QA_recordings.get(session, [])

    async def extract_code_blocks_from_template(self, template_content: str) -> List[Dict[str, str]]:
        # Regex to find code blocks in the template
        code_block_pattern = r'```(?P<lang>[\w:]+)?\n(?P<code>.*?)```'
        matches = re.finditer(code_block_pattern, template_content, re.DOTALL)
        
        code_blocks = []
        for match in matches:
            lang = match.group('lang')
            code = match.group('code')
            if lang and code:
                code_blocks.append({
                    'lang': lang,
                    'code': code
                })
        return code_blocks

    async def load_and_register_template(self, template_path: str = None):
        if not template_path:
            # Default template path
            template_path = os.path.join('templates', 'default.md.j2')

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template file not found: {template_path}")

        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        self.template = jinja2.Template(template_content)

        # Extract code blocks after loading the template
        self.code_blocks = await self.extract_code_blocks_from_template(template_content)

    async def read_content(self, file_path: str, max_bytes: int = None) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read(max_bytes)

    async def traverse_directory(self, dir_path: str, max_bytes: int = None) -> Dict[str, Union[str, List[Dict[str, str]]]]:
        tree = {}
        files_array = []
        absolute_path = os.path.abspath(dir_path)

        for root, _, files in os.walk(absolute_path):
            for file in files:
                extension = Path(file).suffix.lower()
                relative_path = os.path.relpath(os.path.join(root, file), absolute_path)

                if not self.extensions or extension[1:] in self.extensions:
                    if extension in self.custom_viewers:
                        content = await self.custom_viewers[extension](os.path.join(root, file))
                    else:
                        content = await self.read_content(os.path.join(root, file), max_bytes)

                    files_array.append({"path": relative_path, "code": content})
                    parts = relative_path.split(os.sep)
                    current = tree
                    for part in parts[:-1]:
                        current = current.setdefault(part, {})
                    current[parts[-1]] = relative_path

        source_tree = self.stringify_tree(tree)
        return {"absolute_path": absolute_path, "source_tree": source_tree, "files_array": files_array}

    def stringify_tree(self, tree: dict, prefix: str = '') -> str:
        result = ''
        keys = list(tree.keys())
        for index, key in enumerate(keys):
            is_last = index == len(keys) - 1
            result += f"{prefix}{'└── ' if is_last else '├── '}{key}\n"
            if isinstance(tree[key], dict):
                result += self.stringify_tree(tree[key], f"{prefix}{'    ' if is_last else '|   '}")
        return result

    async def execute_blocks(self, pre: bool = True, context_: dict = None) -> dict:
        if context_ is None:
            context_ = {}

        code_helper = CodeBlocks()
        for block in self.code_blocks:
            if (pre and block['lang'].endswith(':pre')) or (not pre and ':' not in block['lang']):
                if 'python' in block['lang']:
                    code_executed = await code_helper.execute_python(context_, block['code'])
                    context_.update(code_executed)
                elif 'bash' in block['lang']:
                    code_executed = await code_helper.execute_bash(context_, block['code'])
                    context_.update(code_executed)

        return context_

    async def run_template(self, prompt: str = '', methods: dict = None, context: dict = None) -> dict:
        if methods is None:
            methods = {}
        if context is None:
            context = {}

        base_methods = {
            "queryLLM": self.query_LLM,
            "queryContext": self.request,
            "extractCodeBlocks": self.extract_code_blocks_from_template  # Correct method name
        }

        methods.update(base_methods)

        context_prompt = await self.generate_context_prompt(None, True, context)
        context_ = context_prompt['context']  # Initialize context_ with context from context_prompt

        context_ = await self.execute_blocks(True, context_)
        context_ = await self.execute_blocks(False, context_)

        return context_


    async def generate_context_prompt(self, template: str = None, obj: bool = False, variables: dict = None) -> dict:
        if template:
            await self.load_and_register_template(template)

        variables_ = variables or {}
        traverse_result = await self.traverse_directory(self.options['path'], self.max_bytes_per_file)
        variables_.update(traverse_result)

        rendered = self.template.render(variables_)

        if obj:
            return {"context": variables_, "rendered": rendered}
        return rendered

    async def query_LLM(self, prompt: str = '', schema: BaseModel = None) -> Optional[Dict[str, Any]]:
        # Placeholder function to query an LLM (e.g., OpenAI)
        pass

    async def request(self, prompt: str = '', schema: BaseModel = None, options: dict = None) -> Optional[Dict[str, Any]]:
        # Placeholder function for making a request with the LLM
        pass

    def create_pydantic_model(self, input_dict: Dict[str, Any]) -> BaseModel:
        def create_field(key: str, value: Any) -> Any:
            if isinstance(value, str):
                return (str, ...)
            elif isinstance(value, int):
                return (int, ...)
            elif isinstance(value, float):
                return (float, ...)
            elif isinstance(value, bool):
                return (bool, ...)
            elif isinstance(value, dict):
                return (Dict[str, Any], ...)
            elif isinstance(value, list):
                return (List[Any], ...)
            else:
                return (str, ...)

        fields = {key: create_field(key, value) for key, value in input_dict.items()}
        return create_model('DynamicModel', **fields)

    def validate_schema(self, schema: BaseModel, data: Dict[str, Any]) -> bool:
        try:
            schema(**data)
            return True
        except ValidationError as e:
            print(f"Schema validation error: {e}")
            return False
