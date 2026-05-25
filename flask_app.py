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
