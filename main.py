from agent import Agent
from config import SYSTEM_PROMPT

# Create the agent instance
agent = Agent(SYSTEM_PROMPT)

def main():
    while True:
        try:
            user_input = input("> ")
            if not user_input.strip():
                continue
            response = agent(user_input)
            print(response)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

if __name__ == "__main__":
    main()
