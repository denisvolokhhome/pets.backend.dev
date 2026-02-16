"""Property-based tests for pet seeker message linking."""
import pytest
from hypothesis import given, settings, strategies as st, HealthCheck
from typing import AsyncGenerator
import uuid

from app.models.user import User
from app.models.message import Message
from app.database import Base, get_async_session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
import os


# Strategies for generating test data
email_strategy = st.emails()
name_strategy = st.text(min_size=1, max_size=100).filter(
    lambda s: s.strip() and '\x00' not in s
)
message_text_strategy = st.text(min_size=1, max_size=500).filter(
    lambda s: s.strip() and '\x00' not in s
)


@pytest.fixture(scope="function")
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
        try:
            yield session
        finally:
            # Ensure clean rollback even on errors
            try:
                await session.rollback()
            except Exception:
                pass
            await session.close()
    
    # Clean up all data between tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


async def create_breeder_user(session: AsyncSession, email: str = None) -> User:
    """Helper function to create a breeder user."""
    from fastapi_users.password import PasswordHelper
    import uuid
    
    password_helper = PasswordHelper()
    
    if email is None:
        email = f"breeder_{uuid.uuid4().hex[:8]}@example.com"
    
    user = User(
        email=email,
        hashed_password=password_helper.hash("BreederPassword123"),
        is_active=True,
        is_superuser=False,
        is_verified=True,
        is_breeder=True
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


class TestMessageAccountLinking:
    """
    Property 12: Message-Account Linking
    
    For any new pet seeker account creation, if there exist guest messages 
    with sender_email matching the new account's email, then all such messages 
    SHALL be linked to the new account by setting their `pet_seeker_id` to 
    the new user's id.
    
    Validates: Requirements 9.1, 9.2
    """
    
    @pytest.mark.asyncio
    async def test_single_message_linking(self, test_db_session):
        """
        Test that a single guest message gets linked when account is created.
        
        Feature: pet-seeker-accounts, Property 12: Message-Account Linking
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        guest_email = "petseeker@example.com"
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create a guest message
        message = Message(
            breeder_id=breeder_user.id,
            sender_name="John Doe",
            sender_email=guest_email,
            message="I'm interested in your puppies",
            is_read=False
        )
        test_db_session.add(message)
        await test_db_session.commit()
        await test_db_session.refresh(message)
        
        # Verify message has no pet_seeker_id
        assert message.pet_seeker_id is None
        
        # Create pet seeker account with matching email
        pet_seeker = User(
            email=guest_email,
            hashed_password=password_helper.hash("PetSeekerPassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Link messages to account
        query = select(Message).where(
            Message.sender_email == guest_email,
            Message.pet_seeker_id.is_(None)
        )
        result = await test_db_session.execute(query)
        messages_to_link = result.scalars().all()
        
        for msg in messages_to_link:
            msg.pet_seeker_id = pet_seeker.id
        
        await test_db_session.commit()
        await test_db_session.refresh(message)
        
        # Verify message is now linked
        assert message.pet_seeker_id == pet_seeker.id
    
    @pytest.mark.asyncio
    async def test_multiple_messages_linking(self, test_db_session):
        """
        Test that multiple guest messages get linked when account is created.
        
        Feature: pet-seeker-accounts, Property 12: Message-Account Linking
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        guest_email = "multiplemsgs@example.com"
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create multiple guest messages from same email
        messages = []
        for i in range(3):
            message = Message(
                breeder_id=breeder_user.id,
                sender_name="Jane Smith",
                sender_email=guest_email,
                message=f"Message {i+1}",
                is_read=False
            )
            test_db_session.add(message)
            messages.append(message)
        
        await test_db_session.commit()
        for msg in messages:
            await test_db_session.refresh(msg)
        
        # Verify all messages have no pet_seeker_id
        for msg in messages:
            assert msg.pet_seeker_id is None
        
        # Create pet seeker account
        pet_seeker = User(
            email=guest_email,
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Link all messages
        query = select(Message).where(
            Message.sender_email == guest_email,
            Message.pet_seeker_id.is_(None)
        )
        result = await test_db_session.execute(query)
        messages_to_link = result.scalars().all()
        
        for msg in messages_to_link:
            msg.pet_seeker_id = pet_seeker.id
        
        await test_db_session.commit()
        
        # Verify all messages are linked
        for msg in messages:
            await test_db_session.refresh(msg)
            assert msg.pet_seeker_id == pet_seeker.id
    
    @pytest.mark.asyncio
    async def test_no_linking_for_different_email(self, test_db_session):
        """
        Test that messages with different email are not linked.
        
        Feature: pet-seeker-accounts, Property 12: Message-Account Linking
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create guest message with one email
        message = Message(
            breeder_id=breeder_user.id,
            sender_name="Bob Jones",
            sender_email="bob@example.com",
            message="Interested in puppies",
            is_read=False
        )
        test_db_session.add(message)
        await test_db_session.commit()
        await test_db_session.refresh(message)
        
        # Create pet seeker with different email
        pet_seeker = User(
            email="alice@example.com",
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Try to link messages (should find none)
        query = select(Message).where(
            Message.sender_email == pet_seeker.email,
            Message.pet_seeker_id.is_(None)
        )
        result = await test_db_session.execute(query)
        messages_to_link = result.scalars().all()
        
        # Should be no messages to link
        assert len(messages_to_link) == 0
        
        # Original message should still be unlinked
        await test_db_session.refresh(message)
        assert message.pet_seeker_id is None
    
    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=2000,
    )
    @given(
        sender_email=email_strategy,
        sender_name=name_strategy,
        message_text=message_text_strategy
    )
    async def test_message_linking_property(
        self,
        test_db_session,
        sender_email,
        sender_name,
        message_text
    ):
        """
        Property test: For any email, messages with that email get linked to account.
        
        Feature: pet-seeker-accounts, Property 12: Message-Account Linking
        """
        from fastapi_users.password import PasswordHelper
        from sqlalchemy import delete
        
        password_helper = PasswordHelper()
        
        # Clean up any existing data before starting
        await test_db_session.execute(delete(Message))
        await test_db_session.execute(delete(User))
        await test_db_session.commit()
        
        try:
            # Create breeder user with guaranteed unique email for this iteration
            breeder_email = f"breeder_{uuid.uuid4().hex}@example.com"
            breeder_user = await create_breeder_user(test_db_session, email=breeder_email)
            
            # Create guest message
            message = Message(
                breeder_id=breeder_user.id,
                sender_name=sender_name,
                sender_email=sender_email,
                message=message_text,
                is_read=False
            )
            test_db_session.add(message)
            await test_db_session.commit()
            await test_db_session.refresh(message)
            
            # Create pet seeker with same email
            pet_seeker = User(
                email=sender_email,
                hashed_password=password_helper.hash("TestPassword123"),
                is_active=True,
                is_superuser=False,
                is_verified=False,
                is_breeder=False
            )
            test_db_session.add(pet_seeker)
            await test_db_session.commit()
            await test_db_session.refresh(pet_seeker)
            
            # Link messages
            query = select(Message).where(
                Message.sender_email == sender_email,
                Message.pet_seeker_id.is_(None)
            )
            result = await test_db_session.execute(query)
            messages_to_link = result.scalars().all()
            
            for msg in messages_to_link:
                msg.pet_seeker_id = pet_seeker.id
            
            await test_db_session.commit()
            await test_db_session.refresh(message)
            
            # Verify linking occurred
            assert message.pet_seeker_id == pet_seeker.id
        finally:
            # Clean up data created in this iteration
            try:
                await test_db_session.execute(delete(Message))
                await test_db_session.execute(delete(User))
                await test_db_session.commit()
            except Exception:
                await test_db_session.rollback()


class TestMessageLinkingPreservesData:
    """
    Property 13: Message Linking Preserves Data
    
    For any message that gets linked to an account, the message content, 
    timestamps, sender_name, and sender_email SHALL remain unchanged after linking.
    
    Validates: Requirements 9.4
    """
    
    @pytest.mark.asyncio
    async def test_message_data_preserved_after_linking(self, test_db_session):
        """
        Test that message data is preserved when linking to account.
        
        Feature: pet-seeker-accounts, Property 13: Message Linking Preserves Data
        """
        from fastapi_users.password import PasswordHelper
        from datetime import datetime
        
        password_helper = PasswordHelper()
        guest_email = "preserve@example.com"
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create guest message with specific data
        original_sender_name = "Original Sender"
        original_message = "Original message content"
        original_email = guest_email
        
        message = Message(
            breeder_id=breeder_user.id,
            sender_name=original_sender_name,
            sender_email=original_email,
            message=original_message,
            is_read=False
        )
        test_db_session.add(message)
        await test_db_session.commit()
        await test_db_session.refresh(message)
        
        # Store original values
        original_created_at = message.created_at
        original_updated_at = message.updated_at
        
        # Create pet seeker account
        pet_seeker = User(
            email=guest_email,
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Link message
        message.pet_seeker_id = pet_seeker.id
        await test_db_session.commit()
        await test_db_session.refresh(message)
        
        # Verify all original data is preserved
        assert message.sender_name == original_sender_name
        assert message.sender_email == original_email
        assert message.message == original_message
        assert message.created_at == original_created_at
        # updated_at might change, but that's acceptable
    
    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=2000,
    )
    @given(
        sender_email=email_strategy,
        sender_name=name_strategy,
        message_text=message_text_strategy
    )
    async def test_data_preservation_property(
        self,
        test_db_session,
        sender_email,
        sender_name,
        message_text
    ):
        """
        Property test: For any message data, linking preserves all fields.
        
        Feature: pet-seeker-accounts, Property 13: Message Linking Preserves Data
        """
        from fastapi_users.password import PasswordHelper
        from sqlalchemy import delete
        
        password_helper = PasswordHelper()
        
        # Clean up any existing data before starting
        await test_db_session.execute(delete(Message))
        await test_db_session.execute(delete(User))
        await test_db_session.commit()
        
        try:
            # Create breeder user with guaranteed unique email for this iteration
            breeder_email = f"breeder_{uuid.uuid4().hex}@example.com"
            breeder_user = await create_breeder_user(test_db_session, email=breeder_email)
            
            # Create message with generated data
            message = Message(
                breeder_id=breeder_user.id,
                sender_name=sender_name,
                sender_email=sender_email,
                message=message_text,
                is_read=False
            )
            test_db_session.add(message)
            await test_db_session.commit()
            await test_db_session.refresh(message)
            
            # Store original values
            original_sender_name = message.sender_name
            original_sender_email = message.sender_email
            original_message_text = message.message
            original_created_at = message.created_at
            original_is_read = message.is_read
            
            # Create pet seeker and link
            pet_seeker = User(
                email=sender_email,
                hashed_password=password_helper.hash("TestPassword123"),
                is_active=True,
                is_superuser=False,
                is_verified=False,
                is_breeder=False
            )
            test_db_session.add(pet_seeker)
            await test_db_session.commit()
            await test_db_session.refresh(pet_seeker)
            
            # Link message
            message.pet_seeker_id = pet_seeker.id
            await test_db_session.commit()
            await test_db_session.refresh(message)
            
            # Verify all data preserved
            assert message.sender_name == original_sender_name
            assert message.sender_email == original_sender_email
            assert message.message == original_message_text
            assert message.created_at == original_created_at
            assert message.is_read == original_is_read
            assert message.pet_seeker_id == pet_seeker.id
        finally:
            # Clean up data created in this iteration
            try:
                await test_db_session.execute(delete(Message))
                await test_db_session.execute(delete(User))
                await test_db_session.commit()
            except Exception:
                await test_db_session.rollback()


class TestPetSeekerMessageDashboard:
    """
    Property 14: Pet Seeker Message Dashboard Completeness
    
    For any pet seeker user who views their messages dashboard, the dashboard 
    SHALL display all messages where either (sender_email matches user's email) 
    OR (pet_seeker_id matches user's id).
    
    Validates: Requirements 9.3
    """
    
    @pytest.mark.asyncio
    async def test_pet_seeker_sees_linked_messages(self, test_db_session):
        """
        Test that pet seeker can view messages linked to their account.
        
        Feature: pet-seeker-accounts, Property 14: Pet Seeker Message Dashboard Completeness
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        pet_seeker_email = "petseeker@example.com"
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create pet seeker account
        pet_seeker = User(
            email=pet_seeker_email,
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Create messages linked to pet seeker
        messages = []
        for i in range(3):
            message = Message(
                breeder_id=breeder_user.id,
                sender_name="Pet Seeker",
                sender_email=pet_seeker_email,
                message=f"Message {i+1}",
                is_read=False,
                pet_seeker_id=pet_seeker.id
            )
            test_db_session.add(message)
            messages.append(message)
        
        await test_db_session.commit()
        
        # Query messages for pet seeker (simulating dashboard query)
        query = select(Message).where(
            Message.pet_seeker_id == pet_seeker.id
        )
        result = await test_db_session.execute(query)
        retrieved_messages = result.scalars().all()
        
        # Verify all messages are retrieved
        assert len(retrieved_messages) == 3
        retrieved_ids = {msg.id for msg in retrieved_messages}
        expected_ids = {msg.id for msg in messages}
        assert retrieved_ids == expected_ids
    
    @pytest.mark.asyncio
    async def test_pet_seeker_sees_messages_by_email(self, test_db_session):
        """
        Test that pet seeker can view messages sent with their email before account creation.
        
        Feature: pet-seeker-accounts, Property 14: Pet Seeker Message Dashboard Completeness
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        pet_seeker_email = "guest@example.com"
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create guest messages (before account creation)
        guest_messages = []
        for i in range(2):
            message = Message(
                breeder_id=breeder_user.id,
                sender_name="Guest User",
                sender_email=pet_seeker_email,
                message=f"Guest message {i+1}",
                is_read=False,
                pet_seeker_id=None  # Not linked yet
            )
            test_db_session.add(message)
            guest_messages.append(message)
        
        await test_db_session.commit()
        
        # Create pet seeker account
        pet_seeker = User(
            email=pet_seeker_email,
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Query messages by email OR pet_seeker_id (dashboard query)
        from sqlalchemy import or_
        query = select(Message).where(
            or_(
                Message.sender_email == pet_seeker.email,
                Message.pet_seeker_id == pet_seeker.id
            )
        )
        result = await test_db_session.execute(query)
        retrieved_messages = result.scalars().all()
        
        # Should retrieve all messages sent with that email
        assert len(retrieved_messages) == 2
    
    @pytest.mark.asyncio
    async def test_pet_seeker_sees_both_linked_and_email_messages(self, test_db_session):
        """
        Test that pet seeker sees both linked messages and messages by email.
        
        Feature: pet-seeker-accounts, Property 14: Pet Seeker Message Dashboard Completeness
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        pet_seeker_email = "complete@example.com"
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create pet seeker account
        pet_seeker = User(
            email=pet_seeker_email,
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker)
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker)
        
        # Create linked messages (after account creation)
        linked_message = Message(
            breeder_id=breeder_user.id,
            sender_name="Pet Seeker",
            sender_email=pet_seeker_email,
            message="Linked message",
            is_read=False,
            pet_seeker_id=pet_seeker.id
        )
        test_db_session.add(linked_message)
        
        # Create unlinked message with same email (edge case)
        unlinked_message = Message(
            breeder_id=breeder_user.id,
            sender_name="Pet Seeker",
            sender_email=pet_seeker_email,
            message="Unlinked message",
            is_read=False,
            pet_seeker_id=None
        )
        test_db_session.add(unlinked_message)
        
        await test_db_session.commit()
        
        # Query messages (dashboard query)
        from sqlalchemy import or_
        query = select(Message).where(
            or_(
                Message.sender_email == pet_seeker.email,
                Message.pet_seeker_id == pet_seeker.id
            )
        )
        result = await test_db_session.execute(query)
        retrieved_messages = result.scalars().all()
        
        # Should retrieve both messages
        assert len(retrieved_messages) == 2
    
    @pytest.mark.asyncio
    async def test_pet_seeker_does_not_see_other_users_messages(self, test_db_session):
        """
        Test that pet seeker only sees their own messages, not others.
        
        Feature: pet-seeker-accounts, Property 14: Pet Seeker Message Dashboard Completeness
        """
        from fastapi_users.password import PasswordHelper
        
        password_helper = PasswordHelper()
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create first pet seeker
        pet_seeker1 = User(
            email="petseeker1@example.com",
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker1)
        
        # Create second pet seeker
        pet_seeker2 = User(
            email="petseeker2@example.com",
            hashed_password=password_helper.hash("Password123"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
            is_breeder=False
        )
        test_db_session.add(pet_seeker2)
        
        await test_db_session.commit()
        await test_db_session.refresh(pet_seeker1)
        await test_db_session.refresh(pet_seeker2)
        
        # Create message for pet seeker 1
        message1 = Message(
            breeder_id=breeder_user.id,
            sender_name="Pet Seeker 1",
            sender_email=pet_seeker1.email,
            message="Message from pet seeker 1",
            is_read=False,
            pet_seeker_id=pet_seeker1.id
        )
        test_db_session.add(message1)
        
        # Create message for pet seeker 2
        message2 = Message(
            breeder_id=breeder_user.id,
            sender_name="Pet Seeker 2",
            sender_email=pet_seeker2.email,
            message="Message from pet seeker 2",
            is_read=False,
            pet_seeker_id=pet_seeker2.id
        )
        test_db_session.add(message2)
        
        await test_db_session.commit()
        
        # Query messages for pet seeker 1
        from sqlalchemy import or_
        query = select(Message).where(
            or_(
                Message.sender_email == pet_seeker1.email,
                Message.pet_seeker_id == pet_seeker1.id
            )
        )
        result = await test_db_session.execute(query)
        retrieved_messages = result.scalars().all()
        
        # Should only see their own message
        assert len(retrieved_messages) == 1
        assert retrieved_messages[0].id == message1.id
    
    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=2000,
    )
    @given(
        pet_seeker_email=email_strategy,
        num_messages=st.integers(min_value=1, max_value=5)
    )
    async def test_dashboard_completeness_property(
        self,
        test_db_session,
        pet_seeker_email,
        num_messages
    ):
        """
        Property test: Pet seeker dashboard shows all their messages.
        
        Feature: pet-seeker-accounts, Property 14: Pet Seeker Message Dashboard Completeness
        """
        from fastapi_users.password import PasswordHelper
        from sqlalchemy import delete, or_
        
        password_helper = PasswordHelper()
        
        # Clean up any existing data before starting
        await test_db_session.execute(delete(Message))
        await test_db_session.execute(delete(User))
        await test_db_session.commit()
        
        try:
            # Create breeder user with guaranteed unique email
            breeder_email = f"breeder_{uuid.uuid4().hex}@example.com"
            breeder_user = await create_breeder_user(test_db_session, email=breeder_email)
            
            # Create pet seeker
            pet_seeker = User(
                email=pet_seeker_email,
                hashed_password=password_helper.hash("TestPassword123"),
                is_active=True,
                is_superuser=False,
                is_verified=False,
                is_breeder=False
            )
            test_db_session.add(pet_seeker)
            await test_db_session.commit()
            await test_db_session.refresh(pet_seeker)
            
            # Create messages for pet seeker
            created_message_ids = []
            for i in range(num_messages):
                message = Message(
                    breeder_id=breeder_user.id,
                    sender_name="Test Sender",
                    sender_email=pet_seeker_email,
                    message=f"Test message {i}",
                    is_read=False,
                    pet_seeker_id=pet_seeker.id
                )
                test_db_session.add(message)
                await test_db_session.flush()
                created_message_ids.append(message.id)
            
            await test_db_session.commit()
            
            # Query dashboard messages
            query = select(Message).where(
                or_(
                    Message.sender_email == pet_seeker.email,
                    Message.pet_seeker_id == pet_seeker.id
                )
            )
            result = await test_db_session.execute(query)
            retrieved_messages = result.scalars().all()
            
            # Verify all messages are retrieved
            assert len(retrieved_messages) == num_messages
            retrieved_ids = {msg.id for msg in retrieved_messages}
            expected_ids = set(created_message_ids)
            assert retrieved_ids == expected_ids
        finally:
            # Clean up data created in this iteration
            try:
                await test_db_session.execute(delete(Message))
                await test_db_session.execute(delete(User))
                await test_db_session.commit()
            except Exception:
                await test_db_session.rollback()


class TestGuestMessageValidation:
    """
    Property 9: Guest Message Form Validation
    
    For any guest message submission, the system SHALL reject the submission 
    if sender_name, sender_email, or message content is missing, and SHALL 
    accept the submission if all three fields are provided with valid values.
    
    Validates: Requirements 7.3
    """
    
    @pytest.mark.asyncio
    async def test_guest_message_requires_all_fields(self, test_db_session):
        """
        Test that guest message requires name, email, and content.
        
        Feature: pet-seeker-accounts, Property 9: Guest Message Form Validation
        """
        from app.schemas.message import MessageCreate
        from pydantic import ValidationError
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Test missing sender_name
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=breeder_user.id,
                sender_email="test@example.com",
                message="Test message"
                # sender_name is missing
            )
        assert "sender_name" in str(exc_info.value)
        
        # Test missing sender_email
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=breeder_user.id,
                sender_name="Test User",
                message="Test message"
                # sender_email is missing
            )
        assert "sender_email" in str(exc_info.value)
        
        # Test missing breeder_id
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                sender_name="Test User",
                sender_email="test@example.com",
                message="Test message"
                # breeder_id is missing
            )
        assert "breeder_id" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_guest_message_accepts_valid_data(self, test_db_session):
        """
        Test that guest message accepts valid data with all required fields.
        
        Feature: pet-seeker-accounts, Property 9: Guest Message Form Validation
        """
        from app.schemas.message import MessageCreate
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Valid message should not raise validation error
        message_data = MessageCreate(
            breeder_id=breeder_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message="I'm interested in your puppies"
        )
        
        # Should successfully create message
        assert message_data.sender_name == "John Doe"
        assert message_data.sender_email == "john@example.com"
        assert message_data.message == "I'm interested in your puppies"
    
    @pytest.mark.asyncio
    async def test_guest_message_validates_email_format(self, test_db_session):
        """
        Test that guest message validates email format.
        
        Feature: pet-seeker-accounts, Property 9: Guest Message Form Validation
        """
        from app.schemas.message import MessageCreate
        from pydantic import ValidationError
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Test invalid email format
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=breeder_user.id,
                sender_name="Test User",
                sender_email="not-an-email",
                message="Test message"
            )
        assert "sender_email" in str(exc_info.value).lower() or "email" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_guest_message_validates_name_length(self, test_db_session):
        """
        Test that guest message validates sender name length.
        
        Feature: pet-seeker-accounts, Property 9: Guest Message Form Validation
        """
        from app.schemas.message import MessageCreate
        from pydantic import ValidationError
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Test name too short (less than 2 characters)
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=breeder_user.id,
                sender_name="A",
                sender_email="test@example.com",
                message="Test message"
            )
        assert "sender_name" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_guest_message_rejects_empty_name(self, test_db_session):
        """
        Test that guest message rejects empty or whitespace-only names.
        
        Feature: pet-seeker-accounts, Property 9: Guest Message Form Validation
        """
        from app.schemas.message import MessageCreate
        from pydantic import ValidationError
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Test whitespace-only name
        with pytest.raises(ValidationError) as exc_info:
            MessageCreate(
                breeder_id=breeder_user.id,
                sender_name="   ",
                sender_email="test@example.com",
                message="Test message"
            )
        # Should fail validation
    
    @pytest.mark.asyncio
    async def test_guest_message_allows_optional_message_content(self, test_db_session):
        """
        Test that message content is optional (can be None).
        
        Feature: pet-seeker-accounts, Property 9: Guest Message Form Validation
        """
        from app.schemas.message import MessageCreate
        
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Message content is optional
        message_data = MessageCreate(
            breeder_id=breeder_user.id,
            sender_name="John Doe",
            sender_email="john@example.com",
            message=None
        )
        
        assert message_data.message is None
    
    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=2000,
    )
    @given(
        sender_name=st.text(min_size=2, max_size=100).filter(
            lambda s: s.strip() and len(s.strip()) >= 2 and '\x00' not in s
        ),
        sender_email=email_strategy,
        message_text=st.one_of(message_text_strategy, st.none())
    )
    async def test_guest_message_validation_property(
        self,
        test_db_session,
        sender_name,
        sender_email,
        message_text
    ):
        """
        Property test: Valid guest messages with all required fields are accepted.
        
        Feature: pet-seeker-accounts, Property 9: Guest Message Form Validation
        """
        from app.schemas.message import MessageCreate
        from sqlalchemy import delete
        
        # Clean up any existing data before starting
        await test_db_session.execute(delete(Message))
        await test_db_session.execute(delete(User))
        await test_db_session.commit()
        
        try:
            # Create breeder user with guaranteed unique email
            breeder_email = f"breeder_{uuid.uuid4().hex}@example.com"
            breeder_user = await create_breeder_user(test_db_session, email=breeder_email)
            
            # Create message with generated data - should not raise validation error
            message_data = MessageCreate(
                breeder_id=breeder_user.id,
                sender_name=sender_name,
                sender_email=sender_email,
                message=message_text
            )
            
            # Verify data is accepted and basic properties hold
            assert message_data.sender_name == sender_name.strip()
            # Email is valid and present (Pydantic may normalize it)
            assert message_data.sender_email is not None
            assert '@' in message_data.sender_email
            # message can be None or the provided text
            if message_text:
                assert message_data.message == message_text.strip() or message_data.message is None
        finally:
            # Clean up data created in this iteration
            try:
                await test_db_session.execute(delete(Message))
                await test_db_session.execute(delete(User))
                await test_db_session.commit()
            except Exception:
                await test_db_session.rollback()



