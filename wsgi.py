"""
WSGI entry point for production deployment
"""
import os
from app import create_app

# Create app instance
app = create_app('production')

# Initialize database if needed
with app.app_context():
    from app import create_tables_and_seed
    create_tables_and_seed()

if __name__ == "__main__":
    app.run()
