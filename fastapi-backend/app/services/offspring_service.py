"""Offspring service for managing individual animals from litters."""
from datetime import date
from typing import List, Optional
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.offspring import Offspring
from app.models.breeding import Breeding
from app.schemas.offspring import OffspringCreate, OffspringUpdate


class OffspringService:
    """Service for managing offspring CRUD operations and business logic."""
    
    @staticmethod
    def calculate_age(date_of_birth: date) -> str:
        """
        Calculate human-readable age from date of birth.
        
        Returns age in weeks (< 12 weeks), months (12-24 months), or years (> 24 months).
        
        Args:
            date_of_birth: The birth date of the offspring
            
        Returns:
            Human-readable age string (e.g., "8 weeks", "6 months", "2 years")
        """
        today = date.today()
        delta = today - date_of_birth
        
        weeks = delta.days // 7
        months = (today.year - date_of_birth.year) * 12 + (today.month - date_of_birth.month)
        years = today.year - date_of_birth.year
        
        if weeks < 12:
            return f"{weeks} week{'s' if weeks != 1 else ''}"
        elif months < 24:
            return f"{months} month{'s' if months != 1 else ''}"
        else:
            return f"{years} year{'s' if years != 1 else ''}"
    
    async def create_offspring(
        self,
        db: AsyncSession,
        offspring_data: OffspringCreate,
        user_id: uuid.UUID
    ) -> Offspring:
        """
        Create a new offspring record.
        
        Validates breeding relationship and auto-populates breed_id from breeding.
        
        Args:
            db: Database session
            offspring_data: Offspring creation data
            user_id: ID of the authenticated breeder
            
        Returns:
            Created offspring instance
            
        Raises:
            HTTPException: If breeding not found or doesn't belong to user
        """
        # Validate breeding exists and belongs to user
        breeding_query = select(Breeding).where(
            Breeding.id == offspring_data.breeding_id,
            Breeding.user_id == user_id
        )
        result = await db.execute(breeding_query)
        breeding = result.scalar_one_or_none()
        
        if not breeding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Breeding not found or does not belong to you"
            )
        
        # Get breed_id from parent pets in the breeding
        # Query breeding_pets to find the parents
        from app.models.breeding_pet import BreedingPet
        breeding_pets_query = select(BreedingPet).where(
            BreedingPet.breeding_id == offspring_data.breeding_id
        ).limit(1)
        result = await db.execute(breeding_pets_query)
        breeding_pet = result.scalar_one_or_none()
        
        breed_id = None
        if breeding_pet:
            # Get the pet to find breed_id
            from app.models.pet import Pet
            pet_query = select(Pet).where(Pet.id == breeding_pet.pet_id)
            pet_result = await db.execute(pet_query)
            pet = pet_result.scalar_one_or_none()
            if pet:
                breed_id = pet.breed_id
        
        # Generate temporary name if not provided
        name = offspring_data.name
        if not name:
            name = f"Offspring-{uuid.uuid4().hex[:8]}"
        
        # Create offspring
        offspring = Offspring(
            breeding_id=offspring_data.breeding_id,
            user_id=user_id,
            breed_id=breed_id,
            name=name,
            gender=offspring_data.gender,
            date_of_birth=offspring_data.date_of_birth,
            status=offspring_data.status,
            price=offspring_data.price,
            description=offspring_data.description,
            color_markings=offspring_data.color_markings
        )
        
        db.add(offspring)
        await db.commit()
        await db.refresh(offspring)
        
        return offspring
    
    async def get_offspring(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        check_owner: bool = True
    ) -> Offspring:
        """
        Get offspring by ID with optional owner verification.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            user_id: ID of the authenticated user (optional)
            check_owner: Whether to verify ownership
            
        Returns:
            Offspring instance
            
        Raises:
            HTTPException: If offspring not found or access denied
        """
        query = select(Offspring).where(Offspring.id == offspring_id)
        
        if check_owner and user_id:
            query = query.where(Offspring.user_id == user_id)
        
        result = await db.execute(query)
        offspring = result.scalar_one_or_none()
        
        if not offspring:
            if check_owner:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Offspring not found or access denied"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Offspring not found"
                )
        
        return offspring
    
    async def list_offsprings(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        status_filter: Optional[str] = None,
        breed_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Offspring]:
        """
        List offsprings for a breeder with filtering and pagination.
        
        Args:
            db: Database session
            user_id: ID of the breeder
            status_filter: Optional status filter
            breed_id: Optional breed filter
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of offspring instances
        """
        query = select(Offspring).where(Offspring.user_id == user_id)
        
        if status_filter:
            query = query.where(Offspring.status == status_filter)
        
        if breed_id:
            query = query.where(Offspring.breed_id == breed_id)
        
        # Order by created_at descending (newest first)
        query = query.order_by(Offspring.created_at.desc())
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        offsprings = result.scalars().all()
        
        return list(offsprings)
    
    async def count_offsprings(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        status_filter: Optional[str] = None,
        breed_id: Optional[int] = None
    ) -> int:
        """
        Count total offsprings for a breeder with filtering.
        
        Args:
            db: Database session
            user_id: ID of the breeder
            status_filter: Optional status filter
            breed_id: Optional breed filter
            
        Returns:
            Total count of offsprings matching filters
        """
        from sqlalchemy import func
        
        query = select(func.count(Offspring.id)).where(Offspring.user_id == user_id)
        
        if status_filter:
            query = query.where(Offspring.status == status_filter)
        
        if breed_id:
            query = query.where(Offspring.breed_id == breed_id)
        
        result = await db.execute(query)
        count = result.scalar_one()
        
        return count
    
    async def update_offspring(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        offspring_data: OffspringUpdate,
        user_id: uuid.UUID
    ) -> Offspring:
        """
        Update offspring record.
        
        Only allows updating mutable fields (name, status, price, description, color_markings).
        Breeding relationship, gender, and date_of_birth are immutable.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            offspring_data: Update data
            user_id: ID of the authenticated breeder
            
        Returns:
            Updated offspring instance
            
        Raises:
            HTTPException: If offspring not found or access denied
        """
        # Get offspring with owner verification
        offspring = await self.get_offspring(db, offspring_id, user_id, check_owner=True)
        
        # Update only provided fields
        update_data = offspring_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(offspring, field, value)
        
        await db.commit()
        await db.refresh(offspring)
        
        return offspring
    
    async def delete_offspring(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> None:
        """
        Delete offspring record.
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            user_id: ID of the authenticated breeder
            
        Raises:
            HTTPException: If offspring not found or access denied
        """
        # Get offspring with owner verification
        offspring = await self.get_offspring(db, offspring_id, user_id, check_owner=True)
        
        await db.delete(offspring)
        await db.commit()
    
    async def list_public_offsprings(
        self,
        db: AsyncSession,
        breeder_id: uuid.UUID,
        breed_id: Optional[int] = None,
        gender: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Offspring]:
        """
        List public offsprings for a breeder (excludes Archived).
        
        Args:
            db: Database session
            breeder_id: ID of the breeder
            breed_id: Optional breed filter
            gender: Optional gender filter
            status_filter: Optional status filter
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of offspring instances
        """
        query = select(Offspring).where(
            Offspring.user_id == breeder_id,
            Offspring.status != "Archived"  # Exclude archived offsprings
        )
        
        if breed_id:
            query = query.where(Offspring.breed_id == breed_id)
        
        if gender:
            query = query.where(Offspring.gender == gender)
        
        if status_filter:
            query = query.where(Offspring.status == status_filter)
        
        # Order by created_at descending (newest first)
        query = query.order_by(Offspring.created_at.desc())
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        offsprings = result.scalars().all()
        
        return list(offsprings)
    
    async def count_public_offsprings(
        self,
        db: AsyncSession,
        breeder_id: uuid.UUID,
        breed_id: Optional[int] = None,
        gender: Optional[str] = None,
        status_filter: Optional[str] = None
    ) -> int:
        """
        Count total public offsprings for a breeder (excludes Archived).
        
        Args:
            db: Database session
            breeder_id: ID of the breeder
            breed_id: Optional breed filter
            gender: Optional gender filter
            status_filter: Optional status filter
            
        Returns:
            Total count of public offsprings matching filters
        """
        from sqlalchemy import func
        
        query = select(func.count(Offspring.id)).where(
            Offspring.user_id == breeder_id,
            Offspring.status != "Archived"  # Exclude archived offsprings
        )
        
        if breed_id:
            query = query.where(Offspring.breed_id == breed_id)
        
        if gender:
            query = query.where(Offspring.gender == gender)
        
        if status_filter:
            query = query.where(Offspring.status == status_filter)
        
        result = await db.execute(query)
        count = result.scalar_one()
        
        return count
    
    async def get_public_offspring(
        self,
        db: AsyncSession,
        offspring_id: uuid.UUID
    ) -> Offspring:
        """
        Get public offspring by ID (excludes Archived).
        
        Args:
            db: Database session
            offspring_id: ID of the offspring
            
        Returns:
            Offspring instance
            
        Raises:
            HTTPException: If offspring not found or is archived
        """
        query = select(Offspring).where(
            Offspring.id == offspring_id,
            Offspring.status != "Archived"
        )
        
        result = await db.execute(query)
        offspring = result.scalar_one_or_none()
        
        if not offspring:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offspring not found or not available"
            )
        
        return offspring


# Singleton instance
offspring_service = OffspringService()
