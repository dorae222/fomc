
import os
import subprocess

COMMANDS_FILE = "/home/cora3/workSpace/fomc_py/fomc/prediction_commands.txt"

def main():
    """Read and execute prediction commands from a file."""
    if not os.path.exists(COMMANDS_FILE):
        print(f"Error: Commands file not found at {COMMANDS_FILE}")
        return

    with open(COMMANDS_FILE, 'r') as f:
        commands = f.readlines()

    for cmd in commands:
        cmd = cmd.strip()
        if cmd and cmd.startswith('python'):
            print(f"Executing: {cmd}")
            try:
                subprocess.run(cmd, shell=True, check=True)
                print("--- Command finished ---")
            except subprocess.CalledProcessError as e:
                print(f"--- Command failed with error: {e} ---")

if __name__ == "__main__":
    main()
