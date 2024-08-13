import asyncio
from code2prompt import Code2Prompt  # Assuming your class is in a file named code2prompt.py

async def main():
    # Setup the options dictionary
    options = {
        "path": ".",  # Path to the directory you want to process
        "extensions": ["py"],  # File extensions to include
        "ignore": ["__pycache__"],  # Patterns to ignore
        "template": None,  # Use the default template
        "schema": None,
        "debugger": True
    }

    # Create an instance of Code2Prompt
    code2prompt = Code2Prompt(options)
    await code2prompt.initialize()  # Initialize the template

    # Generate the context prompt using the default template
    context_prompt = await code2prompt.generate_context_prompt()

    # Print out the generated markdown content
    print(context_prompt)

    # Optionally, you can run the template processing
    # and print the final context after processing any code blocks
    final_context = await code2prompt.run_template()
    print("Final context:", final_context)

# Run the test
if __name__ == "__main__":
    asyncio.run(main())
