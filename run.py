from app import create_app
import sys

app = create_app()

if __name__ == "__main__":
    # Check for port argument
    port = 5001  # Default to 5001 to avoid macOS AirPlay conflict
    if len(sys.argv) > 1 and sys.argv[1].startswith('--port'):
        try:
            port = int(sys.argv[1].split('=')[1] if '=' in sys.argv[1] else sys.argv[2])
        except (ValueError, IndexError):
            print("Invalid port number. Using default port 5001.")
    
    print(f"Starting IMDB Natural Language Search on http://127.0.0.1:{port}")
    app.run(debug=True, host='127.0.0.1', port=port)