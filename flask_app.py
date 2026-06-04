import sys, io

# Force UTF-8 on Windows — prevents UnicodeEncodeError when printing ₹ symbols
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from app import create_app

app = create_app()

if __name__ == '__main__':
    print(" Personal Financial Intelligence System")
    print(" Starting Flask server...")
    print(" Dashboard: http://localhost:5000")

    app.run(
        debug=True,
        host='localhost',
        port=5000,
        use_reloader=True
    )
