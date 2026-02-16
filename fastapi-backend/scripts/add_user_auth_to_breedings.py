"""Add user authentication and filtering to breedings router."""
import re

# Read the current file
with open('app/routers/breedings.py', 'r') as f:
    content = f.read()

# Add User import and current_active_user dependency
imports_section = """from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.dependencies import current_active_user
from app.models.user import User
from app.models.breeding import Breeding
from app.models.breeding_pet import BreedingPet
from app.models.pet import Pet
from app.models.breed import Breed
from app.models.location import Location
from app.schemas.breeding import LitterCreate, LitterRead, LitterUpdate, LitterResponse, LitterStatus, PetAssignment, PuppyBatch"""

# Replace the imports section
content = re.sub(
    r'from typing import.*?from app\.schemas\.breeding import.*?PuppyBatch',
    imports_section,
    content,
    flags=re.DOTALL
)

# Update create_litter to require authentication and set user_id
create_litter_pattern = r'@router\.post\("/", response_model=LitterResponse, status_code=status\.HTTP_201_CREATED\)\nasync def create_litter\(\s+breeding_data: LitterCreate,\s+session: AsyncSession = Depends\(get_async_session\),\s*\) -> dict:'

create_litter_replacement = '''@router.post("/", response_model=LitterResponse, status_code=status.HTTP_201_CREATED)
async def create_litter(
    breeding_data: LitterCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> dict:'''

content = re.sub(create_litter_pattern, create_litter_replacement, content)

# Update the breeding creation to include user_id
breeding_creation_pattern = r'breeding = Breeding\(\s+description=breeding_data\.description,\s+status=LitterStatus\.STARTED\.value,\s+\)'

breeding_creation_replacement = '''breeding = Breeding(
        user_id=current_user.id,
        description=breeding_data.description,
        status=LitterStatus.STARTED.value,
    )'''

content = re.sub(breeding_creation_pattern, breeding_creation_replacement, content)

# Update list_litters to require authentication and filter by user
list_litters_pattern = r'@router\.get\("/", response_model=List\[LitterResponse\]\)\nasync def list_litters\(\s+session: AsyncSession = Depends\(get_async_session\),'

list_litters_replacement = '''@router.get("/", response_model=List[LitterResponse])
async def list_litters(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),'''

content = re.sub(list_litters_pattern, list_litters_replacement, content)

# Add user_id filter to the query
query_pattern = r'# Start with base query\s+query = select\(Breeding\)\.options\('

query_replacement = '''# Start with base query - filter by current user
    query = select(Breeding).where(Breeding.user_id == current_user.id).options('''

content = re.sub(query_pattern, query_replacement, content)

# Write the updated content
with open('app/routers/breedings.py', 'w') as f:
    f.write(content)

print("✅ Updated breedings router with user authentication and filtering")
