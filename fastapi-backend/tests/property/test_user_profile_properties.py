"""Property-based tests for user profile functionality."""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from typing import AsyncGenerator, Optional
import uuid
import copy

from app.models.user import User
from app.database import Base, get_async_session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
import os


# Strategies for generating test data
tag_strategy = st.text(min_size=1, max_size=50, alphabet=st.characters(
    whitelist_categories=('Lu', 'Ll', 'Nd'),
    whitelist_characters=' -_'
)).filter(lambda s: s.strip())

tag_list_strategy = st.lists(
    tag_strategy,
    min_size=0,
    max_size=10,
    unique=True
)

# Strategy for profile update data
profile_update_strategy = st.fixed_dictionaries({
    'breedery_name': st.one_of(
        st.none(), 
        st.text(min_size=1, max_size=255).filter(lambda s: '\x00' not in s)
    ),
    'breedery_description': st.one_of(
        st.none(), 
        st.text(min_size=0, max_size=1000).filter(lambda s: '\x00' not in s)
    ),
    'search_tags': st.one_of(st.none(), tag_list_strategy)
})


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with proper setup and teardown."""
    test_database_url = os.environ.get(
        'TEST_DATABASE_URL',
        'postgresql+asyncpg://test:test@localhost:5432/test_db'
    )
    
    engine = create_async_engine(
        test_database_url,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session_maker_test = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker_test() as session:
        yield session
        await session.rollback()
    
    # Drop tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


class TestUserProfileUpdateIdempotence:
    """
    Property 1: User Profile Update Idempotence
    
    For any user profile update request with the same data, applying the update 
    multiple times should result in the same final state as applying it once.
    
    Validates: Requirements 3.6, 3.7
    """
    
    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=1000
    )
    @given(update_data=profile_update_strategy)
    async def test_profile_update_idempotence(
        self, 
        test_db_session: AsyncSession, 
        update_data: dict
    ):
        """
        Property test: Applying the same profile update multiple times should 
        result in the same final state as applying it once.
        
        Feature: user-profile-settings, Property 1: User Profile Update Idempotence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            breedery_name="Initial Name",
            breedery_description="Initial Description",
            search_tags={"tags": ["initial"]}
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Apply update once
        if update_data['breedery_name'] is not None:
            user.breedery_name = update_data['breedery_name']
        if update_data['breedery_description'] is not None:
            user.breedery_description = update_data['breedery_description']
        if update_data['search_tags'] is not None:
            user.search_tags = {"tags": update_data['search_tags']}
        
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Capture state after first update
        state_after_first = {
            'breedery_name': user.breedery_name,
            'breedery_description': user.breedery_description,
            'search_tags': copy.deepcopy(user.search_tags)
        }
        
        # Apply the same update again
        if update_data['breedery_name'] is not None:
            user.breedery_name = update_data['breedery_name']
        if update_data['breedery_description'] is not None:
            user.breedery_description = update_data['breedery_description']
        if update_data['search_tags'] is not None:
            user.search_tags = {"tags": update_data['search_tags']}
        
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Capture state after second update
        state_after_second = {
            'breedery_name': user.breedery_name,
            'breedery_description': user.breedery_description,
            'search_tags': copy.deepcopy(user.search_tags)
        }
        
        # Assert idempotence: state after first update == state after second update
        assert state_after_first == state_after_second
    
    @pytest.mark.asyncio
    async def test_multiple_updates_same_result(self, test_db_session: AsyncSession):
        """
        Test that applying the same update 5 times produces the same result.
        
        Feature: user-profile-settings, Property 1: User Profile Update Idempotence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user
        user = User(
            email=f"multi_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Define update data
        update_data = {
            'breedery_name': 'Test Breedery',
            'breedery_description': 'A test breedery description',
            'search_tags': ['golden', 'retriever', 'puppies']
        }
        
        # Apply update 5 times
        states = []
        for i in range(5):
            user.breedery_name = update_data['breedery_name']
            user.breedery_description = update_data['breedery_description']
            user.search_tags = {"tags": update_data['search_tags']}
            
            await test_db_session.commit()
            await test_db_session.refresh(user)
            
            states.append({
                'breedery_name': user.breedery_name,
                'breedery_description': user.breedery_description,
                'search_tags': copy.deepcopy(user.search_tags)
            })
        
        # All states should be identical
        for state in states[1:]:
            assert state == states[0]
    
    @pytest.mark.asyncio
    async def test_partial_update_idempotence(self, test_db_session: AsyncSession):
        """
        Test that partial updates (only some fields) are also idempotent.
        
        Feature: user-profile-settings, Property 1: User Profile Update Idempotence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user with initial data
        user = User(
            email=f"partial_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            breedery_name="Initial Name",
            breedery_description="Initial Description",
            search_tags={"tags": ["initial"]}
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Update only breedery_name (partial update)
        user.breedery_name = "Updated Name"
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        state_after_first = {
            'breedery_name': user.breedery_name,
            'breedery_description': user.breedery_description,
            'search_tags': copy.deepcopy(user.search_tags)
        }
        
        # Apply same partial update again
        user.breedery_name = "Updated Name"
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        state_after_second = {
            'breedery_name': user.breedery_name,
            'breedery_description': user.breedery_description,
            'search_tags': copy.deepcopy(user.search_tags)
        }
        
        # States should be identical
        assert state_after_first == state_after_second
        # Other fields should remain unchanged
        assert user.breedery_description == "Initial Description"
        assert user.search_tags == {"tags": ["initial"]}


class TestTagArrayPersistence:
    """
    Property 8: Tag Array Persistence
    
    For any user profile update that includes search_tags, the tags should be 
    stored as a JSON array and retrieved in the same order with the same values.
    
    Validates: Requirements 3.4, 3.6
    """
    
    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=1000
    )
    @given(tags=tag_list_strategy)
    async def test_tag_array_round_trip(self, test_db_session: AsyncSession, tags: list[str]):
        """
        Property test: For any list of tags, storing and retrieving should preserve 
        the exact order and values.
        
        Feature: user-profile-settings, Property 8: Tag Array Persistence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create a user with search tags
        user = User(
            email=f"test_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            search_tags={"tags": tags}  # Store as JSON object with tags array
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        user_id = user.id
        
        # Clear session to ensure we're reading from database
        await test_db_session.close()
        
        # Create new session and retrieve user
        test_database_url = os.environ.get(
            'TEST_DATABASE_URL',
            'postgresql+asyncpg://test:test@localhost:5432/test_db'
        )
        engine = create_async_engine(test_database_url, echo=False)
        async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session_maker() as new_session:
            result = await new_session.execute(
                select(User).where(User.id == user_id)
            )
            retrieved_user = result.scalar_one()
            
            # Verify tags are preserved
            if tags:
                assert retrieved_user.search_tags is not None
                assert "tags" in retrieved_user.search_tags
                retrieved_tags = retrieved_user.search_tags["tags"]
                assert retrieved_tags == tags
                assert len(retrieved_tags) == len(tags)
                # Verify order is preserved
                for i, tag in enumerate(tags):
                    assert retrieved_tags[i] == tag
            else:
                # Empty list should be stored
                assert retrieved_user.search_tags is not None
                assert retrieved_user.search_tags["tags"] == []
        
        await engine.dispose()
    
    @pytest.mark.asyncio
    async def test_tag_array_with_special_characters(self, test_db_session: AsyncSession):
        """
        Test that tags with special characters are preserved correctly.
        
        Feature: user-profile-settings, Property 8: Tag Array Persistence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Tags with various special characters
        special_tags = [
            "Golden-Retriever",
            "Labrador_Retriever",
            "German Shepherd",
            "Poodle123",
            "Mix-Breed_Dog"
        ]
        
        user = User(
            email=f"special_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            search_tags={"tags": special_tags}
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Verify tags are preserved with special characters
        assert user.search_tags["tags"] == special_tags
    
    @pytest.mark.asyncio
    async def test_tag_array_update_preserves_order(self, test_db_session: AsyncSession):
        """
        Test that updating tags preserves the new order.
        
        Feature: user-profile-settings, Property 8: Tag Array Persistence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create user with initial tags
        initial_tags = ["tag1", "tag2", "tag3"]
        user = User(
            email=f"update_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            search_tags={"tags": initial_tags}
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Update tags with different order
        updated_tags = ["tag3", "tag1", "tag2", "tag4"]
        user.search_tags = {"tags": updated_tags}
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Verify new order is preserved
        assert user.search_tags["tags"] == updated_tags
        assert user.search_tags["tags"][0] == "tag3"
        assert user.search_tags["tags"][3] == "tag4"
    
    @pytest.mark.asyncio
    async def test_null_tags_handled_correctly(self, test_db_session: AsyncSession):
        """
        Test that null/None tags are handled correctly.
        
        Feature: user-profile-settings, Property 8: Tag Array Persistence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create user without tags
        user = User(
            email=f"null_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            search_tags=None
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Verify null is preserved
        assert user.search_tags is None
        
        # Update to empty array
        user.search_tags = {"tags": []}
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Verify empty array is preserved
        assert user.search_tags is not None
        assert user.search_tags["tags"] == []
    
    @pytest.mark.asyncio
    async def test_duplicate_tags_preserved(self, test_db_session: AsyncSession):
        """
        Test that duplicate tags (if allowed) are preserved.
        
        Feature: user-profile-settings, Property 8: Tag Array Persistence
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Tags with duplicates
        tags_with_duplicates = ["dog", "puppy", "dog", "canine"]
        
        user = User(
            email=f"dup_{uuid.uuid4()}@example.com",
            hashed_password=password_helper.hash("TestPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            search_tags={"tags": tags_with_duplicates}
        )
        
        test_db_session.add(user)
        await test_db_session.commit()
        await test_db_session.refresh(user)
        
        # Verify duplicates are preserved
        assert user.search_tags["tags"] == tags_with_duplicates
        assert user.search_tags["tags"].count("dog") == 2
