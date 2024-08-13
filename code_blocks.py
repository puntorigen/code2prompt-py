import os
import subprocess
import asyncio
import jinja2
from typing import Dict, Any
from functools import reduce

class CodeBlocks:
    def __init__(self):
        self.code_blocks = []
        self.current_folder = os.getcwd()
        self.last_eval = ""

    async def execute_python(self, context: Dict[str, Any] = None, code: str = None) -> Any:
        if context is None:
            context = {}

        # Preparing the Python code to be executed
        python_code = f"""
async def _temp_func():
    {code}

result = await _temp_func()
    """

        # Update the context with any necessary built-ins or external imports
        context.update({
            'os': os,
            'subprocess': subprocess,
            'asyncio': asyncio,
            'print': print,
        })

        exec_globals = {}
        exec_globals.update(context)

        # Execute the Python code
        exec(python_code, exec_globals)

        # Return the result or updated context if needed
        return exec_globals.get('result', None)

    async def execute_node(self, context: Dict[str, Any] = None, code: str = None) -> Any:
        if context is None:
            context = {}

        async_code = f"(async () => {{ {code} }})()"

        context.update({
            'os': os,
            'subprocess': subprocess,
            'asyncio': asyncio,
            'print': print,
        })

        exec_globals = {}
        exec_globals.update(context)

        exec(async_code, exec_globals)
        return exec_globals

    async def spawn_bash(self, context: Dict[str, Any] = None, code: str = None) -> str:
        if code is None:
            raise ValueError("Command must not be empty")

        if context is None:
            context = {}

        simple_context = {key: value for key, value in context.items() if isinstance(value, (str, int, bool))}
        shell = '/bin/sh' if os.name != 'nt' else 'cmd.exe'

        process = await asyncio.create_subprocess_shell(
            code,
            env={**os.environ, **simple_context, "CI": "true"},
            cwd=self.current_folder,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True
        )

        stdout, stderr = await process.communicate()
        output = stdout.decode() + stderr.decode()

        if process.returncode != 0:
            raise RuntimeError(f"Process exited with code {process.returncode}: {output}")

        return output

    async def execute_bash(self, context: Dict[str, Any] = None, code: str = None) -> Dict[str, str]:
        if code is None:
            raise ValueError("No code provided for execution")

        processed_code = code.format(**context)
        full_script = processed_code

        try:
            output = await self.spawn_bash(context, full_script)
            return {"output": output}
        except Exception as e:
            raise e