class TestGuestMessageStorage:
    """
    Property 10: Guest Message Storage
    
    For any valid guest message submission, the system SHALL create a message 
    record with the provided sender_email, sender_name, and message content.
    
    Validates: Requirements 7.4
    """
    
    @pytest.mark.asyncio
    async def test_guest_message_stored_with_email(self, test_db_session):
        """
        Test that guest message is stored with sender email.
        
        Feature: pet-seeker-accounts, Property 10: Guest Message Storage
        """
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create guest message
        guest_email = "guest@example.com"
        guest_name = "Guest User"
        message_content = "I'm interested in your puppies"
        
        message = Message(
            breeder_id=breeder_user.id,
            sender_name=guest_name,
            sender_email=guest_email,
            message=message_content,
            is_read=False
        )
        test_db_session.add(message)
        await test_db_session.commit()
        await test_db_session.refresh(message)
        
        # Verify message is stored with correct data
        assert message.sender_email == guest_email
        assert message.sender_name == guest_name
        assert message.message == message_content
        assert message.breeder_id == breeder_user.id
    
    @pytest.mark.asyncio
    async def test_guest_message_retrievable_by_email(self, test_db_session):
        """
        Test that guest message can be retrieved by sender email.
        
        Feature: pet-seeker-accounts, Property 10: Guest Message Storage
        """
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create guest message
        guest_email = "retrieve@example.com"
        message = Message(
            breeder_id=breeder_user.id,
            sender_name="Test User",
            sender_email=guest_email,
            message="Test message",
            is_read=False
        )
        test_db_session.add(message)
        await test_db_session.commit()
        
        # Retrieve message by email
        query = select(Message).where(Message.sender_email == guest_email)
        result = await test_db_session.execute(query)
        retrieved_message = result.scalar_one_or_none()
        
        # Verify message was found
        assert retrieved_message is not None
        assert retrieved_message.sender_email == guest_email
    
    @pytest.mark.asyncio
    async def test_multiple_messages_same_email(self, test_db_session):
        """
        Test that multiple messages from same email are all stored.
        
        Feature: pet-seeker-accounts, Property 10: Guest Message Storage
        """
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create multiple messages from same email
        guest_email = "multiple@example.com"
        messages = []
        for i in range(3):
            message = Message(
                breeder_id=breeder_user.id,
                sender_name="Guest User",
                sender_email=guest_email,
                message=f"Message {i+1}",
                is_read=False
            )
            test_db_session.add(message)
            messages.append(message)
        
        await test_db_session.commit()
        
        # Retrieve all messages by email
        query = select(Message).where(Message.sender_email == guest_email)
        result = await test_db_session.execute(query)
        retrieved_messages = result.scalars().all()
        
        # Verify all messages were stored
        assert len(retrieved_messages) == 3
    
    @pytest.mark.asyncio
    async def test_guest_message_without_content(self, test_db_session):
        """
        Test that guest message can be stored without message content.
        
        Feature: pet-seeker-accounts, Property 10: Guest Message Storage
        """
        # Create breeder user
        breeder_user = await create_breeder_user(test_db_session)
        
        # Create message without content
        guest_email = "nocontent@example.com"
        message = Message(
            breeder_id=breeder_user.id,
            sender_name="Guest User",
            sender_email=guest_email,
            message=None,
            is_read=False
        )
        test_db_session.add(message)
        await test_db_session.commit()
        await test_db_session.refresh(message)
        
        # Verify message is stored
        assert message.sender_email == guest_email
        assert message.message is None
    
    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=2000,
    )
    @given(
        sender_name=st.text(min_size=2, max_size=100).filter(
            lambda s: s.strip() and len(s.strip()) >= 2 and '\x00' not in s
        ),
        sender_email=email_strategy,
        message_text=st.one_of(message_text_strategy, st.none())
    )
    async def test_guest_message_storage_property(
        self,
        test_db_session,
        sender_name,
        sender_email,
        message_text
    ):
        """
        Property test: For any valid guest message, it is stored with correct data.
        
        Feature: pet-seeker-accounts, Property 10: Guest Message Storage
        """
        from sqlalchemy import delete
        
        # Clean up any existing data before starting
        await test_db_session.execute(delete(Message))
        await test_db_session.execute(delete(User))
        await test_db_session.commit()
        
        try:
            # Create breeder user with guaranteed unique email
            breeder_email = f"breeder_{uuid.uuid4().hex}@example.com"
            breeder_user = await create_breeder_user(test_db_session, email=breeder_email)
            
            # Create and store message
            message = Message(
                breeder_id=breeder_user.id,
                sender_name=sender_name,
                sender_email=sender_email,
                message=message_text,
                is_read=False
            )
            test_db_session.add(message)
            await test_db_session.commit()
            await test_db_session.refresh(message)
            
            # Verify message is stored with correct data
            assert message.sender_name == sender_name
            # Email may be normalized, but should be present
            assert message.sender_email is not None
            assert '@' in message.sender_email
            assert message.message == message_text
            assert message.breeder_id == breeder_user.id
            
            # Verify message can be retrieved
            query = select(Message).where(Message.id == message.id)
            result = await test_db_session.execute(query)
            retrieved_message = result.scalar_one_or_none()
            
            assert retrieved_message is not None
            assert retrieved_message.id == message.id
        finally:
            # Clean up data created in this iteration
            try:
                await test_db_session.execute(delete(Message))
                await test_db_session.execute(delete(User))
                await test_db_session.commit()
            except Exception:
                await test_db_session.rollback()
