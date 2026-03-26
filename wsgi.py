"""
WSGI entry point for production deployment
"""
import os
from app import create_app, create_tables_and_seed

# Create app instance
app = create_app('production')

# Initialize database if needed
with app.app_context():
    try:
        create_tables_and_seed()
    except Exception as e:
        print(f"Database initialization error: {e}")
        # Continue deployment even if database initialization fails

if __name__ == "__main__":
    app.run()
