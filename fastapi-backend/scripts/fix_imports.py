"""Fix imports after file renames."""
import re
from pathlib import Path

def fix_imports_in_file(filepath):
    """Fix imports in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        
        # Fix router imports
        content = re.sub(
            r'from app\.routers\.litters import',
            'from app.routers.breedings import',
            content
        )
        content = re.sub(
            r'from app\.routers import litters',
            'from app.routers import breedings',
            content
        )
        
        # Fix schema imports
        content = re.sub(
            r'from app\.schemas\.litter import',
            'from app.schemas.breeding import',
            content
        )
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

# Fix main.py
if fix_imports_in_file('app/main.py'):
    print("✓ Fixed app/main.py")

# Fix all test files
for test_file in Path('tests').rglob('*.py'):
    if fix_imports_in_file(test_file):
        print(f"✓ Fixed {test_file}")

# Fix router files
for router_file in Path('app/routers').glob('*.py'):
    if fix_imports_in_file(router_file):
        print(f"✓ Fixed {router_file}")

# Fix schema __init__.py
if fix_imports_in_file('app/schemas/__init__.py'):
    print("✓ Fixed app/schemas/__init__.py")

print("\n✅ Import fixes complete")
