# run.py
from app import create_app

# This calls the factory function we defined in app/__init__.py
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
