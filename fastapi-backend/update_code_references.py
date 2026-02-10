"""Script to update all code references from litter to breeding."""
import os
import re
from pathlib import Path

# Define the replacements
REPLACEMENTS = [
    # Model imports
    (r'from app\.models\.litter import Litter', 'from app.models.breeding import Breeding'),
    (r'from app\.models\.litter_pet import LitterPet', 'from app.models.breeding_pet import BreedingPet'),
    
    # Class names
    (r'\bLitter\b', 'Breeding'),
    (r'\bLitterPet\b', 'BreedingPet'),
    
    # Variable names (common patterns)
    (r'\blitter_id\b', 'breeding_id'),
    (r'\blitter_pets\b', 'breeding_pets'),
    (r'\blitter_data\b', 'breeding_data'),
    (r'\blitter\b(?!_)', 'breeding'),  # litter but not litter_id, litter_pets, etc.
    (r'\blitters\b', 'breedings'),
    
    # Schema imports
    (r'from app\.schemas\.litter import', 'from app.schemas.breeding import'),
    
    # API paths
    (r'"/api/litters"', '"/api/breedings"'),
    (r"'/api/litters'", "'/api/breedings'"),
    (r'prefix="/api/litters"', 'prefix="/api/breedings"'),
    
    # Tags
    (r'tags=\["litters"\]', 'tags=["breedings"]'),
    
    # Comments and docstrings (be careful with these)
    (r'Litter router', 'Breeding router'),
    (r'litter records', 'breeding records'),
    (r'litter management', 'breeding management'),
    (r'Litter model', 'Breeding model'),
]

def should_skip_file(filepath):
    """Check if file should be skipped."""
    skip_patterns = [
        '__pycache__',
        '.pyc',
        '.git',
        'venv',
        '.hypothesis',
        'alembic/versions',  # Don't modify migration files
        'update_code_references.py',  # Don't modify this script
        'fix_litters_user_id.py',
        'verify_migration.py',
        '.md',  # Don't modify markdown files
    ]
    
    filepath_str = str(filepath)
    return any(pattern in filepath_str for pattern in skip_patterns)

def update_file(filepath):
    """Update a single file with all replacements."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Apply all replacements
        for pattern, replacement in REPLACEMENTS:
            content = re.sub(pattern, replacement, content)
        
        # Only write if content changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    """Main function to update all files."""
    base_dir = Path('.')
    updated_files = []
    
    # Find all Python files
    for filepath in base_dir.rglob('*.py'):
        if should_skip_file(filepath):
            continue
        
        if update_file(filepath):
            updated_files.append(str(filepath))
            print(f"✓ Updated: {filepath}")
    
    print(f"\n✅ Updated {len(updated_files)} files")
    
    if updated_files:
        print("\nUpdated files:")
        for f in updated_files:
            print(f"  - {f}")

if __name__ == "__main__":
    main()
