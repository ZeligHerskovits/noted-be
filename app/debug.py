import os
import datetime
from pathlib import Path

# Create debug directory if it doesn't exist
debug_dir = Path("debug")
debug_dir.mkdir(exist_ok=True)

# Create debug file path
debug_file_path = debug_dir / "debug.log"

def debug(message, *args, **kwargs):
    """
    Debug function that logs to both terminal and debug file.
    
    Args:
        message: The message to log
        *args: Additional arguments to format the message
        **kwargs: Additional keyword arguments to format the message
    """
    # Format the message if args/kwargs are provided
    if args or kwargs:
        try:
            formatted_message = message.format(*args, **kwargs)
        except (ValueError, KeyError):
            # Fallback to simple formatting if the format fails
            formatted_message = f"{message} {' '.join(str(arg) for arg in args)}"
    else:
        formatted_message = str(message)
    
    # Add timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {formatted_message}"
    
    # Print to terminal (original behavior)
    print(log_entry)
    
    # Write to debug file
    try:
        with open(debug_file_path, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
            f.flush()  # Ensure it's written immediately
    except Exception as e:
        # If we can't write to debug file, just print the error
        print(f"[ERROR] Could not write to debug file: {e}")

def clear_debug_log():
    """Clear the debug log file"""
    try:
        with open(debug_file_path, "w", encoding="utf-8") as f:
            f.write("")
        print("Debug log cleared")
    except Exception as e:
        print(f"Could not clear debug log: {e}")

def get_debug_log():
    """Get the contents of the debug log file"""
    try:
        with open(debug_file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Could not read debug log: {e}"

def get_debug_file_path():
    """Get the path to the debug file"""
    return str(debug_file_path) 