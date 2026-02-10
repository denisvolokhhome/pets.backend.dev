# Breeding Refactoring Summary

## Overview
This document tracks the refactoring from "litters" to "breedings" terminology and the addition of user_id to ensure proper data isolation.

## Changes Made

### 1. Database Migration
**File:** `alembic/versions/8f602ce5a841_add_user_id_and_rename_litters_to_.py`

- Added `user_id` column to litters table with foreign key to users
- Populated `user_id` from parent pets' user_id
- Renamed `litters` table to `breedings`
- Renamed `litter_pets` table to `breeding_pets`
- Updated all foreign key references in pets table (`litter_id` → `breeding_id`)
- Updated all indexes

### 2. Model Files Renamed
- `app/models/litter.py` → `app/models/breeding.py`
- `app/models/litter_pet.py` → `app/models/breeding_pet.py`

### 3. Model Classes Renamed
- `Litter` → `Breeding`
- `LitterPet` → `BreedingPet`

### 4. Model Updates

**breeding.py:**
- Added `user_id` field with UUID type
- Added `user` relationship to User model
- Updated table name to `breedings`
- Updated relationship names: `litter_pets` → `breeding_pets`

**breeding_pet.py:**
- Updated table name to `breeding_pets`
- Renamed foreign key: `litter_id` → `breeding_id`
- Updated relationship names: `litter` → `breeding`

**pet.py:**
- Renamed foreign key: `litter_id` → `breeding_id`
- Updated relationship names: `litter` → `breeding`, `litter_assignments` → `breeding_assignments`

**user.py:**
- Added `breedings` relationship

**models/__init__.py:**
- Updated imports and exports

### 5. Files That Need Updating

#### Routers
- [ ] `app/routers/litters.py` → rename to `breedings.py` and update all references

#### Schemas
- [ ] `app/schemas/litter.py` → rename to `breeding.py` and update all references

#### Tests - Integration
- [ ] `tests/integration/test_litter_endpoints.py`
- [ ] `tests/integration/test_litter_e2e_workflows.py`
- [ ] `tests/integration/test_e2e_workflows.py`

#### Tests - Property
- [ ] `tests/property/test_litter_properties.py`
- [ ] `tests/property/test_error_properties.py`
- [ ] `tests/property/test_api_contract_properties.py`

#### Main Application
- [ ] `app/main.py` - update router registration

### 6. API Endpoints to Update
- `/api/litters` → `/api/breedings`
- All litter-related endpoints need to be updated

### 7. Frontend Updates Needed
- Update all API calls from `/litters` to `/breedings`
- Update model interfaces
- Update component references

## Migration Steps

### Backend
1. ✅ Create migration file
2. ✅ Update model files and classes
3. ⏳ Update routers
4. ⏳ Update schemas
5. ⏳ Update tests
6. ⏳ Update main.py router registration
7. ⏳ Run migration
8. ⏳ Run tests to verify

### Frontend
1. ⏳ Update API service calls
2. ⏳ Update TypeScript interfaces
3. ⏳ Update component references
4. ⏳ Update routing if needed

## Running the Migration

```bash
# Backup database first!
pg_dump your_database > backup.sql

# Run the migration
cd pets.backend.dev/fastapi-backend
./venv/bin/alembic upgrade head

# Verify the changes
./venv/bin/alembic current
```

## Rollback if Needed

```bash
./venv/bin/alembic downgrade -1
```

## Testing After Migration

```bash
# Run all tests
./venv/bin/pytest

# Run specific test suites
./venv/bin/pytest tests/integration/test_litter_endpoints.py
./venv/bin/pytest tests/property/test_litter_properties.py
```

## Notes
- The migration preserves all existing data
- User isolation is now enforced at the database level
- All existing litters will be assigned to the user who owns the parent pets
- The term "litter" is still used in some field names (e.g., `date_of_litter`) for backward compatibility
