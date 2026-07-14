from agent import Agent
from config import SYSTEM_PROMPT
from routines import RoutinesScheduler

# Create the agent instance
agent = Agent(SYSTEM_PROMPT)

def main():
    # Start routines scheduler daemon thread
    scheduler = RoutinesScheduler()
    scheduler.start()
    
    try:
        while True:
            try:
                user_input = input("> ")
                if not user_input.strip():
                    continue
                # Stream the response from the agent, printing each chunk as it arrives
                for chunk in agent.stream(user_input):
                    print(chunk, end="", flush=True)
                # After streaming is complete, print a newline for the next prompt
                print()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break
    finally:
        # Graceful shutdown of routines executor and daemon thread
        scheduler.stop()

if __name__ == "__main__":
    main()
